#!/usr/bin/env python
# -*- coding: utf-8 -*-

from math import hypot, pi
import os

import pcbnew
import wx

from .compat import KiCadCompat
from .electrical import (
        solve_motor_sector_design, solve_motor_spiral_design,
        solve_spiral_electrical_design,
    )
from .geometry import (
    GeometryError,
    axial_flux_motor_dimensions, estimate_axial_flux_motor_torque,
    connector_endpoint_index,
    multilayer_connection_layout, motor_sector_connection_layout,
    estimate_dc_metrics,
    iter_motor_sector_spiral_segments, iter_shaped_spiral_segments,
    iter_spiral_arcs,
    multilayer_track_count,
    motor_array_instances, motor_inner_trace_dfm, motor_sector_dimensions,
    required_inner_radius,
    resolve_motor_spiral_parameters,
    shape_endpoint_scale,
)
from .i18n import Translator, detect_language, localize_error
from .interface import SpiralPanel
from .metadata import PLUGIN_VERSION
from .presets import (
    MANUFACTURING_PRESETS, QUALITY_PRESETS, build_preset_values,
    manufacturing_violation, recommend_copper_fill_ratio,
    recommend_motor_parameters,
)
from .preview import (
    build_preview_scene, build_safe_preview_scene, coerce_preview_values,
)
from .settings import (
    DEFAULTS, SettingsStore, UserProfileStore, default_settings_path,
    shared_profiles_path,
)
from .workflow import (
    WorkflowLocks, parameter_visibility, workflow_page_keys,
    workflow_step_fields,
)
from .ui_layout import fitted_window_size



class ValidationError(Exception):
    pass


