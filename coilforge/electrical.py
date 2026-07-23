# -*- coding: utf-8 -*-
"""Electrical estimates and constrained design helpers for CoilForge."""

from math import asin, cos, log, pi, sin, sqrt

try:
    from .geometry import (
        GeometryError, estimate_dc_metrics, motor_sector_dimensions,
        resolve_motor_sector_parameters, resolve_motor_spiral_parameters,
        resolve_spiral_parameters, shape_area_scale,
    )
except ImportError:
    from geometry import (
        GeometryError, estimate_dc_metrics, motor_sector_dimensions,
        resolve_motor_sector_parameters, resolve_motor_spiral_parameters,
        resolve_spiral_parameters, shape_area_scale,
    )


MU_0 = 4.0e-7 * pi
COPPER_TEMPERATURE_COEFFICIENT = 0.00393
DC_BUS_TO_MAX_LINE_RMS = 1.0 / sqrt(2.0)


def estimate_planar_spiral_inductance_uh(
        turns, outer_diameter_mm, inner_diameter_mm, geometry_factor=1.0):
    """Return a Mohan current-sheet estimate for a planar spiral in microhenry."""
    outer = float(outer_diameter_mm) * 1e-3
    inner = float(inner_diameter_mm) * 1e-3
    count = float(turns)
    if outer <= 0.0 or inner < 0.0 or inner >= outer or count <= 0.0:
        return 0.0
    average = (outer + inner) / 2.0
    fill = (outer - inner) / (outer + inner)
    # Circular current-sheet coefficients from the compact Mohan expression.
    inductance_h = (
        MU_0 * count * count * average / 2.0
        * (log(2.46 / fill) + 0.20 * fill * fill)
    )
    return max(0.0, inductance_h * 1e6 * max(0.01, float(geometry_factor)))


def estimate_motor_sector_inductance_uh(
        turns_per_slot, board_outer_diameter_mm, board_inner_diameter_mm,
        slot_count, layer_count=1):
    """Return a deliberately rough sector-winding inductance estimate."""
    slots = max(2, int(slot_count))
    annulus_width = (
        float(board_outer_diameter_mm) - float(board_inner_diameter_mm)
    ) / 2.0
    mean_diameter = (
        float(board_outer_diameter_mm) + float(board_inner_diameter_mm)
    ) / 2.0
    equivalent_outer = max(annulus_width, mean_diameter * pi / slots)
    equivalent_inner = max(0.05, equivalent_outer - annulus_width)
    turns = float(turns_per_slot) * max(1, int(layer_count))
    sector_fraction = min(1.0, 2.0 / slots)
    return estimate_planar_spiral_inductance_uh(
        turns, equivalent_outer, equivalent_inner, sector_fraction
    )


def _turn_area_sum_m2(turns, start_radius_mm, pitch_mm, area_scale):
    """Approximate total linked area of concentric shaped turns."""
    count = max(0.0, float(turns))
    whole = int(count)
    fraction = count - whole
    total_mm2 = 0.0
    for index in range(whole):
        radius = float(start_radius_mm) + float(pitch_mm) * (index + 0.5)
        total_mm2 += float(area_scale) * radius * radius
    if fraction > 1e-12:
        radius = float(start_radius_mm) + float(pitch_mm) * (whole + fraction / 2.0)
        total_mm2 += fraction * float(area_scale) * radius * radius
    return max(0.0, total_mm2) * 1e-6


def _sector_turn_area_mm2(dimensions, inset):
    """Return the exact area enclosed by one offset annular-sector turn."""
    inset = max(0.0, float(inset))
    outer = dimensions["centerline_outer_radius"] - inset
    inner = dimensions["centerline_inner_radius"] + inset
    if inner >= outer:
        return 0.0
    half_angle = dimensions["usable_half_angle"]
    outer_angle = half_angle - asin(min(1.0, inset / outer))
    inner_angle = half_angle - asin(min(1.0, inset / inner))
    if outer_angle <= 0.0 or inner_angle <= 0.0:
        return 0.0
    outer_end = (outer * cos(outer_angle),
                 outer * sin(outer_angle))
    inner_start = (inner * cos(inner_angle),
                   inner * sin(inner_angle))
    inner_end = (inner_start[0], -inner_start[1])
    outer_start = (outer_end[0], -outer_end[1])
    side_one = outer_end[0] * inner_start[1] - outer_end[1] * inner_start[0]
    side_two = inner_end[0] * outer_start[1] - inner_end[1] * outer_start[0]
    return max(0.0, (
        outer * outer * outer_angle - inner * inner * inner_angle
        + 0.5 * (side_one + side_two)
    ))


