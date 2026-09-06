# -*- coding: utf-8 -*-
"""KiCad IPC backend for creating spiral PCB coils."""

from math import cos, hypot, pi, sin
import os

try:
    from .geometry import (
        connector_endpoint_index,
        multilayer_connection_layout, motor_sector_connection_layout,
        iter_motor_sector_spiral_segments, iter_shaped_spiral_segments,
        iter_spiral_arcs, motor_array_instances, motor_sector_dimensions,
    )
except ImportError:
    from geometry import (
        connector_endpoint_index,
        multilayer_connection_layout, motor_sector_connection_layout,
        iter_motor_sector_spiral_segments, iter_shaped_spiral_segments,
        iter_spiral_arcs, motor_array_instances, motor_sector_dimensions,
    )

try:
    from .kicad_paths import platform_kicad_config_root
    from .metadata import (
        IPC_PLUGIN_IDENTIFIER, LEGACY_IPC_PLUGIN_IDENTIFIER, SETTINGS_FILENAME,
    )
except ImportError:
    from kicad_paths import platform_kicad_config_root
    from metadata import (
        IPC_PLUGIN_IDENTIFIER, LEGACY_IPC_PLUGIN_IDENTIFIER, SETTINGS_FILENAME,
    )


PLUGIN_IDENTIFIER = IPC_PLUGIN_IDENTIFIER
NM_PER_MM = 1000000


def mm_to_nm(value):
    return int(round(float(value) * NM_PER_MM))


def nm_to_mm(value):
    return float(value) / NM_PER_MM


class IpcBackendError(RuntimeError):
    pass