class SpiralDialog(wx.Dialog):
    def __init__(self, parent, board, on_destroy=None):
        self.compat = KiCadCompat(pcbnew)
        self.board = board
        self.on_destroy_callback = on_destroy
        self._closing = False
        self._applying_preset = False
        self._applying_recommendation = False
        self._motor_parameters_auto = True
        self._preview_timer = None
        self.store = SettingsStore(default_settings_path(pcbnew))
        self.profile_store = UserProfileStore(shared_profiles_path())
        self.settings = self.store.load()
        self._workflow = WorkflowLocks()
        self._last_page = 0
        self._changing_workflow = False
        language = detect_language(pcbnew_module=pcbnew, wx_module=wx)
        self.tr = Translator(language)
        self.window_title = self.tr(
            "window_title", version=PLUGIN_VERSION
        )

        style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        wx.Dialog.__init__(
            self, parent, title=self.window_title, style=style
        )
        self.panel = SpiralPanel(self, self.tr)
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(self.panel, 1, wx.EXPAND)
        root.Add(
            self.panel.footer, 0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 8,
        )
        self.SetSizer(root)

        self.net_items = self.compat.net_items(board) or [("", None)]
        self.layers = self.compat.copper_layers(board)
        self._populate_board_choices()
        self._apply_settings(self.settings)
        self._refresh_profile_choices()

        selected_center = self.compat.selected_center(board)
        if selected_center is not None:
            self._set_center(selected_center)

        self._bind_events()
        self._update_preview()
        self.Layout()
        display_size = wx.GetDisplaySize()
        display_width = (
            display_size.GetWidth()
            if hasattr(display_size, "GetWidth")
            else display_size.width
        )
        display_height = (
            display_size.GetHeight()
            if hasattr(display_size, "GetHeight")
            else display_size.height
        )
        try:
            display_index = wx.Display.GetFromWindow(self)
            not_found = getattr(wx, "NOT_FOUND", -1)
            if display_index != not_found:
                client = wx.Display(display_index).GetClientArea()
                display_width = client.GetWidth()
                display_height = client.GetHeight()
        except Exception:
            pass
        target_width, target_height, min_width, min_height = fitted_window_size(
            display_width, display_height
        )
        self.SetMinSize(wx.Size(min_width, min_height))
        self.SetSize(wx.Size(target_width, target_height))
        self.panel.FitInside()
        self.CentreOnParent()

    def _bind_events(self):
        panel = self.panel
        panel.cancel_button.Bind(wx.EVT_BUTTON, self._on_cancel)
        panel.create_button.Bind(wx.EVT_BUTTON, self._on_create)
        panel.reset_button.Bind(wx.EVT_BUTTON, self._on_reset)
        panel.selection_button.Bind(wx.EVT_BUTTON, self._on_selection_center)
        panel.apply_motor_recommendation_button.Bind(
            wx.EVT_BUTTON, self._on_apply_motor_recommendation
        )
        panel.profile_load_button.Bind(wx.EVT_BUTTON, self._on_profile_load)
        panel.profile_save_button.Bind(wx.EVT_BUTTON, self._on_profile_save)
        panel.profile_delete_button.Bind(wx.EVT_BUTTON, self._on_profile_delete)
        panel.show_advanced_parameters.Bind(
            wx.EVT_CHECKBOX, self._on_visibility_changed
        )
        panel.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._on_workflow_page)
        panel.application_preset_choice.Bind(
            wx.EVT_CHOICE, self._on_preset_selection_changed
        )
        panel.manufacturing_preset_choice.Bind(
            wx.EVT_CHOICE, self._on_preset_selection_changed
        )
        panel.layer_choice.Bind(
            wx.EVT_CHOICE, self._on_layer_configuration_changed
        )
        panel.layer_count_choice.Bind(
            wx.EVT_CHOICE, self._on_layer_configuration_changed
        )
        panel.sizing_mode_choice.Bind(
            wx.EVT_CHOICE, self._on_sizing_mode_changed
        )
        panel.design_mode_choice.Bind(
            wx.EVT_CHOICE, self._on_design_mode_changed
        )
        panel.motor_connection_choice.Bind(
            wx.EVT_CHOICE, self._on_preview_choice_changed
        )
        panel.coil_shape_choice.Bind(
            wx.EVT_CHOICE, self._on_coil_shape_changed
        )
        panel.motor_layout_choice.Bind(
            wx.EVT_CHOICE, self._on_motor_layout_changed
        )
        panel.motor_orientation_choice.Bind(
            wx.EVT_CHOICE, self._on_preview_choice_changed
        )
        panel.motor_alternate_winding.Bind(
            wx.EVT_CHECKBOX, self._on_preview_choice_changed
        )
        panel.primitive_mode_choice.Bind(
            wx.EVT_CHOICE, self._on_primitive_mode_changed
        )
        panel.quality_preset_choice.Bind(
            wx.EVT_CHOICE, self._on_quality_changed
        )
        panel.spacing_mode_choice.Bind(
            wx.EVT_CHOICE, self._on_spacing_mode_changed
        )
        panel.angle_unit_choice.Bind(
            wx.EVT_CHOICE, self._on_angle_unit_changed
        )
        panel.direction_choice.Bind(
            wx.EVT_CHOICE, self._on_preview_choice_changed
        )
        for control in (
                panel.start_radius, panel.turns, panel.arcs_per_turn,
                panel.segments_per_turn, panel.additional_segments,
                panel.track_width, panel.spacing, panel.available_diameter,
                panel.target_length, panel.fill_ratio,
                panel.motor_board_outer_diameter,
                panel.motor_board_inner_diameter, panel.target_resistance,
                panel.target_inductance, panel.motor_edge_clearance,
                panel.motor_slot_gap, panel.motor_supply_voltage,
                panel.motor_target_speed, panel.motor_max_phase_current,
                panel.allowed_temperature_rise,
                panel.minimum_track_width, panel.minimum_clearance,
                panel.copper_thickness, panel.target_current,
                panel.via_diameter, panel.via_drill, panel.via_clearance,
                panel.shape_aspect_ratio, panel.shape_taper,
                panel.motor_array_radius, panel.motor_linear_pitch,
                panel.motor_array_angle,
                panel.angle_offset):
            control.Bind(wx.EVT_TEXT, self._on_geometry_changed)
        for control in (
                panel.motor_pole_pairs, panel.motor_slot_count,
                panel.motor_phase_count, panel.target_torque,
                panel.motor_target_force, panel.motor_target_linear_speed,
                panel.air_gap_flux_density, panel.electrical_loading,
                panel.winding_factor, panel.motor_inner_ratio):
            control.Bind(wx.EVT_TEXT, self._on_motor_driver_changed)
        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _refresh_profile_choices(self, selected=""):
        self.panel.set_profile_names(self.profile_store.names(), selected)

    def _on_profile_load(self, _event=None):
        name = self.panel.selected_profile_name()
        values = self.profile_store.load(name) if name else None
        if values is None:
            wx.MessageBox(self.tr("profile_not_found"), self.tr("profile_title"),
                          wx.OK | wx.ICON_WARNING, self)
            return
        self.settings = values
        self._workflow.unlock_from(0)
        self._apply_settings(values)
        self._update_preview()

    def _on_profile_save(self, _event=None):
        name = self.panel.profile_name.GetValue().strip()
        if not name:
            wx.MessageBox(self.tr("profile_name_required"), self.tr("profile_title"),
                          wx.OK | wx.ICON_WARNING, self)
            return
        try:
            values = self._read_form()[0]
        except ValidationError as error:
            wx.MessageBox(str(error), self.tr("profile_title"),
                          wx.OK | wx.ICON_WARNING, self)
            return
        overwrite = self.profile_store.load(name) is not None
        if overwrite:
            answer = wx.MessageBox(
                self.tr("profile_overwrite", name=name), self.tr("profile_title"),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self,
            )
            if answer != wx.YES:
                return
        try:
            self.profile_store.save(name, values, overwrite=overwrite)
        except (IOError, OSError, ValueError) as error:
            wx.MessageBox(
                self._error_message(error), self.tr("profile_title"),
                wx.OK | wx.ICON_WARNING, self,
            )
            return
        self.panel.profile_name.SetValue("")
        self._refresh_profile_choices(name)

    def _on_profile_delete(self, _event=None):
        name = self.panel.selected_profile_name()
        if not name:
            return
        answer = wx.MessageBox(
            self.tr("profile_delete_confirm", name=name), self.tr("profile_title"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self,
        )
        if answer == wx.YES:
            self.profile_store.delete(name)
            self._refresh_profile_choices()

    def _visibility_values(self):
        values = dict(self.settings)
        panel = self.panel
        values.update({
            "application_preset": panel.choice_code(
                panel.application_preset_choice, "custom"
            ),
            "coil_shape": panel.choice_code(panel.coil_shape_choice, "circular"),
            "design_mode": panel.choice_code(panel.design_mode_choice, "manual"),
            "layer_count": panel.choice_code(panel.layer_count_choice, 1),
            "show_advanced_parameters": panel.show_advanced_parameters.GetValue(),
        })
        return values

    def _apply_parameter_visibility(self):
        values = self._visibility_values()
        advanced = values["show_advanced_parameters"]
        pages = workflow_page_keys(values, advanced)
        self._changing_workflow = True
        try:
            changed = self.panel.set_workflow_pages(pages)
        finally:
            self._changing_workflow = False
        if changed:
            self._workflow = WorkflowLocks(
                workflow_step_fields(values, advanced)
            )
            self._last_page = max(0, self.panel.notebook.GetSelection())
        self.panel.set_visible_fields(parameter_visibility(values, advanced))

    def _on_visibility_changed(self, _event=None):
        self._apply_parameter_visibility()
        self._schedule_preview()

    def _on_design_mode_changed(self, _event=None):
        design_mode = self.panel.choice_code(
            self.panel.design_mode_choice, "manual"
        )
        sizing_mode = {
            "manual": "manual", "fit_turns": "fit_turns",
            "fit_length": "fit_length",
        }.get(design_mode, "fit_turns")
        self.panel.set_choice_code(self.panel.sizing_mode_choice, sizing_mode)
        self.panel.set_sizing_mode(sizing_mode)
        self._apply_parameter_visibility()
        self._schedule_preview()

    def _on_workflow_page(self, event):
        if self._changing_workflow:
            event.Skip()
            return
        current = self.panel.notebook.GetSelection()
        try:
            if current > self._last_page:
                values = self._read_form(preview=True)[0]
                for index in range(self._last_page, current):
                    self._workflow.lock_step(index, values)
            elif current < self._last_page:
                self._workflow.unlock_from(current)
        except ValidationError:
            pass
        self._last_page = current
        self._apply_parameter_visibility()
        event.Skip()

    def _populate_board_choices(self):
        selected_net = self.panel.choice_code(
            self.panel.net_choice, self.settings.get("net_name", "")
        )
        selected_layer = self.panel.choice_code(self.panel.layer_choice)

        net_options = [
            (name, name or self.tr("no_net")) for name, _item in self.net_items
        ]
        self.panel.set_choice_options(
            self.panel.net_choice, net_options, selected_net
        )

        if selected_layer is None:
            wanted_layer = self.settings.get("layer_name")
            for layer in self.layers:
                if str(self.board.GetLayerName(layer)) == wanted_layer:
                    selected_layer = layer
                    break
        layer_options = [
            (layer, str(self.board.GetLayerName(layer))) for layer in self.layers
        ]
        self.panel.set_choice_options(
            self.panel.layer_choice, layer_options, selected_layer
        )

        selected_count = self.panel.choice_code(
            self.panel.layer_count_choice,
            self.settings.get("layer_count", 1),
        )
        count_options = [
            (count, self.tr("layer_count_option", count=count))
            for count in range(1, 13)
        ]
        self.panel.set_choice_options(
            self.panel.layer_count_choice, count_options, selected_count
        )
        self._update_layer_summary()

    def _update_layer_summary(self):
        start_index = self.panel.layer_choice.GetSelection()
        layer_count = self.panel.choice_code(
            self.panel.layer_count_choice, 1
        )
        if start_index < 0:
            names = []
        else:
            names = [
                str(self.board.GetLayerName(layer))
                for layer in self.layers[
                    start_index:start_index + int(layer_count)
                ]
            ]
        summary = " → ".join(names) if names else "—"
        missing = max(0, int(layer_count) - len(names))
        if missing:
            summary = self.tr(
                "layer_summary_unavailable", layers=summary, missing=missing
            )
        self.panel.layer_summary.SetLabel(summary)
        self.panel.layer_summary.Wrap(180)
        self.panel.set_multilayer_enabled(int(layer_count) > 1)
        self.panel.Layout()
        self.panel.FitInside()

    def _update_preset_summary(self, requested_layers=None, actual_layers=None):
        panel = self.panel
        application = panel.choice_code(
            panel.application_preset_choice, "custom"
        )
        manufacturing = panel.choice_code(
            panel.manufacturing_preset_choice, "custom"
        )
        summary = self.tr(
            "preset_summary",
            application=self.tr("application_" + application),
            manufacturing=self.tr("manufacturing_" + manufacturing),
            description=self.tr("preset_description_" + application),
        )
        if (
                requested_layers is not None
                and actual_layers is not None
                and int(requested_layers) != int(actual_layers)):
            summary += self.tr(
                "preset_layers_adjusted",
                requested=int(requested_layers),
                actual=int(actual_layers),
            )
        panel.set_preset_summary(summary)

    def _apply_preset_values(self, values):
        panel = self.panel
        fmt = self.compat.format_number
        to_user = self.compat.mm_to_user
        requested_layers = values.get("layer_count")
        actual_layers = None

        self._applying_preset = True
        try:
            for key, control in (
                    ("start_radius_mm", panel.start_radius),
                    ("available_diameter_mm", panel.available_diameter),
                    ("target_length_mm", panel.target_length),
                    ("motor_board_outer_diameter_mm",
                     panel.motor_board_outer_diameter),
                    ("motor_board_inner_diameter_mm",
                     panel.motor_board_inner_diameter),
                    ("motor_edge_clearance_mm", panel.motor_edge_clearance),
                    ("motor_slot_gap_mm", panel.motor_slot_gap),
                    ("minimum_track_width_mm", panel.minimum_track_width),
                    ("minimum_clearance_mm", panel.minimum_clearance),
                    ("via_diameter_mm", panel.via_diameter),
                    ("via_drill_mm", panel.via_drill),
                    ("via_clearance_mm", panel.via_clearance)):
                if key in values:
                    control.SetValue(fmt(to_user(values[key])))

            for key, control in (
                    ("turns", panel.turns),
                    ("target_current_a", panel.target_current),
                    ("motor_target_force_n", panel.motor_target_force),
                    ("motor_target_linear_speed_mps",
                     panel.motor_target_linear_speed),
                    ("motor_supply_voltage_v", panel.motor_supply_voltage),
                    ("motor_target_speed_rpm", panel.motor_target_speed),
                    ("motor_max_phase_current_a",
                     panel.motor_max_phase_current),
                    ("allowed_temperature_rise_c",
                     panel.allowed_temperature_rise),
                    ("target_resistance_ohm", panel.target_resistance),
                    ("target_inductance_uh", panel.target_inductance),
                    ("copper_thickness_um", panel.copper_thickness),
                    ("shape_aspect_ratio", panel.shape_aspect_ratio),
                    ("motor_pole_pairs", panel.motor_pole_pairs),
                    ("motor_array_radius_mm", panel.motor_array_radius),
                    ("motor_linear_pitch_mm", panel.motor_linear_pitch),
                    ("motor_array_angle_degrees", panel.motor_array_angle)):
                if key in values:
                    control.SetValue(fmt(values[key]))

            if "fill_ratio" in values:
                panel.fill_ratio.SetValue(fmt(values["fill_ratio"] * 100.0))
            if "shape_taper_ratio" in values:
                panel.shape_taper.SetValue(fmt(
                    values["shape_taper_ratio"] * 100.0
                ))
            if "additional_segments" in values:
                panel.additional_segments.SetValue(
                    str(values["additional_segments"])
                )

            for key, choice in (
                    ("application_preset", panel.application_preset_choice),
                    ("manufacturing_preset", panel.manufacturing_preset_choice),
                    ("design_mode", panel.design_mode_choice),
                    ("motor_connection", panel.motor_connection_choice),
                    ("sizing_mode", panel.sizing_mode_choice),
                    ("primitive_mode", panel.primitive_mode_choice),
                    ("coil_shape", panel.coil_shape_choice),
                    ("quality_preset", panel.quality_preset_choice),
                    ("spacing_mode", panel.spacing_mode_choice),
                    ("motor_layout", panel.motor_layout_choice),
                    ("motor_orientation", panel.motor_orientation_choice)):
                if key in values:
                    panel.set_choice_code(choice, values[key])

            quality = values.get("quality_preset")
            quality_values = QUALITY_PRESETS.get(quality)
            if quality_values is not None:
                arcs_per_turn, segments_per_turn = quality_values
                panel.arcs_per_turn.SetValue(str(arcs_per_turn))
                panel.segments_per_turn.SetValue(str(segments_per_turn))
                values["arcs_per_turn"] = arcs_per_turn
                values["segments_per_turn"] = segments_per_turn

            if requested_layers is not None:
                start_index = max(0, panel.layer_choice.GetSelection())
                available_layers = max(1, len(self.layers) - start_index)
                actual_layers = min(
                    max(1, int(requested_layers)), available_layers, 12
                )
                panel.set_choice_code(
                    panel.layer_count_choice, actual_layers
                )
                values["layer_count"] = actual_layers

            self.settings.update(values)
            sizing_mode = panel.choice_code(
                panel.sizing_mode_choice, "manual"
            )
            primitive_mode = panel.choice_code(
                panel.primitive_mode_choice, "auto"
            )
            panel.set_sizing_mode(sizing_mode)
            coil_shape = panel.choice_code(
                panel.coil_shape_choice, "circular"
            )
            panel.set_coil_shape(coil_shape)
            panel.set_primitive_mode(
                primitive_mode,
                self.compat.supports_arcs() and coil_shape == "circular",
            )
            self._update_layer_summary()
        finally:
            self._applying_preset = False

        if "fill_ratio" not in values:
            self._apply_application_fill_recommendation()
        self._refresh_motor_recommendation(
            apply=(self._motor_parameters_auto
                   or not self._application_is_custom()),
            update_preview=False, preserve_keys=tuple(values),
        )
        self._update_preset_summary(requested_layers, actual_layers)
        self._apply_parameter_visibility()
        self._update_preview()

    def _apply_settings(self, values):
        panel = self.panel
        fmt = self.compat.format_number
        to_user = self.compat.mm_to_user
        self._motor_parameters_auto = bool(
            values.get("motor_parameters_auto", True)
        )

        panel.group_name.SetValue(values["group_name"])
        panel.center_x.SetValue(fmt(to_user(values["center_x_mm"])))
        panel.center_y.SetValue(fmt(to_user(values["center_y_mm"])))
        panel.start_radius.SetValue(fmt(to_user(values["start_radius_mm"])))
        panel.turns.SetValue(fmt(values["turns"]))
        panel.shape_aspect_ratio.SetValue(fmt(values["shape_aspect_ratio"]))
        panel.shape_taper.SetValue(fmt(values["shape_taper_ratio"] * 100.0))
        panel.motor_pole_pairs.SetValue(str(values["motor_pole_pairs"]))
        panel.motor_array_radius.SetValue(fmt(to_user(
            values["motor_array_radius_mm"]
        )))
        panel.motor_linear_pitch.SetValue(fmt(to_user(
            values["motor_linear_pitch_mm"]
        )))
        panel.motor_array_angle.SetValue(fmt(
            values["motor_array_angle_degrees"]
        ))
        panel.motor_alternate_winding.SetValue(
            values["motor_alternate_winding"]
        )
        panel.arcs_per_turn.SetValue(str(values["arcs_per_turn"]))
        panel.segments_per_turn.SetValue(str(values["segments_per_turn"]))
        panel.additional_segments.SetValue(
            str(values["additional_segments"])
        )
        panel.track_width.SetValue(fmt(to_user(values["track_width_mm"])))
        panel.spacing.SetValue(fmt(to_user(values["spacing_mm"])))
        panel.available_diameter.SetValue(
            fmt(to_user(values["available_diameter_mm"]))
        )
        panel.target_length.SetValue(
            fmt(to_user(values["target_length_mm"]))
        )
        panel.fill_ratio.SetValue(fmt(values["fill_ratio"] * 100.0))
        panel.minimum_track_width.SetValue(
            fmt(to_user(values["minimum_track_width_mm"]))
        )
        panel.minimum_clearance.SetValue(
            fmt(to_user(values["minimum_clearance_mm"]))
        )
        panel.copper_thickness.SetValue(
            fmt(values["copper_thickness_um"])
        )
        panel.target_current.SetValue(fmt(values["target_current_a"]))
        panel.target_torque.SetValue(fmt(values["target_torque_nm"]))
        panel.motor_target_force.SetValue(fmt(values["motor_target_force_n"]))
        panel.motor_target_linear_speed.SetValue(fmt(
            values["motor_target_linear_speed_mps"]
        ))
        panel.air_gap_flux_density.SetValue(fmt(
            values["air_gap_flux_density_t"]
        ))
        panel.electrical_loading.SetValue(fmt(
            values["electrical_loading_a_per_m"]
        ))
        panel.winding_factor.SetValue(fmt(values["winding_factor"]))
        panel.motor_inner_ratio.SetValue(fmt(values["motor_inner_ratio"]))
        panel.motor_board_outer_diameter.SetValue(fmt(to_user(
            values["motor_board_outer_diameter_mm"]
        )))
        panel.motor_board_inner_diameter.SetValue(fmt(to_user(
            values["motor_board_inner_diameter_mm"]
        )))
        panel.motor_edge_clearance.SetValue(fmt(to_user(
            values["motor_edge_clearance_mm"]
        )))
        panel.motor_slot_gap.SetValue(fmt(to_user(values["motor_slot_gap_mm"])))
        panel.motor_supply_voltage.SetValue(fmt(values["motor_supply_voltage_v"]))
        panel.motor_target_speed.SetValue(fmt(values["motor_target_speed_rpm"]))
        panel.motor_max_phase_current.SetValue(fmt(
            values["motor_max_phase_current_a"]
        ))
        panel.allowed_temperature_rise.SetValue(fmt(
            values["allowed_temperature_rise_c"]
        ))
        panel.target_resistance.SetValue(fmt(values["target_resistance_ohm"]))
        panel.target_inductance.SetValue(fmt(values["target_inductance_uh"]))
        panel.motor_slot_count.SetValue(str(values["motor_slot_count"]))
        panel.motor_phase_count.SetValue(str(values["motor_phase_count"]))
        panel.via_diameter.SetValue(
            fmt(to_user(values["via_diameter_mm"]))
        )
        panel.via_drill.SetValue(fmt(to_user(values["via_drill_mm"])))
        panel.via_clearance.SetValue(
            fmt(to_user(values["via_clearance_mm"]))
        )
        panel.create_group.SetValue(values["create_group"])
        panel.close_after_create.SetValue(values["close_after_create"])
        panel.show_advanced_parameters.SetValue(
            values.get("show_advanced_parameters", False)
        )

        angle_value = values["angle_degrees"]
        if values["angle_unit"] == "radians":
            angle_value = angle_value * pi / 180.0
        panel.angle_offset.SetValue(fmt(angle_value))

        panel.apply_translations(self.tr)
        panel.set_choice_code(panel.design_mode_choice, values["design_mode"])
        panel.set_choice_code(
            panel.motor_connection_choice, values["motor_connection"]
        )
        panel.set_choice_options(panel.application_preset_choice, (
            ("custom", self.tr("application_custom")),
            ("general", self.tr("application_general")),
            ("compact_sensor", self.tr("application_compact_sensor")),
            ("nfc_rfid", self.tr("application_nfc_rfid")),
            ("wireless_power", self.tr("application_wireless_power")),
            ("heating", self.tr("application_heating")),
            ("long_trace", self.tr("application_long_trace")),
            ("motor_axial_ellipse", self.tr("application_motor_axial_ellipse")),
            ("motor_racetrack", self.tr("application_motor_racetrack")),
            ("motor_trapezoid", self.tr("application_motor_trapezoid")),
            ("motor_sector", self.tr("application_motor_sector")),
            ("motor_linear", self.tr("application_motor_linear")),
        ), values["application_preset"])
        if values.get("application_preset", "custom") != "custom":
            self._motor_parameters_auto = True
            self.settings["motor_parameters_auto"] = True

        panel.set_choice_options(panel.manufacturing_preset_choice, (
            ("custom", self.tr("manufacturing_custom")),
            ("standard", self.tr("manufacturing_standard")),
            ("conservative", self.tr("manufacturing_conservative")),
            ("fine", self.tr("manufacturing_fine")),
            ("heavy_copper", self.tr("manufacturing_heavy_copper")),
        ), values["manufacturing_preset"])
        panel.set_choice_options(panel.sizing_mode_choice, (
            ("manual", self.tr("sizing_manual")),
            ("fit_turns", self.tr("sizing_fit_turns")),
            ("fit_length", self.tr("sizing_fit_length")),
        ), values["sizing_mode"])
        panel.set_choice_options(panel.primitive_mode_choice, (
            ("auto", self.tr("primitive_auto")),
            ("arc", self.tr("primitive_arc")),
            ("segment", self.tr("primitive_segment")),
        ), values["primitive_mode"])
        panel.set_choice_code(panel.coil_shape_choice, values["coil_shape"])
        panel.set_choice_options(panel.quality_preset_choice, (
            ("fast", self.tr("quality_fast")),
            ("balanced", self.tr("quality_balanced")),
            ("smooth", self.tr("quality_smooth")),
            ("custom", self.tr("quality_custom")),
        ), values["quality_preset"])
        panel.set_choice_options(panel.motor_layout_choice, (
            ("single", self.tr("motor_layout_single")),
            ("radial", self.tr("motor_layout_radial")),
            ("linear", self.tr("motor_layout_linear")),
        ), values["motor_layout"])
        panel.set_choice_options(panel.motor_orientation_choice, (
            ("radial", self.tr("motor_orientation_radial")),
            ("tangential", self.tr("motor_orientation_tangential")),
        ), values["motor_orientation"])
        panel.set_choice_options(panel.spacing_mode_choice, (
            ("pitch", self.tr("spacing_pitch")),
            ("clearance", self.tr("spacing_clearance")),
        ), values["spacing_mode"])
        panel.set_choice_options(panel.angle_unit_choice, (
            ("degrees", self.tr("degrees")),
            ("radians", self.tr("radians")),
        ), values["angle_unit"])
        panel.set_choice_options(panel.direction_choice, (
            ("clockwise", self.tr("clockwise")),
            ("counterclockwise", self.tr("counterclockwise")),
        ), values["direction"])
        panel.set_choice_options(panel.layer_count_choice, (
            (count, self.tr("layer_count_option", count=count))
            for count in range(1, 13)
        ), values["layer_count"])

        self.current_angle_unit = values["angle_unit"]
        panel.set_units(self.compat.unit_label())
        panel.set_sizing_mode(values["sizing_mode"])
        panel.set_coil_shape(values["coil_shape"])
        panel.set_primitive_mode(
            values["primitive_mode"],
            self.compat.supports_arcs() and values["coil_shape"] == "circular",
        )
        backend_key = (
            "backend_arcs"
            if self.compat.supports_arcs()
            else "backend_segments"
        )
        panel.compatibility_summary.SetLabel(self.tr(
            "compatibility_info",
            version=self.compat.version_string(),
            backend=self.tr(backend_key),
        ))
        self._update_layer_summary()
        self._update_preset_summary()
        self._refresh_motor_recommendation(
            apply=False, update_preview=False,
        )
        self._apply_parameter_visibility()

    def _set_center(self, point):
        x, y = point
        self.panel.center_x.SetValue(self.compat.format_number(
            self.compat.internal_to_user(x)
        ))
        self.panel.center_y.SetValue(self.compat.format_number(
            self.compat.internal_to_user(y)
        ))

    def _number(self, control, field_key, focus=True):
        try:
            return float(control.GetValue().strip())
        except (TypeError, ValueError):
            if focus:
                control.SetFocus()
            raise ValidationError(self.tr(
                "invalid_number", field=self.tr(field_key)
            ))

    def _integer(self, control, field_key, focus=True):
        value = self._number(control, field_key, focus)
        if not value.is_integer():
            if focus:
                control.SetFocus()
            raise ValidationError(self.tr(
                "invalid_number", field=self.tr(field_key)
            ))
        return int(value)

    @staticmethod
    def _optional_number(control, fallback):
        try:
            return float(control.GetValue().strip())
        except (TypeError, ValueError):
            return float(fallback)

    @classmethod
    def _optional_integer(cls, control, fallback):
        value = cls._optional_number(control, fallback)
        return int(value) if value.is_integer() else int(fallback)

    def _motor_shape_active(self):
        return self.panel.choice_code(
            self.panel.coil_shape_choice, "circular"
        ).startswith("motor_")

    def _application_is_custom(self):
        return self.panel.choice_code(
            self.panel.application_preset_choice, "custom"
        ) == "custom"

    def _apply_application_fill_recommendation(self):
        if self._application_is_custom():
            return
        panel = self.panel
        value = recommend_copper_fill_ratio(
            panel.choice_code(
                panel.application_preset_choice, "custom"
            ),
            panel.choice_code(
                panel.manufacturing_preset_choice, "custom"
            ),
            self._optional_number(
                panel.target_current,
                self.settings.get("target_current_a", 0.0),
            ),
            self._optional_number(
                panel.copper_thickness,
                self.settings.get("copper_thickness_um", 35.0),
            ),
            self._optional_number(
                panel.fill_ratio,
                self.settings.get("fill_ratio", 0.55) * 100.0,
            ) / 100.0,
        )
        self._applying_recommendation = True
        try:
            panel.fill_ratio.SetValue(
                self.compat.format_number(value * 100.0)
            )
            self.settings["fill_ratio"] = value
        finally:
            self._applying_recommendation = False

    def _current_motor_recommendation(self):
        panel = self.panel
        shape = panel.choice_code(panel.coil_shape_choice, "circular")
        if not shape.startswith("motor_"):
            return {}
        layout = panel.choice_code(panel.motor_layout_choice, "single")
        pairs = self._optional_integer(
            panel.motor_pole_pairs,
            self.settings.get("motor_pole_pairs", 3),
        )
        to_mm = self.compat.user_to_mm
        to_user = self.compat.mm_to_user

        def length(control, key):
            return to_mm(self._optional_number(
                control, to_user(self.settings.get(key, 0.0))
            ))

        return recommend_motor_parameters(
            shape,
            layout,
            pairs,
            panel.choice_code(
                panel.manufacturing_preset_choice, "custom"
            ),
            panel.choice_code(panel.layer_count_choice, 1),
            length(panel.via_diameter, "via_diameter_mm"),
            length(panel.via_clearance, "via_clearance_mm"),
            length(panel.track_width, "track_width_mm"),
            length(panel.minimum_track_width, "minimum_track_width_mm"),
            length(panel.minimum_clearance, "minimum_clearance_mm"),
            application_code=panel.choice_code(
                panel.application_preset_choice, "custom"
            ),
            target_current_a=self._optional_number(
                panel.target_current,
                self.settings.get("target_current_a", 0.0),
            ),
            copper_thickness_um=self._optional_number(
                panel.copper_thickness,
                self.settings.get("copper_thickness_um", 35.0),
            ),
            target_torque_nm=self._optional_number(
                panel.target_torque, self.settings.get("target_torque_nm", 0.0)
            ),
            air_gap_flux_density_t=self._optional_number(
                panel.air_gap_flux_density,
                self.settings.get("air_gap_flux_density_t", 0.45),
            ),
            electrical_loading_a_per_m=self._optional_number(
                panel.electrical_loading,
                self.settings.get("electrical_loading_a_per_m", 12000.0),
            ),
            winding_factor=self._optional_number(
                panel.winding_factor, self.settings.get("winding_factor", 0.9)
            ),
            motor_inner_ratio=self._optional_number(
                panel.motor_inner_ratio,
                self.settings.get("motor_inner_ratio", 0.58),
            ),
            motor_slot_count=self._optional_integer(
                panel.motor_slot_count, self.settings.get("motor_slot_count", 0)
            ),
            motor_phase_count=self._optional_integer(
                panel.motor_phase_count, self.settings.get("motor_phase_count", 3)
            ),
        )

    def _show_motor_recommendation(self, recommendation,
                                   preserved_field=None):
        if not recommendation:
            self.panel.set_motor_recommendation(
                self.tr("motor_recommendation_not_applicable"), False
            )
            return
        if preserved_field:
            key = "motor_recommendation_constrained"
        else:
            key = (
                "motor_recommendation_auto"
                if self._motor_parameters_auto
                else "motor_recommendation_manual"
            )
        fmt = self.compat.format_number
        layout = self.tr("motor_layout_" + recommendation["layout"])
        text = self.tr(
            key,
            field=preserved_field or "",
            layout=layout,
            poles=recommendation["pole_count"],
            aspect=fmt(recommendation["shape_aspect_ratio"]),
            taper=fmt(recommendation["shape_taper_ratio"] * 100.0),
            radius=fmt(self.compat.mm_to_user(
                recommendation["start_radius_mm"]
            )),
            unit=self.compat.unit_label(),
            fill=fmt(recommendation["fill_ratio"] * 100.0),
        )
        if "motor_outer_diameter_mm" in recommendation:
            text += " " + self.tr(
                "motor_dimensioning_recommendation",
                outer=fmt(self.compat.mm_to_user(
                    recommendation["motor_outer_diameter_mm"]
                )),
                inner=fmt(self.compat.mm_to_user(
                    recommendation["motor_inner_diameter_mm"]
                )),
                ratio=fmt(recommendation["motor_inner_ratio"]),
                unit=self.compat.unit_label(),
            )
        self.panel.set_motor_recommendation(text, True)

    def _apply_motor_recommendation_values(self, recommendation,
                                            preserve_keys=()):
        if not recommendation:
            return
        preserve = set(preserve_keys)
        panel = self.panel
        fmt = self.compat.format_number
        self._applying_recommendation = True
        try:
            if "shape_aspect_ratio" not in preserve:
                panel.shape_aspect_ratio.SetValue(fmt(
                    recommendation["shape_aspect_ratio"]
                ))
            if "shape_taper_ratio" not in preserve:
                panel.shape_taper.SetValue(fmt(
                    recommendation["shape_taper_ratio"] * 100.0
                ))
            if "start_radius_mm" not in preserve:
                panel.start_radius.SetValue(fmt(self.compat.mm_to_user(
                    recommendation["start_radius_mm"]
                )))
            if "fill_ratio" not in preserve:
                panel.fill_ratio.SetValue(fmt(
                    recommendation["fill_ratio"] * 100.0
                ))
            if "spacing_mode" not in preserve:
                panel.set_choice_code(
                    panel.spacing_mode_choice, recommendation["spacing_mode"]
                )
            if "quality_preset" not in preserve:
                panel.set_choice_code(
                    panel.quality_preset_choice,
                    recommendation["quality_preset"],
                )
                quality = QUALITY_PRESETS[recommendation["quality_preset"]]
                panel.arcs_per_turn.SetValue(str(quality[0]))
                panel.segments_per_turn.SetValue(str(quality[1]))
            if "additional_segments" not in preserve:
                panel.additional_segments.SetValue(str(
                    recommendation["additional_segments"]
                ))
            if "sizing_mode" in recommendation and "sizing_mode" not in preserve:
                panel.set_choice_code(
                    panel.sizing_mode_choice, recommendation["sizing_mode"]
                )
                panel.set_sizing_mode(recommendation["sizing_mode"])
            if ("available_diameter_mm" in recommendation
                    and "available_diameter_mm" not in preserve):
                panel.available_diameter.SetValue(fmt(self.compat.mm_to_user(
                    recommendation["available_diameter_mm"]
                )))
            if "motor_array_radius_mm" not in preserve:
                panel.motor_array_radius.SetValue(fmt(self.compat.mm_to_user(
                    recommendation["motor_array_radius_mm"]
                )))
            if "motor_linear_pitch_mm" not in preserve:
                panel.motor_linear_pitch.SetValue(fmt(self.compat.mm_to_user(
                    recommendation["motor_linear_pitch_mm"]
                )))
            if "motor_orientation" not in preserve:
                panel.set_choice_code(
                    panel.motor_orientation_choice,
                    recommendation["motor_orientation"],
                )
            if "motor_alternate_winding" not in preserve:
                panel.motor_alternate_winding.SetValue(
                    recommendation["motor_alternate_winding"]
                )
            self.settings.update({
                key: value for key, value in recommendation.items()
                if key not in (
                    "pole_count", "slot_count", "phase_count",
                    "phase_balanced", "layout", "motor_outer_diameter_mm",
                    "motor_inner_diameter_mm",
                )
                and key not in preserve
            })
            self._motor_parameters_auto = True
            self.settings["motor_parameters_auto"] = True
        finally:
            self._applying_recommendation = False

    def _refresh_motor_recommendation(self, apply=False,
                                      update_preview=False,
                                      preserve_keys=(),
                                      preserved_field=None):
        recommendation = self._current_motor_recommendation()
        fixed_keys = tuple(self._workflow.fixed_values())
        preserve_keys = tuple(set(preserve_keys) | set(fixed_keys))
        if apply and recommendation:
            self._apply_motor_recommendation_values(
                recommendation, preserve_keys
            )
            recommendation = self._current_motor_recommendation()
        self._show_motor_recommendation(recommendation, preserved_field)
        if update_preview:
            self._update_preview()

    def _mark_motor_parameters_manual(self, preserve_key=None,
                                      field_key=None):
        if not self._motor_shape_active():
            return
        if self._application_is_custom():
            self._motor_parameters_auto = False
            self.settings["motor_parameters_auto"] = False
            self._refresh_motor_recommendation(apply=False)
            return
        self._motor_parameters_auto = True
        self.settings["motor_parameters_auto"] = True
        self._refresh_motor_recommendation(
            apply=True,
            preserve_keys=(preserve_key,) if preserve_key else (),
            preserved_field=self.tr(field_key) if field_key else None,
        )

    def _on_apply_motor_recommendation(self, _event):
        self._motor_parameters_auto = True
        self.settings["motor_parameters_auto"] = True
        self._refresh_motor_recommendation(apply=True, update_preview=True)

    def _on_motor_driver_changed(self, event):
        if not self._applying_preset and not self._applying_recommendation:
            auto = self._motor_parameters_auto or not self._application_is_custom()
            self._refresh_motor_recommendation(
                apply=auto, update_preview=True
            )
        event.Skip()

    def _actual_primitive_mode(self):
        coil_shape = self.panel.choice_code(
            self.panel.coil_shape_choice, "circular"
        )
        if coil_shape != "circular":
            return "segment"
        requested = self.panel.choice_code(
            self.panel.primitive_mode_choice, "auto"
        )
        if requested == "segment":
            return "segment"
        return "arc" if self.compat.supports_arcs() else "segment"

    def _geometry_error_message(self, error):
        values = dict(error.values)
        for key in ("actual", "minimum"):
            if key in values:
                values[key] = self.compat.format_number(values[key])
        values.setdefault("unit", self.compat.unit_label())
        translated = self.tr(error.code, **values)
        return translated if translated != error.code else str(error)

    def _error_message(self, error):
        if isinstance(error, GeometryError):
            return self._geometry_error_message(error)
        return localize_error(self.tr, error)

    def _manufacturing_error_message(self, violation):
        return self.tr(
            violation["code"],
            process=self.tr("manufacturing_" + violation["process"]),
            actual=self.compat.format_number(self.compat.mm_to_user(
                violation["actual"]
            )),
            minimum=self.compat.format_number(self.compat.mm_to_user(
                violation["minimum"]
            )),
            unit=self.compat.unit_label(),
        )

    def _read_form(self, preview=False):
        panel = self.panel
        focus = not preview
        design_mode = panel.choice_code(
            panel.design_mode_choice, "manual"
        )
        sizing_mode = {
            "manual": "manual", "fit_turns": "fit_turns",
            "fit_length": "fit_length",
        }.get(design_mode, "fit_turns")
        coil_shape = panel.choice_code(
            panel.coil_shape_choice, "circular"
        )
        actual_primitive_mode = self._actual_primitive_mode()
        shape_aspect_ratio = self._number(
            panel.shape_aspect_ratio, "shape_aspect_ratio", focus
        )
        shape_taper_percent = self._number(
            panel.shape_taper, "shape_taper_percent", focus
        )
        center_x = self._number(panel.center_x, "center_xy", focus)
        center_y = self._number(panel.center_y, "center_xy", focus)
        motor_layout = panel.choice_code(
            panel.motor_layout_choice, "single"
        )
        motor_pole_pairs = self._integer(
            panel.motor_pole_pairs, "motor_pole_pairs", focus
        )
        motor_array_radius = self._number(
            panel.motor_array_radius, "motor_array_radius", focus
        )
        motor_linear_pitch = self._number(
            panel.motor_linear_pitch, "motor_linear_pitch", focus
        )
        motor_array_angle = self._number(
            panel.motor_array_angle, "motor_array_angle", focus
        )
        motor_orientation = panel.choice_code(
            panel.motor_orientation_choice, "radial"
        )
        start_radius = self._number(
            panel.start_radius, "initial_radius", focus
        )
        turns = (
            self._number(panel.turns, "turns", focus)
            if sizing_mode != "fit_length"
            else self._optional_number(
                panel.turns,
                self.settings.get("turns", DEFAULTS["turns"]),
            )
        )
        arcs_per_turn = (
            self._integer(panel.arcs_per_turn, "arcs_per_turn", focus)
            if actual_primitive_mode == "arc"
            else self._optional_integer(
                panel.arcs_per_turn,
                self.settings.get(
                    "arcs_per_turn", DEFAULTS["arcs_per_turn"]
                ),
            )
        )
        segments_per_turn = (
            self._integer(
                panel.segments_per_turn, "segments_per_turn", focus
            )
            if actual_primitive_mode == "segment"
            else self._optional_integer(
                panel.segments_per_turn,
                self.settings.get(
                    "segments_per_turn", DEFAULTS["segments_per_turn"]
                ),
            )
        )
        additional_segments = self._integer(
            panel.additional_segments, "additional_segments", focus
        )
        if sizing_mode == "manual":
            track_width = self._number(
                panel.track_width, "track_width", focus
            )
            spacing = self._number(panel.spacing, "spacing", focus)
            available_diameter = self._optional_number(
                panel.available_diameter,
                self.compat.mm_to_user(self.settings.get(
                    "available_diameter_mm",
                    DEFAULTS["available_diameter_mm"],
                )),
            )
            target_length = self._optional_number(
                panel.target_length,
                self.compat.mm_to_user(self.settings.get(
                    "target_length_mm", DEFAULTS["target_length_mm"]
                )),
            )
            fill_ratio_percent = self._optional_number(
                panel.fill_ratio,
                self.settings.get("fill_ratio", DEFAULTS["fill_ratio"])
                * 100.0,
            )
            minimum_track_width = self._optional_number(
                panel.minimum_track_width,
                self.compat.mm_to_user(self.settings.get(
                    "minimum_track_width_mm",
                    DEFAULTS["minimum_track_width_mm"],
                )),
            )
            minimum_clearance = self._optional_number(
                panel.minimum_clearance,
                self.compat.mm_to_user(self.settings.get(
                    "minimum_clearance_mm",
                    DEFAULTS["minimum_clearance_mm"],
                )),
            )
        else:
            track_width = self._optional_number(
                panel.track_width,
                self.compat.mm_to_user(self.settings.get(
                    "track_width_mm", DEFAULTS["track_width_mm"]
                )),
            )
            spacing = self._optional_number(
                panel.spacing,
                self.compat.mm_to_user(self.settings.get(
                    "spacing_mm", DEFAULTS["spacing_mm"]
                )),
            )
            available_diameter = self._number(
                panel.available_diameter, "available_diameter", focus
            )
            target_length = (
                self._number(panel.target_length, "target_length", focus)
                if sizing_mode == "fit_length"
                else self._optional_number(
                    panel.target_length,
                    self.compat.mm_to_user(self.settings.get(
                        "target_length_mm", DEFAULTS["target_length_mm"]
                    )),
                )
            )
            fill_ratio_percent = self._number(
                panel.fill_ratio, "fill_ratio", focus
            )
            minimum_track_width = self._number(
                panel.minimum_track_width, "minimum_track_width", focus
            )
            minimum_clearance = self._number(
                panel.minimum_clearance, "minimum_clearance", focus
            )
        copper_thickness = self._number(
            panel.copper_thickness, "copper_thickness", focus
        )
        target_current = self._number(
            panel.target_current, "target_current", focus
        )
        target_torque = self._number(panel.target_torque, "target_torque", focus)
        target_force = self._number(
            panel.motor_target_force, "motor_target_force", focus
        )
        target_linear_speed = self._number(
            panel.motor_target_linear_speed,
            "motor_target_linear_speed", focus,
        )
        air_gap_flux_density = self._number(
            panel.air_gap_flux_density, "air_gap_flux_density", focus
        )
        electrical_loading = self._number(
            panel.electrical_loading, "electrical_loading", focus
        )
        winding_factor = self._number(
            panel.winding_factor, "winding_factor", focus
        )
        motor_inner_ratio = self._number(
            panel.motor_inner_ratio, "motor_inner_ratio", focus
        )
        motor_board_outer_diameter = self._number(
            panel.motor_board_outer_diameter,
            "motor_board_outer_diameter", focus,
        )
        motor_board_inner_diameter = self._number(
            panel.motor_board_inner_diameter,
            "motor_board_inner_diameter", focus,
        )
        motor_edge_clearance = self._number(
            panel.motor_edge_clearance, "motor_edge_clearance", focus
        )
        motor_slot_gap = self._number(
            panel.motor_slot_gap, "motor_slot_gap", focus
        )
        motor_supply_voltage = self._number(
            panel.motor_supply_voltage, "motor_supply_voltage", focus
        )
        motor_target_speed = self._number(
            panel.motor_target_speed, "motor_target_speed", focus
        )
        motor_max_phase_current = self._number(
            panel.motor_max_phase_current, "motor_max_phase_current", focus
        )
        allowed_temperature_rise = self._number(
            panel.allowed_temperature_rise, "allowed_temperature_rise", focus
        )
        target_resistance = self._number(
            panel.target_resistance, "target_resistance", focus
        )
        target_inductance = self._number(
            panel.target_inductance, "target_inductance", focus
        )
        motor_connection = panel.choice_code(
            panel.motor_connection_choice, "star"
        )
        motor_slot_count = self._integer(
            panel.motor_slot_count, "motor_slot_count", focus
        )
        motor_phase_count = self._integer(
            panel.motor_phase_count, "motor_phase_count", focus
        )
        angle = self._number(panel.angle_offset, "angle_offset", focus)
        layer_count = int(panel.choice_code(
            panel.layer_count_choice, 1
        ))
        if coil_shape == "motor_sector":
            available_diameter = motor_board_outer_diameter
            if motor_board_outer_diameter > 0.0:
                motor_inner_ratio = (
                    motor_board_inner_diameter / motor_board_outer_diameter
                )

        if layer_count > 1:
            via_diameter = self._number(
                panel.via_diameter, "via_diameter", focus
            )
            via_drill = self._number(panel.via_drill, "via_drill", focus)
            via_clearance = self._number(
                panel.via_clearance, "via_clearance", focus
            )
        else:
            via_diameter = self._optional_number(
                panel.via_diameter,
                self.compat.mm_to_user(self.settings["via_diameter_mm"]),
            )
            via_drill = self._optional_number(
                panel.via_drill,
                self.compat.mm_to_user(self.settings["via_drill_mm"]),
            )
            via_clearance = self._optional_number(
                panel.via_clearance,
                self.compat.mm_to_user(self.settings["via_clearance_mm"]),
            )

        if start_radius < 0:
            raise ValidationError(self.tr(
                "must_be_nonnegative", field=self.tr("initial_radius")
            ))
        if turns <= 0:
            raise ValidationError(self.tr(
                "must_be_positive", field=self.tr("turns")
            ))
        if shape_aspect_ratio < 1.0:
            raise ValidationError(self.tr(
                "must_be_at_least_one", field=self.tr("shape_aspect_ratio")
            ))
        if not -75.0 <= shape_taper_percent <= 75.0:
            raise ValidationError(self.tr(
                "shape_taper_out_of_range"
            ))
        if arcs_per_turn < 4:
            raise ValidationError(self.tr("arcs_per_turn_too_small"))
        if segments_per_turn < 4:
            raise ValidationError(self.tr("segments_too_small"))
        if additional_segments < 0:
            raise ValidationError(self.tr(
                "must_be_nonnegative", field=self.tr("additional_segments")
            ))
        if minimum_track_width < 0:
            raise ValidationError(self.tr(
                "must_be_nonnegative",
                field=self.tr("minimum_track_width"),
            ))
        if minimum_clearance < 0:
            raise ValidationError(self.tr(
                "must_be_nonnegative", field=self.tr("minimum_clearance")
            ))
        if copper_thickness <= 0:
            raise ValidationError(self.tr(
                "must_be_positive", field=self.tr("copper_thickness")
            ))
        if target_current < 0:
            raise ValidationError(self.tr(
                "must_be_nonnegative", field=self.tr("target_current")
            ))
        if (target_torque < 0 or target_force < 0
                or target_linear_speed < 0 or motor_slot_count < 0):
            raise ValidationError(self.tr("motor_engineering_invalid"))
        if (air_gap_flux_density <= 0 or electrical_loading <= 0
                or not 0 < winding_factor <= 1
                or not 0 < motor_inner_ratio < 1
                or motor_phase_count not in (1, 3)):
            raise ValidationError(self.tr("motor_engineering_invalid"))
        if coil_shape == "motor_sector" and (
                motor_board_outer_diameter <= 0.0
                or motor_board_inner_diameter < 0.0
                or motor_board_inner_diameter >= motor_board_outer_diameter
                or motor_edge_clearance < 0.0 or motor_slot_gap < 0.0):
            raise ValidationError(self.tr("motor_sector_invalid"))
        if coil_shape.startswith("motor_") and (
                motor_supply_voltage <= 0.0 or motor_target_speed < 0.0
                or motor_max_phase_current <= 0.0
                or allowed_temperature_rise <= 0.0
                or target_resistance < 0.0 or target_inductance < 0.0):
            raise ValidationError(self.tr("motor_engineering_invalid"))

        layer_index = panel.layer_choice.GetSelection()
        if layer_index < 0 or layer_index >= len(self.layers):
            raise ValidationError(self.tr("no_layer"))
        available_layers = len(self.layers) - layer_index
        if layer_count > available_layers:
            raise ValidationError(self.tr(
                "not_enough_layers",
                available=available_layers,
                requested=layer_count,
                start=str(self.board.GetLayerName(
                    self.layers[layer_index]
                )),
            ))
        selected_layers = self.layers[
            layer_index:layer_index + layer_count
        ]

        if layer_count > 1:
            if via_diameter <= 0:
                raise ValidationError(self.tr(
                    "must_be_positive", field=self.tr("via_diameter")
                ))
            if via_drill <= 0:
                raise ValidationError(self.tr(
                    "must_be_positive", field=self.tr("via_drill")
                ))
            if via_clearance < 0:
                raise ValidationError(self.tr(
                    "must_be_nonnegative", field=self.tr("via_clearance")
                ))
            if via_drill >= via_diameter:
                raise ValidationError(self.tr("via_drill_too_large"))

        spacing_mode = panel.choice_code(
            panel.spacing_mode_choice, "pitch"
        )
        if sizing_mode == "manual":
            if track_width <= 0:
                raise ValidationError(self.tr(
                    "must_be_positive", field=self.tr("track_width")
                ))
            if spacing < 0 or (
                    spacing_mode == "pitch" and spacing == 0):
                key = (
                    "must_be_nonnegative"
                    if spacing_mode == "clearance"
                    else "must_be_positive"
                )
                raise ValidationError(self.tr(
                    key, field=self.tr("spacing")
                ))
            if spacing_mode == "pitch" and spacing < track_width:
                raise ValidationError(self.tr(
                    "pitch_smaller_than_width"
                ))
        else:
            if available_diameter <= 0:
                raise ValidationError(self.tr(
                    "available_diameter_invalid"
                ))
            if not 0.0 < fill_ratio_percent < 100.0:
                raise ValidationError(self.tr("fill_ratio_invalid"))
            if sizing_mode == "fit_length" and target_length <= 0:
                raise ValidationError(self.tr("target_length_invalid"))

        solver_result = None
        try:
            if (coil_shape.startswith("motor_") and design_mode in (
                    "motor_target", "target_resistance",
                    "target_inductance", "target_current")):
                fixed = self._workflow.fixed_values()
                if "spacing_mm" in fixed:
                    spacing_value = float(fixed["spacing_mm"])
                    fixed["clearance_mm"] = (
                        max(0.0, spacing_value - float(fixed.get(
                            "track_width_mm",
                            self.compat.user_to_mm(track_width),
                        ))) if spacing_mode == "pitch" else spacing_value
                    )
                if coil_shape == "motor_sector":
                    solver_result = solve_motor_sector_design(
                        board_outer_diameter_mm=self.compat.user_to_mm(
                            motor_board_outer_diameter
                        ),
                        board_inner_diameter_mm=self.compat.user_to_mm(
                            motor_board_inner_diameter
                        ),
                        pole_pairs=motor_pole_pairs,
                        slot_count=motor_slot_count,
                        phase_count=motor_phase_count,
                        layer_count=layer_count,
                        supply_voltage_v=motor_supply_voltage,
                        target_speed_rpm=motor_target_speed,
                        target_torque_nm=target_torque,
                        max_phase_current_a=(
                            target_current if design_mode == "target_current"
                            and target_current > 0.0
                            else motor_max_phase_current
                        ),
                        copper_thickness_um=copper_thickness,
                        minimum_track_width_mm=self.compat.user_to_mm(
                            minimum_track_width
                        ),
                        minimum_clearance_mm=self.compat.user_to_mm(
                            minimum_clearance
                        ),
                        flux_density_t=air_gap_flux_density,
                        winding_factor=winding_factor,
                        connection=motor_connection,
                        edge_clearance_mm=self.compat.user_to_mm(
                            motor_edge_clearance
                        ),
                        slot_gap_mm=self.compat.user_to_mm(motor_slot_gap),
                        fill_ratio=fill_ratio_percent / 100.0,
                        target_resistance_ohm=(
                            target_resistance
                            if design_mode == "target_resistance" else 0.0
                        ),
                        target_inductance_uh=(
                            target_inductance
                            if design_mode == "target_inductance" else 0.0
                        ),
                        allowed_temperature_rise_c=allowed_temperature_rise,
                        fixed=fixed,
                    )
                else:
                    solver_result = solve_motor_spiral_design(
                        available_diameter_mm=self.compat.user_to_mm(
                            available_diameter
                        ),
                        start_radius_mm=self.compat.user_to_mm(start_radius),
                        coil_shape=coil_shape,
                        shape_aspect_ratio=shape_aspect_ratio,
                        shape_taper_ratio=shape_taper_percent / 100.0,
                        motor_layout=motor_layout,
                        pole_pairs=motor_pole_pairs,
                        slot_count=motor_slot_count,
                        phase_count=motor_phase_count,
                        motor_orientation=motor_orientation,
                        motor_array_radius_mm=self.compat.user_to_mm(
                            motor_array_radius
                        ),
                        motor_linear_pitch_mm=self.compat.user_to_mm(
                            motor_linear_pitch
                        ),
                        layer_count=layer_count,
                        supply_voltage_v=motor_supply_voltage,
                        target_speed_rpm=motor_target_speed,
                        target_torque_nm=target_torque,
                        max_phase_current_a=(
                            target_current if design_mode == "target_current"
                            and target_current > 0.0
                            else motor_max_phase_current
                        ),
                        copper_thickness_um=copper_thickness,
                        minimum_track_width_mm=self.compat.user_to_mm(
                            minimum_track_width
                        ),
                        minimum_clearance_mm=self.compat.user_to_mm(
                            minimum_clearance
                        ),
                        via_diameter_mm=self.compat.user_to_mm(via_diameter),
                        via_clearance_mm=self.compat.user_to_mm(via_clearance),
                        flux_density_t=air_gap_flux_density,
                        winding_factor=winding_factor,
                        connection=motor_connection,
                        fill_ratio=fill_ratio_percent / 100.0,
                        target_resistance_ohm=(
                            target_resistance
                            if design_mode == "target_resistance" else 0.0
                        ),
                        target_inductance_uh=(
                            target_inductance
                            if design_mode == "target_inductance" else 0.0
                        ),
                        allowed_temperature_rise_c=allowed_temperature_rise,
                        fixed=fixed,
                        target_force_n=target_force,
                        target_linear_speed_mps=target_linear_speed,
                    )
                if not solver_result["feasible"]:
                    raise GeometryError(
                        "motor_target_constraints_unmet",
                        required_voltage=solver_result[
                            "required_line_voltage_v"
                        ],
                        available_voltage=solver_result[
                            "available_line_voltage_rms_v"
                        ],
                        required_current=solver_result[
                            "required_phase_current_a"
                        ],
                        available_current=solver_result[
                            "effective_phase_current_limit_a"
                        ],
                    )
                resolved = dict(solver_result["resolved"])
                arrangement = dict(solver_result["arrangement"])
                for key in (
                        "track_width", "clearance", "pitch", "start_radius",
                        "outer_radius", "outer_diameter", "spiral_diameter",
                        "array_outer_diameter", "requested_array_diameter",
                        "length_per_layer", "total_spiral_length",
                        "motor_board_outer_diameter",
                        "motor_board_inner_diameter"):
                    if key in resolved:
                        resolved[key] = self.compat.mm_to_user(resolved[key])
                arrangement["array_radius"] = self.compat.mm_to_user(
                    arrangement["array_radius"]
                )
                arrangement["linear_pitch"] = self.compat.mm_to_user(
                    arrangement["linear_pitch"]
                )
                resolved["motor_target"] = solver_result
            elif coil_shape == "circular" and design_mode in (
                    "target_resistance", "target_inductance",
                    "target_current"):
                electrical_target = solve_spiral_electrical_design(
                    design_mode=design_mode,
                    available_diameter_mm=self.compat.user_to_mm(
                        available_diameter
                    ),
                    start_radius_mm=self.compat.user_to_mm(start_radius),
                    layer_count=layer_count,
                    copper_thickness_um=copper_thickness,
                    minimum_track_width_mm=self.compat.user_to_mm(
                        minimum_track_width
                    ),
                    minimum_clearance_mm=self.compat.user_to_mm(
                        minimum_clearance
                    ),
                    fill_ratio=fill_ratio_percent / 100.0,
                    target_resistance_ohm=target_resistance,
                    target_inductance_uh=target_inductance,
                    target_current_a=target_current,
                    allowed_temperature_rise_c=allowed_temperature_rise,
                    via_diameter_mm=self.compat.user_to_mm(via_diameter),
                    via_clearance_mm=self.compat.user_to_mm(via_clearance),
                    fixed=self._workflow.fixed_values(),
                )
                if not electrical_target["feasible"]:
                    raise GeometryError(
                        "electrical_target_constraints_unmet",
                        required_current=electrical_target["current_target_a"],
                        available_current=electrical_target[
                            "current_capacity_a"
                        ],
                    )
                resolved = dict(electrical_target["resolved"])
                for key in (
                        "track_width", "clearance", "pitch", "start_radius",
                        "outer_radius", "outer_diameter", "spiral_diameter",
                        "array_outer_diameter", "requested_array_diameter",
                        "length_per_layer", "total_spiral_length"):
                    if key in resolved:
                        resolved[key] = self.compat.mm_to_user(resolved[key])
                resolved["electrical_target"] = electrical_target
                arrangement = {
                    "layout": "single", "count": 1,
                    "array_radius": 0.0, "linear_pitch": 0.0,
                }
            else:
                resolved, arrangement = resolve_motor_spiral_parameters(
                    sizing_mode=sizing_mode,
                    start_radius=start_radius,
                    turns=turns,
                    track_width=track_width,
                    spacing=spacing,
                    spacing_mode=spacing_mode,
                    available_diameter=available_diameter,
                    target_length=target_length,
                    fill_ratio=fill_ratio_percent / 100.0,
                    layer_count=layer_count,
                    via_diameter=via_diameter,
                    via_clearance=via_clearance,
                    minimum_track_width=minimum_track_width,
                    minimum_clearance=minimum_clearance,
                    coil_shape=coil_shape,
                    shape_aspect_ratio=shape_aspect_ratio,
                    shape_taper_ratio=shape_taper_percent / 100.0,
                    motor_layout=motor_layout,
                    motor_pole_pairs=motor_pole_pairs,
                    motor_orientation=motor_orientation,
                    motor_array_radius=motor_array_radius,
                    motor_linear_pitch=motor_linear_pitch,
                    motor_slot_count=motor_slot_count,
                    motor_inner_ratio=motor_inner_ratio,
                    motor_edge_clearance=motor_edge_clearance,
                    motor_slot_gap=motor_slot_gap,
                )
        except GeometryError as error:
            raise ValidationError(self._geometry_error_message(error))

        turns = resolved["turns"]
        track_width = resolved["track_width"]
        start_radius = resolved["start_radius"]
        spacing = (
            resolved["pitch"]
            if spacing_mode == "pitch"
            else resolved["clearance"]
        )

        violation = manufacturing_violation(
            panel.choice_code(
                panel.manufacturing_preset_choice, "custom"
            ),
            self.compat.user_to_mm(resolved["track_width"]),
            self.compat.user_to_mm(resolved["clearance"]),
            layer_count,
            self.compat.user_to_mm(via_diameter),
            self.compat.user_to_mm(via_drill),
            self.compat.user_to_mm(via_clearance),
        )
        if violation is not None:
            raise ValidationError(
                self._manufacturing_error_message(violation)
            )

        resolved["electrical"] = estimate_dc_metrics(
            self.compat.user_to_mm(resolved["total_spiral_length"]),
            self.compat.user_to_mm(resolved["track_width"]),
            copper_thickness,
            target_current,
        )

        if layer_count > 1:
            if not float(turns).is_integer() or additional_segments != 0:
                raise ValidationError(self.tr(
                    "multilayer_integer_turns"
                ))
            if coil_shape != "motor_sector":
                required_radius = required_inner_radius(
                    layer_count, via_diameter, via_clearance, track_width
                ) / shape_endpoint_scale(
                    coil_shape, shape_aspect_ratio,
                    shape_taper_percent / 100.0,
                )
                if start_radius + 1e-9 < required_radius:
                    raise ValidationError(self.tr(
                        "inner_radius_too_small",
                        required=self.compat.format_number(required_radius),
                        unit=self.compat.unit_label(),
                    ))

        motor_count = arrangement["count"]
        resolved["motor_count"] = motor_count
        resolved["motor_layout"] = arrangement["layout"]
        resolved["motor_array_radius_mm"] = self.compat.user_to_mm(
            arrangement["array_radius"]
        )
        resolved["motor_linear_pitch_mm"] = self.compat.user_to_mm(
            arrangement["linear_pitch"]
        )
        if (arrangement["layout"] == "radial"
                and motor_orientation == "radial"):
            if coil_shape == "motor_sector":
                outer_radius_mm = self.compat.user_to_mm(
                    resolved["motor_board_outer_diameter"]
                ) / 2.0
                inner_radius_mm = self.compat.user_to_mm(
                    resolved["motor_board_inner_diameter"]
                ) / 2.0
            else:
                half_span_mm = self.compat.user_to_mm(
                    resolved["outer_diameter"]
                ) / 2.0
                outer_radius_mm = self.compat.user_to_mm(
                    arrangement["array_radius"]
                ) + half_span_mm
                inner_radius_mm = self.compat.user_to_mm(
                    arrangement["array_radius"]
                ) - half_span_mm
            if inner_radius_mm > 0.0:
                dfm = motor_inner_trace_dfm(
                    inner_radius_mm, motor_pole_pairs, turns,
                    self.compat.user_to_mm(resolved["track_width"]),
                    self.compat.user_to_mm(resolved["clearance"]),
                    outer_radius_mm,
                )
                resolved["motor_engineering"] = {
                    "outer_radius_mm": outer_radius_mm,
                    "inner_radius_mm": inner_radius_mm,
                    "inner_ratio": inner_radius_mm / outer_radius_mm,
                    "estimated_torque_nm": estimate_axial_flux_motor_torque(
                        outer_radius_mm, inner_radius_mm,
                        air_gap_flux_density, electrical_loading,
                        winding_factor,
                    ),
                    "dfm": dfm,
                    "phase_balanced": motor_count % motor_phase_count == 0,
                }
        resolved["total_spiral_length"] *= motor_count
        resolved["electrical"] = estimate_dc_metrics(
            self.compat.user_to_mm(resolved["total_spiral_length"]),
            self.compat.user_to_mm(resolved["track_width"]),
            copper_thickness, target_current,
        )
        actual_primitive_mode = self._actual_primitive_mode()
        primitives_per_turn = (
            arcs_per_turn
            if actual_primitive_mode == "arc"
            else segments_per_turn
        )
        count = motor_count * multilayer_track_count(
            turns,
            primitives_per_turn,
            additional_segments,
            layer_count,
        )
        limit = int(self.settings.get(
            "max_segments", DEFAULTS["max_segments"]
        ))
        if count > limit:
            raise ValidationError(self.tr(
                "too_many_segments", count=count, limit=limit
            ))

        angle_unit = panel.choice_code(
            panel.angle_unit_choice, "degrees"
        )
        angle_degrees = (
            angle if angle_unit == "degrees" else angle * 180.0 / pi
        )
        net_index = panel.net_choice.GetSelection()
        if net_index < 0 or net_index >= len(self.net_items):
            net_index = 0

        values = {
            "schema_version": DEFAULTS["schema_version"],
            "application_preset": panel.choice_code(
                panel.application_preset_choice, "custom"
            ),
            "manufacturing_preset": panel.choice_code(
                panel.manufacturing_preset_choice, "custom"
            ),
            "group_name": (
                panel.group_name.GetValue().strip()
                or DEFAULTS["group_name"]
            ),
            "net_name": self.net_items[net_index][0],
            "layer_name": str(self.board.GetLayerName(selected_layers[0])),
            "layer_count": layer_count,
            "center_x_mm": self.compat.user_to_mm(center_x),
            "center_y_mm": self.compat.user_to_mm(center_y),
            "start_radius_mm": self.compat.user_to_mm(start_radius),
            "turns": turns,
            "arcs_per_turn": arcs_per_turn,
            "segments_per_turn": segments_per_turn,
            "additional_segments": additional_segments,
            "primitive_mode": panel.choice_code(
                panel.primitive_mode_choice, "auto"
            ),
            "coil_shape": coil_shape,
            "shape_aspect_ratio": shape_aspect_ratio,
            "shape_taper_ratio": shape_taper_percent / 100.0,
            "motor_layout": arrangement["layout"],
            "motor_pole_pairs": motor_pole_pairs,
            "motor_slot_count": motor_slot_count,
            "motor_phase_count": motor_phase_count,
            "motor_array_radius_mm": arrangement["array_radius"],
            "motor_linear_pitch_mm": arrangement["linear_pitch"],
            "motor_array_angle_degrees": motor_array_angle,
            "motor_orientation": motor_orientation,
            "motor_alternate_winding": panel.motor_alternate_winding.GetValue(),
            "motor_parameters_auto": self._motor_parameters_auto,
            "quality_preset": panel.choice_code(
                panel.quality_preset_choice, "custom"
            ),
            "sizing_mode": sizing_mode,
            "design_mode": design_mode,
            "available_diameter_mm": self.compat.user_to_mm(
                available_diameter
            ),
            "target_length_mm": self.compat.user_to_mm(target_length),
            "fill_ratio": fill_ratio_percent / 100.0,
            "minimum_track_width_mm": self.compat.user_to_mm(
                minimum_track_width
            ),
            "minimum_clearance_mm": self.compat.user_to_mm(
                minimum_clearance
            ),
            "copper_thickness_um": copper_thickness,
            "target_current_a": target_current,
            "target_torque_nm": target_torque,
            "motor_target_force_n": target_force,
            "motor_target_linear_speed_mps": target_linear_speed,
            "air_gap_flux_density_t": air_gap_flux_density,
            "electrical_loading_a_per_m": electrical_loading,
            "winding_factor": winding_factor,
            "motor_inner_ratio": motor_inner_ratio,
            "motor_board_outer_diameter_mm": self.compat.user_to_mm(
                resolved.get("motor_board_outer_diameter", available_diameter)
            ),
            "motor_board_inner_diameter_mm": self.compat.user_to_mm(
                resolved.get(
                    "motor_board_inner_diameter",
                    available_diameter * motor_inner_ratio,
                )
            ),
            "motor_edge_clearance_mm": self.compat.user_to_mm(
                motor_edge_clearance
            ),
            "motor_slot_gap_mm": self.compat.user_to_mm(motor_slot_gap),
            "motor_supply_voltage_v": motor_supply_voltage,
            "motor_target_speed_rpm": motor_target_speed,
            "motor_max_phase_current_a": motor_max_phase_current,
            "allowed_temperature_rise_c": allowed_temperature_rise,
            "motor_connection": motor_connection,
            "target_resistance_ohm": target_resistance,
            "target_inductance_uh": target_inductance,
            "show_advanced_parameters": panel.show_advanced_parameters.GetValue(),
            "track_width_mm": self.compat.user_to_mm(track_width),
            "spacing_mm": self.compat.user_to_mm(spacing),
            "via_diameter_mm": self.compat.user_to_mm(via_diameter),
            "via_drill_mm": self.compat.user_to_mm(via_drill),
            "via_clearance_mm": self.compat.user_to_mm(via_clearance),
            "spacing_mode": spacing_mode,
            "angle_degrees": angle_degrees,
            "angle_unit": angle_unit,
            "direction": panel.choice_code(
                panel.direction_choice, "clockwise"
            ),
            "create_group": panel.create_group.GetValue(),
            "close_after_create": panel.close_after_create.GetValue(),
            "max_segments": limit,
        }
        return (
            values,
            count,
            net_index,
            selected_layers,
            resolved,
            actual_primitive_mode,
        )

    def _preview_length_value(self, control, setting_key):
        try:
            return self.compat.user_to_mm(float(control.GetValue()))
        except (TypeError, ValueError):
            return self.settings.get(setting_key, DEFAULTS[setting_key])

    def _draft_preview_values(self):
        panel = self.panel
        angle_degrees = self.settings.get(
            "angle_degrees", DEFAULTS["angle_degrees"]
        )
        try:
            angle_value = float(panel.angle_offset.GetValue())
            angle_degrees = (
                angle_value
                if panel.choice_code(panel.angle_unit_choice, "degrees")
                == "degrees"
                else angle_value * 180.0 / pi
            )
        except (TypeError, ValueError):
            pass
        try:
            taper_ratio = float(panel.shape_taper.GetValue()) / 100.0
        except (TypeError, ValueError):
            taper_ratio = self.settings.get(
                "shape_taper_ratio", DEFAULTS["shape_taper_ratio"]
            )
        draft = dict(self.settings)
        draft.update({
            "start_radius_mm": self._preview_length_value(
                panel.start_radius, "start_radius_mm"
            ),
            "turns": panel.turns.GetValue(),
            "track_width_mm": self._preview_length_value(
                panel.track_width, "track_width_mm"
            ),
            "spacing_mm": self._preview_length_value(
                panel.spacing, "spacing_mm"
            ),
            "spacing_mode": panel.choice_code(
                panel.spacing_mode_choice, "pitch"
            ),
            "segments_per_turn": panel.segments_per_turn.GetValue(),
            "additional_segments": panel.additional_segments.GetValue(),
            "coil_shape": panel.choice_code(
                panel.coil_shape_choice, "circular"
            ),
            "shape_aspect_ratio": panel.shape_aspect_ratio.GetValue(),
            "shape_taper_ratio": taper_ratio,
            "motor_layout": panel.choice_code(
                panel.motor_layout_choice, "single"
            ),
            "motor_pole_pairs": panel.motor_pole_pairs.GetValue(),
            "motor_slot_count": panel.motor_slot_count.GetValue(),
            "motor_phase_count": panel.motor_phase_count.GetValue(),
            "motor_array_radius_mm": self._preview_length_value(
                panel.motor_array_radius, "motor_array_radius_mm"
            ),
            "motor_linear_pitch_mm": self._preview_length_value(
                panel.motor_linear_pitch, "motor_linear_pitch_mm"
            ),
            "motor_array_angle_degrees": panel.motor_array_angle.GetValue(),
            "motor_orientation": panel.choice_code(
                panel.motor_orientation_choice, "radial"
            ),
            "motor_alternate_winding": panel.motor_alternate_winding.GetValue(),
            "motor_target_force_n": panel.motor_target_force.GetValue(),
            "motor_target_linear_speed_mps": (
                panel.motor_target_linear_speed.GetValue()
            ),
            "angle_degrees": angle_degrees,
            "direction": panel.choice_code(
                panel.direction_choice, "clockwise"
            ),
            "layer_count": panel.choice_code(
                panel.layer_count_choice, 1
            ),
            "via_diameter_mm": self._preview_length_value(
                panel.via_diameter, "via_diameter_mm"
            ),
            "via_clearance_mm": self._preview_length_value(
                panel.via_clearance, "via_clearance_mm"
            ),
        })
        return coerce_preview_values(draft, self.settings)

    def _schedule_preview(self, delay_ms=60):
        if self._applying_preset:
            return
        if self._preview_timer is not None:
            try:
                self._preview_timer.Stop()
            except Exception:
                pass
        self._preview_timer = wx.CallLater(
            int(delay_ms), self._run_scheduled_preview
        )

    def _run_scheduled_preview(self):
        self._preview_timer = None
        if not self._closing:
            self._update_preview()

    def _update_preview(self):
        preview_scene = build_safe_preview_scene(
            self._draft_preview_values()
        )
        resolved = {}
        layer_count = int(self.panel.choice_code(
            self.panel.layer_count_choice, 1
        ))
        actual_mode = self._actual_primitive_mode()
        primitive_label = self.tr(
            "primitive_label_arcs"
            if actual_mode == "arc"
            else "primitive_label_segments"
        )
        try:
            (_values, count, _net_index, _layers,
             resolved, _actual_mode) = self._read_form(preview=True)
            fmt = self.compat.format_number
            unit = self.compat.unit_label()
            key = (
                "resolved_manual"
                if self.panel.choice_code(
                    self.panel.sizing_mode_choice, "manual"
                ) == "manual"
                else "resolved_auto"
            )
            summary = self.tr(
                key,
                turns=fmt(resolved["turns"]),
                width=fmt(resolved["track_width"]),
                clearance=fmt(resolved["clearance"]),
                diameter=fmt(resolved.get(
                    "array_outer_diameter", resolved["outer_diameter"]
                )),
                length=fmt(resolved["total_spiral_length"]),
                unit=unit,
            )
            electrical = resolved["electrical"]
            electrical_summary = self.tr(
                "electrical_estimate",
                resistance=fmt(electrical["resistance_ohm"]),
                current=fmt(_values["target_current_a"]),
                voltage=fmt(electrical["voltage_drop_v"]),
                power=fmt(electrical["power_w"]),
            )
            motor_target = resolved.get("motor_target")
            if motor_target:
                electrical_summary = self.tr(
                    "motor_target_estimate",
                    turns=fmt(motor_target["turns_per_slot"]),
                    emf=fmt(motor_target["back_emf_line_v"]),
                    voltage=fmt(motor_target["required_line_voltage_v"]),
                    available_voltage=fmt(
                        motor_target["available_line_voltage_rms_v"]
                    ),
                    current=fmt(motor_target["required_phase_current_a"]),
                    available_current=fmt(
                        motor_target["effective_phase_current_limit_a"]
                    ),
                    resistance=fmt(motor_target["phase_resistance_ohm"]),
                    hot_resistance=fmt(
                        motor_target["phase_resistance_hot_ohm"]
                    ),
                    inductance=fmt(motor_target["phase_inductance_uh"]),
                    loss=fmt(motor_target["copper_loss_w"]),
                )
            engineering = resolved.get("motor_engineering")
            if engineering:
                dfm = engineering["dfm"]
                ratio_ok = 0.55 <= engineering["inner_ratio"] <= 0.62
                status = self.tr(
                    "motor_engineering_ok"
                    if dfm["passes"] and ratio_ok
                    and engineering["phase_balanced"]
                    else "motor_engineering_warning"
                )
                electrical_summary += "\n" + self.tr(
                    "motor_engineering_estimate",
                    outer=fmt(2.0 * engineering["outer_radius_mm"]),
                    inner=fmt(2.0 * engineering["inner_radius_mm"]),
                    ratio=fmt(engineering["inner_ratio"]),
                    torque=fmt(engineering["estimated_torque_nm"]),
                    usage=fmt(dfm["utilization"] * 100.0),
                    max_turns=dfm["maximum_turns_per_layer"],
                    outer_width=fmt(dfm["recommended_outer_width_mm"]),
                    unit="mm", status=status,
                )
            if _values["application_preset"] != "custom":
                self._applying_recommendation = True
                try:
                    self._apply_resolved_to_controls(_values)
                finally:
                    self._applying_recommendation = False
            preview_scene = build_preview_scene(_values)
            self.panel.set_validation_feedback(
                self.tr("validation_ready"), True
            )
        except (ValidationError, GeometryError, ValueError, TypeError) as error:
            count = "—"
            summary = "—"
            electrical_summary = self.tr("electrical_unavailable")
            self.panel.set_validation_feedback(
                self.tr("validation_issue", error=self._error_message(error)),
                False,
            )
        self.panel.set_segment_estimate(
            count,
            layer_count=layer_count,
            via_count=max(0, layer_count - 1) * int(
                resolved.get("motor_count", 1)
            ),
            primitive_label=primitive_label,
        )
        self.panel.set_resolved_summary(summary)
        self.panel.set_electrical_summary(electrical_summary)
        self.panel.set_preview_scene(preview_scene)

    def _apply_resolved_to_controls(self, values):
        if values["sizing_mode"] == "manual":
            return
        panel = self.panel
        fmt = self.compat.format_number
        to_user = self.compat.mm_to_user
        panel.start_radius.SetValue(fmt(to_user(values["start_radius_mm"])))
        panel.turns.SetValue(fmt(values["turns"]))
        panel.shape_aspect_ratio.SetValue(fmt(values["shape_aspect_ratio"]))
        panel.shape_taper.SetValue(fmt(values["shape_taper_ratio"] * 100.0))
        panel.track_width.SetValue(fmt(to_user(values["track_width_mm"])))
        panel.spacing.SetValue(fmt(to_user(values["spacing_mm"])))

    def _on_preset_selection_changed(self, event):
        if not self._applying_preset:
            application = self.panel.choice_code(
                self.panel.application_preset_choice, "custom"
            )
            manufacturing = self.panel.choice_code(
                self.panel.manufacturing_preset_choice, "custom"
            )
            if event.GetEventObject() is self.panel.application_preset_choice:
                self._motor_parameters_auto = True
                self.settings["motor_parameters_auto"] = True
                values = build_preset_values(application, manufacturing)
            else:
                values = {
                    "application_preset": application,
                    "manufacturing_preset": manufacturing,
                }
                values.update(MANUFACTURING_PRESETS.get(manufacturing, {}))
            self._apply_preset_values(values)
        event.Skip()

    def _on_geometry_changed(self, event):
        if self._applying_preset or self._applying_recommendation:
            event.Skip()
            return
        control = event.GetEventObject()
        if not self._applying_preset and not self._applying_recommendation:
            controlled = {
                self.panel.start_radius: ("start_radius_mm", "initial_radius"),
                self.panel.shape_aspect_ratio: (
                    "shape_aspect_ratio", "shape_aspect_ratio"
                ),
                self.panel.shape_taper: (
                    "shape_taper_ratio", "shape_taper_percent"
                ),
                self.panel.fill_ratio: ("fill_ratio", "fill_ratio"),
                self.panel.additional_segments: (
                    "additional_segments", "additional_segments"
                ),
                self.panel.motor_array_radius: (
                    "motor_array_radius_mm", "motor_array_radius"
                ),
                self.panel.motor_linear_pitch: (
                    "motor_linear_pitch_mm", "motor_linear_pitch"
                ),
            }
            if control in controlled:
                key, field_key = controlled[control]
                self._mark_motor_parameters_manual(key, field_key)
            elif (
                    not self._application_is_custom()
                    and control in (
                        self.panel.copper_thickness,
                        self.panel.target_current,
                    )):
                self._apply_application_fill_recommendation()
                if self._motor_shape_active():
                    self._refresh_motor_recommendation(apply=True)
            elif (
                    self._motor_shape_active()
                    and not self._application_is_custom()
                    and control in (
                        self.panel.track_width,
                        self.panel.minimum_track_width,
                        self.panel.minimum_clearance,
                        self.panel.via_diameter,
                        self.panel.via_clearance,
                    )):
                self._refresh_motor_recommendation(apply=True)
        self._schedule_preview(60)
        event.Skip()

    def _on_preview_choice_changed(self, event):
        if not self._applying_preset and not self._applying_recommendation:
            controlled = {
                self.panel.motor_orientation_choice: (
                    "motor_orientation", "motor_orientation"
                ),
                self.panel.motor_alternate_winding: (
                    "motor_alternate_winding", "motor_alternate_winding"
                ),
            }
            control = event.GetEventObject()
            if control in controlled:
                key, field_key = controlled[control]
                self._mark_motor_parameters_manual(key, field_key)
        if not self._applying_preset:
            if self._preview_timer is not None:
                try:
                    self._preview_timer.Stop()
                except Exception:
                    pass
                self._preview_timer = None
            self._update_preview()
        event.Skip()

    def _on_layer_configuration_changed(self, event):
        if not self._applying_preset:
            self._update_layer_summary()
            self._refresh_motor_recommendation(
                apply=(self._motor_parameters_auto
                       or not self._application_is_custom()),
                update_preview=True
            )
        event.Skip()

    def _on_sizing_mode_changed(self, event):
        mode = self.panel.choice_code(
            self.panel.sizing_mode_choice, "manual"
        )
        self.panel.set_sizing_mode(mode)
        self._update_preview()
        event.Skip()

    def _on_coil_shape_changed(self, event):
        shape = self.panel.choice_code(
            self.panel.coil_shape_choice, "circular"
        )
        self.panel.set_coil_shape(shape)
        self._refresh_motor_recommendation(
            apply=(self._motor_parameters_auto
                       or not self._application_is_custom()),
                update_preview=True
        )
        event.Skip()

    def _on_motor_layout_changed(self, event):
        shape = self.panel.choice_code(
            self.panel.coil_shape_choice, "circular"
        )
        layout = self.panel.choice_code(
            self.panel.motor_layout_choice, "single"
        )
        self.panel.set_motor_layout(shape, layout)
        self._refresh_motor_recommendation(
            apply=(self._motor_parameters_auto
                       or not self._application_is_custom()),
                update_preview=True
        )
        event.Skip()

    def _on_primitive_mode_changed(self, event):
        mode = self.panel.choice_code(
            self.panel.primitive_mode_choice, "auto"
        )
        self.panel.set_primitive_mode(
            mode, self.compat.supports_arcs()
        )
        self._update_preview()
        event.Skip()

    def _on_quality_changed(self, event):
        preset = self.panel.choice_code(
            self.panel.quality_preset_choice, "custom"
        )
        values = QUALITY_PRESETS.get(preset)
        if values is not None:
            arcs_per_turn, segments_per_turn = values
            self.panel.arcs_per_turn.SetValue(str(arcs_per_turn))
            self.panel.segments_per_turn.SetValue(str(segments_per_turn))
        if not self._applying_preset and not self._applying_recommendation:
            self._mark_motor_parameters_manual(
                "quality_preset", "quality_preset"
            )
        self._update_preview()
        event.Skip()

    def _on_spacing_mode_changed(self, event):
        mode = self.panel.choice_code(
            self.panel.spacing_mode_choice, "pitch"
        )
        key = (
            "tooltip_spacing_clearance"
            if mode == "clearance"
            else "tooltip_spacing_pitch"
        )
        self.panel.spacing.SetToolTip(self.tr(key))
        if not self._applying_preset and not self._applying_recommendation:
            self._mark_motor_parameters_manual(
                "spacing_mode", "spacing_mode"
            )
        self._update_preview()
        event.Skip()

    def _on_angle_unit_changed(self, event):
        new_unit = self.panel.choice_code(
            self.panel.angle_unit_choice, "degrees"
        )
        try:
            value = float(self.panel.angle_offset.GetValue())
            if (
                    self.current_angle_unit == "degrees"
                    and new_unit == "radians"):
                value = value * pi / 180.0
            elif (
                    self.current_angle_unit == "radians"
                    and new_unit == "degrees"):
                value = value * 180.0 / pi
            self.panel.angle_offset.SetValue(
                self.compat.format_number(value)
            )
        except ValueError:
            pass
        self.current_angle_unit = new_unit
        event.Skip()

    def _on_selection_center(self, _event):
        center = self.compat.selected_center(self.board)
        if center is None:
            wx.MessageBox(
                self.tr("selection_not_found"),
                self.window_title,
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        self._set_center(center)

    def _on_reset(self, _event):
        values = dict(DEFAULTS)
        self.settings = values
        self._apply_settings(values)
        self._populate_board_choices()
        self._update_preview()

    def _on_create(self, _event):
        try:
            (values, count, net_index, selected_layers,
             _resolved, primitive_mode) = self._read_form()
        except ValidationError as error:
            wx.MessageBox(
                str(error),
                self.window_title,
                wx.OK | wx.ICON_WARNING,
            )
            return

        self._apply_resolved_to_controls(values)
        panel = self.panel
        panel.create_button.Disable()
        busy = wx.BusyCursor()
        items = []
        group = None
        group_unsupported = False
        layer_count = len(selected_layers)
        via_count = max(0, layer_count - 1)
        try:
            center_x = self.compat.from_mm(values["center_x_mm"])
            center_y = self.compat.from_mm(values["center_y_mm"])
            start_radius = self.compat.from_mm(
                values["start_radius_mm"]
            )
            width = self.compat.from_mm(values["track_width_mm"])
            spacing = self.compat.from_mm(values["spacing_mm"])
            via_diameter = self.compat.from_mm(
                values["via_diameter_mm"]
            )
            via_drill = self.compat.from_mm(values["via_drill_mm"])
            via_clearance = self.compat.from_mm(
                values["via_clearance_mm"]
            )
            radial_pitch = (
                width + spacing
                if values["spacing_mode"] == "clearance"
                else spacing
            )
            angle_radians = values["angle_degrees"] * pi / 180.0
            base_counterclockwise = (
                values["direction"] == "counterclockwise"
            )
            net_item = self.net_items[net_index][1]

            add_to_board = self.board.Add
            new_track = self.compat.new_track
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
                    self.compat.from_mm(board_outer_mm),
                    self.compat.from_mm(board_inner_mm), slot_count, width,
                    radial_pitch - width,
                    self.compat.from_mm(values.get("motor_edge_clearance_mm", 1.0)),
                    self.compat.from_mm(values.get("motor_slot_gap_mm", 1.0)),
                )
                instances = []
                start_angle = values.get(
                    "motor_array_angle_degrees", 0.0
                ) * pi / 180.0
                from math import cos, sin
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
                    self.compat.from_mm(values.get("motor_array_radius_mm", 0.0)),
                    self.compat.from_mm(values.get("motor_linear_pitch_mm", 0.0)),
                    values.get("motor_array_angle_degrees", 0.0) * pi / 180.0,
                    values.get("motor_orientation", "radial"),
                    values.get("motor_alternate_winding", True),
                    values.get("motor_slot_count", 0),
                )
            sector_connection_layout = None
            if (values.get("coil_shape") == "motor_sector"
                    and layer_count > 1):
                local_paths = []
                for layer_offset in range(layer_count):
                    local_counterclockwise = (
                        base_counterclockwise
                        if layer_offset % 2 == 0
                        else not base_counterclockwise
                    )
                    local_segments = list(iter_motor_sector_spiral_segments(
                        0, 0, self.compat.from_mm(board_outer_mm),
                        self.compat.from_mm(board_inner_mm), slot_count, width,
                        radial_pitch - width, values["turns"],
                        values["segments_per_turn"],
                        values["additional_segments"],
                        self.compat.from_mm(values.get(
                            "motor_edge_clearance_mm", 1.0
                        )),
                        self.compat.from_mm(values.get(
                            "motor_slot_gap_mm", 1.0
                        )),
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
                    self.compat.from_mm(values.get(
                        "motor_edge_clearance_mm", 1.0
                    )),
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
                        primitive_iterator = iter_spiral_arcs(
                            center_x,
                            center_y,
                            start_radius,
                            radial_pitch,
                            values["turns"],
                            values["arcs_per_turn"],
                            values["additional_segments"],
                            angle_radians,
                            counterclockwise,
                        )
                        for start, midpoint, end in primitive_iterator:
                            maximum_centerline_radius = max(
                                maximum_centerline_radius,
                                hypot(start[0] - center_x, start[1] - center_y),
                                hypot(midpoint[0] - center_x, midpoint[1] - center_y),
                                hypot(end[0] - center_x, end[1] - center_y),
                            )
                            if first_point is None:
                                first_point = start
                            last_point = end
                            try:
                                item = self.compat.new_arc(
                                    self.board,
                                    start,
                                    midpoint,
                                    end,
                                    width,
                                    net_item,
                                    layer,
                                )
                            except (TypeError, RuntimeError):
                                item = new_track(
                                    self.board,
                                    start,
                                    end,
                                    width,
                                    net_item,
                                    layer,
                                )
                            add_to_board(item)
                            items.append(item)
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
                            primitive_iterator = iter_motor_sector_spiral_segments(
                                center_x, center_y,
                                self.compat.from_mm(board_outer_mm),
                                self.compat.from_mm(board_inner_mm), slot_count,
                                width, radial_pitch - width, values["turns"],
                                values["segments_per_turn"],
                                values["additional_segments"],
                                self.compat.from_mm(values.get(
                                    "motor_edge_clearance_mm", 1.0
                                )),
                                self.compat.from_mm(values.get(
                                    "motor_slot_gap_mm", 1.0
                                )),
                                angle_radians, counterclockwise,
                            )
                        else:
                            primitive_iterator = iter_shaped_spiral_segments(
                                center_x,
                                center_y,
                                start_radius,
                                radial_pitch,
                                values["turns"],
                                values["segments_per_turn"],
                                values["additional_segments"],
                                angle_radians,
                                counterclockwise,
                                values.get("coil_shape", "circular"),
                                values.get("shape_aspect_ratio", 1.0),
                                values.get("shape_taper_ratio", 0.0),
                            )
                        for start, end in primitive_iterator:
                            maximum_centerline_radius = max(
                                maximum_centerline_radius,
                                hypot(start[0] - center_x, start[1] - center_y),
                                hypot(end[0] - center_x, end[1] - center_y),
                            )
                            if first_point is None:
                                first_point = start
                            last_point = end
                            item = new_track(
                                self.board,
                                start,
                                end,
                                width,
                                net_item,
                                layer,
                            )
                            add_to_board(item)
                            items.append(item)
                    endpoints.append((first_point, last_point))

                if layer_count > 1:
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
                            (center_x, center_y),
                            endpoints[0][0],
                            endpoints[0][1],
                            outer_radius,
                            layer_count,
                            via_diameter,
                            via_clearance,
                            width,
                        )
                    via_positions = connection_layout["via_points"]
                    for transition in range(layer_count - 1):
                        endpoint_index = connector_endpoint_index(transition)
                        via_position = via_positions[transition]
                        for layer_offset in (transition, transition + 1):
                            connector = new_track(
                                self.board,
                                endpoints[layer_offset][endpoint_index],
                                via_position,
                                width,
                                net_item,
                                selected_layers[layer_offset],
                            )
                            add_to_board(connector)
                            items.append(connector)
                        via_layer_pair = None
                        if values.get("coil_shape") != "motor_sector":
                            via_layer_pair = (
                                selected_layers[transition],
                                selected_layers[transition + 1],
                            )
                        via = self.compat.new_via(
                            self.board,
                            via_position,
                            via_diameter,
                            via_drill,
                            net_item,
                            via_layer_pair,
                        )
                        add_to_board(via)
                        items.append(via)
                    for layer_offset, endpoint_index, terminal_point in (
                            connection_layout["terminal_routes"]):
                        lead = new_track(
                            self.board,
                            endpoints[layer_offset][endpoint_index],
                            terminal_point,
                            width,
                            net_item,
                            selected_layers[layer_offset],
                        )
                        add_to_board(lead)
                        items.append(lead)

            if values["create_group"]:
                group = self.compat.add_group(
                    self.board, items, values["group_name"]
                )
                group_unsupported = group is None

            self.compat.refresh()
        except Exception as error:
            if group is not None:
                try:
                    self.compat.remove_item(self.board, group)
                except Exception:
                    pass
            for item in reversed(items):
                try:
                    self.compat.remove_item(self.board, item)
                except Exception:
                    pass
            self.compat.refresh()
            wx.MessageBox(
                self.tr("create_failed", error=self._error_message(error)),
                self.window_title,
                wx.OK | wx.ICON_ERROR,
            )
            return
        finally:
            del busy
            panel.create_button.Enable()

        settings_error = None
        try:
            self.store.save(values)
            self.settings = values
        except Exception as error:
            settings_error = error

        primitive_label = self.tr(
            "primitive_label_arcs"
            if primitive_mode == "arc"
            else "primitive_label_segments"
        )
        if layer_count > 1:
            message = self.tr(
                "success_generated_multilayer",
                layers=layer_count,
                count=count,
                vias=via_count,
                primitive=primitive_label,
            )
        else:
            message = self.tr(
                "success_generated",
                count=count,
                primitive=primitive_label,
            )
        if group_unsupported:
            message += "\n\n" + self.tr("group_unsupported")
        if settings_error is not None:
            message += "\n\n" + self.tr(
                "settings_failed", error=settings_error
            )
        wx.MessageBox(
            message,
            self.window_title,
            wx.OK | wx.ICON_INFORMATION,
        )
        self._update_preview()
        if values["close_after_create"]:
            self.Close()

    def _destroy_dialog(self):
        if self._closing:
            return
        self._closing = True
        if self._preview_timer is not None:
            try:
                self._preview_timer.Stop()
            except Exception:
                pass
            self._preview_timer = None
        callback = self.on_destroy_callback
        self.on_destroy_callback = None
        try:
            if callback:
                callback(self)
        finally:
            self.Destroy()

    def _on_cancel(self, _event):
        self._destroy_dialog()

    def _on_close(self, _event):
        self._destroy_dialog()


class SpiralPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        translator = Translator(detect_language(
            pcbnew_module=pcbnew, wx_module=wx
        ))
        self.name = translator("plugin_name", version=PLUGIN_VERSION)
        self.category = translator("plugin_category")
        self.description = translator(
            "plugin_description", version=PLUGIN_VERSION
        )
        self.icon_file_name = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "assets", "coilforge.png"
        )
        self.show_toolbar_button = True
        self._dialog = None

    def _dialog_closed(self, dialog):
        if self._dialog is dialog:
            self._dialog = None

    def Run(self):
        if self._dialog is not None:
            try:
                if self._dialog.IsShown():
                    self._dialog.Raise()
                    return
            except RuntimeError:
                self._dialog = None

        compat = KiCadCompat(pcbnew)
        board = compat.get_board()
        translator = Translator(detect_language(
            pcbnew_module=pcbnew, wx_module=wx
        ))
        if board is None:
            wx.MessageBox(
                translator("no_board"),
                translator("window_title", version=PLUGIN_VERSION),
                wx.OK | wx.ICON_WARNING,
            )
            return
        try:
            dialog = SpiralDialog(
                None, board, on_destroy=self._dialog_closed
            )
        except Exception as error:
            wx.MessageBox(
                translator(
                    "legacy_start_failed",
                    error=localize_error(translator, error),
                ),
                translator("window_title", version=PLUGIN_VERSION),
                wx.OK | wx.ICON_ERROR,
            )
            return
        self._dialog = dialog
        dialog.Show()