def estimate_motor_sector_emf(
        board_outer_diameter_mm, board_inner_diameter_mm, slot_count,
        pole_pairs, phase_count, turns_per_slot, layer_count, speed_rpm,
        flux_density_t, winding_factor=0.90, connection="star",
        track_width_mm=None, clearance_mm=None, edge_clearance_mm=1.0,
        slot_gap_mm=1.0):
    """Estimate phase and line RMS back-EMF for an annular PCB stator.

    When trace geometry is supplied, flux linkage uses the actual area of every
    nested sector turn instead of multiplying every turn by the full slot area.
    """
    outer = float(board_outer_diameter_mm) * 0.5e-3
    inner = float(board_inner_diameter_mm) * 0.5e-3
    slots = max(2, int(slot_count))
    phases = max(1, int(phase_count))
    pairs = max(1, int(pole_pairs))
    speed = max(0.0, float(speed_rpm))
    turns = max(0.0, float(turns_per_slot))
    layers = max(1, int(layer_count))
    annulus_area = pi * max(0.0, outer * outer - inner * inner)
    flux_linkage_area = None
    if track_width_mm is not None and clearance_mm is not None:
        dimensions = motor_sector_dimensions(
            board_outer_diameter_mm, board_inner_diameter_mm, slots,
            track_width_mm, clearance_mm, edge_clearance_mm, slot_gap_mm,
        )
        whole = int(turns)
        fraction = turns - whole
        area_mm2 = sum(
            _sector_turn_area_mm2(
                dimensions, dimensions["pitch"] * (index + 0.5)
            )
            for index in range(whole)
        )
        if fraction > 1e-12:
            area_mm2 += fraction * _sector_turn_area_mm2(
                dimensions, dimensions["pitch"] * (whole + fraction / 2.0)
            )
        flux_linkage_area = area_mm2 * 1e-6 * layers
    if flux_linkage_area is None:
        flux_linkage_area = turns * layers * annulus_area / slots
    flux_per_slot = max(0.0, float(flux_density_t)) * (
        flux_linkage_area / max(turns * layers, 1e-12)
    )
    slots_per_phase = slots / float(phases)
    series_turns = turns * layers * slots_per_phase
    electrical_frequency = pairs * speed / 60.0
    winding = min(1.0, max(0.01, float(winding_factor)))
    phase_rms = (
        4.44 * electrical_frequency * max(0.0, float(flux_density_t))
        * flux_linkage_area * slots_per_phase * winding
    )
    line_rms = phase_rms * sqrt(3.0) if connection == "star" else phase_rms
    mechanical_omega = 2.0 * pi * speed / 60.0
    phase_constant = (
        phase_rms / mechanical_omega if mechanical_omega > 1e-12
        else 4.44 * pairs / (2.0 * pi)
        * max(0.0, float(flux_density_t))
        * flux_linkage_area * slots_per_phase * winding
    )
    return {
        "phase_rms_v": phase_rms,
        "line_rms_v": line_rms,
        "electrical_frequency_hz": electrical_frequency,
        "flux_per_slot_wb": flux_per_slot,
        "flux_linkage_area_m2": flux_linkage_area,
        "series_turns_per_phase": series_turns,
        "phase_emf_constant_v_per_rad_s": phase_constant,
    }


