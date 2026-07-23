# -*- coding: utf-8 -*-
"""Shared, UI-independent schematic preview data for CoilForge."""

from math import cos, hypot, isfinite, pi, sin

try:
    from .geometry import (
        GeometryError,
        connector_endpoint_index,
        iter_motor_sector_spiral_segments, iter_shaped_spiral_segments,
        motor_array_instances, motor_sector_dimensions,
        multilayer_connection_layout, motor_sector_connection_layout,
    )
except ImportError:
    from geometry import (
        GeometryError,
        connector_endpoint_index,
        iter_motor_sector_spiral_segments, iter_shaped_spiral_segments,
        motor_array_instances, motor_sector_dimensions,
        multilayer_connection_layout, motor_sector_connection_layout,
    )


_PREVIEW_COORDINATE_SCALE = 100000.0
_PREVIEW_MAX_TURNS = 480.0
_PREVIEW_MAX_PATH_POINTS = 1920
_PREVIEW_MAX_SEGMENTS_PER_TURN = 96
_PREVIEW_MIN_SEGMENTS_PER_TURN = 12
_PREVIEW_MAX_VISIBLE_LAYERS = 4

_PREVIEW_DEFAULTS = {
    "start_radius_mm": 1.0,
    "turns": 5.0,
    "track_width_mm": 0.25,
    "spacing_mm": 0.5,
    "spacing_mode": "pitch",
    "segments_per_turn": 64,
    "additional_segments": 0,
    "coil_shape": "circular",
    "shape_aspect_ratio": 1.6,
    "shape_taper_ratio": 0.45,
    "motor_layout": "single",
    "motor_pole_pairs": 3,
    "motor_array_radius_mm": 0.0,
    "motor_linear_pitch_mm": 0.0,
    "motor_array_angle_degrees": 0.0,
    "motor_orientation": "radial",
    "motor_alternate_winding": True,
    "angle_degrees": 0.0,
    "direction": "clockwise",
    "layer_count": 1,
    "via_diameter_mm": 0.6,
    "via_clearance_mm": 0.25,
}


def _number(value, fallback):
    try:
        result = float(value)
        if result == result and abs(result) != float("inf"):
            return result
    except (TypeError, ValueError):
        pass
    return float(fallback)


