# -*- coding: utf-8 -*-
"""Feature-detected compatibility helpers for multiple KiCad pcbnew APIs."""


class KiCadCompat(object):
    def __init__(self, pcbnew_module):
        self.pcbnew = pcbnew_module

    def get_board(self):
        return self.pcbnew.GetBoard()

    def version_string(self):
        """Return the best available KiCad version string without parsing it."""
        for name in ("GetMajorMinorVersion", "GetBuildVersion", "FullVersion", "Version"):
            getter = getattr(self.pcbnew, name, None)
            if callable(getter):
                try:
                    value = getter()
                    if value:
                        return str(value)
                except Exception:
                    pass
        return "unknown"

    def make_point(self, x, y):
        x, y = int(round(x)), int(round(y))
        point_type = getattr(self.pcbnew, "VECTOR2I", None)
        if point_type is not None:
            return point_type(x, y)
        point_type = getattr(self.pcbnew, "wxPoint", None)
        if point_type is not None:
            return point_type(x, y)
        raise RuntimeError("kicad_point_type_unavailable")

    def _point_candidates(self, x, y):
        """Yield point variants accepted by different SWIG generations."""
        x, y = int(round(x)), int(round(y))
        seen = set()
        for name in ("VECTOR2I", "wxPoint"):
            point_type = getattr(self.pcbnew, name, None)
            if point_type is None or point_type in seen:
                continue
            seen.add(point_type)
            try:
                yield point_type(x, y)
            except Exception:
                pass

    def _set_point(self, setter, point):
        last_error = None
        for candidate in self._point_candidates(point[0], point[1]):
            try:
                setter(candidate)
                return
            except (TypeError, RuntimeError) as error:
                last_error = error
        if last_error is not None:
            raise last_error
        setter(self.make_point(*point))

    @staticmethod
    def _set_net(item, net_item):
        if net_item is None:
            return
        set_net = getattr(item, "SetNet", None)
        if callable(set_net):
            set_net(net_item)
            return
        item.SetNetCode(net_item.GetNetCode())

    def supports_arcs(self):
        arc_type = getattr(self.pcbnew, "PCB_ARC", None)
        return bool(
            arc_type
            and callable(getattr(arc_type, "SetStart", None))
            and callable(getattr(arc_type, "SetMid", None))
            and callable(getattr(arc_type, "SetEnd", None))
        )

    @staticmethod
    def point_xy(point):
        try:
            return int(point[0]), int(point[1])
        except (TypeError, IndexError, AttributeError):
            pass
        x = getattr(point, "x", None)
        y = getattr(point, "y", None)
        if x is not None and y is not None:
            return int(x), int(y)
        get_x = getattr(point, "GetX", None)
        get_y = getattr(point, "GetY", None)
        if callable(get_x) and callable(get_y):
            return int(get_x()), int(get_y())
        raise TypeError("kicad_point_unsupported")

    def from_mm(self, value):
        converter = getattr(self.pcbnew, "FromMM", None)
        if callable(converter):
            return int(round(converter(float(value))))
        return int(round(float(value) * 1000000.0))

    def to_mm(self, value):
        converter = getattr(self.pcbnew, "ToMM", None)
        if callable(converter):
            return float(converter(value))
        return float(value) / 1000000.0

    def user_unit(self):
        getter = getattr(self.pcbnew, "GetUserUnits", None)
        if not callable(getter):
            return "mm"
        try:
            units = getter()
        except Exception:
            return "mm"
        inch_units = (
            getattr(self.pcbnew, "EDA_UNITS_INCH", None),
            getattr(self.pcbnew, "EDA_UNITS_INCHES", None),
        )
        if units is not None and units in inch_units:
            return "inch"
        if units == getattr(self.pcbnew, "EDA_UNITS_MILS", object()):
            return "mil"
        return "mm"

    def unit_label(self):
        return {"inch": "in", "mil": "mil", "mm": "mm"}[self.user_unit()]

    def mm_to_user(self, value):
        unit = self.user_unit()
        if unit == "inch":
            return float(value) / 25.4
        if unit == "mil":
            return float(value) * 1000.0 / 25.4
        return float(value)

    def user_to_mm(self, value):
        unit = self.user_unit()
        if unit == "inch":
            return float(value) * 25.4
        if unit == "mil":
            return float(value) * 25.4 / 1000.0
        return float(value)

    def user_to_internal(self, value):
        return self.from_mm(self.user_to_mm(value))

    def internal_to_user(self, value):
        return self.mm_to_user(self.to_mm(value))

    @staticmethod
    def format_number(value):
        return ("{:.6f}".format(float(value))).rstrip("0").rstrip(".") or "0"

    def net_items(self, board):
        net_info = board.GetNetInfo()
        by_name = net_info.NetsByName()
        try:
            items = list(by_name.items())
        except AttributeError:
            items = [(str(key), by_name[key]) for key in by_name.keys()]
        items.sort(key=lambda item: (item[0] != "", str(item[0]).lower()))
        return [(str(name), net_item) for name, net_item in items]

    @staticmethod
    def _layer_set_contains(layer_set, layer):
        for method_name in ("Contains", "test"):
            method = getattr(layer_set, method_name, None)
            if callable(method):
                try:
                    return bool(method(layer))
                except Exception:
                    pass
        try:
            return layer in layer_set
        except TypeError:
            return False

    def copper_layers(self, board):
        enabled = board.GetEnabledLayers()
        cu_stack = getattr(enabled, "CuStack", None)
        if callable(cu_stack):
            try:
                return list(cu_stack())
            except Exception:
                pass

        layers = []
        front = getattr(self.pcbnew, "F_Cu", 0)
        back = getattr(self.pcbnew, "B_Cu", 31)
        for layer in range(int(front), int(back) + 1):
            if not self._layer_set_contains(enabled, layer):
                continue
            is_copper = getattr(self.pcbnew, "IsCopperLayer", None)
            if not callable(is_copper) or is_copper(layer):
                layers.append(layer)
        return layers

    def footprints(self, board):
        for method_name in ("GetFootprints", "GetModules"):
            method = getattr(board, method_name, None)
            if callable(method):
                try:
                    return list(method())
                except Exception:
                    pass
        return []

    def pads(self, board):
        method = getattr(board, "GetPads", None)
        if callable(method):
            try:
                return list(method())
            except Exception:
                pass
        pads = []
        for footprint in self.footprints(board):
            for method_name in ("Pads", "GetPads"):
                method = getattr(footprint, method_name, None)
                if callable(method):
                    try:
                        pads.extend(list(method()))
                        break
                    except Exception:
                        pass
        return pads

    @staticmethod
    def groups(board):
        method = getattr(board, "Groups", None)
        if callable(method):
            try:
                return list(method())
            except Exception:
                pass
        return []

    def selected_center(self, board):
        for group in self.groups(board):
            if group.IsSelected():
                return self.point_xy(group.GetBoundingBox().GetCenter())

        collections = []
        tracks = getattr(board, "GetTracks", None)
        if callable(tracks):
            collections.append(list(tracks()))
        collections.append(self.footprints(board))
        collections.append(self.pads(board))
        for collection in collections:
            for item in collection:
                if item.IsSelected():
                    return self.point_xy(item.GetPosition())
        return None

    def new_track(self, board, start, end, width, net_item, layer):
        track = self.pcbnew.PCB_TRACK(board)
        self._set_point(track.SetStart, start)
        self._set_point(track.SetEnd, end)
        track.SetWidth(int(width))
        self._set_net(track, net_item)
        track.SetLayer(layer)
        return track

    def new_arc(self, board, start, midpoint, end, width, net_item, layer):
        """Create a PCB_ARC using APIs reflected in KiCad 6.0 through 10.0."""
        arc_type = getattr(self.pcbnew, "PCB_ARC", None)
        if arc_type is None:
            raise RuntimeError("kicad_arc_type_unavailable")
        arc = arc_type(board)
        self._set_point(arc.SetStart, start)
        self._set_point(arc.SetMid, midpoint)
        self._set_point(arc.SetEnd, end)
        arc.SetWidth(int(width))
        self._set_net(arc, net_item)
        arc.SetLayer(layer)
        return arc

    def new_via(self, board, position, diameter, drill, net_item,
                layer_pair=None):
        via_type = getattr(self.pcbnew, "PCB_VIA", None) or getattr(self.pcbnew, "VIA", None)
        if via_type is None:
            raise RuntimeError("kicad_via_type_unavailable")
        via = via_type(board)
        self._set_point(via.SetPosition, position)
        via.SetWidth(int(diameter))
        set_via_type = getattr(via, "SetViaType", None)
        via_enum = getattr(self.pcbnew, "VIATYPE", None)
        via_type_value = getattr(self.pcbnew, "VIATYPE_THROUGH", None)
        if via_type_value is None:
            via_type_value = getattr(via_enum, "THROUGH", None)
        if callable(set_via_type) and via_type_value is not None:
            set_via_type(via_type_value)

        drill_set = False
        for method_name in ("SetDrill", "SetDrillValue"):
            method = getattr(via, method_name, None)
            if callable(method):
                try:
                    method(int(drill))
                    drill_set = True
                    break
                except (TypeError, RuntimeError):
                    try:
                        method(self.make_point(drill, drill))
                        drill_set = True
                        break
                    except (TypeError, RuntimeError):
                        pass
        if not drill_set:
            raise RuntimeError("kicad_via_drill_unavailable")

        if layer_pair:
            set_layer_pair = getattr(via, "SetLayerPair", None)
            if callable(set_layer_pair):
                set_layer_pair(layer_pair[0], layer_pair[1])
        self._set_net(via, net_item)
        return via

    def add_group(self, board, tracks, name):
        group_type = getattr(self.pcbnew, "PCB_GROUP", None)
        if group_type is None:
            return None
        group = group_type(board)
        group.SetName(name)
        add_item = getattr(group, "AddItem", None) or getattr(group, "Add", None)
        if not callable(add_item):
            return None
        for track in tracks:
            add_item(track)
        board.Add(group)
        if hasattr(group, "thisown"):
            group.thisown = 0
        return group

    @staticmethod
    def remove_item(board, item):
        remover = getattr(board, "Remove", None)
        if callable(remover):
            remover(item)
            return
        remover = getattr(board, "Delete", None)
        if callable(remover):
            remover(item)

    def refresh(self):
        refresh = getattr(self.pcbnew, "Refresh", None)
        if callable(refresh):
            refresh()