def estimate_motor_spiral_emf(
        turns_per_slot, start_radius_mm, pitch_mm, coil_shape,
        shape_aspect_ratio, shape_taper_ratio, slot_count, pole_pairs,
        phase_count, layer_count, speed_rpm, flux_density_t,
        winding_factor=0.90, connection="star"):
    """Estimate back-EMF for elliptical, racetrack, and tapered pole coils."""
    slots = max(2, int(slot_count))
    phases = max(1, int(phase_count))
    pairs = max(1, int(pole_pairs))
    layers = max(1, int(layer_count))
    speed = max(0.0, float(speed_rpm))
    area = _turn_area_sum_m2(
        turns_per_slot, start_radius_mm, pitch_mm,
        shape_area_scale(coil_shape, shape_aspect_ratio, shape_taper_ratio),
    ) * layers
    slots_per_phase = slots / float(phases)
    frequency = pairs * speed / 60.0
    winding = min(1.0, max(0.01, float(winding_factor)))
    phase_rms = (
        4.44 * frequency * max(0.0, float(flux_density_t))
        * area * slots_per_phase * winding
    )
    line_rms = phase_rms * sqrt(3.0) if connection == "star" else phase_rms
    omega = 2.0 * pi * speed / 60.0
    phase_constant = (
        phase_rms / omega if omega > 1e-12
        else 4.44 * pairs / (2.0 * pi)
        * max(0.0, float(flux_density_t)) * area
        * slots_per_phase * winding
    )
    return {
        "phase_rms_v": phase_rms, "line_rms_v": line_rms,
        "electrical_frequency_hz": frequency,
        "flux_linkage_area_m2": area,
        "series_turns_per_phase": (
            float(turns_per_slot) * layers * slots_per_phase
        ),
        "phase_emf_constant_v_per_rad_s": phase_constant,
    }



def estimate_motor_linear_emf(
        turns_per_slot, start_radius_mm, pitch_mm, coil_shape,
        shape_aspect_ratio, shape_taper_ratio, slot_count, phase_count,
        layer_count, linear_speed_mps, pole_pitch_mm, flux_density_t,
        winding_factor=0.90, connection="star"):
    """Estimate linear-motor back-EMF from translator speed and pole pitch."""
    slots = max(2, int(slot_count))
    phases = max(1, int(phase_count))
    layers = max(1, int(layer_count))
    speed = max(0.0, float(linear_speed_mps))
    pole_pitch_m = max(1e-9, float(pole_pitch_mm) * 1e-3)
    area = _turn_area_sum_m2(
        turns_per_slot, start_radius_mm, pitch_mm,
        shape_area_scale(coil_shape, shape_aspect_ratio, shape_taper_ratio),
    ) * layers
    slots_per_phase = slots / float(phases)
    frequency = speed / (2.0 * pole_pitch_m)
    winding = min(1.0, max(0.01, float(winding_factor)))
    phase_rms = (
        4.44 * frequency * max(0.0, float(flux_density_t))
        * area * slots_per_phase * winding
    )
    line_rms = phase_rms * sqrt(3.0) if connection == "star" else phase_rms
    phase_constant = (
        phase_rms / speed if speed > 1e-12
        else 4.44 / (2.0 * pole_pitch_m)
        * max(0.0, float(flux_density_t)) * area
        * slots_per_phase * winding
    )
    return {
        "phase_rms_v": phase_rms, "line_rms_v": line_rms,
        "electrical_frequency_hz": frequency,
        "flux_linkage_area_m2": area,
        "series_turns_per_phase": (
            float(turns_per_slot) * layers * slots_per_phase
        ),
        "phase_emf_constant_v_per_mps": phase_constant,
        "phase_emf_constant_v_per_rad_s": phase_constant,
    }