def coerce_preview_values(values=None, fallback=None):
    """Return safe preview values while the user is midway through editing."""
    source = dict(_PREVIEW_DEFAULTS)
    if isinstance(fallback, dict):
        source.update(fallback)
    if isinstance(values, dict):
        source.update(values)

    result = dict(source)
    result["start_radius_mm"] = max(
        0.0, _number(source.get("start_radius_mm"), 1.0)
    )
    result["turns"] = max(
        0.001, _number(source.get("turns"), 5.0)
    )
    result["track_width_mm"] = max(
        1e-6, _number(source.get("track_width_mm"), 0.25)
    )
    spacing_mode = source.get("spacing_mode")
    result["spacing_mode"] = (
        spacing_mode if spacing_mode in ("pitch", "clearance") else "pitch"
    )
    spacing = _number(source.get("spacing_mm"), 0.5)
    result["spacing_mm"] = (
        max(1e-6, spacing)
        if result["spacing_mode"] == "pitch"
        else max(0.0, spacing)
    )
    try:
        result["segments_per_turn"] = min(
            4096, max(4, int(float(source.get("segments_per_turn", 64))))
        )
    except (TypeError, ValueError):
        result["segments_per_turn"] = 64
    try:
        result["additional_segments"] = max(
            0, int(float(source.get("additional_segments", 0)))
        )
    except (TypeError, ValueError):
        result["additional_segments"] = 0
    shape = source.get("coil_shape")
    result["coil_shape"] = (
        shape if shape in (
            "circular", "motor_ellipse", "motor_racetrack",
            "motor_trapezoid", "motor_sector",
        ) else "circular"
    )
    result["shape_aspect_ratio"] = min(
        4.0, max(1.0, _number(source.get("shape_aspect_ratio"), 1.6))
    )
    result["shape_taper_ratio"] = min(
        0.75, max(-0.75, _number(source.get("shape_taper_ratio"), 0.45))
    )
    result["angle_degrees"] = _number(
        source.get("angle_degrees"), 0.0
    )
    layout = source.get("motor_layout")
    result["motor_layout"] = (
        layout if layout in ("single", "radial", "linear") else "single"
    )
    try:
        result["motor_pole_pairs"] = min(
            64, max(1, int(float(source.get("motor_pole_pairs", 3))))
        )
    except (TypeError, ValueError):
        result["motor_pole_pairs"] = 3
    try:
        result["motor_slot_count"] = min(
            128, max(0, int(float(source.get("motor_slot_count", 0))))
        )
    except (TypeError, ValueError):
        result["motor_slot_count"] = 0
    board_outer = max(1e-6, _number(
        source.get("motor_board_outer_diameter_mm",
                   source.get("available_diameter_mm", 100.0)),
        100.0,
    ))
    result["motor_board_outer_diameter_mm"] = board_outer
    default_inner = board_outer * _number(
        source.get("motor_inner_ratio"), 0.58
    )
    board_inner = _number(
        source.get("motor_board_inner_diameter_mm", default_inner),
        default_inner,
    )
    result["motor_board_inner_diameter_mm"] = max(
        0.0, min(board_outer * 0.95, board_inner)
    )
    result["motor_edge_clearance_mm"] = max(
        0.0, _number(source.get("motor_edge_clearance_mm"), 1.0)
    )
    result["motor_slot_gap_mm"] = max(
        0.0, _number(source.get("motor_slot_gap_mm"), 1.0)
    )
    result["motor_array_radius_mm"] = max(
        0.0, _number(source.get("motor_array_radius_mm"), 0.0)
    )
    result["motor_linear_pitch_mm"] = max(
        0.0, _number(source.get("motor_linear_pitch_mm"), 0.0)
    )
    result["motor_array_angle_degrees"] = _number(
        source.get("motor_array_angle_degrees"), 0.0
    )
    orientation = source.get("motor_orientation")
    result["motor_orientation"] = (
        orientation if orientation in ("radial", "tangential") else "radial"
    )
    result["motor_alternate_winding"] = bool(
        source.get("motor_alternate_winding", True)
    )
    direction = source.get("direction")
    result["direction"] = (
        direction
        if direction in ("clockwise", "counterclockwise")
        else "clockwise"
    )
    try:
        result["layer_count"] = min(
            12, max(1, int(float(source.get("layer_count", 1))))
        )
    except (TypeError, ValueError):
        result["layer_count"] = 1
    result["via_diameter_mm"] = max(
        1e-6, _number(source.get("via_diameter_mm"), 0.6)
    )
    result["via_clearance_mm"] = max(
        0.0, _number(source.get("via_clearance_mm"), 0.25)
    )
    return result



def _preview_sampling(values):
    turns = max(0.001, float(values.get("turns", 1.0)))
    shown_turns = min(turns, _PREVIEW_MAX_TURNS)
    requested_segments = max(
        _PREVIEW_MIN_SEGMENTS_PER_TURN,
        int(values.get("segments_per_turn", 64)),
    )
    point_budget_segments = max(
        4, int(_PREVIEW_MAX_PATH_POINTS / max(1.0, shown_turns))
    )
    segments_per_turn = min(
        _PREVIEW_MAX_SEGMENTS_PER_TURN, requested_segments,
        point_budget_segments,
    )
    radial_pitch = float(values.get("spacing_mm", 0.5))
    if values.get("spacing_mode", "pitch") == "clearance":
        radial_pitch += float(values.get("track_width_mm", 0.25))
    # Keep the true turn count whenever it fits the point budget. Only very
    # large coils are compressed, while preserving their actual envelope.
    shown_pitch = radial_pitch * turns / shown_turns
    additional_fraction = (
        max(0, int(values.get("additional_segments", 0)))
        / float(max(1, requested_segments))
    )
    shown_additional = int(round(additional_fraction * segments_per_turn))
    return shown_turns, shown_pitch, segments_per_turn, shown_additional


