# -*- coding: utf-8 -*-
"""Practical starting-point presets for common PCB coil workflows."""

from math import log, sqrt

try:
    from .geometry import (
        axial_flux_motor_dimensions, required_inner_radius,
        shape_endpoint_scale,
    )
except ImportError:
    from geometry import (
        axial_flux_motor_dimensions, required_inner_radius,
        shape_endpoint_scale,
    )


APPLICATION_PRESET_CODES = (
    "custom",
    "general",
    "compact_sensor",
    "nfc_rfid",
    "wireless_power",
    "heating",
    "long_trace",
    "motor_axial_ellipse",
    "motor_racetrack",
    "motor_trapezoid",
    "motor_sector",
    "motor_linear",
)

QUALITY_PRESETS = {
    "fast": (8, 32),
    "balanced": (16, 64),
    "smooth": (32, 128),
}


MANUFACTURING_PRESET_CODES = (
    "custom",
    "standard",
    "conservative",
    "fine",
    "heavy_copper",
)


MOTOR_SHAPE_DEFAULTS = {
    "motor_ellipse": {
        "shape_aspect_ratio": 1.55,
        "shape_taper_ratio": 0.0,
        "start_radius_mm": 2.0,
        "fill_ratio": 0.62,
    },
    "motor_racetrack": {
        "shape_aspect_ratio": 1.80,
        "shape_taper_ratio": 0.0,
        "start_radius_mm": 2.5,
        "fill_ratio": 0.65,
    },
    "motor_trapezoid": {
        "shape_aspect_ratio": 1.65,
        "shape_taper_ratio": 0.45,
        "start_radius_mm": 3.0,
        "fill_ratio": 0.62,
    },
    "motor_sector": {
        "shape_aspect_ratio": 1.0,
        "shape_taper_ratio": 0.0,
        "start_radius_mm": 0.0,
        "fill_ratio": 0.62,
    },
}

_PROCESS_FILL_ADJUSTMENTS = {
    "custom": 0.0,
    "standard": 0.0,
    "conservative": -0.07,
    "fine": 0.04,
    "heavy_copper": -0.10,
}


def recommend_copper_fill_ratio(application_code, manufacturing_code,
                                target_current_a=0.0,
                                copper_thickness_um=35.0,
                                fallback=0.55):
    """Balance copper loss, process spacing, and a visually regular pitch."""
    application = (
        application_code
        if application_code in APPLICATION_PRESET_CODES
        else "custom"
    )
    manufacturing = (
        manufacturing_code
        if manufacturing_code in MANUFACTURING_PRESET_CODES
        else "custom"
    )
    base_fill = APPLICATION_PRESETS.get(application, {}).get(
        "fill_ratio", float(fallback)
    )
    copper_thickness = max(1.0, float(copper_thickness_um))
    current_load = max(0.0, float(target_current_a)) * 35.0 / copper_thickness
    current_boost = min(0.08, 0.025 * (log(1.0 + current_load) / log(2.0)))
    if application in ("compact_sensor", "nfc_rfid", "long_trace"):
        current_boost *= 0.4
    value = (
        base_fill
        + _PROCESS_FILL_ADJUSTMENTS[manufacturing]
        + current_boost
    )
    return round(min(0.78, max(0.45, value)) * 100.0) / 100.0