def _motor_electrical_candidate(
        phase_resistance_20c, phase_inductance_uh, emf, target_torque_nm,
        max_phase_current_a, supply_voltage_v, track_width_mm,
        copper_thickness_um, allowed_temperature_rise_c, connection,
        effort_constant=None):
    """Evaluate one motor winding candidate at its hot operating point."""
    rise = max(0.0, float(allowed_temperature_rise_c))
    phase_resistance_hot = float(phase_resistance_20c) * (
        1.0 + COPPER_TEMPERATURE_COEFFICIENT * rise
    )
    torque = max(0.0, float(target_torque_nm))
    emf_constant = max(0.0, (
        emf["phase_emf_constant_v_per_rad_s"]
        if effort_constant is None else float(effort_constant)
    ))
    required_phase_current = 0.0
    if torque > 0.0:
        required_phase_current = (
            torque / (3.0 * emf_constant)
            if emf_constant > 1e-15 else float("inf")
        )
    inductive_drop = (
        required_phase_current * 2.0 * pi
        * emf["electrical_frequency_hz"]
        * float(phase_inductance_uh) * 1e-6
    )
    phase_active_voltage = (
        emf["phase_rms_v"] + required_phase_current * phase_resistance_hot
    )
    required_phase_voltage = sqrt(
        phase_active_voltage * phase_active_voltage
        + inductive_drop * inductive_drop
    )
    required_line_voltage = (
        required_phase_voltage * sqrt(3.0)
        if connection == "star" else required_phase_voltage
    )
    available_line_voltage = max(0.0, float(supply_voltage_v)) * (
        DC_BUS_TO_MAX_LINE_RMS
    )
    thermal_current_limit = estimate_external_trace_current_capacity_a(
        track_width_mm, copper_thickness_um, rise
    )
    effective_current_limit = min(
        max(0.0, float(max_phase_current_a)), thermal_current_limit
    )
    feasible = (
        required_line_voltage <= available_line_voltage + 1e-9
        and required_phase_current <= effective_current_limit + 1e-9
    )
    return {
        "feasible": feasible,
        "phase_resistance_hot_ohm": phase_resistance_hot,
        "required_phase_current_a": required_phase_current,
        "configured_phase_current_limit_a": float(max_phase_current_a),
        "thermal_phase_current_limit_a": thermal_current_limit,
        "effective_phase_current_limit_a": effective_current_limit,
        "required_phase_voltage_v": required_phase_voltage,
        "required_line_voltage_v": required_line_voltage,
        "available_line_voltage_rms_v": available_line_voltage,
        "inductive_phase_drop_v": inductive_drop,
        "copper_loss_w": (
            3.0 * required_phase_current ** 2 * phase_resistance_hot
        ),
        "violations": tuple(
            name for name, violated in (
                ("supply_voltage", required_line_voltage > available_line_voltage),
                ("phase_current", required_phase_current > effective_current_limit),
            ) if violated
        ),
    }


def estimate_external_trace_current_capacity_a(
        track_width_mm, copper_thickness_um, temperature_rise_c):
    """Return a conservative preliminary external-trace current estimate."""
    width = max(0.0, float(track_width_mm))
    thickness = max(0.0, float(copper_thickness_um)) / 1000.0
    rise = max(0.0, float(temperature_rise_c))
    if width <= 0.0 or thickness <= 0.0 or rise <= 0.0:
        return 0.0
    area_mil2 = width * thickness * 1550.0031
    return 0.048 * rise ** 0.44 * area_mil2 ** 0.725