def _path_for_direction(values, counterclockwise):
    turns, pitch, segments_per_turn, additional = _preview_sampling(values)
    scale = _PREVIEW_COORDINATE_SCALE
    if values.get("coil_shape") == "motor_sector":
        board_outer = float(values.get(
            "motor_board_outer_diameter_mm",
            values.get("available_diameter_mm", 100.0),
        ))
        board_inner = float(values.get(
            "motor_board_inner_diameter_mm",
            board_outer * float(values.get("motor_inner_ratio", 0.58)),
        ))
        slot_count = max(
            2, int(values.get("motor_slot_count", 0))
            or 2 * int(values.get("motor_pole_pairs", 1))
        )
        segments = iter_motor_sector_spiral_segments(
            0, 0, board_outer * scale, board_inner * scale, slot_count,
            float(values.get("track_width_mm", 0.25)) * scale,
            max(0.0, pitch - float(values.get("track_width_mm", 0.25))) * scale,
            turns, segments_per_turn, additional,
            float(values.get("motor_edge_clearance_mm", 1.0)) * scale,
            float(values.get("motor_slot_gap_mm", 1.0)) * scale,
            0.0, counterclockwise,
        )
    else:
        segments = iter_shaped_spiral_segments(
            0,
            0,
            float(values.get("start_radius_mm", 0.0)) * scale,
            pitch * scale,
            turns,
            segments_per_turn,
            additional,
            float(values.get("angle_degrees", 0.0)) * pi / 180.0,
            counterclockwise,
            values.get("coil_shape", "circular"),
            values.get("shape_aspect_ratio", 1.0),
            values.get("shape_taper_ratio", 0.0),
        )
    points = []
    for start, end in segments:
        if not points:
            points.append((start[0] / scale, start[1] / scale))
        points.append((end[0] / scale, end[1] / scale))
    return points


def _build_single_preview_scene(values):
    """Build a lightweight preview scene from resolved settings in millimeters."""
    values = coerce_preview_values(values)
    layer_count = max(1, int(values.get("layer_count", 1)))
    base_counterclockwise = values.get("direction") == "counterclockwise"
    clockwise_path = _path_for_direction(values, base_counterclockwise)
    opposite_path = _path_for_direction(values, not base_counterclockwise)
    if len(clockwise_path) < 2:
        raise GeometryError("preview_geometry_empty")

    visible_layers = min(layer_count, _PREVIEW_MAX_VISIBLE_LAYERS)
    coil_paths = [
        clockwise_path if index % 2 == 0 else opposite_path
        for index in range(visible_layers)
    ]
    endpoints = [
        (
            clockwise_path[0] if index % 2 == 0 else opposite_path[0],
            clockwise_path[-1] if index % 2 == 0 else opposite_path[-1],
        )
        for index in range(layer_count)
    ]
    connector_paths = []
    via_points = []
    terminal_points = [endpoints[0][0], endpoints[-1][1]]

    if layer_count > 1:
        centerline_radius = max(
            hypot(point[0], point[1])
            for point in clockwise_path + opposite_path
        )
        scale = _PREVIEW_COORDINATE_SCALE
        scaled_endpoint = lambda point: (point[0] * scale, point[1] * scale)
        try:
            if values.get("coil_shape") == "motor_sector":
                board_outer = float(values.get(
                    "motor_board_outer_diameter_mm",
                    values.get("available_diameter_mm", 100.0),
                ))
                board_inner = float(values.get(
                    "motor_board_inner_diameter_mm",
                    board_outer * float(values.get("motor_inner_ratio", 0.58)),
                ))
                slot_count = max(
                    2, int(values.get("motor_slot_count", 0))
                    or 2 * int(values.get("motor_pole_pairs", 1))
                )
                track_width = float(values.get("track_width_mm", 0.25))
                clearance = (
                    float(values.get("spacing_mm", 0.5)) - track_width
                    if values.get("spacing_mode", "pitch") == "pitch"
                    else float(values.get("spacing_mm", 0.25))
                )
                dimensions = motor_sector_dimensions(
                    board_outer * scale, board_inner * scale, slot_count,
                    track_width * scale, max(0.0, clearance) * scale,
                    float(values.get("motor_edge_clearance_mm", 1.0)) * scale,
                    float(values.get("motor_slot_gap_mm", 1.0)) * scale,
                )
                layer_paths = [
                    clockwise_path if index % 2 == 0 else opposite_path
                    for index in range(layer_count)
                ]
                layout = motor_sector_connection_layout(
                    (-dimensions["array_radius"], 0.0),
                    [[scaled_endpoint(point) for point in path]
                     for path in layer_paths],
                    dimensions["board_outer_radius"],
                    dimensions["board_inner_radius"],
                    float(values.get("motor_edge_clearance_mm", 1.0)) * scale,
                    float(values.get("via_diameter_mm", 0.6)) * scale,
                    float(values.get("via_clearance_mm", 0.25)) * scale,
                    track_width * scale, max(0.0, clearance) * scale,
                )
            else:
                layout = multilayer_connection_layout(
                    (0.0, 0.0), scaled_endpoint(endpoints[0][0]),
                    scaled_endpoint(endpoints[0][1]), centerline_radius * scale,
                    layer_count,
                    float(values.get("via_diameter_mm", 0.6)) * scale,
                    float(values.get("via_clearance_mm", 0.25)) * scale,
                    float(values.get("track_width_mm", 0.25)) * scale,
                )
        except GeometryError:
            layout = None
        if layout is not None:
            via_map = layout["via_points"]
            via_points = [
                (
                    via_map[transition][0] / scale,
                    via_map[transition][1] / scale,
                )
                for transition in range(layer_count - 1)
            ]
            for transition, via_point in enumerate(via_points):
                endpoint_index = connector_endpoint_index(transition)
                connector_paths.append((
                    endpoints[transition][endpoint_index], via_point
                ))
                connector_paths.append((
                    endpoints[transition + 1][endpoint_index], via_point
                ))
            if layout["terminal_routes"]:
                terminal_points = []
            for layer_index, endpoint_index, scaled_terminal in layout[
                    "terminal_routes"]:
                terminal_point = (
                    scaled_terminal[0] / scale, scaled_terminal[1] / scale
                )
                connector_paths.append((
                    endpoints[layer_index][endpoint_index], terminal_point
                ))
                terminal_points.append(terminal_point)

    return {
        "coil_shape": values.get("coil_shape", "circular"),
        "layer_count": layer_count,
        "coil_paths": coil_paths,
        "connector_paths": connector_paths,
        "via_points": via_points,
        "terminal_points": terminal_points,
        "center": (0.0, 0.0),
        "track_width_mm": float(values.get("track_width_mm", 0.25)),
        "via_diameter_mm": float(values.get("via_diameter_mm", 0.6)),
    }