def recommend_motor_parameters(coil_shape, motor_layout, pole_pairs,
                               manufacturing_code="custom", layer_count=1,
                               via_diameter_mm=0.6, via_clearance_mm=0.25,
                               track_width_mm=0.25,
                               minimum_track_width_mm=0.1,
                               minimum_clearance_mm=0.1,
                               application_code="custom",
                               target_current_a=0.0,
                               copper_thickness_um=35.0,
                               target_torque_nm=0.0,
                               air_gap_flux_density_t=0.45,
                               electrical_loading_a_per_m=12000.0,
                               winding_factor=0.90,
                               motor_inner_ratio=0.58,
                               motor_slot_count=0,
                               motor_phase_count=3):
    """Return safe, visually balanced motor-coil starting parameters.

    Radial arrays become progressively slimmer as pole count increases, while
    tapered poles use more widening when fewer, wider angular sectors are
    available. A zero array radius/pitch deliberately delegates final spacing
    to the geometry engine, which calculates the minimum non-overlapping value.
    """
    defaults = MOTOR_SHAPE_DEFAULTS.get(coil_shape)
    if defaults is None:
        return {}

    layout = motor_layout if motor_layout in ("single", "radial", "linear")         else "single"
    pairs = min(64, max(1, int(pole_pairs)))
    slots = min(128, max(0, int(motor_slot_count)))
    pole_count = (
        1 if layout == "single" else slots if slots > 0 else 2 * pairs
    )
    phases = int(motor_phase_count) if int(motor_phase_count) in (1, 3) else 3
    aspect = defaults["shape_aspect_ratio"]
    taper = defaults["shape_taper_ratio"]
    start_radius = defaults["start_radius_mm"]

    if layout == "radial":
        pole_ratio = max(0.25, float(pole_count) / 12.0)
        aspect += 0.22 * (log(pole_ratio) / log(2.0))
        if coil_shape == "motor_trapezoid":
            taper = defaults["shape_taper_ratio"] / sqrt(pole_ratio)
        start_radius /= pole_ratio ** 0.10
        orientation = "radial"
    elif layout == "linear":
        pole_ratio = max(0.5, float(pole_count) / 8.0)
        aspect += 0.08 * (log(pole_ratio) / log(2.0))
        if coil_shape == "motor_trapezoid":
            taper = min(0.25, defaults["shape_taper_ratio"])
        orientation = "tangential"
    else:
        orientation = "radial"

    # Quantize the main proportions to calm, repeatable values. Besides making
    # the UI easier to read, this keeps pole arrays visually regular when the
    # pole-pair count changes repeatedly.
    aspect = round(min(2.8, max(1.20, aspect)) / 0.05) * 0.05
    taper = round(min(0.68, max(0.0, taper)) / 0.025) * 0.025
    manufacturing = (
        manufacturing_code
        if manufacturing_code in MANUFACTURING_PRESET_CODES
        else "custom"
    )
    process = MANUFACTURING_PRESETS.get(manufacturing, {})
    minimum_width = max(
        float(minimum_track_width_mm),
        float(process.get("minimum_track_width_mm", 0.0)),
    )
    minimum_clearance = max(
        float(minimum_clearance_mm),
        float(process.get("minimum_clearance_mm", 0.0)),
    )
    via_diameter = max(
        float(via_diameter_mm),
        float(process.get("via_diameter_mm", 0.0)),
    )
    via_clearance = max(
        float(via_clearance_mm),
        float(process.get("via_clearance_mm", 0.0)),
    )
    application = (
        application_code
        if application_code in APPLICATION_PRESET_CODES
        else "custom"
    )
    copper_thickness = max(1.0, float(copper_thickness_um))
    current_load = max(0.0, float(target_current_a)) * 35.0 / copper_thickness
    # A practical current-oriented width floor. It is deliberately conservative
    # and is used for fan-out clearance, not as a thermal-current guarantee.
    electrical_width = min(2.5, 0.18 * current_load)
    reference_width = max(
        float(track_width_mm), minimum_width, electrical_width
    )
    endpoint_scale = shape_endpoint_scale(coil_shape, aspect, taper)
    required_radius = required_inner_radius(
        layer_count, via_diameter, via_clearance, reference_width
    ) / max(endpoint_scale, 1e-9)
    process_margin = 0.5 * max(minimum_width, minimum_clearance)
    start_radius = max(start_radius, required_radius + process_margin)
    fill_ratio = recommend_copper_fill_ratio(
        application, manufacturing, target_current_a, copper_thickness_um,
        defaults["fill_ratio"],
    )
    # Clean decimal recommendations look intentional and produce a regular
    # pitch/clearance rhythm instead of visually noisy near-identical values.
    start_radius = round(start_radius * 10.0) / 10.0

    result = {
        "shape_aspect_ratio": round(aspect, 3),
        "shape_taper_ratio": round(taper, 3),
        "start_radius_mm": round(start_radius, 3),
        "fill_ratio": round(fill_ratio, 3),
        "spacing_mode": "clearance",
        "quality_preset": "smooth",
        "additional_segments": 0,
        "motor_array_radius_mm": 0.0,
        "motor_linear_pitch_mm": 0.0,
        "motor_orientation": orientation,
        "motor_alternate_winding": True,
        "pole_count": pole_count,
        "slot_count": pole_count,
        "phase_count": phases,
        "phase_balanced": layout == "single" or pole_count % phases == 0,
        "layout": layout,
    }
    if layout == "radial" and float(target_torque_nm) > 0.0:
        dimensions = axial_flux_motor_dimensions(
            target_torque_nm, air_gap_flux_density_t,
            electrical_loading_a_per_m, winding_factor, motor_inner_ratio,
        )
        result.update({
            "sizing_mode": "fit_turns",
            "available_diameter_mm": round(
                dimensions["outer_diameter_mm"], 3
            ),
            "motor_array_radius_mm": round(
                dimensions["array_radius_mm"], 3
            ),
            "motor_outer_diameter_mm": dimensions["outer_diameter_mm"],
            "motor_inner_diameter_mm": dimensions["inner_diameter_mm"],
            "motor_inner_ratio": dimensions["inner_ratio"],
        })
    return result


