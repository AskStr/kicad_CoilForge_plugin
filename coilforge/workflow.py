# -*- coding: utf-8 -*-
"""Shared guided-workflow locking and conditional parameter visibility."""


STEP_FIELDS = (
    (
        "application_preset", "target_current_a", "target_torque_nm",
        "motor_target_force_n", "motor_target_linear_speed_mps",
        "motor_supply_voltage_v", "motor_target_speed_rpm",
        "motor_max_phase_current_a", "allowed_temperature_rise_c",
        "motor_connection", "design_mode",
    ),
    (
        "manufacturing_preset", "copper_thickness_um",
        "minimum_track_width_mm", "minimum_clearance_mm",
    ),
    (
        "available_diameter_mm", "motor_board_outer_diameter_mm",
        "motor_board_inner_diameter_mm", "turns", "target_length_mm",
        "target_resistance_ohm", "target_inductance_uh",
        "fill_ratio", "start_radius_mm", "track_width_mm",
        "spacing_mm", "spacing_mode",
    ),
    (
        "coil_shape", "shape_aspect_ratio", "shape_taper_ratio",
        "angle_degrees", "direction",
    ),
    (
        "motor_layout", "motor_pole_pairs", "motor_slot_count",
        "motor_phase_count", "motor_edge_clearance_mm",
        "motor_slot_gap_mm", "motor_array_radius_mm",
        "motor_linear_pitch_mm", "motor_array_angle_degrees",
        "motor_orientation", "motor_alternate_winding",
    ),
    (
        "net_name", "layer_name", "layer_count", "via_diameter_mm",
        "via_drill_mm", "via_clearance_mm",
    ),
    (
        "group_name", "quality_preset", "primitive_mode",
        "arcs_per_turn", "segments_per_turn", "additional_segments",
        "center_x_mm", "center_y_mm",
        "create_group", "close_after_create",
    ),
)


WORKFLOW_PAGE_KEYS = (
    "section_quick_setup", "section_board", "section_sizing",
    "section_geometry", "section_placement", "section_multilayer",
    "section_options",
)

WORKFLOW_PAGE_FIELDS = dict(zip(WORKFLOW_PAGE_KEYS, STEP_FIELDS))


def workflow_page_keys(values, show_advanced=False):
    """Return the shortest useful page sequence for the active scenario."""
    values = dict(values or {})
    application = values.get("application_preset", "custom")
    shape = values.get("coil_shape", "circular")
    motor = shape.startswith("motor_") or application.startswith("motor_")
    advanced = bool(
        show_advanced or values.get("show_advanced_parameters", False)
    )
    pages = [
        "section_quick_setup", "section_board", "section_sizing",
    ]
    if application == "custom" or advanced:
        pages.append("section_geometry")
    if motor:
        pages.append("section_placement")
    pages.extend(("section_multilayer", "section_options"))
    return tuple(pages)


def workflow_step_fields(values, show_advanced=False):
    """Return visible lock fields aligned with the active page sequence.

    Hidden controls must never become solver constraints. In particular,
    electrical-target workflows hide manual turns/width values; locking those
    stale settings would silently disable the electrical optimizer.
    """
    visible = parameter_visibility(values, show_advanced)
    return tuple(
        tuple(
            field for field in WORKFLOW_PAGE_FIELDS[key]
            if field in visible
        )
        for key in workflow_page_keys(values, show_advanced)
    )


class WorkflowLocks(object):
    """Snapshot completed steps and protect them from later optimization."""

    def __init__(self, step_fields=STEP_FIELDS):
        self.step_fields = tuple(tuple(fields) for fields in step_fields)
        self._snapshots = {}

    @property
    def locked_through(self):
        return max(self._snapshots) if self._snapshots else -1

    def lock_step(self, step_index, values):
        index = int(step_index)
        if index < 0 or index >= len(self.step_fields):
            raise IndexError("workflow_step")
        self.unlock_from(index + 1)
        self._snapshots[index] = {
            key: values[key] for key in self.step_fields[index] if key in values
        }

    def unlock_from(self, step_index):
        index = int(step_index)
        for key in tuple(self._snapshots):
            if key >= index:
                del self._snapshots[key]

    def fixed_values(self):
        fixed = {}
        for index in sorted(self._snapshots):
            fixed.update(self._snapshots[index])
        return fixed

    def conflicts(self, candidate, tolerance=1e-9):
        conflicts = []
        for step_index in sorted(self._snapshots):
            for key, locked_value in self._snapshots[step_index].items():
                if key not in candidate:
                    continue
                suggested = candidate[key]
                if isinstance(locked_value, (int, float)) and isinstance(
                        suggested, (int, float)):
                    equal = abs(float(locked_value) - float(suggested)) <= tolerance
                else:
                    equal = locked_value == suggested
                if not equal:
                    conflicts.append({
                        "step": step_index, "key": key,
                        "locked": locked_value, "suggested": suggested,
                    })
        return tuple(conflicts)

    def merge_derived(self, current, derived):
        fixed = self.fixed_values()
        merged = dict(current)
        for key, value in derived.items():
            if key not in fixed:
                merged[key] = value
        return merged