def _transform_preview_point(point, center_x, center_y, rotation,
                             standard_rotation=False):
    cosine = cos(rotation)
    sine = sin(rotation)
    if standard_rotation:
        return (
            center_x + point[0] * cosine - point[1] * sine,
            center_y + point[0] * sine + point[1] * cosine,
        )
    return (
        center_x + point[0] * cosine + point[1] * sine,
        center_y - point[0] * sine + point[1] * cosine,
    )


def build_preview_scene(values):
    """Build one pole or a complete circular/linear motor coil array."""
    values = coerce_preview_values(values)
    base_scene = _build_single_preview_scene(values)
    if values.get("coil_shape") == "circular":
        return base_scene
    if values.get("coil_shape") == "motor_sector":
        board_outer = float(values.get(
            "motor_board_outer_diameter_mm",
            values.get("available_diameter_mm", 100.0),
        ))
        board_inner = float(values.get(
            "motor_board_inner_diameter_mm",
            board_outer * float(values.get("motor_inner_ratio", 0.58)),
        ))
        slot_count = max(
            2, int(values.get("motor_slot_count", 0))
            or 2 * int(values.get("motor_pole_pairs", 1))
        )
        dimensions = motor_sector_dimensions(
            board_outer, board_inner, slot_count,
            float(values.get("track_width_mm", 0.25)),
            max(0.0, (
                float(values.get("spacing_mm", 0.5))
                - float(values.get("track_width_mm", 0.25))
                if values.get("spacing_mode", "pitch") == "pitch"
                else float(values.get("spacing_mm", 0.25))
            )),
            float(values.get("motor_edge_clearance_mm", 1.0)),
            float(values.get("motor_slot_gap_mm", 1.0)),
        )
        start_angle = values.get("motor_array_angle_degrees", 0.0) * pi / 180.0
        instances = []
        for index in range(slot_count):
            angle = start_angle + 2.0 * pi * index / slot_count
            instances.append((
                dimensions["array_radius"] * cos(angle),
                dimensions["array_radius"] * sin(angle),
                angle,
                bool(values.get("motor_alternate_winding", True) and index % 2),
            ))
    else:
        instances = motor_array_instances(
            0.0, 0.0, values.get("coil_shape"),
            values.get("motor_layout", "single"),
            values.get("motor_pole_pairs", 1),
            values.get("motor_array_radius_mm", 0.0),
            values.get("motor_linear_pitch_mm", 0.0),
            values.get("motor_array_angle_degrees", 0.0) * pi / 180.0,
            values.get("motor_orientation", "radial"),
            values.get("motor_alternate_winding", True),
            values.get("motor_slot_count", 0),
        )
    if len(instances) == 1:
        return base_scene
    reverse_values = dict(values)
    reverse_values["direction"] = (
        "clockwise" if values.get("direction") == "counterclockwise"
        else "counterclockwise"
    )
    reverse_scene = _build_single_preview_scene(reverse_values)
    combined = {
        "coil_shape": values.get("coil_shape"),
        "layer_count": values.get("layer_count", 1),
        "coil_paths": [], "connector_paths": [], "via_points": [],
        "terminal_points": [], "center": (0.0, 0.0),
        "motor_instance_count": len(instances),
        "track_width_mm": base_scene["track_width_mm"],
        "via_diameter_mm": base_scene["via_diameter_mm"],
    }
    standard_rotation = values.get("coil_shape") == "motor_sector"
    for center_x, center_y, rotation, reverse in instances:
        scene = reverse_scene if reverse else base_scene
        for key in ("coil_paths", "connector_paths"):
            combined[key].extend([
                [_transform_preview_point(
                    point, center_x, center_y, rotation, standard_rotation
                ) for point in path]
                for path in scene.get(key, ())
            ])
        for key in ("via_points", "terminal_points"):
            combined[key].extend([
                _transform_preview_point(
                    point, center_x, center_y, rotation, standard_rotation
                )
                for point in scene.get(key, ())
            ])
    return combined