APPLICATION_PRESETS = {
    "general": {
        "design_mode": "fit_turns",
        "sizing_mode": "fit_turns",
        "available_diameter_mm": 40.0,
        "start_radius_mm": 2.0,
        "turns": 10.0,
        "target_length_mm": 1000.0,
        "fill_ratio": 0.55,
        "layer_count": 1,
        "quality_preset": "balanced",
        "primitive_mode": "auto",
        "spacing_mode": "clearance",
        "additional_segments": 0,
        "target_current_a": 1.0,
    },
    "compact_sensor": {
        "design_mode": "target_inductance",
        "target_inductance_uh": 10.0,
        "sizing_mode": "fit_turns",
        "available_diameter_mm": 20.0,
        "start_radius_mm": 1.0,
        "turns": 12.0,
        "target_length_mm": 500.0,
        "fill_ratio": 0.45,
        "layer_count": 1,
        "quality_preset": "smooth",
        "primitive_mode": "auto",
        "spacing_mode": "clearance",
        "additional_segments": 0,
        "target_current_a": 0.1,
    },
    "nfc_rfid": {
        "design_mode": "target_inductance",
        "target_inductance_uh": 2.2,
        "sizing_mode": "fit_turns",
        "available_diameter_mm": 40.0,
        "start_radius_mm": 8.0,
        "turns": 5.0,
        "target_length_mm": 500.0,
        "fill_ratio": 0.55,
        "layer_count": 1,
        "quality_preset": "smooth",
        "primitive_mode": "auto",
        "spacing_mode": "clearance",
        "additional_segments": 0,
        "target_current_a": 0.1,
    },
    "wireless_power": {
        "design_mode": "target_inductance",
        "target_inductance_uh": 10.0,
        "sizing_mode": "fit_turns",
        "available_diameter_mm": 50.0,
        "start_radius_mm": 5.0,
        "turns": 8.0,
        "target_length_mm": 1200.0,
        "fill_ratio": 0.70,
        "layer_count": 2,
        "quality_preset": "smooth",
        "primitive_mode": "auto",
        "spacing_mode": "clearance",
        "additional_segments": 0,
        "target_current_a": 2.0,
    },
    "heating": {
        "design_mode": "target_resistance",
        "target_resistance_ohm": 8.0,
        "sizing_mode": "fit_turns",
        "available_diameter_mm": 45.0,
        "start_radius_mm": 3.0,
        "turns": 6.0,
        "target_length_mm": 1200.0,
        "fill_ratio": 0.78,
        "layer_count": 1,
        "quality_preset": "balanced",
        "primitive_mode": "auto",
        "spacing_mode": "clearance",
        "additional_segments": 0,
        "target_current_a": 2.0,
    },
    "long_trace": {
        "design_mode": "fit_length",
        "sizing_mode": "fit_length",
        "available_diameter_mm": 40.0,
        "start_radius_mm": 2.0,
        "turns": 10.0,
        "target_length_mm": 1200.0,
        "fill_ratio": 0.50,
        "layer_count": 1,
        "quality_preset": "balanced",
        "primitive_mode": "auto",
        "spacing_mode": "clearance",
        "additional_segments": 0,
        "target_current_a": 0.1,
    },
    "motor_axial_ellipse": {
        "design_mode": "motor_target",
        "sizing_mode": "fit_turns",
        "available_diameter_mm": 60.0,
        "start_radius_mm": 2.0,
        "turns": 4.0,
        "target_length_mm": 1200.0,
        "fill_ratio": 0.55,
        "layer_count": 2,
        "quality_preset": "smooth",
        "primitive_mode": "segment",
        "coil_shape": "motor_ellipse",
        "shape_aspect_ratio": 1.45,
        "shape_taper_ratio": 0.0,
        "spacing_mode": "clearance",
        "additional_segments": 0,
        "motor_layout": "radial",
        "motor_pole_pairs": 6,
        "motor_array_radius_mm": 0.0,
        "motor_orientation": "radial",
        "motor_alternate_winding": True,
        "motor_slot_count": 12,
        "target_torque_nm": 0.01,
        "target_current_a": 2.0,
    },
    "motor_racetrack": {
        "design_mode": "motor_target",
        "sizing_mode": "fit_turns",
        "available_diameter_mm": 55.0,
        "start_radius_mm": 2.5,
        "turns": 3.0,
        "target_length_mm": 1500.0,
        "fill_ratio": 0.55,
        "layer_count": 2,
        "quality_preset": "smooth",
        "primitive_mode": "segment",
        "coil_shape": "motor_racetrack",
        "shape_aspect_ratio": 1.55,
        "shape_taper_ratio": 0.0,
        "spacing_mode": "clearance",
        "additional_segments": 0,
        "motor_layout": "radial",
        "motor_pole_pairs": 3,
        "motor_array_radius_mm": 0.0,
        "motor_orientation": "radial",
        "motor_alternate_winding": True,
        "motor_slot_count": 6,
        "target_torque_nm": 0.008,
        "target_current_a": 2.5,
    },
    "motor_trapezoid": {
        "design_mode": "motor_target",
        "sizing_mode": "fit_turns",
        "available_diameter_mm": 60.0,
        "start_radius_mm": 3.0,
        "turns": 3.0,
        "target_length_mm": 1500.0,
        "fill_ratio": 0.55,
        "layer_count": 2,
        "quality_preset": "smooth",
        "primitive_mode": "segment",
        "coil_shape": "motor_trapezoid",
        "shape_aspect_ratio": 1.50,
        "shape_taper_ratio": 0.35,
        "spacing_mode": "clearance",
        "additional_segments": 0,
        "motor_layout": "radial",
        "motor_pole_pairs": 3,
        "motor_array_radius_mm": 0.0,
        "motor_orientation": "radial",
        "motor_alternate_winding": True,
        "motor_slot_count": 6,
        "target_torque_nm": 0.003,
        "target_current_a": 3.0,
    },
    "motor_sector": {
        "design_mode": "motor_target",
        "sizing_mode": "fit_turns",
        "available_diameter_mm": 60.0,
        "motor_board_outer_diameter_mm": 60.0,
        "motor_board_inner_diameter_mm": 24.0,
        "motor_edge_clearance_mm": 0.8,
        "motor_slot_gap_mm": 0.6,
        "start_radius_mm": 0.0,
        "turns": 6.0,
        "target_length_mm": 1800.0,
        "fill_ratio": 0.55,
        "layer_count": 2,
        "quality_preset": "smooth",
        "primitive_mode": "segment",
        "coil_shape": "motor_sector",
        "shape_aspect_ratio": 1.0,
        "shape_taper_ratio": 0.0,
        "spacing_mode": "clearance",
        "additional_segments": 0,
        "motor_layout": "radial",
        "motor_pole_pairs": 3,
        "motor_slot_count": 6,
        "motor_inner_ratio": 0.40,
        "motor_array_radius_mm": 0.0,
        "motor_orientation": "radial",
        "motor_alternate_winding": True,
        "target_torque_nm": 0.02,
        "target_current_a": 3.0,
        "motor_supply_voltage_v": 24.0,
        "motor_target_speed_rpm": 1000.0,
    },
    "motor_linear": {
        "design_mode": "motor_target",
        "sizing_mode": "fit_turns",
        "available_diameter_mm": 60.0,
        "start_radius_mm": 2.0,
        "turns": 3.0,
        "target_length_mm": 1200.0,
        "fill_ratio": 0.55,
        "layer_count": 2,
        "quality_preset": "smooth",
        "primitive_mode": "segment",
        "coil_shape": "motor_racetrack",
        "shape_aspect_ratio": 1.50,
        "shape_taper_ratio": 0.0,
        "motor_layout": "linear",
        "motor_pole_pairs": 3,
        "motor_linear_pitch_mm": 0.0,
        "motor_orientation": "tangential",
        "motor_alternate_winding": True,
        "spacing_mode": "clearance",
        "additional_segments": 0,
        "motor_slot_count": 6,
        "motor_target_force_n": 0.1,
        "motor_target_linear_speed_mps": 0.5,
        "motor_supply_voltage_v": 12.0,
        "motor_max_phase_current_a": 3.0,
        "target_current_a": 2.5,
    },

}