def solve_spiral_electrical_design(
        design_mode, available_diameter_mm, start_radius_mm, layer_count,
        copper_thickness_um, minimum_track_width_mm, minimum_clearance_mm,
        fill_ratio=0.55, target_resistance_ohm=0.0,
        target_inductance_uh=0.0, target_current_a=0.0,
        allowed_temperature_rise_c=30.0, via_diameter_mm=0.6,
        via_clearance_mm=0.25, fixed=None):
    """Fit a circular spiral to a PCB envelope for an electrical target."""
    mode = str(design_mode)
    if mode not in ("target_resistance", "target_inductance", "target_current"):
        raise GeometryError("target_mode_invalid")
    fixed = dict(fixed or {})
    diameter = float(available_diameter_mm)
    start_radius = float(start_radius_mm)
    minimum_pitch = float(minimum_track_width_mm) + float(minimum_clearance_mm)
    if diameter <= 0.0 or minimum_pitch <= 0.0:
        raise GeometryError("available_diameter_invalid")
    maximum_turns = max(1, min(512, int(
        max(0.0, diameter / 2.0 - start_radius) / minimum_pitch
    )))
    candidates = (
        (max(1, int(round(float(fixed["turns"])))),)
        if "turns" in fixed else range(1, maximum_turns + 1)
    )
    best = None
    best_score = None
    for turns in candidates:
        try:
            resolved = resolve_spiral_parameters(
                sizing_mode="fit_turns", start_radius=start_radius,
                turns=turns, track_width=minimum_track_width_mm,
                spacing=minimum_clearance_mm, spacing_mode="clearance",
                available_diameter=diameter, target_length=0.0,
                fill_ratio=fill_ratio, layer_count=layer_count,
                via_diameter=via_diameter_mm, via_clearance=via_clearance_mm,
                minimum_track_width=minimum_track_width_mm,
                minimum_clearance=minimum_clearance_mm,
                coil_shape="circular",
            )
        except GeometryError:
            continue
        metrics = estimate_dc_metrics(
            resolved["total_spiral_length"], resolved["track_width"],
            copper_thickness_um, target_current_a,
        )
        inductance = estimate_planar_spiral_inductance_uh(
            turns * max(1, int(layer_count)),
            2.0 * resolved["outer_radius"],
            max(0.0, 2.0 * resolved["start_radius"]),
        )
        current_capacity = estimate_external_trace_current_capacity_a(
            resolved["track_width"], copper_thickness_um,
            allowed_temperature_rise_c,
        )
        current_target = max(0.0, float(target_current_a))
        current_deficit = (
            max(0.0, current_target - current_capacity)
            / max(current_target, 1e-12)
            if current_target > 0.0 else 0.0
        )
        current_ok = current_target <= 0.0 or current_capacity >= current_target
        if mode == "target_resistance":
            target = max(float(target_resistance_ohm), 1e-12)
            score = (
                abs(metrics["resistance_ohm"] - target) / target
                + 10.0 * current_deficit
            )
            feasible = float(target_resistance_ohm) > 0.0 and current_ok
        elif mode == "target_inductance":
            target = max(float(target_inductance_uh), 1e-12)
            score = (
                abs(inductance - target) / target
                + 10.0 * current_deficit
            )
            feasible = float(target_inductance_uh) > 0.0 and current_ok
        else:
            target = max(current_target, 1e-12)
            excess = max(0.0, current_capacity - target) / target
            score = 10.0 * current_deficit + 0.05 * excess - 0.0001 * turns
            feasible = current_target > 0.0 and current_ok
        result = {
            "feasible": feasible, "design_mode": mode,
            "resolved": resolved, "turns": resolved["turns"],
            "track_width_mm": resolved["track_width"],
            "clearance_mm": resolved["clearance"],
            "resistance_ohm": metrics["resistance_ohm"],
            "inductance_uh": inductance,
            "current_capacity_a": current_capacity,
            "current_target_a": current_target,
            "violations": (() if current_ok else ("trace_current",)),
            "electrical": metrics,
        }
        candidate_key = (0 if feasible else 1, score)
        if best_score is None or candidate_key < best_score:
            best, best_score = result, candidate_key
    if best is None:
        raise GeometryError("target_design_no_solution")
    return best


def _motor_candidate_score(
        operating, supply_voltage_v, target_resistance_ohm,
        phase_resistance_ohm, target_inductance_uh, phase_inductance_uh):
    """Return a stable preference score for a valid or fallback winding."""
    voltage_ratio = (
        operating["required_line_voltage_v"]
        / max(operating["available_line_voltage_rms_v"], 1e-9)
    )
    current_ratio = (
        operating["required_phase_current_a"]
        / max(operating["effective_phase_current_limit_a"], 1e-9)
    )
    resistance_error = (
        abs(float(phase_resistance_ohm) - float(target_resistance_ohm))
        / max(float(target_resistance_ohm), 1e-9)
        if float(target_resistance_ohm) > 0.0 else 0.0
    )
    inductance_error = (
        abs(float(phase_inductance_uh) - float(target_inductance_uh))
        / max(float(target_inductance_uh), 1e-9)
        if float(target_inductance_uh) > 0.0 else 0.0
    )
    target_weight = 1.0 if (
        float(target_resistance_ohm) > 0.0
        or float(target_inductance_uh) > 0.0
    ) else 0.05
    return (
        abs(0.85 - voltage_ratio)
        + 0.15 * current_ratio
        + target_weight * (resistance_error + inductance_error)
        + 0.001 * operating["copper_loss_w"]
    )


