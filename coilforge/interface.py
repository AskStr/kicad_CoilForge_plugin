# -*- coding: utf-8 -*-
"""wxPython user interface for the spiral generator."""

import wx

try:
    from .preview import fit_preview_scene
    from .ui_layout import WORKSPACE_MAIN_RATIO, workspace_main_width
except ImportError:
    from preview import fit_preview_scene
    from ui_layout import WORKSPACE_MAIN_RATIO, workspace_main_width


class CoilPreviewCanvas(wx.Panel):
    """Small native wx schematic canvas shared by every legacy KiCad UI."""

    _LAYER_COLOURS = (
        wx.Colour(35, 111, 196), wx.Colour(111, 66, 193),
        wx.Colour(0, 137, 123), wx.Colour(198, 104, 0),
    )

    def __init__(self, parent, placeholder):
        wx.Panel.__init__(self, parent, style=wx.BORDER_SIMPLE)
        self._scene = None
        self._placeholder = placeholder
        self.SetMinSize(wx.Size(340, 220))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def set_scene(self, scene):
        self._scene = scene
        self.Refresh(False)

    def set_placeholder(self, text):
        self._placeholder = text
        self.Refresh(False)

    def _on_size(self, event):
        self.Refresh(False)
        event.Skip()

    def _on_paint(self, _event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(wx.Colour(250, 251, 253)))
        dc.Clear()
        size = self.GetClientSize()
        width = max(1, size.GetWidth())
        height = max(1, size.GetHeight())
        if not self._scene:
            dc.SetTextForeground(wx.Colour(95, 99, 104))
            dc.DrawLabel(
                self._placeholder,
                wx.Rect(12, 12, max(1, width - 24), max(1, height - 24)),
                wx.ALIGN_CENTER,
            )
            return

        fitted = fit_preview_scene(self._scene, width, height, 22)
        center_x, center_y = fitted["center"]
        dc.SetPen(wx.Pen(wx.Colour(225, 228, 232), 1))
        dc.DrawLine(10, int(round(center_y)), width - 10, int(round(center_y)))
        dc.DrawLine(int(round(center_x)), 10, int(round(center_x)), height - 10)

        track_width = max(1, int(round(fitted.get("track_width_px", 2.0))))
        for index, path in enumerate(fitted["coil_paths"]):
            if len(path) < 2:
                continue
            dc.SetPen(wx.Pen(
                self._LAYER_COLOURS[index % len(self._LAYER_COLOURS)],
                track_width,
            ))
            dc.DrawLines([
                wx.Point(int(round(x)), int(round(y))) for x, y in path
            ])

        dc.SetPen(wx.Pen(wx.Colour(95, 99, 104), track_width))
        for start, end in fitted["connector_paths"]:
            dc.DrawLine(
                int(round(start[0])), int(round(start[1])),
                int(round(end[0])), int(round(end[1])),
            )

        dc.SetPen(wx.Pen(wx.Colour(0, 121, 140), 2))
        dc.SetBrush(wx.Brush(wx.Colour(213, 245, 249)))
        via_radius = max(3, int(round(
            fitted.get("via_diameter_px", 8.0) / 2.0
        )))
        for x, y in fitted["via_points"]:
            dc.DrawCircle(int(round(x)), int(round(y)), via_radius)

        terminal_colours = (wx.Colour(35, 145, 66), wx.Colour(229, 122, 0))
        for index, (x, y) in enumerate(fitted["terminal_points"]):
            colour = terminal_colours[index % len(terminal_colours)]
            dc.SetPen(wx.Pen(colour, 2))
            dc.SetBrush(wx.Brush(colour))
            dc.DrawCircle(int(round(x)), int(round(y)), 4)


_FIELD_SETTING_KEYS = {
    "target_current": "target_current_a",
    "target_torque": "target_torque_nm",
    "motor_target_force": "motor_target_force_n",
    "motor_target_linear_speed": "motor_target_linear_speed_mps",
    "air_gap_flux_density": "air_gap_flux_density_t",
    "electrical_loading": "electrical_loading_a_per_m",
    "motor_supply_voltage": "motor_supply_voltage_v",
    "motor_target_speed": "motor_target_speed_rpm",
    "motor_max_phase_current": "motor_max_phase_current_a",
    "allowed_temperature_rise": "allowed_temperature_rise_c",
    "motor_board_outer_diameter": "motor_board_outer_diameter_mm",
    "motor_board_inner_diameter": "motor_board_inner_diameter_mm",
    "target_resistance": "target_resistance_ohm",
    "target_inductance": "target_inductance_uh",
    "motor_edge_clearance": "motor_edge_clearance_mm",
    "motor_slot_gap": "motor_slot_gap_mm",
    "center_x": "center_x_mm",
    "center_y": "center_y_mm",
    "motor_array_radius": "motor_array_radius_mm",
    "motor_linear_pitch": "motor_linear_pitch_mm",
    "motor_array_angle": "motor_array_angle_degrees",
    "available_diameter": "available_diameter_mm",
    "target_length": "target_length_mm",
    "initial_radius": "start_radius_mm",
    "minimum_track_width": "minimum_track_width_mm",
    "minimum_clearance": "minimum_clearance_mm",
    "shape_taper_percent": "shape_taper_ratio",
    "track_width": "track_width_mm",
    "spacing": "spacing_mm",
    "angle_offset": "angle_degrees",
    "start_layer": "layer_name",
    "via_diameter": "via_diameter_mm",
    "via_drill": "via_drill_mm",
    "via_clearance": "via_clearance_mm",
    "copper_thickness": "copper_thickness_um",
}