MANUFACTURING_PRESETS = {
    "standard": {
        "minimum_track_width_mm": 0.20,
        "minimum_clearance_mm": 0.20,
        "via_diameter_mm": 0.80,
        "via_drill_mm": 0.40,
        "via_clearance_mm": 0.25,
        "copper_thickness_um": 35.0,
    },
    "conservative": {
        "minimum_track_width_mm": 0.30,
        "minimum_clearance_mm": 0.25,
        "via_diameter_mm": 1.00,
        "via_drill_mm": 0.50,
        "via_clearance_mm": 0.30,
        "copper_thickness_um": 35.0,
    },
    "fine": {
        "minimum_track_width_mm": 0.15,
        "minimum_clearance_mm": 0.15,
        "via_diameter_mm": 0.60,
        "via_drill_mm": 0.30,
        "via_clearance_mm": 0.20,
        "copper_thickness_um": 35.0,
    },
    "heavy_copper": {
        "minimum_track_width_mm": 0.30,
        "minimum_clearance_mm": 0.30,
        "via_diameter_mm": 1.20,
        "via_drill_mm": 0.60,
        "via_clearance_mm": 0.35,
        "copper_thickness_um": 70.0,
    },
}


def manufacturing_violation(manufacturing_code, track_width_mm,
                            clearance_mm, layer_count=1,
                            via_diameter_mm=0.0, via_drill_mm=0.0,
                            via_clearance_mm=0.0):
    """Return the first selected-process violation with actionable values."""
    process = MANUFACTURING_PRESETS.get(manufacturing_code)
    if process is None:
        return None
    checks = (
        ("manufacturing_track_width_too_small", track_width_mm,
         process["minimum_track_width_mm"]),
        ("manufacturing_clearance_too_small", clearance_mm,
         process["minimum_clearance_mm"]),
    )
    if int(layer_count) > 1:
        checks += (
            ("manufacturing_via_diameter_too_small", via_diameter_mm,
             process["via_diameter_mm"]),
            ("manufacturing_via_drill_too_small", via_drill_mm,
             process["via_drill_mm"]),
            ("manufacturing_via_clearance_too_small", via_clearance_mm,
             process["via_clearance_mm"]),
        )
    for code, actual, minimum in checks:
        actual = float(actual)
        minimum = float(minimum)
        if actual + 1e-9 < minimum:
            return {
                "code": code,
                "process": manufacturing_code,
                "actual": actual,
                "minimum": minimum,
            }
    return None


def build_preset_values(application_code, manufacturing_code):
    """Return a fresh settings override for the selected starting points."""
    application = (
        application_code
        if application_code in APPLICATION_PRESET_CODES
        else "custom"
    )
    manufacturing = (
        manufacturing_code
        if manufacturing_code in MANUFACTURING_PRESET_CODES
        else "custom"
    )
    values = {
        "application_preset": application,
        "manufacturing_preset": manufacturing,
    }
    if application != "custom":
        values.update({
            "coil_shape": "circular",
            "shape_aspect_ratio": 1.6,
            "shape_taper_ratio": 0.45,
        })
    values.update(APPLICATION_PRESETS.get(application, {}))
    values.update(MANUFACTURING_PRESETS.get(manufacturing, {}))
    return values