class IpcBoardBackend(object):
    """Small verified surface over kicad-python 0.7.1+ APIs."""

    def __init__(self, kicad_client):
        from kipy.board_types import ArcTrack, Group, Track, Via
        from kipy.geometry import Box2, Vector2
        from kipy.util.board_layer import (
            canonical_name,
            is_copper_layer,
            iter_copper_layers,
        )

        self.kicad = kicad_client
        self.board = kicad_client.get_board()
        self.ArcTrack = ArcTrack
        self.Group = Group
        self.Track = Track
        self.Via = Via
        self.Box2 = Box2
        self.Vector2 = Vector2
        self.canonical_name = canonical_name
        self.is_copper_layer = is_copper_layer
        self.iter_copper_layers = iter_copper_layers
        version = kicad_client.get_version()
        self.version = version
        self.version_text = (
            getattr(version, "full_version", None)
            or "{}.{}.{}".format(version.major, version.minor, version.patch)
        )

    def plugin_settings_file(self):
        from kipy.errors import ApiError
        from kipy.proto.common.envelope_pb2 import ApiStatusCode

        try:
            directory = self.kicad.get_plugin_settings_path(PLUGIN_IDENTIFIER)
        except ApiError as error:
            # KiCad 9.0/10.0 handlers have an inverted IsValidIdentifier check
            # (reproduced on 9.0.7 and 10.0.4). Do not hide transport or unrelated errors.
            if ((self.version.major, self.version.minor) not in ((9, 0), (10, 0))
                    or error.code != ApiStatusCode.AS_BAD_REQUEST
                    or str(error) != "KiCad returned error: plugin identifier is invalid"):
                raise
            config_root = os.environ.get("KICAD_CONFIG_HOME") or platform_kicad_config_root()
            directory = os.path.join(
                config_root, "{}.{}".format(self.version.major, self.version.minor),
                "plugins", PLUGIN_IDENTIFIER,
            )

        current = os.path.join(directory, SETTINGS_FILENAME)
        legacy = os.path.join(
            os.path.dirname(directory), LEGACY_IPC_PLUGIN_IDENTIFIER, SETTINGS_FILENAME
        )
        # Retain existing settings in place; never move/delete a user's files.
        # If both exist, the current identity takes precedence.
        if not os.path.isfile(current) and os.path.isfile(legacy):
            return legacy
        return current

    def net_items(self):
        nets = sorted(self.board.get_nets(), key=lambda net: net.name.lower())
        return [("", None)] + [(net.name, net) for net in nets if net.name]

    def copper_layers(self):
        enabled = set(self.board.get_enabled_layers())
        return [
            (layer, self.canonical_name(layer))
            for layer in self.iter_copper_layers()
            if layer in enabled and self.is_copper_layer(layer)
        ]

    def selected_center_mm(self):
        selection = list(self.board.get_selection())
        if not selection:
            return None
        boxes = list(self.board.get_item_bounding_box(selection))
        if not boxes:
            return None
        merged = self.Box2.from_pos_size(boxes[0].pos, boxes[0].size)
        for box in boxes[1:]:
            merged.merge(box)
        center = merged.center()
        return nm_to_mm(center.x), nm_to_mm(center.y)

    def _new_track(self, start, end, width, net, layer):
        item = self.Track()
        item.start = self.Vector2.from_xy(*start)
        item.end = self.Vector2.from_xy(*end)
        item.width = int(width)
        item.layer = layer
        if net is not None:
            item.net = net
        return item

    def _new_arc(self, start, midpoint, end, width, net, layer):
        item = self.ArcTrack()
        item.start = self.Vector2.from_xy(*start)
        item.mid = self.Vector2.from_xy(*midpoint)
        item.end = self.Vector2.from_xy(*end)
        item.width = int(width)
        item.layer = layer
        if net is not None:
            item.net = net
        return item

    def _new_via(self, position, diameter, drill, net):
        item = self.Via()
        item.position = self.Vector2.from_xy(*position)
        item.diameter = int(diameter)
        item.drill_diameter = int(drill)
        if net is not None:
            item.net = net
        return item

    def create_spiral(self, values, selected_layers, net, primitive_mode):
        """Create the resolved coil as one undoable IPC transaction."""
        center_x = mm_to_nm(values["center_x_mm"])
        center_y = mm_to_nm(values["center_y_mm"])
        start_radius = mm_to_nm(values["start_radius_mm"])
        width = mm_to_nm(values["track_width_mm"])
        spacing = mm_to_nm(values["spacing_mm"])
        via_diameter = mm_to_nm(values["via_diameter_mm"])
        via_drill = mm_to_nm(values["via_drill_mm"])
        via_clearance = mm_to_nm(values["via_clearance_mm"])
        radial_pitch = (
            width + spacing
            if values["spacing_mode"] == "clearance"
            else spacing
        )
        angle_radians = values["angle_degrees"] * pi / 180.0
        base_counterclockwise = values["direction"] == "counterclockwise"
        items = []
        if values.get("coil_shape") == "motor_sector":
            board_outer_mm = values.get(
                "motor_board_outer_diameter_mm",
                values.get("available_diameter_mm", 100.0),
            )
            board_inner_mm = values.get(
                "motor_board_inner_diameter_mm",
                board_outer_mm * values.get("motor_inner_ratio", 0.58),
            )
            slot_count = max(
                2, int(values.get("motor_slot_count", 0))
                or 2 * int(values.get("motor_pole_pairs", 1))
            )
            sector_dimensions = motor_sector_dimensions(
                mm_to_nm(board_outer_mm), mm_to_nm(board_inner_mm),
                slot_count, width, radial_pitch - width,
                mm_to_nm(values.get("motor_edge_clearance_mm", 1.0)),
                mm_to_nm(values.get("motor_slot_gap_mm", 1.0)),
            )
            instances = []
            start_angle = values.get(
                "motor_array_angle_degrees", 0.0
            ) * pi / 180.0
            for index in range(slot_count):
                placement = start_angle + 2.0 * pi * index / slot_count
                instances.append((
                    center_x + sector_dimensions["array_radius"] * cos(placement),
                    center_y + sector_dimensions["array_radius"] * sin(placement),
                    placement,
                    bool(values.get("motor_alternate_winding", True)
                         and index % 2),
                ))
        else:
            instances = motor_array_instances(
                center_x, center_y, values.get("coil_shape", "circular"),
                values.get("motor_layout", "single"),
                values.get("motor_pole_pairs", 1),
                mm_to_nm(values.get("motor_array_radius_mm", 0.0)),
                mm_to_nm(values.get("motor_linear_pitch_mm", 0.0)),
                values.get("motor_array_angle_degrees", 0.0) * pi / 180.0,
                values.get("motor_orientation", "radial"),
                values.get("motor_alternate_winding", True),
                values.get("motor_slot_count", 0),
            )
        sector_connection_layout = None
        if (values.get("coil_shape") == "motor_sector"
                and len(selected_layers) > 1):
            local_paths = []
            for layer_offset in range(len(selected_layers)):
                local_counterclockwise = (
                    base_counterclockwise
                    if layer_offset % 2 == 0
                    else not base_counterclockwise
                )
                local_segments = list(iter_motor_sector_spiral_segments(
                    0, 0, mm_to_nm(board_outer_mm), mm_to_nm(board_inner_mm),
                    slot_count, width, radial_pitch - width, values["turns"],
                    values["segments_per_turn"],
                    values["additional_segments"],
                    mm_to_nm(values.get("motor_edge_clearance_mm", 1.0)),
                    mm_to_nm(values.get("motor_slot_gap_mm", 1.0)),
                    0.0, local_counterclockwise,
                ))
                local_paths.append(
                    [local_segments[0][0]]
                    + [end for _start, end in local_segments]
                )
            sector_connection_layout = motor_sector_connection_layout(
                (-sector_dimensions["array_radius"], 0), local_paths,
                sector_dimensions["board_outer_radius"],
                sector_dimensions["board_inner_radius"],
                mm_to_nm(values.get("motor_edge_clearance_mm", 1.0)),
                via_diameter, via_clearance, width, radial_pitch - width,
            )

        base_angle_radians = angle_radians
        base_direction = base_counterclockwise
        for center_x, center_y, instance_rotation, reverse_winding in instances:
            angle_radians = base_angle_radians + instance_rotation
            base_counterclockwise = bool(base_direction) != bool(reverse_winding)
            endpoints = []
            maximum_centerline_radius = 0.0
            for layer_offset, layer in enumerate(selected_layers):
                counterclockwise = (
                    base_counterclockwise
                    if layer_offset % 2 == 0
                    else not base_counterclockwise
                )
                first_point = None
                last_point = None
                if primitive_mode == "arc":
                    iterator = iter_spiral_arcs(
                        center_x, center_y, start_radius, radial_pitch,
                        values["turns"], values["arcs_per_turn"],
                        values["additional_segments"], angle_radians,
                        counterclockwise,
                    )
                    for start, midpoint, end in iterator:
                        maximum_centerline_radius = max(
                            maximum_centerline_radius,
                            hypot(start[0] - center_x, start[1] - center_y),
                            hypot(midpoint[0] - center_x, midpoint[1] - center_y),
                            hypot(end[0] - center_x, end[1] - center_y),
                        )
                        if first_point is None:
                            first_point = start
                        last_point = end
                        items.append(self._new_arc(
                            start, midpoint, end, width, net, layer
                        ))
                else:
                    if values.get("coil_shape") == "motor_sector":
                        board_outer_mm = values.get(
                            "motor_board_outer_diameter_mm",
                            values.get("available_diameter_mm", 100.0),
                        )
                        board_inner_mm = values.get(
                            "motor_board_inner_diameter_mm",
                            board_outer_mm * values.get("motor_inner_ratio", 0.58),
                        )
                        slot_count = max(
                            2, int(values.get("motor_slot_count", 0))
                            or 2 * int(values.get("motor_pole_pairs", 1))
                        )
                        iterator = iter_motor_sector_spiral_segments(
                            center_x, center_y, mm_to_nm(board_outer_mm),
                            mm_to_nm(board_inner_mm), slot_count, width,
                            radial_pitch - width, values["turns"],
                            values["segments_per_turn"],
                            values["additional_segments"],
                            mm_to_nm(values.get("motor_edge_clearance_mm", 1.0)),
                            mm_to_nm(values.get("motor_slot_gap_mm", 1.0)),
                            angle_radians, counterclockwise,
                        )
                    else:
                        iterator = iter_shaped_spiral_segments(
                            center_x, center_y, start_radius, radial_pitch,
                            values["turns"], values["segments_per_turn"],
                            values["additional_segments"], angle_radians,
                            counterclockwise,
                            values.get("coil_shape", "circular"),
                            values.get("shape_aspect_ratio", 1.0),
                            values.get("shape_taper_ratio", 0.0),
                        )
                    for start, end in iterator:
                        maximum_centerline_radius = max(
                            maximum_centerline_radius,
                            hypot(start[0] - center_x, start[1] - center_y),
                            hypot(end[0] - center_x, end[1] - center_y),
                        )
                        if first_point is None:
                            first_point = start
                        last_point = end
                        items.append(self._new_track(
                            start, end, width, net, layer
                        ))
                endpoints.append((first_point, last_point))

            if len(selected_layers) > 1:
                if sector_connection_layout is not None:
                    cosine = cos(instance_rotation)
                    sine = sin(instance_rotation)

                    def transform_sector_point(point):
                        return (
                            int(round(center_x + point[0] * cosine
                                      - point[1] * sine)),
                            int(round(center_y + point[0] * sine
                                      + point[1] * cosine)),
                        )

                    connection_layout = {
                        "via_points": {
                            transition: transform_sector_point(point)
                            for transition, point in
                            sector_connection_layout["via_points"].items()
                        },
                        "terminal_routes": [
                            (layer, endpoint_index,
                             transform_sector_point(point))
                            for layer, endpoint_index, point in
                            sector_connection_layout["terminal_routes"]
                        ],
                    }
                else:
                    outer_radius = maximum_centerline_radius
                    connection_layout = multilayer_connection_layout(
                        (center_x, center_y), endpoints[0][0], endpoints[0][1],
                        outer_radius, len(selected_layers), via_diameter,
                        via_clearance, width,
                    )
                via_positions = connection_layout["via_points"]
                for transition in range(len(selected_layers) - 1):
                    endpoint_index = connector_endpoint_index(transition)
                    via_position = via_positions[transition]
                    for layer_offset in (transition, transition + 1):
                        items.append(self._new_track(
                            endpoints[layer_offset][endpoint_index],
                            via_position,
                            width,
                            net,
                            selected_layers[layer_offset],
                        ))
                    items.append(self._new_via(
                        via_position, via_diameter, via_drill, net,
                    ))
                for layer_offset, endpoint_index, terminal_point in (
                        connection_layout["terminal_routes"]):
                    items.append(self._new_track(
                        endpoints[layer_offset][endpoint_index],
                        terminal_point,
                        width,
                        net,
                        selected_layers[layer_offset],
                    ))

        commit = self.board.begin_commit()
        try:
            created = self.board.create_items(items)
            if values.get("create_group"):
                group = self.Group()
                group.proto.name = values.get("group_name") or "spiral"
                group.items = created
                self.board.create_items(group)
            self.board.push_commit(commit, "Create CoilForge spiral")
        except Exception:
            try:
                self.board.drop_commit(commit)
            except Exception:
                pass
            raise
        return created