class SpiralPanel(wx.Panel):
    def __init__(self, parent, translator):
        wx.Panel.__init__(self, parent)
        self.tr = translator
        self.labels = {}
        self.unit_labels = []
        self._choice_codes = {}
        self._field_sizers = {}
        self._pages = []
        self._page_keys = []
        self._page_parent = None
        self._all_page_records = []

        root = wx.BoxSizer(wx.VERTICAL)
        guide = wx.BoxSizer(wx.VERTICAL)
        self.guide_title = wx.StaticText(self, label="")
        title_font = self.guide_title.GetFont()
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        title_font.SetPointSize(title_font.GetPointSize() + 2)
        self.guide_title.SetFont(title_font)
        self.guide_hint = wx.StaticText(self, label="")
        guide.Add(self.guide_title, 0, wx.BOTTOM, 3)
        guide.Add(self.guide_hint, 0, wx.EXPAND)
        root.Add(guide, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        profile_row = wx.BoxSizer(wx.HORIZONTAL)
        self.profile_label = wx.StaticText(self, label="")
        self.profile_choice = wx.Choice(self)
        self.profile_choice.SetMinSize(wx.Size(170, -1))
        self.profile_name = wx.TextCtrl(self)
        self.profile_name.SetMinSize(wx.Size(140, -1))
        self.profile_load_button = wx.Button(self)
        self.profile_save_button = wx.Button(self)
        self.profile_delete_button = wx.Button(self)
        profile_row.Add(self.profile_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        profile_row.Add(self.profile_choice, 0, wx.RIGHT, 6)
        profile_row.Add(self.profile_name, 1, wx.RIGHT, 6)
        profile_row.Add(self.profile_load_button, 0, wx.RIGHT, 4)
        profile_row.Add(self.profile_save_button, 0, wx.RIGHT, 4)
        profile_row.Add(self.profile_delete_button, 0)
        root.Add(profile_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        workspace = wx.BoxSizer(wx.HORIZONTAL)
        splitter_style = wx.SP_LIVE_UPDATE | getattr(wx, "SP_NOSASH", 0)
        self.workspace_splitter = wx.SplitterWindow(
            self, style=splitter_style
        )
        self.workspace_splitter.SetMinimumPaneSize(1)
        self.workspace_splitter.SetSashGravity(WORKSPACE_MAIN_RATIO)
        self.notebook = wx.Notebook(self.workspace_splitter)
        for key, builder in (
                ("section_quick_setup", self._build_quick_setup_section),
                ("section_board", self._build_board_section),
                ("section_sizing", self._build_sizing_section),
                ("section_geometry", self._build_geometry_section),
                ("section_placement", self._build_placement_section),
                ("section_multilayer", self._build_multilayer_section),
                ("section_options", self._build_options_section)):
            self._add_page(key, builder)
        self._all_page_records = list(zip(self._page_keys, self._pages))
        self.preview_sidebar = self._build_preview_sidebar(
            self.workspace_splitter
        )
        self.workspace_splitter.SplitVertically(
            self.notebook, self.preview_sidebar
        )
        workspace.Add(self.workspace_splitter, 1, wx.EXPAND | wx.ALL, 5)
        root.Add(workspace, 1, wx.EXPAND)

        self.footer = self._build_footer(parent)
        self.SetSizer(root)
        self.apply_translations(translator)
        self.FitInside()
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._on_page_changed)

    def _add_page(self, key, builder):
        page = wx.Panel(self.notebook)
        self._page_parent = page
        content = builder(page)
        page_root = wx.BoxSizer(wx.VERTICAL)
        page_root.Add(content, 1, wx.EXPAND | wx.ALL, 8)
        page.SetSizer(page_root)
        self.notebook.AddPage(page, "")
        self._pages.append(page)
        self._page_keys.append(key)

    def _page_label(self, key, index):
        label = self.tr(key)
        if "·" in label:
            label = label.split("·", 1)[1].strip()
        return "{} · {}".format(index + 1, label)

    def _static_box(self, _key):
        return wx.BoxSizer(wx.VERTICAL)

    def _grid(self, columns=2):
        grid = wx.FlexGridSizer(0, columns, 8, 12)
        for column in range(columns):
            grid.AddGrowableCol(column, 1)
        return grid

    @staticmethod
    def _compact_control(control, width=90):
        control.SetMinSize(wx.Size(width, -1))
        return control

    def _add_row(self, grid, key, control):
        field = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self._page_parent, label="")
        label.SetMaxSize(wx.Size(240, -1))
        label.Wrap(240)
        self.labels[key] = label
        self._field_sizers[_FIELD_SETTING_KEYS.get(key, key)] = field
        field.Add(label, 0, wx.EXPAND | wx.BOTTOM, 3)
        field.Add(control, 0, wx.EXPAND)
        grid.Add(field, 1, wx.EXPAND)

    def _unit_control(self, text_control, unit="length"):
        self._compact_control(text_control)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(text_control, 1, wx.EXPAND)
        label = wx.StaticText(
            text_control.GetParent(),
            label="mm" if unit == "length" else unit,
        )
        if unit == "length":
            self.unit_labels.append(label)
        sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 3)
        return sizer

    def _build_quick_setup_section(self, parent):
        section = self._static_box("section_quick_setup")
        grid = self._grid()

        self.application_preset_choice = self._compact_control(
            wx.Choice(parent), 190
        )
        self._add_row(
            grid, "application_preset", self.application_preset_choice
        )

        self.design_mode_choice = self._compact_control(wx.Choice(parent), 190)
        self._add_row(grid, "design_mode", self.design_mode_choice)

        self.target_current = self._compact_control(wx.TextCtrl(parent), 80)
        self._add_row(
            grid, "target_current",
            self._unit_control(self.target_current, "A"),
        )

        self.target_torque = self._compact_control(wx.TextCtrl(parent), 80)
        self._add_row(
            grid, "target_torque",
            self._unit_control(self.target_torque, "N·m"),
        )
        self.motor_target_force = self._compact_control(
            wx.TextCtrl(parent), 80
        )
        self._add_row(
            grid, "motor_target_force",
            self._unit_control(self.motor_target_force, "N"),
        )
        self.motor_target_linear_speed = self._compact_control(
            wx.TextCtrl(parent), 80
        )
        self._add_row(
            grid, "motor_target_linear_speed",
            self._unit_control(self.motor_target_linear_speed, "m/s"),
        )

        self.air_gap_flux_density = self._compact_control(
            wx.TextCtrl(parent), 80
        )
        self._add_row(
            grid, "air_gap_flux_density",
            self._unit_control(self.air_gap_flux_density, "T"),
        )

        self.electrical_loading = self._compact_control(
            wx.TextCtrl(parent), 90
        )
        self._add_row(
            grid, "electrical_loading",
            self._unit_control(self.electrical_loading, "A/m"),
        )

        self.winding_factor = self._compact_control(wx.TextCtrl(parent), 80)
        self._add_row(grid, "winding_factor", self.winding_factor)

        self.motor_inner_ratio = self._compact_control(wx.TextCtrl(parent), 80)
        self._add_row(grid, "motor_inner_ratio", self.motor_inner_ratio)

        self.motor_supply_voltage = wx.TextCtrl(parent)
        self._add_row(grid, "motor_supply_voltage", self._unit_control(
            self.motor_supply_voltage, "V"
        ))
        self.motor_target_speed = wx.TextCtrl(parent)
        self._add_row(grid, "motor_target_speed", self._unit_control(
            self.motor_target_speed, "rpm"
        ))
        self.motor_max_phase_current = wx.TextCtrl(parent)
        self._add_row(grid, "motor_max_phase_current", self._unit_control(
            self.motor_max_phase_current, "A"
        ))
        self.allowed_temperature_rise = wx.TextCtrl(parent)
        self._add_row(grid, "allowed_temperature_rise", self._unit_control(
            self.allowed_temperature_rise, "°C"
        ))
        self.motor_connection_choice = self._compact_control(
            wx.Choice(parent), 120
        )
        self._add_row(grid, "motor_connection", self.motor_connection_choice)
        grid.Add((0, 0))

        self.preset_summary = wx.StaticText(parent, label="")
        self.preset_summary.Wrap(480)
        section.Add(grid, 0, wx.EXPAND | wx.ALL, 5)
        section.Add(
            self.preset_summary, 0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5,
        )
        return section

    def _build_board_section(self, parent):
        section = self._static_box("section_board")
        grid = self._grid()

        self.manufacturing_preset_choice = self._compact_control(
            wx.Choice(parent), 170
        )
        self._add_row(
            grid, "manufacturing_preset", self.manufacturing_preset_choice
        )

        self.copper_thickness = self._compact_control(wx.TextCtrl(parent), 80)
        self._add_row(
            grid, "copper_thickness",
            self._unit_control(self.copper_thickness, "µm"),
        )

        self.minimum_track_width = wx.TextCtrl(parent)
        self._add_row(
            grid, "minimum_track_width",
            self._unit_control(self.minimum_track_width),
        )

        self.minimum_clearance = wx.TextCtrl(parent)
        self._add_row(
            grid, "minimum_clearance",
            self._unit_control(self.minimum_clearance),
        )

        section.Add(grid, 0, wx.EXPAND | wx.ALL, 5)
        return section

    def _build_sizing_section(self, parent):
        section = self._static_box("section_sizing")
        grid = self._grid()

        self.sizing_mode_choice = self._compact_control(wx.Choice(parent), 140)
        self._add_row(grid, "sizing_mode", self.sizing_mode_choice)

        self.available_diameter = wx.TextCtrl(parent)
        self._add_row(
            grid, "available_diameter",
            self._unit_control(self.available_diameter),
        )

        self.turns = self._compact_control(wx.TextCtrl(parent), 75)
        self._add_row(grid, "turns", self.turns)

        self.target_length = wx.TextCtrl(parent)
        self._add_row(
            grid, "target_length", self._unit_control(self.target_length)
        )

        self.fill_ratio = wx.TextCtrl(parent)
        self._add_row(
            grid, "fill_ratio", self._unit_control(self.fill_ratio, "%")
        )

        self.start_radius = wx.TextCtrl(parent)
        self._add_row(
            grid, "initial_radius", self._unit_control(self.start_radius)
        )

        self.track_width = wx.TextCtrl(parent)
        self._add_row(
            grid, "track_width", self._unit_control(self.track_width)
        )

        self.spacing = wx.TextCtrl(parent)
        self._add_row(grid, "spacing", self._unit_control(self.spacing))

        self.spacing_mode_choice = self._compact_control(
            wx.Choice(parent), 110
        )
        self._add_row(grid, "spacing_mode", self.spacing_mode_choice)

        self.motor_board_outer_diameter = wx.TextCtrl(parent)
        self._add_row(grid, "motor_board_outer_diameter", self._unit_control(
            self.motor_board_outer_diameter
        ))
        self.motor_board_inner_diameter = wx.TextCtrl(parent)
        self._add_row(grid, "motor_board_inner_diameter", self._unit_control(
            self.motor_board_inner_diameter
        ))
        self.target_resistance = wx.TextCtrl(parent)
        self._add_row(grid, "target_resistance", self._unit_control(
            self.target_resistance, "Ω"
        ))
        self.target_inductance = wx.TextCtrl(parent)
        self._add_row(grid, "target_inductance", self._unit_control(
            self.target_inductance, "µH"
        ))

        section.Add(grid, 0, wx.EXPAND | wx.ALL, 5)
        return section

    def _build_geometry_section(self, parent):
        section = self._static_box("section_geometry")
        grid = self._grid()

        self.coil_shape_choice = self._compact_control(
            wx.Choice(parent), 170
        )
        self._add_row(grid, "coil_shape", self.coil_shape_choice)

        self.shape_aspect_ratio = self._compact_control(
            wx.TextCtrl(parent), 80
        )
        self._add_row(
            grid, "shape_aspect_ratio", self.shape_aspect_ratio
        )

        self.shape_taper = self._compact_control(wx.TextCtrl(parent), 80)
        self._add_row(
            grid, "shape_taper_percent",
            self._unit_control(self.shape_taper, "%"),
        )

        self.angle_offset = self._compact_control(wx.TextCtrl(parent), 75)
        self._add_row(grid, "angle_offset", self.angle_offset)

        self.angle_unit_choice = self._compact_control(wx.Choice(parent), 85)
        self._add_row(grid, "angle_unit", self.angle_unit_choice)

        self.direction_choice = self._compact_control(wx.Choice(parent), 100)
        self._add_row(grid, "direction", self.direction_choice)

        recommendation = wx.BoxSizer(wx.HORIZONTAL)
        self.motor_recommendation = wx.StaticText(parent, label="")
        self.motor_recommendation.Wrap(480)
        self.apply_motor_recommendation_button = wx.Button(parent)
        recommendation.Add(
            self.motor_recommendation, 1,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8,
        )
        recommendation.Add(
            self.apply_motor_recommendation_button, 0, wx.ALIGN_CENTER_VERTICAL
        )

        section.Add(grid, 0, wx.EXPAND | wx.ALL, 5)
        section.Add(
            recommendation, 0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5,
        )
        return section

    def _build_placement_section(self, parent):
        section = self._static_box("section_placement")
        grid = self._grid()

        self.motor_layout_choice = self._compact_control(wx.Choice(parent), 150)
        self._add_row(grid, "motor_layout", self.motor_layout_choice)

        self.motor_pole_pairs = self._compact_control(wx.TextCtrl(parent), 75)
        self._add_row(grid, "motor_pole_pairs", self.motor_pole_pairs)

        self.motor_slot_count = self._compact_control(wx.TextCtrl(parent), 75)
        self._add_row(grid, "motor_slot_count", self.motor_slot_count)

        self.motor_phase_count = self._compact_control(wx.TextCtrl(parent), 75)
        self._add_row(grid, "motor_phase_count", self.motor_phase_count)

        self.motor_edge_clearance = wx.TextCtrl(parent)
        self._add_row(grid, "motor_edge_clearance", self._unit_control(
            self.motor_edge_clearance
        ))
        self.motor_slot_gap = wx.TextCtrl(parent)
        self._add_row(grid, "motor_slot_gap", self._unit_control(
            self.motor_slot_gap
        ))

        self.motor_array_radius = wx.TextCtrl(parent)
        self._add_row(
            grid, "motor_array_radius",
            self._unit_control(self.motor_array_radius),
        )

        self.motor_linear_pitch = wx.TextCtrl(parent)
        self._add_row(
            grid, "motor_linear_pitch",
            self._unit_control(self.motor_linear_pitch),
        )

        self.motor_array_angle = self._compact_control(wx.TextCtrl(parent), 75)
        self._add_row(
            grid, "motor_array_angle",
            self._unit_control(self.motor_array_angle, "°"),
        )

        self.motor_orientation_choice = self._compact_control(
            wx.Choice(parent), 150
        )
        self._add_row(
            grid, "motor_orientation", self.motor_orientation_choice
        )

        self.motor_alternate_winding = wx.CheckBox(parent, label="")
        self._add_row(
            grid, "motor_alternate_winding", self.motor_alternate_winding
        )

        grid.Add((0, 0))

        section.Add(grid, 0, wx.EXPAND | wx.ALL, 5)
        return section

    def _build_multilayer_section(self, parent):
        section = self._static_box("section_multilayer")
        grid = self._grid()

        self.net_choice = self._compact_control(wx.Choice(parent), 130)
        self._add_row(grid, "net_name", self.net_choice)

        self.layer_choice = self._compact_control(wx.Choice(parent), 95)
        self._add_row(grid, "start_layer", self.layer_choice)

        self.layer_count_choice = self._compact_control(wx.Choice(parent), 90)
        self._add_row(grid, "layer_count", self.layer_count_choice)

        self.layer_summary = wx.StaticText(parent, label="")
        self.layer_summary.Wrap(180)
        self._add_row(grid, "selected_layers", self.layer_summary)

        self.via_diameter = wx.TextCtrl(parent)
        self._add_row(
            grid, "via_diameter", self._unit_control(self.via_diameter)
        )

        self.via_drill = wx.TextCtrl(parent)
        self._add_row(grid, "via_drill", self._unit_control(self.via_drill))

        self.via_clearance = wx.TextCtrl(parent)
        self._add_row(
            grid, "via_clearance", self._unit_control(self.via_clearance)
        )
        grid.Add((0, 0))

        self.multilayer_hint = wx.StaticText(parent, label="")
        self.multilayer_hint.SetMaxSize(wx.Size(480, -1))
        self.multilayer_hint.Wrap(480)
        section.Add(grid, 0, wx.EXPAND | wx.ALL, 5)
        section.Add(
            self.multilayer_hint, 0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5,
        )
        return section

    def _build_options_section(self, parent):
        section = self._static_box("section_options")
        grid = self._grid()

        self.group_name = self._compact_control(wx.TextCtrl(parent), 110)
        self._add_row(grid, "group_name", self.group_name)

        self.quality_preset_choice = self._compact_control(
            wx.Choice(parent), 110
        )
        self._add_row(grid, "quality_preset", self.quality_preset_choice)

        self.primitive_mode_choice = self._compact_control(
            wx.Choice(parent), 130
        )
        self._add_row(grid, "primitive_mode", self.primitive_mode_choice)

        self.arcs_per_turn = self._compact_control(wx.TextCtrl(parent), 75)
        self._add_row(grid, "arcs_per_turn", self.arcs_per_turn)

        self.segments_per_turn = self._compact_control(
            wx.TextCtrl(parent), 75
        )
        self._add_row(grid, "segments_per_turn", self.segments_per_turn)

        self.additional_segments = self._compact_control(
            wx.TextCtrl(parent), 75
        )
        self._add_row(grid, "additional_segments", self.additional_segments)

        self.center_x = self._compact_control(wx.TextCtrl(parent), 80)
        self._add_row(grid, "center_x", self._unit_control(self.center_x))
        self.center_y = self._compact_control(wx.TextCtrl(parent), 80)
        self._add_row(grid, "center_y", self._unit_control(self.center_y))

        options = wx.BoxSizer(wx.VERTICAL)
        action_row = wx.BoxSizer(wx.HORIZONTAL)
        action_row.AddStretchSpacer(1)
        self.selection_button = wx.Button(parent)
        action_row.Add(self.selection_button, 0)
        checkbox_row = wx.BoxSizer(wx.HORIZONTAL)
        self.create_group = wx.CheckBox(parent)
        self.close_after_create = wx.CheckBox(parent)
        self.show_advanced_parameters = wx.CheckBox(parent)
        checkbox_row.Add(self.create_group, 0, wx.RIGHT, 12)
        checkbox_row.Add(self.close_after_create, 0, wx.RIGHT, 12)
        checkbox_row.Add(self.show_advanced_parameters, 0)

        self.compatibility_summary = wx.StaticText(parent, label="")

        section.Add(grid, 0, wx.EXPAND | wx.ALL, 5)
        options.Add(action_row, 0, wx.EXPAND | wx.BOTTOM, 8)
        options.Add(checkbox_row, 0, wx.EXPAND | wx.BOTTOM, 8)
        options.Add(self.compatibility_summary, 0, wx.EXPAND)
        section.Add(options, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        return section

    def _build_preview_sidebar(self, parent):
        panel = wx.ScrolledWindow(
            parent, style=wx.VSCROLL | wx.TAB_TRAVERSAL
        )
        panel.SetScrollRate(0, 10)
        column = wx.BoxSizer(wx.VERTICAL)

        self.preview_title = wx.StaticText(panel, label="")
        heading_font = self.preview_title.GetFont()
        heading_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self.preview_title.SetFont(heading_font)
        self.preview_canvas = CoilPreviewCanvas(panel, "")
        self.preview_caption = wx.StaticText(panel, label="")
        self.preview_legend = wx.StaticText(panel, label="")

        self.summary_title = wx.StaticText(panel, label="")
        self.summary_title.SetFont(heading_font)
        self.validation_summary = wx.StaticText(panel, label="")
        self.resolved_summary = wx.StaticText(panel, label="—")
        self.electrical_summary = wx.StaticText(panel, label="—")
        self.segment_estimate = wx.StaticText(panel, label="—")
        self.author_label = wx.StaticText(panel, label="")

        column.Add(self.preview_title, 0, wx.BOTTOM, 3)
        column.Add(self.preview_canvas, 1, wx.EXPAND | wx.BOTTOM, 3)
        column.Add(self.preview_caption, 0, wx.EXPAND | wx.BOTTOM, 3)
        column.Add(self.preview_legend, 0, wx.EXPAND | wx.BOTTOM, 6)
        column.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.BOTTOM, 5)
        column.Add(self.summary_title, 0, wx.BOTTOM, 5)
        column.Add(self.validation_summary, 0, wx.EXPAND | wx.BOTTOM, 4)
        column.Add(self.resolved_summary, 0, wx.EXPAND | wx.BOTTOM, 5)
        column.Add(self.electrical_summary, 0, wx.EXPAND | wx.BOTTOM, 5)
        column.Add(self.segment_estimate, 0, wx.EXPAND | wx.BOTTOM, 4)
        column.AddStretchSpacer(1)
        column.Add(self.author_label, 0, wx.ALIGN_RIGHT | wx.TOP, 4)
        panel.SetSizer(column)
        panel.FitInside()
        return panel

    def set_validation_feedback(self, message, valid):
        self.validation_summary.SetLabel(message)
        colour = wx.Colour(31, 122, 72) if valid else wx.Colour(179, 38, 30)
        self.validation_summary.SetForegroundColour(colour)
        self.create_button.Enable(bool(valid))
        self._layout_preview_sidebar()
        self.validation_summary.Refresh()

    def set_preview_scene(self, scene):
        self.preview_canvas.set_scene(scene)
        if scene:
            shape_key = {
                "circular": "shape_circular",
                "motor_ellipse": "shape_motor_ellipse",
                "motor_racetrack": "shape_motor_racetrack",
                "motor_trapezoid": "shape_motor_trapezoid",
                "motor_sector": "shape_motor_sector",
            }.get(scene.get("coil_shape"), "shape_circular")
            self.preview_caption.SetLabel(self.tr(
                "preview_caption", shape=self.tr(shape_key),
                layers=scene.get("layer_count", 1),
            ))
        else:
            self.preview_caption.SetLabel("")
        self._layout_preview_sidebar()
        self.preview_canvas.Refresh(False)

    def _move_page(self, offset):
        page = min(
            len(self._pages) - 1,
            max(0, self.notebook.GetSelection() + int(offset)),
        )
        self.notebook.SetSelection(page)
        self._update_navigation()

    def _on_page_changed(self, event):
        self._update_navigation()
        wx.CallAfter(self._refresh_page_layout)
        event.Skip()

    def _layout_field_labels(self, page_width):
        label_width = max(150, min(300, (int(page_width) - 12) // 2))
        for label in self.labels.values():
            label.SetMaxSize(wx.Size(label_width, -1))
            label.Wrap(label_width)

    def _refresh_page_layout(self):
        page_width = self._page_wrap_width()
        self._layout_field_labels(page_width)
        self.preset_summary.SetMaxSize(wx.Size(page_width, -1))
        self.multilayer_hint.SetMaxSize(wx.Size(page_width, -1))
        self.motor_recommendation.SetMaxSize(wx.Size(page_width, -1))
        self.preset_summary.Wrap(page_width)
        self.multilayer_hint.Wrap(page_width)
        self.motor_recommendation.Wrap(page_width)
        selection = self.notebook.GetSelection()
        if 0 <= selection < len(self._pages):
            page = self._pages[selection]
            page.Layout()

    def _update_navigation(self):
        page = max(0, self.notebook.GetSelection())
        self.previous_button.Enable(page > 0)
        self.next_button.Enable(page < len(self._pages) - 1)
        if self._page_keys:
            page_key = self._page_keys[page]
            if page_key == "section_sizing":
                mode = self.choice_code(
                    self.sizing_mode_choice, "manual"
                )
                hint_key = "guide_hint_sizing_" + mode
            else:
                hint_key = "guide_hint_" + page_key.replace(
                    "section_", ""
                )
            self.guide_hint.SetLabel(self.tr(hint_key))

    def _build_footer(self, parent):
        footer = wx.Panel(parent)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.reset_button = wx.Button(footer)
        self.previous_button = wx.Button(footer)
        self.next_button = wx.Button(footer)
        self.cancel_button = wx.Button(footer, wx.ID_CANCEL)
        self.create_button = wx.Button(footer)
        self.create_button.SetDefault()
        self.previous_button.Bind(
            wx.EVT_BUTTON, lambda _event: self._move_page(-1)
        )
        self.next_button.Bind(
            wx.EVT_BUTTON, lambda _event: self._move_page(1)
        )
        row.Add(self.reset_button, 0)
        row.Add(self.previous_button, 0, wx.LEFT, 8)
        row.Add(self.next_button, 0, wx.LEFT, 6)
        row.AddStretchSpacer(1)
        row.Add(self.cancel_button, 0, wx.RIGHT, 6)
        row.Add(self.create_button, 0)
        footer.SetSizer(row)
        return footer

    def FitInside(self):
        for page in self._pages:
            page.Layout()

    def _layout_workspace_split(self):
        size = self.workspace_splitter.GetClientSize()
        width = size.GetWidth() if hasattr(size, "GetWidth") else size.width
        if width > 1:
            self.workspace_splitter.SetSashPosition(
                workspace_main_width(width), True
            )

    def _on_size(self, event):
        self._layout_workspace_split()
        size = self.GetClientSize()
        client_width = (
            size.GetWidth() if hasattr(size, "GetWidth") else size.width
        )
        width = max(320, client_width - 48)
        notebook_width = self.notebook.GetClientSize().GetWidth()
        page_width = max(260, notebook_width - 48)
        self.guide_hint.Wrap(width)
        self._layout_field_labels(page_width)
        self.preset_summary.SetMaxSize(wx.Size(page_width, -1))
        self.multilayer_hint.SetMaxSize(wx.Size(page_width, -1))
        self.motor_recommendation.SetMaxSize(wx.Size(page_width, -1))
        self.preset_summary.Wrap(page_width)
        self.multilayer_hint.Wrap(page_width)
        self.motor_recommendation.Wrap(page_width)
        self._layout_preview_sidebar()
        self.FitInside()
        event.Skip()

    def choice_code(self, choice, default=None):
        codes = self._choice_codes.get(choice, [])
        selection = choice.GetSelection()
        if 0 <= selection < len(codes):
            return codes[selection]
        return default

    def set_choice_options(self, choice, options, selected_code=None):
        choice.Freeze()
        try:
            choice.Clear()
            codes = []
            selected_index = 0
            for index, (code, label) in enumerate(options):
                choice.Append(label)
                codes.append(code)
                if code == selected_code:
                    selected_index = index
            self._choice_codes[choice] = codes
            if codes:
                choice.SetSelection(selected_index)
        finally:
            choice.Thaw()

    def set_choice_code(self, choice, code):
        codes = self._choice_codes.get(choice, [])
        try:
            choice.SetSelection(codes.index(code))
            return True
        except ValueError:
            return False

    def set_units(self, unit_label):
        for label in self.unit_labels:
            label.SetLabel(unit_label)
        self.Layout()

    def set_sizing_mode(self, mode):
        manual = mode == "manual"
        fit_turns = mode == "fit_turns"
        fit_length = mode == "fit_length"
        self.turns.Enable(not fit_length)
        self.track_width.Enable(manual)
        self.spacing.Enable(manual)
        self.spacing_mode_choice.Enable(manual)
        self.available_diameter.Enable(not manual)
        self.target_length.Enable(fit_length)
        self.fill_ratio.Enable(not manual)
        self.minimum_track_width.Enable(not manual)
        self.minimum_clearance.Enable(not manual)
        if fit_turns:
            self.target_length.Enable(False)
        if self.notebook.GetSelection() == 2:
            self._update_navigation()

    def set_coil_shape(self, shape):
        motor_shape = shape != "circular"
        for control in (
                self.target_torque, self.motor_target_force,
                self.motor_target_linear_speed, self.air_gap_flux_density,
                self.electrical_loading, self.winding_factor,
                self.motor_inner_ratio):
            control.Enable(motor_shape)
        self.shape_aspect_ratio.Enable(motor_shape)
        self.shape_taper.Enable(shape == "motor_trapezoid")
        self.primitive_mode_choice.Enable(not motor_shape)
        if motor_shape:
            self.set_choice_code(self.primitive_mode_choice, "segment")
        self.set_motor_layout(shape, self.choice_code(
            self.motor_layout_choice, "single"
        ))
        self.set_primitive_mode(
            self.choice_code(self.primitive_mode_choice, "auto"),
            arc_supported=not motor_shape,
        )

    def set_motor_layout(self, shape, layout):
        motor_shape = shape != "circular"
        arranged = motor_shape and layout in ("radial", "linear")
        self.motor_layout_choice.Enable(motor_shape)
        self.motor_pole_pairs.Enable(arranged)
        self.motor_slot_count.Enable(arranged)
        self.motor_phase_count.Enable(arranged)
        self.motor_array_radius.Enable(motor_shape and layout == "radial")
        self.motor_linear_pitch.Enable(motor_shape and layout == "linear")
        self.motor_array_angle.Enable(arranged)
        self.motor_orientation_choice.Enable(arranged)
        self.motor_alternate_winding.Enable(arranged)

    def set_primitive_mode(self, mode, arc_supported=True):
        use_arcs = mode in ("auto", "arc") and arc_supported
        use_segments = mode in ("auto", "segment") or not arc_supported
        self.arcs_per_turn.Enable(use_arcs)
        self.segments_per_turn.Enable(use_segments)

    def set_multilayer_enabled(self, enabled):
        for control in (self.via_diameter, self.via_drill, self.via_clearance):
            control.Enable(bool(enabled))

    def _page_wrap_width(self):
        return max(260, self.notebook.GetClientSize().GetWidth() - 48)

    def _sidebar_wrap_width(self):
        return max(260, self.preview_sidebar.GetClientSize().GetWidth() - 20)

    def _layout_preview_sidebar(self):
        wrap_width = self._sidebar_wrap_width()
        for label in (
                self.preview_caption, self.preview_legend,
                self.validation_summary, self.electrical_summary,
                self.resolved_summary, self.segment_estimate):
            label.SetMaxSize(wx.Size(wrap_width, -1))
            label.Wrap(wrap_width)
        self.preview_sidebar.Layout()
        self.preview_sidebar.FitInside()
        client = self.preview_sidebar.GetClientSize()
        virtual = self.preview_sidebar.GetVirtualSize()
        client_width = max(1, client.GetWidth())
        virtual_height = max(client.GetHeight(), virtual.GetHeight())
        self.preview_sidebar.SetVirtualSize(wx.Size(
            client_width, virtual_height
        ))
        view = self.preview_sidebar.GetViewStart()
        try:
            view_y = view[1]
        except (TypeError, IndexError):
            view_y = getattr(view, "y", 0)
        self.preview_sidebar.Scroll(0, view_y)

    def set_segment_estimate(self, count, layer_count=1, via_count=0,
                             primitive_label="segments"):
        self.segment_estimate.SetLabel(self.tr(
            "estimated_objects",
            count=count,
            layers=layer_count,
            vias=via_count,
            primitive=primitive_label,
        ))
        self._layout_preview_sidebar()

    def set_motor_recommendation(self, text, enabled=True):
        self.motor_recommendation.SetLabel(text)
        self.motor_recommendation.Wrap(self._page_wrap_width())
        self.apply_motor_recommendation_button.Enable(bool(enabled))
        self.Layout()
        self.FitInside()

    def set_visible_fields(self, visible_keys):
        visible = set(visible_keys)
        for key, field in self._field_sizers.items():
            field.ShowItems(key in visible)
        self.Layout()
        self.FitInside()

    def set_workflow_pages(self, page_keys):
        wanted = tuple(page_keys)
        if wanted == tuple(self._page_keys):
            return False
        current = self.notebook.GetSelection()
        current_key = (
            self._page_keys[current]
            if 0 <= current < len(self._page_keys) else None
        )
        self.notebook.Freeze()
        try:
            while self.notebook.GetPageCount():
                self.notebook.RemovePage(0)
            records = [
                (key, page) for key, page in self._all_page_records
                if key in wanted
            ]
            for index, (key, page) in enumerate(records):
                self.notebook.AddPage(page, self._page_label(key, index))
            self._page_keys = [key for key, _page in records]
            self._pages = [page for _key, page in records]
            selection = (
                self._page_keys.index(current_key)
                if current_key in self._page_keys else 0
            )
            if self._pages:
                self.notebook.SetSelection(selection)
        finally:
            self.notebook.Thaw()
        self._update_navigation()
        self.Layout()
        self.FitInside()
        return True

    def set_profile_names(self, names, selected=""):
        names = list(names)
        self.profile_choice.Set(names)
        if selected in names:
            self.profile_choice.SetSelection(names.index(selected))
        elif names:
            self.profile_choice.SetSelection(0)
        else:
            self.profile_choice.SetSelection(wx.NOT_FOUND)

    def selected_profile_name(self):
        selection = self.profile_choice.GetSelection()
        return (self.profile_choice.GetString(selection)
                if selection != wx.NOT_FOUND else "")

    def set_preset_summary(self, text):
        self.preset_summary.SetLabel(text)
        self.preset_summary.Wrap(self._page_wrap_width())
        self.Layout()
        self.FitInside()

    def set_electrical_summary(self, text):
        self.electrical_summary.SetLabel(text)
        self._layout_preview_sidebar()

    def set_resolved_summary(self, text):
        self.resolved_summary.SetLabel(text)
        self._layout_preview_sidebar()

    def apply_translations(self, translator):
        spacing_mode = self.choice_code(self.spacing_mode_choice, "pitch")
        coil_shape = self.choice_code(self.coil_shape_choice, "circular")
        angle_unit = self.choice_code(self.angle_unit_choice, "degrees")
        direction = self.choice_code(self.direction_choice, "clockwise")
        design_mode = self.choice_code(self.design_mode_choice, "manual")
        motor_connection = self.choice_code(
            self.motor_connection_choice, "star"
        )
        self.tr = translator

        for index, key in enumerate(self._page_keys):
            self.notebook.SetPageText(index, self._page_label(key, index))

        label_keys = (
            "application_preset", "design_mode",
            "manufacturing_preset", "copper_thickness", "target_current",
            "target_torque", "air_gap_flux_density", "electrical_loading",
            "winding_factor", "motor_inner_ratio",
            "motor_supply_voltage", "motor_target_speed",
            "motor_max_phase_current", "allowed_temperature_rise",
            "motor_connection", "motor_board_outer_diameter",
            "motor_board_inner_diameter", "target_resistance",
            "target_inductance", "motor_edge_clearance", "motor_slot_gap",
            "group_name", "net_name",
            "start_layer", "layer_count", "selected_layers",
            "center_x", "center_y", "motor_layout", "motor_pole_pairs",
            "motor_slot_count", "motor_phase_count",
            "motor_array_radius", "motor_linear_pitch", "motor_array_angle",
            "motor_orientation", "motor_alternate_winding",
            "sizing_mode", "available_diameter", "target_length", "fill_ratio",
            "minimum_track_width", "minimum_clearance", "coil_shape",
            "shape_aspect_ratio", "shape_taper_percent", "primitive_mode",
            "quality_preset", "arcs_per_turn", "segments_per_turn",
            "initial_radius", "turns", "additional_segments", "track_width",
            "spacing", "spacing_mode", "angle_offset", "angle_unit", "direction",
            "via_diameter", "via_drill", "via_clearance",
        )
        for key in label_keys:
            self.labels[key].SetLabel(self.tr(key))
            self.labels[key].Wrap(240)

        self.selection_button.SetLabel(self.tr("center_from_selection"))
        self.apply_motor_recommendation_button.SetLabel(
            self.tr("apply_motor_recommendation")
        )
        self.create_group.SetLabel(self.tr("create_group"))
        self.close_after_create.SetLabel(self.tr("close_after_create"))
        self.show_advanced_parameters.SetLabel(
            self.tr("show_advanced_parameters")
        )
        self.profile_label.SetLabel(self.tr("profile_title"))
        self.profile_load_button.SetLabel(self.tr("profile_load"))
        self.profile_save_button.SetLabel(self.tr("profile_save"))
        self.profile_delete_button.SetLabel(self.tr("profile_delete"))
        self.reset_button.SetLabel(self.tr("reset"))
        self.previous_button.SetLabel(self.tr("previous_step"))
        self.next_button.SetLabel(self.tr("next_step"))
        self.create_button.SetLabel(self.tr("create"))
        self.cancel_button.SetLabel(self.tr("cancel"))
        self.multilayer_hint.SetLabel(self.tr("multilayer_hint"))
        self.multilayer_hint.Wrap(480)
        self.guide_title.SetLabel(self.tr("guide_title"))
        self.preview_title.SetLabel(self.tr("preview_title"))
        self.summary_title.SetLabel(self.tr("preview_summary"))
        self.preview_legend.SetLabel(self.tr("preview_legend"))
        self.author_label.SetLabel(self.tr("author_info"))
        self.preview_canvas.set_placeholder(self.tr("preview_empty"))

        self.set_choice_options(self.design_mode_choice, (
            ("manual", self.tr("design_manual")),
            ("fit_turns", self.tr("design_fit_turns")),
            ("fit_length", self.tr("design_fit_length")),
            ("target_resistance", self.tr("design_target_resistance")),
            ("target_inductance", self.tr("design_target_inductance")),
            ("target_current", self.tr("design_target_current")),
            ("motor_target", self.tr("design_motor_target")),
        ), design_mode)
        self.set_choice_options(self.motor_connection_choice, (
            ("star", self.tr("motor_connection_star")),
            ("delta", self.tr("motor_connection_delta")),
        ), motor_connection)

        self.set_choice_options(self.coil_shape_choice, (
            ("circular", self.tr("shape_circular")),
            ("motor_ellipse", self.tr("shape_motor_ellipse")),
            ("motor_racetrack", self.tr("shape_motor_racetrack")),
            ("motor_trapezoid", self.tr("shape_motor_trapezoid")),
            ("motor_sector", self.tr("shape_motor_sector")),
        ), coil_shape)

        self.set_choice_options(self.spacing_mode_choice, (
            ("pitch", self.tr("spacing_pitch")),
            ("clearance", self.tr("spacing_clearance")),
        ), spacing_mode)
        self.set_choice_options(self.angle_unit_choice, (
            ("degrees", self.tr("degrees")),
            ("radians", self.tr("radians")),
        ), angle_unit)
        self.set_choice_options(self.direction_choice, (
            ("clockwise", self.tr("clockwise")),
            ("counterclockwise", self.tr("counterclockwise")),
        ), direction)

        self.coil_shape_choice.SetToolTip(self.tr("tooltip_coil_shape"))
        self.shape_aspect_ratio.SetToolTip(
            self.tr("tooltip_shape_aspect_ratio")
        )
        self.shape_taper.SetToolTip(self.tr("tooltip_shape_taper"))
        self.arcs_per_turn.SetToolTip(self.tr("tooltip_arcs"))
        self.segments_per_turn.SetToolTip(self.tr("tooltip_segments"))
        self.fill_ratio.SetToolTip(self.tr("tooltip_fill_ratio"))
        self.application_preset_choice.SetToolTip(
            self.tr("tooltip_application_preset")
        )
        self.manufacturing_preset_choice.SetToolTip(
            self.tr("tooltip_manufacturing_preset")
        )
        self.copper_thickness.SetToolTip(
            self.tr("tooltip_copper_thickness")
        )
        self.target_current.SetToolTip(self.tr("tooltip_target_current"))
        self.motor_target_force.SetToolTip(
            self.tr("tooltip_motor_target_force")
        )
        self.motor_target_linear_speed.SetToolTip(
            self.tr("tooltip_motor_target_linear_speed")
        )
        self.available_diameter.SetToolTip(
            self.tr("tooltip_available_diameter")
        )
        self.target_length.SetToolTip(self.tr("tooltip_target_length"))
        spacing_tooltip = (
            "tooltip_spacing_clearance"
            if spacing_mode == "clearance"
            else "tooltip_spacing_pitch"
        )
        self.spacing.SetToolTip(self.tr(spacing_tooltip))
        self._update_navigation()
        self.Layout()
        self.footer.Layout()
        self.FitInside()