def _motor_result(
        turns, resolved, arrangement, phase_resistance, phase_inductance,
        emf, operating):
    """Combine geometry and electrical metrics using one result contract."""
    result = {
        "feasible": operating["feasible"],
        "turns_per_slot": turns,
        "track_width_mm": resolved["track_width"],
        "clearance_mm": resolved["clearance"],
        "pitch_mm": resolved["pitch"],
        "slot_length_mm": resolved["total_spiral_length"],
        "phase_resistance_ohm": phase_resistance,
        "phase_inductance_uh": phase_inductance,
        "back_emf_phase_v": emf["phase_rms_v"],
        "back_emf_line_v": emf["line_rms_v"],
        "electrical_frequency_hz": emf["electrical_frequency_hz"],
        "flux_linkage_area_m2": emf["flux_linkage_area_m2"],
        "series_turns_per_phase": emf["series_turns_per_phase"],
        "arrangement": arrangement,
        "resolved": resolved,
    }
    result.update(operating)
    return result


def solve_motor_sector_design(
        board_outer_diameter_mm, board_inner_diameter_mm, pole_pairs,
        slot_count, phase_count, layer_count, supply_voltage_v,
        target_speed_rpm, target_torque_nm, max_phase_current_a,
        copper_thickness_um, minimum_track_width_mm,
        minimum_clearance_mm, flux_density_t=0.45, winding_factor=0.90,
        connection="star", edge_clearance_mm=1.0, slot_gap_mm=1.0,
        fill_ratio=0.62, target_resistance_ohm=0.0,
        target_inductance_uh=0.0, allowed_temperature_rise_c=30.0,
        fixed=None):
    """Search sector turns from voltage, speed, torque, current, and PCB limits."""
    fixed = dict(fixed or {})
    slots = max(2, int(slot_count) or 2 * int(pole_pairs))
    phases = int(phase_count) if int(phase_count) in (1, 3) else 3
    if slots % phases != 0:
        raise GeometryError(
            "motor_phase_slot_mismatch", slots=slots, phases=phases,
        )
    minimum_dimensions = motor_sector_dimensions(
        board_outer_diameter_mm, board_inner_diameter_mm, slots,
        minimum_track_width_mm, minimum_clearance_mm,
        edge_clearance_mm, slot_gap_mm,
    )
    maximum_turns = max(1, int(minimum_dimensions["max_turns"]))
    if "turns" in fixed:
        candidates = (max(1, int(round(float(fixed["turns"])))),)
    else:
        candidates = range(1, maximum_turns + 1)
    best = None
    best_score = None
    fallback = None
    fallback_score = None
    for turns in candidates:
        try:
            if "track_width_mm" in fixed:
                width = float(fixed["track_width_mm"])
                clearance = float(fixed.get(
                    "clearance_mm", minimum_clearance_mm
                ))
                resolved, arrangement = resolve_motor_sector_parameters(
                    "manual", turns, width, clearance, "clearance",
                    board_outer_diameter_mm, 0.0, fill_ratio, layer_count,
                    minimum_track_width_mm, minimum_clearance_mm, pole_pairs,
                    slots, board_inner_diameter_mm / board_outer_diameter_mm,
                    edge_clearance_mm, slot_gap_mm,
                )
            else:
                resolved, arrangement = resolve_motor_sector_parameters(
                    "fit_turns", turns, minimum_track_width_mm,
                    minimum_clearance_mm, "clearance",
                    board_outer_diameter_mm, 0.0, fill_ratio, layer_count,
                    minimum_track_width_mm, minimum_clearance_mm, pole_pairs,
                    slots, board_inner_diameter_mm / board_outer_diameter_mm,
                    edge_clearance_mm, slot_gap_mm,
                )
        except GeometryError:
            continue
        slot_metrics = estimate_dc_metrics(
            resolved["total_spiral_length"], resolved["track_width"],
            copper_thickness_um, 0.0,
        )
        slots_per_phase = slots / float(phases)
        phase_resistance = slot_metrics["resistance_ohm"] * slots_per_phase
        emf = estimate_motor_sector_emf(
            board_outer_diameter_mm, board_inner_diameter_mm, slots,
            pole_pairs, phases, turns, layer_count, target_speed_rpm,
            flux_density_t, winding_factor, connection,
            track_width_mm=resolved["track_width"],
            clearance_mm=resolved["clearance"],
            edge_clearance_mm=edge_clearance_mm,
            slot_gap_mm=slot_gap_mm,
        )
        phase_inductance = estimate_motor_sector_inductance_uh(
            turns, board_outer_diameter_mm, board_inner_diameter_mm,
            slots, layer_count,
        ) * slots_per_phase
        operating = _motor_electrical_candidate(
            phase_resistance, phase_inductance, emf, target_torque_nm,
            max_phase_current_a, supply_voltage_v, resolved["track_width"],
            copper_thickness_um, allowed_temperature_rise_c, connection,
        )
        score = _motor_candidate_score(
            operating, supply_voltage_v, target_resistance_ohm,
            phase_resistance, target_inductance_uh, phase_inductance,
        )
        result = _motor_result(
            turns, resolved, arrangement, phase_resistance,
            phase_inductance, emf, operating,
        )
        if fallback_score is None or score < fallback_score:
            fallback, fallback_score = result, score
        if result["feasible"] and (best_score is None or score < best_score):
            best, best_score = result, score
    if best is not None:
        return best
    if fallback is not None:
        return fallback
    raise GeometryError("motor_target_no_solution")