def parameter_visibility(values, show_advanced=False):
    """Return visible field keys for the selected design mode and geometry."""
    values = dict(values or {})
    shape = values.get("coil_shape", "circular")
    application = values.get("application_preset", "custom")
    motor = shape.startswith("motor_") or application.startswith("motor_")
    sector = shape == "motor_sector" or application == "motor_sector"
    linear = (
        values.get("motor_layout") == "linear"
        or application == "motor_linear"
    )
    design_mode = values.get("design_mode", "manual")
    layer_count = max(1, int(values.get("layer_count", 1)))
    motor_target_mode = design_mode in (
        "motor_target", "target_resistance",
        "target_inductance", "target_current",
    )
    visible = {
        "application_preset", "manufacturing_preset", "copper_thickness_um",
        "minimum_track_width_mm", "minimum_clearance_mm", "coil_shape",
        "layer_count", "net_name", "group_name", "quality_preset",
        "create_group", "close_after_create", "center_x_mm", "center_y_mm",
        "design_mode", "layer_code", "layer_name", "selected_layers",
    }
    if motor:
        visible.update({
            "motor_connection", "motor_pole_pairs", "motor_slot_count",
            "motor_phase_count", "motor_alternate_winding",
        })
        if motor_target_mode:
            visible.update({
                "motor_supply_voltage_v", "allowed_temperature_rise_c",
            })
            if linear:
                visible.update({
                    "motor_target_force_n",
                    "motor_target_linear_speed_mps",
                })
            else:
                visible.add("motor_target_speed_rpm")
            if design_mode == "motor_target":
                visible.add("motor_max_phase_current_a")
                visible.add(
                    "motor_target_force_n" if linear else "target_torque_nm"
                )
            elif design_mode == "target_resistance":
                visible.update({
                    "target_resistance_ohm", "motor_max_phase_current_a",
                })
            elif design_mode == "target_inductance":
                visible.update({
                    "target_inductance_uh", "motor_max_phase_current_a",
                })
            elif design_mode == "target_current":
                visible.add("target_current_a")
        if sector:
            visible.update({
                "motor_board_outer_diameter_mm",
                "motor_board_inner_diameter_mm",
                "motor_edge_clearance_mm", "motor_slot_gap_mm",
            })
            if design_mode == "manual":
                visible.update({
                    "turns", "track_width_mm", "spacing_mm", "spacing_mode",
                })
            elif design_mode == "fit_turns":
                visible.update({"turns", "fill_ratio", "fill_ratio_percent"})
            elif design_mode == "fit_length":
                visible.update({
                    "target_length_mm", "fill_ratio", "fill_ratio_percent",
                })
            elif motor_target_mode:
                visible.update({"fill_ratio", "fill_ratio_percent"})
        else:
            visible.update({
                "motor_layout", "motor_array_radius_mm",
                "motor_linear_pitch_mm", "motor_array_angle_degrees",
                "motor_orientation",
            })
            if design_mode == "manual":
                visible.update({
                    "turns", "start_radius_mm", "track_width_mm",
                    "spacing_mm", "spacing_mode",
                })
            elif design_mode == "fit_length":
                visible.update({
                    "available_diameter_mm", "target_length_mm",
                    "fill_ratio", "fill_ratio_percent",
                })
            elif design_mode == "fit_turns":
                visible.update({
                    "available_diameter_mm", "turns",
                    "fill_ratio", "fill_ratio_percent",
                })
            elif motor_target_mode:
                visible.update({
                    "available_diameter_mm", "fill_ratio",
                    "fill_ratio_percent",
                })
    else:
        visible.add("target_current_a")
        if design_mode == "target_resistance":
            visible.add("target_resistance_ohm")
        elif design_mode == "target_inductance":
            visible.add("target_inductance_uh")
        elif design_mode == "target_current":
            visible.add("allowed_temperature_rise_c")
        if design_mode in (
                "fit_turns", "fit_length", "target_resistance",
                "target_inductance", "target_current"):
            visible.update({
                "available_diameter_mm", "fill_ratio", "fill_ratio_percent",
            })
        if design_mode == "fit_turns":
            visible.add("turns")
        elif design_mode == "fit_length":
            visible.add("target_length_mm")
        elif design_mode == "manual":
            visible.update({
                "turns", "start_radius_mm", "track_width_mm",
                "spacing_mm", "spacing_mode",
            })
    if layer_count > 1:
        visible.update({
            "via_diameter_mm", "via_drill_mm", "via_clearance_mm"
        })
    if show_advanced or values.get("show_advanced_parameters", False):
        visible.update({
            "air_gap_flux_density_t", "electrical_loading_a_per_m",
            "winding_factor", "motor_inner_ratio",
            "shape_aspect_ratio", "shape_taper_ratio",
            "shape_taper_percent",
            "primitive_mode", "arcs_per_turn", "segments_per_turn",
            "additional_segments",
        })
    return frozenset(visible)