def build_safe_preview_scene(values):
    """Return a draft preview when possible without breaking the UI."""
    try:
        return build_preview_scene(values)
    except (GeometryError, ValueError, TypeError, OverflowError):
        return None


def fit_preview_scene(scene, width, height, padding=18.0):
    """Fit and visually center a preview scene while preserving aspect ratio."""
    width = max(1.0, float(width))
    height = max(1.0, float(height))
    padding = max(0.0, float(padding))
    points = [scene.get("center", (0.0, 0.0))]
    for path in scene.get("coil_paths", ()):
        points.extend(path)
    for path in scene.get("connector_paths", ()):
        points.extend(path)
    points.extend(scene.get("via_points", ()))
    points.extend(scene.get("terminal_points", ()))
    if not points:
        points = [(0.0, 0.0)]

    center_x, center_y = scene.get("center", (0.0, 0.0))
    if not isfinite(center_x) or not isfinite(center_y):
        center_x, center_y = 0.0, 0.0
    points = [
        point for point in points
        if isfinite(point[0]) and isfinite(point[1])
    ] or [(center_x, center_y)]
    envelope = max(
        0.0, float(scene.get("track_width_mm", 0.0)) / 2.0,
        float(scene.get("via_diameter_mm", 0.0)) / 2.0,
    )
    min_x = min(point[0] for point in points) - envelope
    max_x = max(point[0] for point in points) + envelope
    min_y = min(point[1] for point in points) - envelope
    max_y = max(point[1] for point in points) + envelope
    visual_center_x = min_x + (max_x - min_x) / 2.0
    visual_center_y = min_y + (max_y - min_y) / 2.0
    radius_x = max(1e-9, (max_x - min_x) / 2.0)
    radius_y = max(1e-9, (max_y - min_y) / 2.0)
    usable_width = max(1.0, width - 2.0 * padding)
    usable_height = max(1.0, height - 2.0 * padding)
    scale = min(usable_width / (2.0 * radius_x),
                usable_height / (2.0 * radius_y))
    canvas_center_x = width / 2.0
    canvas_center_y = height / 2.0

    def transform(point):
        return (
            canvas_center_x + (point[0] - visual_center_x) * scale,
            canvas_center_y - (point[1] - visual_center_y) * scale,
        )

    return {
        "coil_shape": scene.get("coil_shape", "circular"),
        "layer_count": scene.get("layer_count", 1),
        "coil_paths": [
            [transform(point) for point in path]
            for path in scene.get("coil_paths", ())
        ],
        "connector_paths": [
            tuple(transform(point) for point in path)
            for path in scene.get("connector_paths", ())
        ],
        "via_points": [
            transform(point) for point in scene.get("via_points", ())
        ],
        "terminal_points": [
            transform(point) for point in scene.get("terminal_points", ())
        ],
        "center": transform(scene.get("center", (0.0, 0.0))),
        "scale": scale,
        "track_width_px": max(1.0, float(
            scene.get("track_width_mm", 0.0)
        ) * scale),
        "via_diameter_px": max(1.0, float(
            scene.get("via_diameter_mm", 0.0)
        ) * scale),
    }