def solve_motor_spiral_design(
        available_diameter_mm, start_radius_mm, coil_shape,
        shape_aspect_ratio, shape_taper_ratio, motor_layout, pole_pairs,
        slot_count, phase_count, motor_orientation, motor_array_radius_mm,
        motor_linear_pitch_mm, layer_count, supply_voltage_v,
        target_speed_rpm, target_torque_nm, max_phase_current_a,
        copper_thickness_um, minimum_track_width_mm,
        minimum_clearance_mm, via_diameter_mm=0.6,
        via_clearance_mm=0.25, flux_density_t=0.45,
        winding_factor=0.90, connection="star", fill_ratio=0.62,
        target_resistance_ohm=0.0, target_inductance_uh=0.0,
        allowed_temperature_rise_c=30.0, fixed=None,
        target_force_n=0.0, target_linear_speed_mps=0.0):
    """Size a rotary or linear shaped-coil array from operating targets."""
    linear = str(motor_layout) == "linear"
    if linear and (float(target_force_n) <= 0.0
                   or float(target_linear_speed_mps) <= 0.0):
        raise GeometryError("linear_motor_requires_force_speed")
    fixed = dict(fixed or {})
    phases = int(phase_count) if int(phase_count) in (1, 3) else 3
    slots = max(2, int(slot_count) or 2 * max(1, int(pole_pairs)))
    if slots % phases != 0:
        raise GeometryError(
            "motor_phase_slot_mismatch", slots=slots, phases=phases,
        )
    minimum_pitch = (
        float(minimum_track_width_mm) + float(minimum_clearance_mm)
    )
    maximum_turns = max(1, min(128, int(
        max(0.0, float(available_diameter_mm) / 2.0 - float(start_radius_mm))
        / max(minimum_pitch, 1e-9)
    )))
    if "turns" in fixed:
        candidates = (max(1, int(round(float(fixed["turns"])))),)
    else:
        candidates = range(1, maximum_turns + 1)
    best = None
    best_score = None
    fallback = None
    fallback_score = None
    found_geometry = False
    for turns in candidates:
        try:
            if "track_width_mm" in fixed:
                sizing_mode = "manual"
                width = float(fixed["track_width_mm"])
                clearance = float(fixed.get(
                    "clearance_mm", minimum_clearance_mm
                ))
            else:
                sizing_mode = "fit_turns"
                width = minimum_track_width_mm
                clearance = minimum_clearance_mm
            resolved, arrangement = resolve_motor_spiral_parameters(
                sizing_mode=sizing_mode,
                start_radius=start_radius_mm,
                turns=turns,
                track_width=width,
                spacing=clearance,
                spacing_mode="clearance",
                available_diameter=available_diameter_mm,
                target_length=0.0,
                fill_ratio=fill_ratio,
                layer_count=layer_count,
                via_diameter=via_diameter_mm,
                via_clearance=via_clearance_mm,
                minimum_track_width=minimum_track_width_mm,
                minimum_clearance=minimum_clearance_mm,
                coil_shape=coil_shape,
                shape_aspect_ratio=shape_aspect_ratio,
                shape_taper_ratio=shape_taper_ratio,
                motor_layout=motor_layout,
                motor_pole_pairs=pole_pairs,
                motor_orientation=motor_orientation,
                motor_array_radius=motor_array_radius_mm,
                motor_linear_pitch=motor_linear_pitch_mm,
                motor_slot_count=slots,
            )
        except GeometryError:
            if found_geometry and "turns" not in fixed:
                break
            continue
        found_geometry = True
        actual_slots = int(arrangement.get("count", slots))
        if actual_slots % phases != 0:
            continue
        slots_per_phase = actual_slots / float(phases)
        slot_metrics = estimate_dc_metrics(
            resolved["total_spiral_length"], resolved["track_width"],
            copper_thickness_um, 0.0,
        )
        phase_resistance = slot_metrics["resistance_ohm"] * slots_per_phase
        if linear:
            emf = estimate_motor_linear_emf(
                turns, resolved["start_radius"], resolved["pitch"],
                coil_shape, shape_aspect_ratio, shape_taper_ratio,
                actual_slots, phases, layer_count, target_linear_speed_mps,
                arrangement["linear_pitch"], flux_density_t,
                winding_factor, connection,
            )
        else:
            emf = estimate_motor_spiral_emf(
                turns, resolved["start_radius"], resolved["pitch"],
                coil_shape, shape_aspect_ratio, shape_taper_ratio,
                actual_slots, pole_pairs, phases, layer_count,
                target_speed_rpm, flux_density_t, winding_factor, connection,
            )
        equivalent_scale = sqrt(max(
            1e-12,
            shape_area_scale(
                coil_shape, shape_aspect_ratio, shape_taper_ratio
            ) / pi,
        ))
        phase_inductance = estimate_planar_spiral_inductance_uh(
            turns * max(1, int(layer_count)),
            2.0 * resolved["outer_radius"] * equivalent_scale,
            2.0 * resolved["start_radius"] * equivalent_scale,
        ) * slots_per_phase
        effort_target = target_force_n if linear else target_torque_nm
        effort_constant = (
            emf["phase_emf_constant_v_per_mps"] if linear else None
        )
        operating = _motor_electrical_candidate(
            phase_resistance, phase_inductance, emf, effort_target,
            max_phase_current_a, supply_voltage_v, resolved["track_width"],
            copper_thickness_um, allowed_temperature_rise_c, connection,
            effort_constant=effort_constant,
        )
        score = _motor_candidate_score(
            operating, supply_voltage_v, target_resistance_ohm,
            phase_resistance, target_inductance_uh, phase_inductance,
        )
        result = _motor_result(
            turns, resolved, arrangement, phase_resistance,
            phase_inductance, emf, operating,
        )
        if fallback_score is None or score < fallback_score:
            fallback, fallback_score = result, score
        if result["feasible"] and (best_score is None or score < best_score):
            best, best_score = result, score
    if best is not None:
        return best
    if fallback is not None:
        return fallback
    raise GeometryError("motor_target_no_solution")
