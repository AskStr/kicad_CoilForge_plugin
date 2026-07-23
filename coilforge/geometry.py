# -*- coding: utf-8 -*-
"""Pure geometry and auto-sizing helpers for the spiral generator.

This module intentionally has no KiCad or wxPython imports. Geometry is streamed
so large coils do not require a full point or primitive list in memory.
"""

from functools import lru_cache
from math import asin, asinh, atan2, cos, hypot, pi, sin, sqrt, tan


class GeometryError(ValueError):
    """A geometry error with a stable code suitable for localized UI messages."""

    def __init__(self, code, **values):
        ValueError.__init__(self, code)
        self.code = code
        self.values = values


def segment_count(turns, segments_per_turn, additional_segments=0):
    """Return the number of generated primitives.

    Fractional turns are supported. Rounding avoids losing a primitive because
    of binary floating-point representation (for example 1.2 * 10).
    """
    return max(
        0,
        int(round(float(turns) * int(segments_per_turn)))
        + int(additional_segments),
    )


def _spiral_point(center_x, center_y, radius, angle, counterclockwise):
    y_sign = -1.0 if counterclockwise else 1.0
    return (
        int(round(float(center_x) + float(radius) * cos(angle))),
        int(round(float(center_y) + y_sign * float(radius) * sin(angle))),
    )


def iter_spiral_segments(center_x, center_y, start_radius, radial_pitch,
                         turns, segments_per_turn, additional_segments,
                         angle_offset_radians=0.0, counterclockwise=False):
    """Yield consecutive straight segments for an Archimedean spiral."""
    segments_per_turn = int(segments_per_turn)
    total = segment_count(turns, segments_per_turn, additional_segments)
    if segments_per_turn <= 0 or total <= 0:
        return

    angle_step = 2.0 * pi / segments_per_turn
    radius_step = float(radial_pitch) / segments_per_turn
    angle_offset_radians = float(angle_offset_radians)
    start_angle = angle_offset_radians if counterclockwise else -angle_offset_radians
    y_sign = -1.0 if counterclockwise else 1.0

    # Incremental rotation avoids per-point trigonometric calls. Re-anchor
    # periodically to bound floating-point drift on very large spirals.
    cos_step = cos(angle_step)
    sin_step = sin(angle_step)
    cos_phi = cos(start_angle)
    sin_phi = sin(start_angle)
    radius = float(start_radius)
    previous = (
        int(round(float(center_x) + radius * cos_phi)),
        int(round(float(center_y) + y_sign * radius * sin_phi)),
    )

    for index in range(1, total + 1):
        if index % 1024 == 0:
            angle = start_angle + angle_step * index
            cos_phi = cos(angle)
            sin_phi = sin(angle)
        else:
            cos_phi, sin_phi = (
                cos_phi * cos_step - sin_phi * sin_step,
                sin_phi * cos_step + cos_phi * sin_step,
            )
        radius += radius_step
        current = (
            int(round(float(center_x) + radius * cos_phi)),
            int(round(float(center_y) + y_sign * radius * sin_phi)),
        )
        yield previous, current
        previous = current


COIL_SHAPES = (
    "circular", "motor_ellipse", "motor_racetrack", "motor_trapezoid",
    "motor_sector",
)
MOTOR_SHAPES = COIL_SHAPES[1:]
MOTOR_LAYOUTS = ("single", "radial", "linear")
MOTOR_ORIENTATIONS = ("radial", "tangential")


def _rounded_polygon_sections(vertices, corner_radius):
    """Return line/quadratic sections for a convex rounded polygon."""
    vertices = tuple((float(x), float(y)) for x, y in vertices)
    if len(vertices) < 3:
        raise GeometryError("motor_sector_invalid")
    entries = []
    exits = []
    radius = max(0.0, float(corner_radius))
    for index, vertex in enumerate(vertices):
        previous = vertices[index - 1]
        following = vertices[(index + 1) % len(vertices)]
        incoming = (previous[0] - vertex[0], previous[1] - vertex[1])
        outgoing = (following[0] - vertex[0], following[1] - vertex[1])
        incoming_length = hypot(*incoming)
        outgoing_length = hypot(*outgoing)
        cut = min(radius, incoming_length * 0.45, outgoing_length * 0.45)
        if incoming_length <= 1e-12 or outgoing_length <= 1e-12:
            raise GeometryError("motor_sector_invalid")
        entries.append((
            vertex[0] + incoming[0] * cut / incoming_length,
            vertex[1] + incoming[1] * cut / incoming_length,
        ))
        exits.append((
            vertex[0] + outgoing[0] * cut / outgoing_length,
            vertex[1] + outgoing[1] * cut / outgoing_length,
        ))
    sections = []
    for index, vertex in enumerate(vertices):
        previous_exit = exits[index - 1]
        entry = entries[index]
        sections.append(("line", previous_exit, None, entry))
        sections.append(("curve", entry, vertex, exits[index]))
    weights = tuple(_profile_section_length(section) for section in sections)
    return tuple(sections), weights, sum(weights)


def _closed_profile_point(sections, weights, total_weight, fraction):
    distance = (float(fraction) % 1.0) * total_weight
    for section, weight in zip(sections, weights):
        if distance <= weight or section is sections[-1]:
            ratio = 0.0 if weight <= 1e-12 else min(1.0, distance / weight)
            return _profile_section_point(section, ratio)
        distance -= weight
    return sections[-1][3]


def motor_sector_dimensions(board_outer_diameter, board_inner_diameter,
                            slot_count, track_width, clearance,
                            edge_clearance=1.0, slot_gap=1.0):
    """Resolve the centerline envelope for one annular motor slot."""
    outer_radius = float(board_outer_diameter) / 2.0
    inner_radius = float(board_inner_diameter) / 2.0
    count = min(128, max(2, int(slot_count)))
    width = float(track_width)
    gap = float(clearance)
    edge = max(0.0, float(edge_clearance))
    slot_gap = max(0.0, float(slot_gap))
    if outer_radius <= 0.0 or inner_radius < 0.0 or inner_radius >= outer_radius:
        raise GeometryError("motor_sector_invalid")
    if width <= 0.0 or gap < 0.0:
        raise GeometryError("motor_sector_invalid")
    centerline_outer = outer_radius - edge - width / 2.0
    centerline_inner = inner_radius + edge + width / 2.0
    if centerline_outer <= centerline_inner:
        raise GeometryError("available_diameter_too_small")
    mean_radius = (centerline_outer + centerline_inner) / 2.0
    half_angle = pi / count - (slot_gap + width) / (2.0 * mean_radius)
    half_angle = min(1.45, half_angle)
    if half_angle <= 1e-4:
        raise GeometryError("motor_sector_slot_too_narrow")
    outer_half_width = centerline_outer * sin(half_angle)
    inner_half_width = centerline_inner * sin(half_angle)
    pitch = width + gap
    # Each turn is a true perpendicular offset of the base annular sector.
    # Reserve one pitch across the innermost window so opposite sides of the
    # same turn cannot touch and bypass the intended current path.
    inset_capacity = min(
        (centerline_outer - centerline_inner) / 2.0,
        inner_half_width,
    ) - pitch / 2.0
    if inset_capacity <= 0.0:
        raise GeometryError("motor_sector_slot_too_narrow")
    return {
        "board_outer_radius": outer_radius,
        "board_inner_radius": inner_radius,
        "centerline_outer_radius": centerline_outer,
        "centerline_inner_radius": centerline_inner,
        "array_radius": mean_radius,
        "slot_count": count,
        "slot_angle": 2.0 * pi / count,
        "usable_half_angle": half_angle,
        "outer_half_width": outer_half_width,
        "inner_half_width": inner_half_width,
        "radial_half_span": (centerline_outer - centerline_inner) / 2.0,
        "pitch": pitch,
        "inset_capacity": inset_capacity,
        "max_turns": max(0.0, inset_capacity / pitch),
    }


def _motor_sector_local_point(dimensions, inset, fraction, _corner_radius):
    """Return a point on an exact perpendicular offset sector contour."""
    inset = max(0.0, float(inset))
    outer_radius = dimensions["centerline_outer_radius"] - inset
    inner_radius = dimensions["centerline_inner_radius"] + inset
    base_half_angle = dimensions["usable_half_angle"]
    if inner_radius >= outer_radius:
        raise GeometryError("motor_sector_turns_too_large")

    # Offsetting a radial side does not produce another radial side. Its
    # intersections with the inner and outer circles use different angles.
    # The previous mean-radius approximation made the short arc too long and
    # reduced turn spacing below the requested clearance near its corners.
    outer_ratio = min(1.0, inset / max(outer_radius, 1e-12))
    inner_ratio = min(1.0, inset / max(inner_radius, 1e-12))
    outer_half_angle = base_half_angle - asin(outer_ratio)
    inner_half_angle = base_half_angle - asin(inner_ratio)
    if outer_half_angle <= 1e-6 or inner_half_angle <= 1e-6:
        raise GeometryError("motor_sector_turns_too_large")

    outer_start = (
        outer_radius * cos(-outer_half_angle),
        outer_radius * sin(-outer_half_angle),
    )
    outer_end = (
        outer_radius * cos(outer_half_angle),
        outer_radius * sin(outer_half_angle),
    )
    inner_start = (
        inner_radius * cos(inner_half_angle),
        inner_radius * sin(inner_half_angle),
    )
    inner_end = (
        inner_radius * cos(-inner_half_angle),
        inner_radius * sin(-inner_half_angle),
    )
    outer_arc = 2.0 * outer_half_angle * outer_radius
    side = hypot(
        outer_end[0] - inner_start[0],
        outer_end[1] - inner_start[1],
    )
    inner_arc = 2.0 * inner_half_angle * inner_radius
    perimeter = outer_arc + side + inner_arc + side
    distance = (float(fraction) % 1.0) * perimeter
    if distance <= outer_arc:
        angle = -outer_half_angle + distance / outer_radius
        return outer_radius * cos(angle), outer_radius * sin(angle)
    distance -= outer_arc
    if distance <= side:
        ratio = 0.0 if side <= 1e-12 else distance / side
        return (
            outer_end[0] + (inner_start[0] - outer_end[0]) * ratio,
            outer_end[1] + (inner_start[1] - outer_end[1]) * ratio,
        )
    distance -= side
    if distance <= inner_arc:
        angle = inner_half_angle - distance / inner_radius
        return inner_radius * cos(angle), inner_radius * sin(angle)
    distance -= inner_arc
    ratio = 0.0 if side <= 1e-12 else min(1.0, distance / side)
    return (
        inner_end[0] + (outer_start[0] - inner_end[0]) * ratio,
        inner_end[1] + (outer_start[1] - inner_end[1]) * ratio,
    )


def iter_motor_sector_spiral_segments(
        center_x, center_y, board_outer_diameter, board_inner_diameter,
        slot_count, track_width, clearance, turns, segments_per_turn,
        additional_segments=0, edge_clearance=1.0, slot_gap=1.0,
        rotation_radians=0.0, counterclockwise=False):
    """Yield a continuous rounded spiral constrained to one annular sector."""
    dimensions = motor_sector_dimensions(
        board_outer_diameter, board_inner_diameter, slot_count,
        track_width, clearance, edge_clearance, slot_gap,
    )
    turns = float(turns)
    segments_per_turn = int(segments_per_turn)
    total = segment_count(turns, segments_per_turn, additional_segments)
    if turns <= 0.0 or segments_per_turn <= 0 or total <= 0:
        return
    maximum_inset = dimensions["pitch"] * turns
    inset_tolerance = max(1e-9, dimensions["inset_capacity"] * 1e-9)
    if maximum_inset > dimensions["inset_capacity"] + inset_tolerance:
        raise GeometryError(
            "motor_sector_turns_too_large",
            actual=turns, maximum=dimensions["max_turns"],
        )
    maximum_inset = min(maximum_inset, dimensions["inset_capacity"])
    cos_rotation = cos(float(rotation_radians))
    sin_rotation = sin(float(rotation_radians))
    corner_radius = max(float(track_width), dimensions["pitch"] * 0.75)

    def point(index):
        progress = index / float(total)
        turn_position = turns * progress
        inset = maximum_inset - dimensions["pitch"] * turn_position
        fraction = turn_position if not counterclockwise else -turn_position
        local_x, local_y = _motor_sector_local_point(
            dimensions, max(0.0, inset), fraction, corner_radius
        )
        local_x -= dimensions["array_radius"]
        rotated_x = local_x * cos_rotation - local_y * sin_rotation
        rotated_y = local_x * sin_rotation + local_y * cos_rotation
        return (
            int(round(float(center_x) + rotated_x)),
            int(round(float(center_y) + rotated_y)),
        )

    previous = point(0)
    for index in range(1, total + 1):
        current = point(index)
        yield previous, current
        previous = current


def motor_sector_spiral_length(
        board_outer_diameter, board_inner_diameter, slot_count,
        track_width, clearance, turns, edge_clearance=1.0, slot_gap=1.0,
        samples_per_turn=256):
    """Numerically estimate one annular-sector spiral centerline length."""
    scale = 1000000.0
    length = 0.0
    for start, end in iter_motor_sector_spiral_segments(
            0, 0, float(board_outer_diameter) * scale,
            float(board_inner_diameter) * scale, slot_count,
            float(track_width) * scale, float(clearance) * scale, turns,
            max(16, int(samples_per_turn)), 0,
            float(edge_clearance) * scale, float(slot_gap) * scale):
        length += hypot(end[0] - start[0], end[1] - start[1]) / scale
    return length


def _shape_values(coil_shape, aspect_ratio, taper_ratio):
    shape = str(coil_shape)
    if shape not in COIL_SHAPES:
        shape = "circular"
    aspect = max(1.0, float(aspect_ratio))
    taper = min(0.75, max(-0.75, float(taper_ratio)))
    return shape, aspect, taper


def _quadratic_point(start, control, end, ratio):
    inverse = 1.0 - ratio
    return (
        inverse * inverse * start[0]
        + 2.0 * inverse * ratio * control[0]
        + ratio * ratio * end[0],
        inverse * inverse * start[1]
        + 2.0 * inverse * ratio * control[1]
        + ratio * ratio * end[1],
    )


def _profile_section_point(section, ratio):
    kind, start, control, end = section
    if kind == "line":
        return (
            start[0] + ratio * (end[0] - start[0]),
            start[1] + ratio * (end[1] - start[1]),
        )
    return _quadratic_point(start, control, end, ratio)


def _profile_section_length(section, samples=24):
    previous = _profile_section_point(section, 0.0)
    length = 0.0
    for index in range(1, int(samples) + 1):
        current = _profile_section_point(
            section, float(index) / float(samples)
        )
        length += hypot(
            current[0] - previous[0], current[1] - previous[1]
        )
        previous = current
    return length


def _line_minimum_radius(start, end):
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    denominator = delta_x * delta_x + delta_y * delta_y
    if denominator <= 1e-24:
        return hypot(start[0], start[1])
    ratio = -(
        start[0] * delta_x + start[1] * delta_y
    ) / denominator
    ratio = min(1.0, max(0.0, ratio))
    return hypot(
        start[0] + ratio * delta_x,
        start[1] + ratio * delta_y,
    )


@lru_cache(maxsize=128)
def _motor_trapezoid_profile(aspect, taper):
    """Return a rounded trapezoid with straight tapered upper/lower sides."""
    aspect = float(aspect)
    taper = float(taper)
    left_height = 1.0 - taper
    right_height = 1.0 + taper
    cap_depth = max(0.08, min(
        0.45,
        0.28 * aspect,
        0.70 * aspect * (1.0 - abs(taper)),
    ))
    straight_span = 2.0 * (aspect - cap_depth)
    height_delta = right_height - left_height
    control_offset = cap_depth * height_delta / straight_span

    right_end = (aspect, 0.0)
    right_upper = (aspect - cap_depth, right_height)
    left_upper = (-aspect + cap_depth, left_height)
    left_end = (-aspect, 0.0)
    left_lower = (left_upper[0], -left_upper[1])
    right_lower = (right_upper[0], -right_upper[1])
    right_control_y = right_height + control_offset
    left_control_y = left_height - control_offset

    sections = (
        ("curve", right_end, (aspect, right_control_y), right_upper),
        ("line", right_upper, None, left_upper),
        ("curve", left_upper, (-aspect, left_control_y), left_end),
        ("curve", left_end, (-aspect, -left_control_y), left_lower),
        ("line", left_lower, None, right_lower),
        ("curve", right_lower, (aspect, -right_control_y), right_end),
    )
    lengths = tuple(_profile_section_length(section) for section in sections)
    sampling_weights = tuple(
        length * (1.75 if section[0] == "curve" else 0.50)
        for section, length in zip(sections, lengths)
    )
    sampling_total = sum(sampling_weights)

    minimum_radius = min(
        _line_minimum_radius(section[1], section[3])
        for section in sections if section[0] == "line"
    )
    for section in sections:
        if section[0] != "curve":
            continue
        for index in range(65):
            point = _profile_section_point(section, index / 64.0)
            minimum_radius = min(minimum_radius, hypot(*point))
    scale = max(1.0, 1.000001 / minimum_radius)
    return sections, sampling_weights, sampling_total, scale


def _motor_trapezoid_point(cos_phi, sin_phi, aspect, taper):
    sections, sampling_weights, sampling_total, scale = _motor_trapezoid_profile(
        float(aspect), float(taper)
    )
    angle = atan2(float(sin_phi), float(cos_phi))
    if angle < 0.0:
        angle += 2.0 * pi
    distance = sampling_total * angle / (2.0 * pi)
    for section, weight in zip(sections, sampling_weights):
        if distance <= weight:
            point = _profile_section_point(section, distance / weight)
            return scale * point[0], scale * point[1]
        distance -= weight
    return scale * float(aspect), 0.0


def _motor_capsule_point(cos_phi, sin_phi, aspect):
    """Return a true racetrack made from straight runs and semicircle ends."""
    half_span = float(aspect) - 1.0
    if half_span <= 1e-12:
        return float(cos_phi), float(sin_phi)

    quarter_arc = pi / 2.0
    straight_length = 2.0 * half_span
    perimeter = 2.0 * pi + 2.0 * straight_length
    angle = atan2(float(sin_phi), float(cos_phi))
    if angle < 0.0:
        angle += 2.0 * pi
    distance = perimeter * angle / (2.0 * pi)

    if distance <= quarter_arc:
        return half_span + cos(distance), sin(distance)
    distance -= quarter_arc
    if distance <= straight_length:
        return half_span - distance, 1.0
    distance -= straight_length
    if distance <= pi:
        arc_angle = quarter_arc + distance
        return -half_span + cos(arc_angle), sin(arc_angle)
    distance -= pi
    if distance <= straight_length:
        return -half_span + distance, -1.0
    distance -= straight_length
    arc_angle = 3.0 * quarter_arc + distance
    return half_span + cos(arc_angle), sin(arc_angle)


def _shaped_unit_point(cos_phi, sin_phi, coil_shape,
                       aspect_ratio, taper_ratio):
    shape, aspect, taper = _shape_values(
        coil_shape, aspect_ratio, taper_ratio
    )
    if shape == "circular":
        return float(cos_phi), float(sin_phi)
    if shape == "motor_ellipse":
        return aspect * float(cos_phi), float(sin_phi)
    if shape == "motor_racetrack":
        return _motor_capsule_point(cos_phi, sin_phi, aspect)

    return _motor_trapezoid_point(
        cos_phi, sin_phi, aspect, taper
    )


def shape_endpoint_scale(coil_shape, aspect_ratio, taper_ratio=0.0):
    """Return radial scale at the shared inner/outer connection endpoints."""
    shape, aspect, taper = _shape_values(
        coil_shape, aspect_ratio, taper_ratio
    )
    if shape in ("circular", "motor_sector"):
        return 1.0
    if shape == "motor_trapezoid":
        return aspect * _motor_trapezoid_profile(aspect, taper)[3]
    return aspect


@lru_cache(maxsize=128)
def shape_area_scale(coil_shape, aspect_ratio, taper_ratio=0.0, samples=720):
    """Return the enclosed area of a unit-radius shaped turn."""
    shape, aspect, taper = _shape_values(
        coil_shape, aspect_ratio, taper_ratio
    )
    count = max(64, int(samples))
    points = []
    for index in range(count):
        angle = 2.0 * pi * index / count
        points.append(_shaped_unit_point(
            cos(angle), sin(angle), shape, aspect, taper
        ))
    twice_area = 0.0
    for start, end in zip(points, points[1:] + points[:1]):
        twice_area += start[0] * end[1] - end[0] * start[1]
    return abs(twice_area) / 2.0


@lru_cache(maxsize=128)
def shape_extent_scale(coil_shape, aspect_ratio, taper_ratio, samples=720):
    """Return maximum distance from center for a unit shaped turn."""
    shape, aspect, taper = _shape_values(
        coil_shape, aspect_ratio, taper_ratio
    )
    if shape == "circular":
        return 1.0
    maximum = 0.0
    samples = max(32, int(samples))
    for index in range(samples):
        angle = 2.0 * pi * index / samples
        x, y = _shaped_unit_point(
            cos(angle), sin(angle), shape, aspect, taper
        )
        maximum = max(maximum, hypot(x, y))
    return maximum


@lru_cache(maxsize=256)
def shape_support_scale(coil_shape, aspect_ratio, taper_ratio,
                        direction_radians, samples=720):
    """Return the convex support radius of a unit shaped turn."""
    shape, aspect, taper = _shape_values(
        coil_shape, aspect_ratio, taper_ratio
    )
    direction = float(direction_radians)
    axis_x, axis_y = cos(direction), sin(direction)
    maximum = 0.0
    count = max(64, int(samples))
    for index in range(count):
        angle = 2.0 * pi * index / count
        x, y = _shaped_unit_point(
            cos(angle), sin(angle), shape, aspect, taper
        )
        maximum = max(maximum, abs(x * axis_x + y * axis_y))
    return maximum


@lru_cache(maxsize=128)
def shape_axis_extent_scales(coil_shape, aspect_ratio, taper_ratio,
                             samples=720):
    """Return maximum absolute local x/y scales for a shaped turn."""
    shape, aspect, taper = _shape_values(
        coil_shape, aspect_ratio, taper_ratio
    )
    maximum_x = 0.0
    maximum_y = 0.0
    for index in range(max(32, int(samples))):
        angle = 2.0 * pi * index / max(32, int(samples))
        x, y = _shaped_unit_point(
            cos(angle), sin(angle), shape, aspect, taper
        )
        maximum_x = max(maximum_x, abs(x))
        maximum_y = max(maximum_y, abs(y))
    return maximum_x, maximum_y


def resolve_motor_arrangement(coil_shape, layout, pole_pairs, orientation,
                              array_radius, linear_pitch, outer_radius,
                              track_width, clearance=0.0,
                              aspect_ratio=1.0, taper_ratio=0.0,
                              slot_count=0, overall_radius=None):
    """Resolve safe motor pole count and radial/linear placement dimensions."""
    if coil_shape not in MOTOR_SHAPES:
        return {
            "layout": "single", "count": 1, "array_radius": 0.0,
            "linear_pitch": 0.0, "minimum_spacing": 0.0,
        }
    layout = layout if layout in MOTOR_LAYOUTS else "single"
    orientation = (
        orientation if orientation in MOTOR_ORIENTATIONS else "radial"
    )
    pairs = min(64, max(1, int(pole_pairs)))
    requested_slots = min(128, max(0, int(slot_count)))
    count = (
        1 if layout == "single"
        else requested_slots if requested_slots > 0 else 2 * pairs
    )
    if layout == "single":
        return {
            "layout": layout, "count": count, "array_radius": 0.0,
            "linear_pitch": 0.0, "minimum_spacing": 0.0,
        }
    extent_x, extent_y = shape_axis_extent_scales(
        coil_shape, aspect_ratio, taper_ratio
    )
    radial_extent = float(outer_radius)
    half_x = radial_extent * extent_x + float(track_width) / 2.0
    half_y = radial_extent * extent_y + float(track_width) / 2.0
    along_half_extent = half_x if orientation == "radial" else half_y
    margin = max(float(clearance), float(track_width))
    shape_bound = (
        radial_extent * shape_extent_scale(
            coil_shape, aspect_ratio, taper_ratio
        ) + float(track_width) / 2.0
    )
    connector_extension = max(
        0.0, float(overall_radius or 0.0) - shape_bound
    )
    if layout == "radial":
        half_step = pi / count
        local_separation_axis = (
            pi / 2.0 + half_step
            if orientation == "radial" else half_step
        )
        across_half_extent = (
            radial_extent * shape_support_scale(
                coil_shape, aspect_ratio, taper_ratio,
                local_separation_axis,
            ) + float(track_width) / 2.0 + connector_extension
        )
        minimum_center_spacing = 2.0 * across_half_extent + margin
        sine = sin(half_step)
        minimum_radius = minimum_center_spacing / (2.0 * sine)
        resolved_radius = (
            minimum_radius if float(array_radius) <= 0.0
            else float(array_radius)
        )
        if resolved_radius + 1e-9 < minimum_radius:
            raise GeometryError(
                "motor_array_radius_too_small",
                actual=resolved_radius, minimum=minimum_radius,
            )
        return {
            "layout": layout, "count": count,
            "array_radius": resolved_radius, "linear_pitch": 0.0,
            "minimum_spacing": minimum_center_spacing,
        }
    minimum_pitch = (
        2.0 * (along_half_extent + connector_extension) + margin
    )
    resolved_pitch = (
        minimum_pitch if float(linear_pitch) <= 0.0 else float(linear_pitch)
    )
    if resolved_pitch + 1e-9 < minimum_pitch:
        raise GeometryError(
            "motor_linear_pitch_too_small",
            actual=resolved_pitch, minimum=minimum_pitch,
        )
    return {
        "layout": layout, "count": count, "array_radius": 0.0,
        "linear_pitch": resolved_pitch,
        "minimum_spacing": minimum_pitch,
    }


def motor_array_instances(center_x, center_y, coil_shape, layout="single",
                          pole_pairs=1, array_radius=0.0, linear_pitch=0.0,
                          array_angle_radians=0.0, orientation="radial",
                          alternate_winding=True, slot_count=0):
    """Return (center_x, center_y, rotation, reverse_winding) instances."""
    if coil_shape not in MOTOR_SHAPES or layout == "single":
        return [(float(center_x), float(center_y), 0.0, False)]
    requested_slots = min(128, max(0, int(slot_count)))
    count = (
        requested_slots if requested_slots > 0
        else 2 * min(64, max(1, int(pole_pairs)))
    )
    angle = float(array_angle_radians)
    quarter_turn = pi / 2.0 if orientation == "tangential" else 0.0
    instances = []
    if layout == "radial":
        for index in range(count):
            placement = angle + 2.0 * pi * index / count
            instances.append((
                float(center_x) + float(array_radius) * cos(placement),
                float(center_y) - float(array_radius) * sin(placement),
                placement + quarter_turn,
                bool(alternate_winding and index % 2),
            ))
    elif layout == "linear":
        for index in range(count):
            offset = (index - (count - 1) / 2.0) * float(linear_pitch)
            instances.append((
                float(center_x) + offset * cos(angle),
                float(center_y) - offset * sin(angle),
                angle + quarter_turn,
                bool(alternate_winding and index % 2),
            ))
    else:
        instances.append((float(center_x), float(center_y), 0.0, False))
    return instances


def iter_shaped_spiral_segments(
        center_x, center_y, start_radius, radial_pitch, turns,
        segments_per_turn, additional_segments,
        angle_offset_radians=0.0, counterclockwise=False,
        coil_shape="circular", aspect_ratio=1.0, taper_ratio=0.0):
    """Yield a circular, elliptical, racetrack, or tapered motor spiral."""
    shape, aspect, taper = _shape_values(
        coil_shape, aspect_ratio, taper_ratio
    )
    if shape == "circular":
        for segment in iter_spiral_segments(
                center_x, center_y, start_radius, radial_pitch, turns,
                segments_per_turn, additional_segments,
                angle_offset_radians, counterclockwise):
            yield segment
        return

    segments_per_turn = int(segments_per_turn)
    total = segment_count(turns, segments_per_turn, additional_segments)
    if segments_per_turn <= 0 or total <= 0:
        return
    angle_step = 2.0 * pi / segments_per_turn
    radius_step = float(radial_pitch) / segments_per_turn
    rotation = float(angle_offset_radians)
    cos_rotation = cos(rotation)
    sin_rotation = sin(rotation)
    y_sign = -1.0 if counterclockwise else 1.0

    def point(radius, angle):
        unit_x, unit_y = _shaped_unit_point(
            cos(angle), sin(angle), shape, aspect, taper
        )
        local_x = radius * unit_x
        local_y = y_sign * radius * unit_y
        rotated_x = local_x * cos_rotation + local_y * sin_rotation
        rotated_y = -local_x * sin_rotation + local_y * cos_rotation
        return (
            int(round(float(center_x) + rotated_x)),
            int(round(float(center_y) + rotated_y)),
        )

    radius = float(start_radius)
    previous = point(radius, 0.0)
    for index in range(1, total + 1):
        radius += radius_step
        current = point(radius, angle_step * index)
        yield previous, current
        previous = current


def shaped_spiral_length(start_radius, radial_pitch, turns,
                         coil_shape="circular", aspect_ratio=1.0,
                         taper_ratio=0.0, samples_per_turn=256):
    """Numerically estimate centerline length for a transformed spiral."""
    shape, aspect, taper = _shape_values(
        coil_shape, aspect_ratio, taper_ratio
    )
    if shape == "circular":
        return spiral_length(start_radius, radial_pitch, turns)
    count = max(8, int(round(float(turns) * samples_per_turn)))
    total_angle = 2.0 * pi * float(turns)
    previous = None
    length = 0.0
    for index in range(count + 1):
        fraction = index / float(count)
        angle = total_angle * fraction
        radius = float(start_radius) + float(radial_pitch) * float(turns) * fraction
        unit_x, unit_y = _shaped_unit_point(
            cos(angle), sin(angle), shape, aspect, taper
        )
        current = (radius * unit_x, radius * unit_y)
        if previous is not None:
            length += hypot(
                current[0] - previous[0], current[1] - previous[1]
            )
        previous = current
    return length


def shaped_overall_coil_radius(outer_radius, track_width, layer_count,
                               via_diameter, via_clearance, coil_shape,
                               aspect_ratio, taper_ratio):
    """Return copper/fan-out envelope for circular and motor pole shapes."""
    centerline_envelope = (
        float(outer_radius) * shape_extent_scale(
            coil_shape, aspect_ratio, taper_ratio
        )
    )
    copper_radius = centerline_envelope + float(track_width) / 2.0
    fanout_radius = overall_coil_radius(
        centerline_envelope, track_width, layer_count,
        via_diameter, via_clearance,
    )
    return max(copper_radius, fanout_radius)


def iter_spiral_arcs(center_x, center_y, start_radius, radial_pitch,
                     turns, arcs_per_turn, additional_arcs,
                     angle_offset_radians=0.0, counterclockwise=False):
    """Yield start/mid/end triples approximating a spiral with circular arcs.

    KiCad's ``PCB_ARC`` is circular, while an Archimedean spiral has changing
    curvature. Sampling each primitive at its start, midpoint and end produces
    a compact circular-arc approximation without building a point list.
    """
    arcs_per_turn = int(arcs_per_turn)
    total = segment_count(turns, arcs_per_turn, additional_arcs)
    if arcs_per_turn <= 0 or total <= 0:
        return

    angle_step = 2.0 * pi / arcs_per_turn
    radius_step = float(radial_pitch) / arcs_per_turn
    start_angle = (
        float(angle_offset_radians)
        if counterclockwise
        else -float(angle_offset_radians)
    )

    for index in range(total):
        start_radius_value = float(start_radius) + radius_step * index
        start_angle_value = start_angle + angle_step * index
        midpoint = _spiral_point(
            center_x,
            center_y,
            start_radius_value + radius_step / 2.0,
            start_angle_value + angle_step / 2.0,
            counterclockwise,
        )
        start = _spiral_point(
            center_x,
            center_y,
            start_radius_value,
            start_angle_value,
            counterclockwise,
        )
        end = _spiral_point(
            center_x,
            center_y,
            start_radius_value + radius_step,
            start_angle_value + angle_step,
            counterclockwise,
        )
        yield start, midpoint, end


def spiral_length(start_radius, radial_pitch, turns):
    """Return the exact Archimedean-spiral centerline length."""
    start_radius = float(start_radius)
    radial_pitch = float(radial_pitch)
    turns = float(turns)
    if turns <= 0.0:
        return 0.0
    if radial_pitch <= 0.0:
        return 2.0 * pi * max(0.0, start_radius) * turns

    b = radial_pitch / (2.0 * pi)
    end_radius = start_radius + radial_pitch * turns

    def primitive(radius):
        root = sqrt(radius * radius + b * b)
        return 0.5 * (radius * root + b * b * asinh(radius / b))

    return (primitive(end_radius) - primitive(start_radius)) / b


def estimate_dc_metrics(length_mm, track_width_mm, copper_thickness_um,
                        current_a=0.0):
    """Estimate 20 °C copper DC resistance, voltage drop, and heating power.

    The estimate intentionally excludes vias, connector fan-out, temperature
    rise, plating variation, and AC skin/proximity effects.
    """
    length_mm = float(length_mm)
    track_width_mm = float(track_width_mm)
    copper_thickness_um = float(copper_thickness_um)
    current_a = float(current_a)
    if length_mm < 0.0 or track_width_mm <= 0.0:
        raise GeometryError("electrical_estimate_invalid")
    if copper_thickness_um <= 0.0 or current_a < 0.0:
        raise GeometryError("electrical_estimate_invalid")

    # 1.724e-8 ohm metre copper resistivity at approximately 20 °C.
    resistance = (
        0.01724 * length_mm / (track_width_mm * copper_thickness_um)
    )
    return {
        "resistance_ohm": resistance,
        "voltage_drop_v": resistance * current_a,
        "power_w": resistance * current_a * current_a,
    }


def axial_flux_motor_dimensions(target_torque_nm, flux_density_t,
                                electrical_loading_a_per_m, winding_factor,
                                inner_ratio=0.58):
    """Dimension an axial-flux PCB stator from the guide equation.

    Radii are returned in millimetres. The equation uses SI inputs and the
    guide's ``(1 - lambda**2)`` annulus factor.
    """
    torque = float(target_torque_nm)
    flux_density = float(flux_density_t)
    electrical_loading = float(electrical_loading_a_per_m)
    winding = float(winding_factor)
    ratio = float(inner_ratio)
    if (torque <= 0.0 or flux_density <= 0.0
            or electrical_loading <= 0.0 or winding <= 0.0
            or not 0.0 < ratio < 1.0):
        raise GeometryError("motor_dimensioning_invalid")
    denominator = (
        pi * flux_density * electrical_loading * winding
        * (1.0 - ratio * ratio)
    )
    outer_radius_mm = 1000.0 * (4.0 * torque / denominator) ** (1.0 / 3.0)
    inner_radius_mm = ratio * outer_radius_mm
    return {
        "outer_radius_mm": outer_radius_mm,
        "inner_radius_mm": inner_radius_mm,
        "outer_diameter_mm": 2.0 * outer_radius_mm,
        "inner_diameter_mm": 2.0 * inner_radius_mm,
        "annulus_width_mm": outer_radius_mm - inner_radius_mm,
        "array_radius_mm": (outer_radius_mm + inner_radius_mm) / 2.0,
        "inner_ratio": ratio,
    }


def estimate_axial_flux_motor_torque(outer_radius_mm, inner_radius_mm,
                                     flux_density_t,
                                     electrical_loading_a_per_m,
                                     winding_factor):
    """Estimate torque by inverting :func:`axial_flux_motor_dimensions`."""
    outer_radius_m = float(outer_radius_mm) / 1000.0
    inner_radius_m = float(inner_radius_mm) / 1000.0
    flux_density = float(flux_density_t)
    electrical_loading = float(electrical_loading_a_per_m)
    winding = float(winding_factor)
    if (outer_radius_m <= 0.0 or inner_radius_m < 0.0
            or inner_radius_m >= outer_radius_m or flux_density <= 0.0
            or electrical_loading <= 0.0 or winding <= 0.0):
        raise GeometryError("motor_dimensioning_invalid")
    ratio = inner_radius_m / outer_radius_m
    return (
        pi * flux_density * electrical_loading * winding
        * (1.0 - ratio * ratio) * outer_radius_m ** 3 / 4.0
    )


def motor_inner_trace_dfm(inner_radius_mm, pole_pairs, turns_per_slot,
                          track_width_mm, clearance_mm,
                          outer_radius_mm=None):
    """Check the guide's inner-sector trace-capacity constraint.

    ``2 * turns * (width + clearance)`` must fit inside the inner pole-sector
    arc ``pi * R_in / pole_pairs``. The optional outer radius also yields the
    guide's linearly tapered outer-width recommendation.
    """
    inner_radius = float(inner_radius_mm)
    pairs = int(pole_pairs)
    turns = float(turns_per_slot)
    width = float(track_width_mm)
    clearance = float(clearance_mm)
    if (inner_radius <= 0.0 or pairs <= 0 or turns <= 0.0
            or width <= 0.0 or clearance < 0.0):
        raise GeometryError("motor_inner_trace_invalid")
    sector_arc = pi * inner_radius / pairs
    pitch = width + clearance
    required = 2.0 * turns * pitch
    maximum_turns = int((sector_arc + 1e-12) / (2.0 * pitch))
    result = {
        "sector_arc_mm": sector_arc,
        "required_arc_mm": required,
        "utilization": required / sector_arc,
        "maximum_turns_per_layer": maximum_turns,
        "passes": required <= sector_arc + 1e-12,
    }
    if outer_radius_mm is not None:
        outer_radius = float(outer_radius_mm)
        if outer_radius <= inner_radius:
            raise GeometryError("motor_inner_trace_invalid")
        result["recommended_outer_width_mm"] = width * (
            outer_radius / inner_radius
        )
    return result


def _validate_fit_inputs(available_diameter, start_radius, fill_ratio):
    available_diameter = float(available_diameter)
    start_radius = float(start_radius)
    fill_ratio = float(fill_ratio)
    if available_diameter <= 0.0:
        raise GeometryError("available_diameter_invalid")
    if start_radius < 0.0:
        raise GeometryError("start_radius_invalid")
    if not 0.0 < fill_ratio < 1.0:
        raise GeometryError("fill_ratio_invalid")
    if start_radius >= available_diameter / 2.0:
        raise GeometryError("available_diameter_too_small")
    return available_diameter, start_radius, fill_ratio


def fit_spiral_by_turns(available_diameter, start_radius, turns, fill_ratio):
    """Fit width and clearance inside a diameter for a fixed turn count."""
    available_diameter, start_radius, fill_ratio = _validate_fit_inputs(
        available_diameter, start_radius, fill_ratio
    )
    turns = float(turns)
    if turns <= 0.0:
        raise GeometryError("turns_invalid")

    available_radius = available_diameter / 2.0
    pitch = (available_radius - start_radius) / (turns + fill_ratio / 2.0)
    width = pitch * fill_ratio
    clearance = pitch - width
    if pitch <= 0.0 or width <= 0.0 or clearance <= 0.0:
        raise GeometryError("available_diameter_too_small")

    outer_radius = start_radius + pitch * turns
    return {
        "turns": turns,
        "track_width": width,
        "pitch": pitch,
        "clearance": clearance,
        "outer_radius": outer_radius,
        "outer_diameter": 2.0 * (outer_radius + width / 2.0),
        "length_per_layer": spiral_length(start_radius, pitch, turns),
    }


def fit_spiral_by_length(available_diameter, start_radius, target_length,
                         fill_ratio, layer_count=1, integer_turns=False,
                         coil_shape="circular", shape_aspect_ratio=1.0,
                         shape_taper_ratio=0.0):
    """Fit turns, width and clearance for a target total spiral length.

    ``target_length`` is the sum of the spiral centerline lengths on all coil
    layers. Short layer-transition connectors are intentionally excluded.
    """
    available_diameter, start_radius, fill_ratio = _validate_fit_inputs(
        available_diameter, start_radius, fill_ratio
    )
    target_length = float(target_length)
    layer_count = max(1, int(layer_count))
    if target_length <= 0.0:
        raise GeometryError("target_length_invalid")
    target_per_layer = target_length / layer_count

    def fit_for_turns(candidate_turns):
        fit = fit_spiral_by_turns(
            available_diameter, start_radius, candidate_turns, fill_ratio
        )
        fit["length_per_layer"] = shaped_spiral_length(
            start_radius, fit["pitch"], candidate_turns,
            coil_shape, shape_aspect_ratio, shape_taper_ratio,
        )
        fit["total_spiral_length"] = fit["length_per_layer"] * layer_count
        return fit

    low = 1e-6
    low_fit = fit_for_turns(low)
    if target_per_layer + 1e-9 < low_fit["length_per_layer"]:
        raise GeometryError(
            "target_length_too_short",
            minimum=low_fit["length_per_layer"] * layer_count,
        )

    high = 1.0
    high_fit = fit_for_turns(high)
    while high_fit["length_per_layer"] < target_per_layer and high < 1000000.0:
        high *= 2.0
        high_fit = fit_for_turns(high)
    if high_fit["length_per_layer"] < target_per_layer:
        raise GeometryError("target_length_too_large")

    for _index in range(72):
        midpoint = (low + high) / 2.0
        fit = fit_for_turns(midpoint)
        if fit["length_per_layer"] < target_per_layer:
            low = midpoint
        else:
            high = midpoint

    turns = (low + high) / 2.0
    if integer_turns:
        lower = max(1, int(turns))
        candidates = (lower, lower + 1)
        turns = min(
            candidates,
            key=lambda value: abs(
                fit_for_turns(value)["length_per_layer"] - target_per_layer
            ),
        )

    result = fit_for_turns(turns)
    result["target_length"] = target_length
    result["total_spiral_length"] = result["length_per_layer"] * layer_count
    return result


def overall_coil_radius(outer_radius, track_width, layer_count,
                        via_diameter, via_clearance):
    """Return the radial envelope including outer transition-via fan-out."""
    outer_radius = float(outer_radius)
    track_width = float(track_width)
    layer_count = max(1, int(layer_count))
    if layer_count <= 1:
        return outer_radius + track_width / 2.0

    clearance_envelope = _clearance_envelope(
        via_diameter, via_clearance, track_width
    )
    outer_via_count = max(0, (layer_count - 1) // 2)
    outer_terminal_count = 2 if layer_count % 2 == 0 else 1
    outer_lane_count = outer_via_count + outer_terminal_count
    tangent_offset = (outer_lane_count - 1) * clearance_envelope
    radial_gap = hypot(tangent_offset, clearance_envelope)
    line_radius = outer_radius + radial_gap
    if outer_terminal_count == 2:
        via_tangent_offset = max(
            0.0, (outer_lane_count - 3) * clearance_envelope
        )
    else:
        via_tangent_offset = tangent_offset
    via_extent = (
        hypot(line_radius, via_tangent_offset)
        + float(via_diameter) / 2.0
        if outer_via_count else 0.0
    )
    terminal_extent = hypot(
        line_radius, tangent_offset
    ) + track_width / 2.0
    return max(
        outer_radius + track_width / 2.0,
        via_extent,
        terminal_extent,
    )


def resolve_spiral_parameters(sizing_mode, start_radius, turns, track_width,
                              spacing, spacing_mode, available_diameter,
                              target_length, fill_ratio, layer_count,
                              via_diameter, via_clearance,
                              minimum_track_width=0.0,
                              minimum_clearance=0.0,
                              coil_shape="circular",
                              shape_aspect_ratio=1.0,
                              shape_taper_ratio=0.0):
    """Resolve manual or automatic spiral dimensions in one unit system.

    Automatic diameter modes reserve space for the complete multilayer fan-out,
    including the outer through vias, instead of fitting only the spiral copper.
    """
    layer_count = max(1, int(layer_count))
    sizing_mode = str(sizing_mode)
    configured_start_radius = float(start_radius)
    coil_shape, shape_aspect_ratio, shape_taper_ratio = _shape_values(
        coil_shape, shape_aspect_ratio, shape_taper_ratio
    )
    endpoint_scale = shape_endpoint_scale(
        coil_shape, shape_aspect_ratio, shape_taper_ratio
    )

    if sizing_mode == "manual":
        width = float(track_width)
        spacing = float(spacing)
        pitch = width + spacing if spacing_mode == "clearance" else spacing
        clearance = pitch - width
        resolved_turns = float(turns)
        spiral_outer_radius = (
            configured_start_radius + pitch * resolved_turns
        )
        result = {
            "turns": resolved_turns,
            "track_width": width,
            "pitch": pitch,
            "clearance": clearance,
            "outer_radius": spiral_outer_radius,
            "spiral_diameter": 2.0 * (
                spiral_outer_radius * shape_extent_scale(
                    coil_shape, shape_aspect_ratio, shape_taper_ratio
                ) + width / 2.0
            ),
            "length_per_layer": shaped_spiral_length(
                configured_start_radius, pitch, resolved_turns,
                coil_shape, shape_aspect_ratio, shape_taper_ratio,
            ),
            "start_radius": configured_start_radius,
        }
        result["outer_diameter"] = 2.0 * shaped_overall_coil_radius(
            spiral_outer_radius,
            width,
            layer_count,
            via_diameter,
            via_clearance,
            coil_shape,
            shape_aspect_ratio,
            shape_taper_ratio,
        )
        result["total_spiral_length"] = (
            result["length_per_layer"] * layer_count
        )
        return result

    requested_diameter = float(available_diameter)
    fit_diameter = requested_diameter
    current_start_radius = configured_start_radius
    result = None
    diameter_response_scale = max(
        1.0,
        shape_extent_scale(
            coil_shape, shape_aspect_ratio, shape_taper_ratio
        ),
    )
    for _index in range(96):
        if sizing_mode == "fit_turns":
            result = fit_spiral_by_turns(
                fit_diameter, current_start_radius, turns, fill_ratio
            )
        elif sizing_mode == "fit_length":
            result = fit_spiral_by_length(
                fit_diameter,
                current_start_radius,
                target_length,
                fill_ratio,
                layer_count,
                integer_turns=layer_count > 1,
                coil_shape=coil_shape,
                shape_aspect_ratio=shape_aspect_ratio,
                shape_taper_ratio=shape_taper_ratio,
            )
        else:
            raise GeometryError("sizing_mode_invalid")

        required_radius = required_inner_radius(
            layer_count,
            via_diameter,
            via_clearance,
            result["track_width"],
        ) / endpoint_scale
        adjusted_radius = max(configured_start_radius, required_radius)
        overall_diameter = 2.0 * shaped_overall_coil_radius(
            result["outer_radius"],
            result["track_width"],
            layer_count,
            via_diameter,
            via_clearance,
            coil_shape,
            shape_aspect_ratio,
            shape_taper_ratio,
        )
        diameter_error = overall_diameter - requested_diameter
        adjusted_fit_diameter = (
            fit_diameter - diameter_error / diameter_response_scale
        )
        if adjusted_fit_diameter <= 0.0:
            raise GeometryError("available_diameter_too_small")

        radius_stable = (
            abs(adjusted_radius - current_start_radius) <= 1e-9
        )
        diameter_stable = abs(diameter_error) <= 1e-9
        if radius_stable and diameter_stable:
            break
        current_start_radius = adjusted_radius
        fit_diameter = adjusted_fit_diameter
    else:
        raise GeometryError("auto_size_not_converged")

    result["start_radius"] = current_start_radius
    result["spiral_diameter"] = 2.0 * (
        result["outer_radius"] * shape_extent_scale(
            coil_shape, shape_aspect_ratio, shape_taper_ratio
        ) + result["track_width"] / 2.0
    )
    result["outer_diameter"] = overall_diameter
    result["length_per_layer"] = shaped_spiral_length(
        current_start_radius,
        result["pitch"],
        result["turns"],
        coil_shape,
        shape_aspect_ratio,
        shape_taper_ratio,
    )
    result["total_spiral_length"] = (
        result["length_per_layer"] * layer_count
    )
    if result["track_width"] + 1e-12 < float(minimum_track_width):
        raise GeometryError(
            "track_width_below_minimum",
            actual=result["track_width"],
            minimum=float(minimum_track_width),
        )
    if result["clearance"] + 1e-12 < float(minimum_clearance):
        raise GeometryError(
            "clearance_below_minimum",
            actual=result["clearance"],
            minimum=float(minimum_clearance),
        )
    return result


def multilayer_track_count(turns, primitives_per_turn, additional_primitives,
                           layer_count):
    """Return spiral primitives plus via connectors and terminal fan-out tracks."""
    layer_count = max(1, int(layer_count))
    spiral_items = segment_count(
        turns, primitives_per_turn, additional_primitives
    ) * layer_count
    connector_tracks = 0 if layer_count <= 1 else 2 * (layer_count - 1) + 2
    return spiral_items + connector_tracks


def connector_endpoint_index(transition):
    """Return the spiral endpoint used by a layer transition.

    The first transition uses the inner endpoint. This leaves the first free
    terminal on the outer edge and, for the common even-layer case, leaves both
    free terminals on the outer edge for practical routing.
    """
    return 0 if int(transition) % 2 == 0 else 1


def _centered_offsets(count, pitch):
    return [
        (slot - (count - 1) / 2.0) * pitch
        for slot in range(max(0, int(count)))
    ]


def _clearance_envelope(via_diameter, via_clearance, track_width):
    return (
        float(track_width) / 2.0
        + float(via_diameter) / 2.0
        + float(via_clearance)
    )



def motor_array_outer_diameter(arrangement, coil_outer_diameter):
    """Return a circular envelope diameter for a complete coil arrangement."""
    diameter = max(0.0, float(coil_outer_diameter))
    layout = arrangement.get("layout", "single")
    count = max(1, int(arrangement.get("count", 1)))
    if layout == "radial":
        return diameter + 2.0 * abs(float(arrangement.get("array_radius", 0.0)))
    if layout == "linear":
        return diameter + (count - 1) * abs(
            float(arrangement.get("linear_pitch", 0.0))
        )
    return diameter


def _motor_coil_diameter_estimate(available_diameter, coil_shape, layout,
                                  count, orientation, array_radius,
                                  linear_pitch, minimum_track_width,
                                  minimum_clearance, aspect_ratio,
                                  taper_ratio):
    """Estimate a safe per-coil diameter before the exact fit-turns solve."""
    available = float(available_diameter)
    if coil_shape not in MOTOR_SHAPES or layout == "single" or count <= 1:
        return available
    margin = max(float(minimum_track_width), float(minimum_clearance), 0.0)
    if layout == "radial" and float(array_radius) > 0.0:
        return available - 2.0 * float(array_radius)
    if layout == "linear" and float(linear_pitch) > 0.0:
        return available - (count - 1) * float(linear_pitch)

    extent_x, extent_y = shape_axis_extent_scales(
        coil_shape, aspect_ratio, taper_ratio
    )
    maximum_extent = max(
        1e-12,
        shape_extent_scale(coil_shape, aspect_ratio, taper_ratio),
    )
    along_extent = extent_x if orientation == "radial" else extent_y
    across_extent = extent_y if orientation == "radial" else extent_x
    if layout == "radial":
        sine = sin(pi / count)
        response = 1.0 + (across_extent / maximum_extent) / sine
        return (available - margin / sine) / response
    response = 1.0 + (count - 1) * (along_extent / maximum_extent)
    return (available - (count - 1) * margin) / response


def resolve_motor_sector_parameters(
        sizing_mode, turns, track_width, spacing, spacing_mode,
        board_outer_diameter, target_length, fill_ratio, layer_count,
        minimum_track_width=0.0, minimum_clearance=0.0,
        motor_pole_pairs=1, motor_slot_count=0, motor_inner_ratio=0.58,
        edge_clearance=1.0, slot_gap=1.0):
    """Resolve a radial annular-sector winding inside a fixed PCB envelope."""
    outer_diameter = float(board_outer_diameter)
    ratio = min(0.90, max(0.05, float(motor_inner_ratio)))
    inner_diameter = outer_diameter * ratio
    slots = min(128, max(2, int(motor_slot_count) or 2 * int(motor_pole_pairs)))
    mode = str(sizing_mode)
    configured_turns = float(turns)
    minimum_width = max(1e-6, float(minimum_track_width))
    minimum_gap = max(0.0, float(minimum_clearance))

    if mode == "manual":
        width = float(track_width)
        configured_spacing = float(spacing)
        pitch = (
            width + configured_spacing
            if spacing_mode == "clearance" else configured_spacing
        )
        clearance = pitch - width
        resolved_turns = configured_turns
    elif mode == "fit_turns":
        if configured_turns <= 0.0 or outer_diameter <= 0.0:
            raise GeometryError("available_diameter_invalid")
        copper_fill = min(0.95, max(0.05, float(fill_ratio)))
        low = minimum_width + minimum_gap
        high = max(low, outer_diameter / max(2.0, configured_turns))
        best = None
        for _index in range(64):
            candidate_pitch = (low + high) / 2.0
            candidate_width = max(minimum_width, candidate_pitch * copper_fill)
            candidate_gap = max(minimum_gap, candidate_pitch - candidate_width)
            candidate_pitch = candidate_width + candidate_gap
            try:
                dimensions = motor_sector_dimensions(
                    outer_diameter, inner_diameter, slots, candidate_width,
                    candidate_gap, edge_clearance, slot_gap,
                )
                fits = configured_turns <= dimensions["max_turns"] + 1e-9
            except GeometryError:
                fits = False
            if fits:
                best = (candidate_width, candidate_gap, candidate_pitch)
                low = candidate_pitch
            else:
                high = candidate_pitch
        if best is None:
            raise GeometryError("available_diameter_too_small")
        width, clearance, pitch = best
        resolved_turns = configured_turns
    elif mode == "fit_length":
        width = max(minimum_width, float(track_width))
        clearance = max(minimum_gap, (
            float(spacing) if spacing_mode == "clearance"
            else float(spacing) - width
        ))
        pitch = width + clearance
        dimensions = motor_sector_dimensions(
            outer_diameter, inner_diameter, slots, width, clearance,
            edge_clearance, slot_gap,
        )
        target = float(target_length) / max(1, int(layer_count))
        if target <= 0.0:
            raise GeometryError("target_length_invalid")
        low_turns = 0.05
        high_turns = max(low_turns, dimensions["max_turns"] * 0.999)
        if motor_sector_spiral_length(
                outer_diameter, inner_diameter, slots, width, clearance,
                high_turns, edge_clearance, slot_gap) + 1e-9 < target:
            raise GeometryError("target_length_too_large")
        for _index in range(48):
            candidate = (low_turns + high_turns) / 2.0
            length = motor_sector_spiral_length(
                outer_diameter, inner_diameter, slots, width, clearance,
                candidate, edge_clearance, slot_gap, 96,
            )
            if length < target:
                low_turns = candidate
            else:
                high_turns = candidate
        resolved_turns = (low_turns + high_turns) / 2.0
    else:
        raise GeometryError("sizing_mode_invalid")

    if width + 1e-12 < minimum_width:
        raise GeometryError(
            "track_width_below_minimum", actual=width, minimum=minimum_width
        )
    if clearance + 1e-12 < minimum_gap:
        raise GeometryError(
            "clearance_below_minimum", actual=clearance, minimum=minimum_gap
        )
    dimensions = motor_sector_dimensions(
        outer_diameter, inner_diameter, slots, width, clearance,
        edge_clearance, slot_gap,
    )
    if resolved_turns > dimensions["max_turns"] + 1e-9:
        raise GeometryError(
            "motor_sector_turns_too_large",
            actual=resolved_turns, maximum=dimensions["max_turns"],
        )
    length_per_layer = motor_sector_spiral_length(
        outer_diameter, inner_diameter, slots, width, clearance,
        resolved_turns, edge_clearance, slot_gap,
    )
    local_half_x = dimensions["radial_half_span"]
    local_half_y = dimensions["outer_half_width"]
    local_radius = hypot(local_half_x, local_half_y)
    result = {
        "turns": resolved_turns,
        "track_width": width,
        "pitch": pitch,
        "clearance": clearance,
        "outer_radius": local_radius,
        "spiral_diameter": 2.0 * local_radius + width,
        "outer_diameter": outer_diameter,
        "length_per_layer": length_per_layer,
        "total_spiral_length": length_per_layer * max(1, int(layer_count)),
        "start_radius": 0.0,
        "array_outer_diameter": outer_diameter,
        "requested_array_diameter": outer_diameter,
        "motor_board_outer_diameter": outer_diameter,
        "motor_board_inner_diameter": inner_diameter,
        "motor_sector": dimensions,
    }
    arrangement = {
        "layout": "radial",
        "count": slots,
        "array_radius": dimensions["array_radius"],
        "linear_pitch": 0.0,
        "minimum_spacing": max(float(slot_gap), clearance),
        "sector": dimensions,
    }
    return result, arrangement


def resolve_motor_spiral_parameters(
        sizing_mode, start_radius, turns, track_width, spacing, spacing_mode,
        available_diameter, target_length, fill_ratio, layer_count,
        via_diameter, via_clearance, minimum_track_width=0.0,
        minimum_clearance=0.0, coil_shape="circular",
        shape_aspect_ratio=1.0, shape_taper_ratio=0.0,
        motor_layout="single", motor_pole_pairs=1,
        motor_orientation="radial", motor_array_radius=0.0,
        motor_linear_pitch=0.0, motor_slot_count=0,
        motor_inner_ratio=0.58, motor_edge_clearance=1.0,
        motor_slot_gap=1.0):
    """Resolve one coil and its complete motor array inside the diameter limit.

    In automatic sizing modes, ``available_diameter`` is the circular envelope
    for the whole radial/linear motor arrangement, not the diameter of every
    repeated pole coil. Manual sizing remains unchanged and only reports the
    resulting complete-array envelope.
    """
    requested_diameter = float(available_diameter)
    if coil_shape == "motor_sector":
        return resolve_motor_sector_parameters(
            sizing_mode, turns, track_width, spacing, spacing_mode,
            requested_diameter, target_length, fill_ratio, layer_count,
            minimum_track_width, minimum_clearance, motor_pole_pairs,
            motor_slot_count, motor_inner_ratio, motor_edge_clearance,
            motor_slot_gap,
        )
    requested_slots = min(128, max(0, int(motor_slot_count)))
    count = (
        requested_slots if requested_slots > 0
        else 2 * min(64, max(1, int(motor_pole_pairs)))
    )
    layout = motor_layout if motor_layout in MOTOR_LAYOUTS else "single"
    if coil_shape not in MOTOR_SHAPES:
        layout = "single"
        count = 1

    def solve(candidate_diameter, enforce_minimums):
        resolved = resolve_spiral_parameters(
            sizing_mode=sizing_mode,
            start_radius=start_radius,
            turns=turns,
            track_width=track_width,
            spacing=spacing,
            spacing_mode=spacing_mode,
            available_diameter=candidate_diameter,
            target_length=target_length,
            fill_ratio=fill_ratio,
            layer_count=layer_count,
            via_diameter=via_diameter,
            via_clearance=via_clearance,
            minimum_track_width=(
                minimum_track_width if enforce_minimums else 0.0
            ),
            minimum_clearance=(
                minimum_clearance if enforce_minimums else 0.0
            ),
            coil_shape=coil_shape,
            shape_aspect_ratio=shape_aspect_ratio,
            shape_taper_ratio=shape_taper_ratio,
        )
        arrangement = resolve_motor_arrangement(
            coil_shape, layout, motor_pole_pairs, motor_orientation,
            motor_array_radius, motor_linear_pitch,
            resolved["outer_radius"], resolved["track_width"],
            resolved["clearance"], shape_aspect_ratio,
            shape_taper_ratio, motor_slot_count,
            resolved["outer_diameter"] / 2.0,
        )
        resolved["array_outer_diameter"] = motor_array_outer_diameter(
            arrangement, resolved["outer_diameter"]
        )
        return resolved, arrangement

    if sizing_mode == "manual" or layout == "single":
        return solve(requested_diameter, True)
    if requested_diameter <= 0.0:
        raise GeometryError("available_diameter_invalid")

    tolerance = max(1e-8, requested_diameter * 1e-8)
    if sizing_mode == "fit_turns":
        low = 0.0
        high = requested_diameter
        best_diameter = None
        for _index in range(40):
            candidate = (low + high) / 2.0
            try:
                resolved, arrangement = solve(candidate, False)
            except GeometryError as error:
                if error.code in (
                        "available_diameter_too_small",
                        "auto_size_not_converged"):
                    low = candidate
                    continue
                if error.code in (
                        "motor_array_radius_too_small",
                        "motor_linear_pitch_too_small"):
                    high = candidate
                    continue
                raise
            if resolved["array_outer_diameter"] <= requested_diameter + tolerance:
                best_diameter = candidate
                low = candidate
            else:
                high = candidate
        if best_diameter is None:
            raise GeometryError("available_diameter_too_small")
        resolved, arrangement = solve(best_diameter, True)
    else:
        candidate = _motor_coil_diameter_estimate(
            requested_diameter, coil_shape, layout, count,
            motor_orientation, motor_array_radius, motor_linear_pitch,
            minimum_track_width, minimum_clearance,
            shape_aspect_ratio, shape_taper_ratio,
        )
        if candidate <= 0.0:
            raise GeometryError("available_diameter_too_small")
        resolved, arrangement = solve(candidate, True)
        if resolved["array_outer_diameter"] > requested_diameter + tolerance:
            candidate *= (
                requested_diameter / resolved["array_outer_diameter"]
            ) * 0.999
            if candidate <= 0.0:
                raise GeometryError("available_diameter_too_small")
            resolved, arrangement = solve(candidate, True)

    if resolved["array_outer_diameter"] > requested_diameter + tolerance:
        raise GeometryError("available_diameter_too_small")
    resolved["requested_array_diameter"] = requested_diameter
    return resolved, arrangement

def required_inner_radius(layer_count, via_diameter, via_clearance, track_width):
    """Return the minimum radius for inner vias and the inner free terminal."""
    layer_count = max(1, int(layer_count))
    if layer_count <= 1:
        return 0.0
    envelope = _clearance_envelope(
        via_diameter, via_clearance, track_width
    )
    inner_lane_count = (layer_count + 1) // 2
    max_offset = (inner_lane_count - 1) * envelope
    return envelope + hypot(max_offset, envelope)


def multilayer_connection_layout(center, inner_endpoint, outer_endpoint,
                                 outer_radius, layer_count, via_diameter,
                                 via_clearance, track_width):
    """Plan compact, clearance-aware transition vias and free-terminal leads."""
    layer_count = max(1, int(layer_count))
    transition_count = layer_count - 1
    if transition_count <= 0:
        return {"via_points": {}, "terminal_routes": []}

    center_x, center_y = float(center[0]), float(center[1])
    envelope = _clearance_envelope(
        via_diameter, via_clearance, track_width
    )
    pitch = 2.0 * envelope

    def unit_vectors(endpoint, error_code):
        dx = float(endpoint[0]) - center_x
        dy = float(endpoint[1]) - center_y
        length = hypot(dx, dy)
        if length <= 0.0:
            raise GeometryError(error_code)
        radial = (dx / length, dy / length)
        tangent = (-radial[1], radial[0])
        return length, radial, tangent

    def point_on_line(radial, tangent, line_radius, offset):
        return (
            int(round(
                center_x + radial[0] * line_radius + tangent[0] * offset
            )),
            int(round(
                center_y + radial[1] * line_radius + tangent[1] * offset
            )),
        )

    inner_radius, inner_radial, inner_tangent = unit_vectors(
        inner_endpoint, "inner_radius_too_small"
    )
    _outer_endpoint_radius, outer_radial, outer_tangent = unit_vectors(
        outer_endpoint, "outer_endpoint_at_center"
    )

    inner_transitions = list(range(0, transition_count, 2))
    outer_transitions = list(range(1, transition_count, 2))
    final_endpoint_index = 1 if layer_count % 2 == 0 else 0

    inner_has_terminal = final_endpoint_index == 0
    inner_lane_count = len(inner_transitions) + int(inner_has_terminal)
    inner_offsets = _centered_offsets(inner_lane_count, pitch)
    inner_terminal_offset = None
    if inner_has_terminal:
        inner_terminal_offset = inner_offsets.pop()
    inner_max_offset = max(
        [abs(value) for value in inner_offsets]
        + ([abs(inner_terminal_offset)] if inner_terminal_offset is not None else [0.0])
    )
    required_radius = envelope + hypot(inner_max_offset, envelope)
    if inner_radius + 1.0 < required_radius:
        raise GeometryError(
            "inner_radius_too_small", required=required_radius
        )
    inner_radial_gap = hypot(inner_max_offset, envelope)
    inner_line_radius = max(envelope, inner_radius - inner_radial_gap)

    outer_terminal_count = 2 if final_endpoint_index == 1 else 1
    outer_lane_count = len(outer_transitions) + outer_terminal_count
    outer_offsets = _centered_offsets(outer_lane_count, pitch)
    if outer_terminal_count == 2:
        start_terminal_offset = outer_offsets.pop(0)
        final_terminal_offset = outer_offsets.pop()
    else:
        start_terminal_offset = outer_offsets.pop(0)
        final_terminal_offset = None
    outer_max_offset = max(
        [abs(value) for value in outer_offsets]
        + [abs(start_terminal_offset)]
        + ([abs(final_terminal_offset)]
           if final_terminal_offset is not None else [0.0])
    )
    outer_radial_gap = hypot(outer_max_offset, envelope)
    outer_line_radius = float(outer_radius) + outer_radial_gap

    via_points = {}
    for transition, offset in zip(inner_transitions, inner_offsets):
        via_points[transition] = point_on_line(
            inner_radial, inner_tangent, inner_line_radius, offset
        )
    for transition, offset in zip(outer_transitions, outer_offsets):
        via_points[transition] = point_on_line(
            outer_radial, outer_tangent, outer_line_radius, offset
        )

    terminal_routes = [(
        0,
        1,
        point_on_line(
            outer_radial, outer_tangent,
            outer_line_radius, start_terminal_offset,
        ),
    )]
    if final_endpoint_index == 1:
        terminal_routes.append((
            layer_count - 1,
            1,
            point_on_line(
                outer_radial, outer_tangent,
                outer_line_radius, final_terminal_offset,
            ),
        ))
    else:
        terminal_routes.append((
            layer_count - 1,
            0,
            point_on_line(
                inner_radial, inner_tangent,
                inner_line_radius, inner_terminal_offset,
            ),
        ))


    return {
        "via_points": via_points,
        "terminal_routes": terminal_routes,
    }


def motor_sector_connection_layout(
        board_center, layer_paths, board_outer_radius, board_inner_radius,
        edge_clearance, via_diameter, via_clearance, track_width,
        trace_clearance=0.0):
    """Route sector-layer transitions only through verified free copper space.

    Generic spiral fanout assumes circular endpoints around the coil center. A
    sector endpoint sits on a corner of an offset annular contour, so that
    assumption can put transition vias on another turn. This planner searches the
    sector window/slot gap and rejects every candidate whose plated through-hole
    or lead would touch winding copper on any layer, another via, or a same-layer
    connector.
    """
    paths = [tuple((float(x), float(y)) for x, y in path)
             for path in layer_paths]
    layer_count = len(paths)
    if layer_count <= 1:
        return {"via_points": {}, "terminal_routes": []}
    if any(len(path) < 2 for path in paths):
        raise GeometryError("motor_sector_connection_space")

    board_x, board_y = float(board_center[0]), float(board_center[1])
    outer_radius = float(board_outer_radius)
    inner_radius = max(0.0, float(board_inner_radius))
    edge = max(0.0, float(edge_clearance))
    via_radius = float(via_diameter) / 2.0
    width = float(track_width)
    via_envelope = _clearance_envelope(
        via_diameter, via_clearance, track_width
    )
    via_pitch = 2.0 * via_envelope
    no_touch = width + max(1.0, abs(width) * 1e-6)
    trace_gap = max(0.0, float(trace_clearance))

    def point_segment_distance(point, start, end):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length_squared = dx * dx + dy * dy
        if length_squared <= 1e-24:
            return hypot(point[0] - start[0], point[1] - start[1])
        projection = (
            (point[0] - start[0]) * dx
            + (point[1] - start[1]) * dy
        ) / length_squared
        projection = min(1.0, max(0.0, projection))
        closest = (
            start[0] + projection * dx,
            start[1] + projection * dy,
        )
        return hypot(point[0] - closest[0], point[1] - closest[1])

    def orientation(first, second, third):
        return (
            (second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0])
        )

    def segment_distance(first_start, first_end, second_start, second_end):
        if (
                orientation(first_start, first_end, second_start)
                * orientation(first_start, first_end, second_end) <= 0.0
                and orientation(second_start, second_end, first_start)
                * orientation(second_start, second_end, first_end) <= 0.0):
            return 0.0
        return min(
            point_segment_distance(first_start, second_start, second_end),
            point_segment_distance(first_end, second_start, second_end),
            point_segment_distance(second_start, first_start, first_end),
            point_segment_distance(second_end, first_start, first_end),
        )

    segments_by_layer = [
        tuple(zip(path, path[1:])) for path in paths
    ]
    all_winding_segments = tuple(dict.fromkeys(
        tuple(sorted((start, end)))
        for segments in segments_by_layer
        for start, end in segments
    ))
    unrelated_segments = [
        (frozenset(segments[2:]), frozenset(segments[:-2]))
        for segments in segments_by_layer
    ]

    # Candidate searching used to compare every point with every arc segment.
    # A small spatial hash keeps full geometric checks while making dense,
    # many-segment sector windings practical.
    grid_size = max(via_envelope, width + trace_gap, 1.0)

    def grid_keys(min_x, min_y, max_x, max_y):
        first_x = int(min_x // grid_size)
        last_x = int(max_x // grid_size)
        first_y = int(min_y // grid_size)
        last_y = int(max_y // grid_size)
        for grid_x in range(first_x, last_x + 1):
            for grid_y in range(first_y, last_y + 1):
                yield (grid_x, grid_y)

    def segment_index(segments):
        index = {}
        for segment in segments:
            start, end = segment
            for key in grid_keys(
                    min(start[0], end[0]), min(start[1], end[1]),
                    max(start[0], end[0]), max(start[1], end[1])):
                index.setdefault(key, []).append(segment)
        return index

    def nearby_segments(index, start, end, clearance):
        seen = set()
        for key in grid_keys(
                min(start[0], end[0]) - clearance,
                min(start[1], end[1]) - clearance,
                max(start[0], end[0]) + clearance,
                max(start[1], end[1]) + clearance):
            for segment in index.get(key, ()):
                if segment not in seen:
                    seen.add(segment)
                    yield segment

    layer_segment_indices = [
        segment_index(segments) for segments in segments_by_layer
    ]
    all_segment_index = segment_index(all_winding_segments)
    endpoints = [(path[0], path[-1]) for path in paths]
    all_copper_layers = frozenset(range(layer_count))
    via_points = {}
    terminal_routes = []
    planned_vias = []
    planned_leads = []

    angle_offsets = [0]
    for value in range(5, 181, 5):
        angle_offsets.extend((value, -value))

    def in_board(point, radius):
        distance = hypot(point[0] - board_x, point[1] - board_y)
        return (
            inner_radius + edge + radius <= distance
            <= outer_radius - edge - radius
        )

    def candidate_points(anchor, endpoint_index, layers, is_via):
        if endpoint_index == 0:
            preferred = atan2(board_y - anchor[1], board_x - anchor[0])
        else:
            # Start by moving toward the annular slot gap; board bounds and
            # copper-clearance tests choose the safe side automatically.
            preferred = atan2(
                anchor[1] - board_y, anchor[0] - board_x
            )
        point_radius = via_radius if is_via else width / 2.0
        point_clearance = (
            via_envelope if is_via else width + trace_gap
        )
        base_distance = max(
            point_clearance * 1.1,
            float(via_diameter) if is_via else width + trace_gap,
        )
        distance_step = max(width, via_envelope * 0.45)
        for distance_index in range(28):
            distance = base_distance + distance_index * distance_step
            for offset_degrees in angle_offsets:
                angle = preferred + offset_degrees * pi / 180.0
                candidate = (
                    float(int(round(anchor[0] + distance * cos(angle)))),
                    float(int(round(anchor[1] + distance * sin(angle)))),
                )
                if not in_board(candidate, point_radius):
                    continue
                if is_via:
                    relevant_winding = nearby_segments(
                        all_segment_index, candidate, candidate,
                        point_clearance,
                    )
                else:
                    relevant_winding = (
                        segment
                        for layer in layers
                        for segment in nearby_segments(
                            layer_segment_indices[layer], candidate, candidate,
                            point_clearance,
                        )
                    )
                if any(
                        point_segment_distance(candidate, start, end)
                        + 1.0 < point_clearance
                        for start, end in relevant_winding):
                    continue

                connector = (anchor, candidate)
                lead_clear = True
                for layer in layers:
                    unrelated = unrelated_segments[layer][endpoint_index]
                    if any(
                            segment in unrelated and segment_distance(
                                connector[0], connector[1],
                                segment[0], segment[1],
                            ) + 1.0 < no_touch
                            for segment in nearby_segments(
                                layer_segment_indices[layer],
                                connector[0], connector[1], no_touch,
                            )):
                        lead_clear = False
                        break
                if not lead_clear:
                    continue

                if is_via and any(
                        hypot(candidate[0] - point[0],
                              candidate[1] - point[1]) + 1.0 < via_pitch
                        for point, _via_layers in planned_vias):
                    continue
                if any(
                        set(layers).intersection(via_layers)
                        and point_segment_distance(
                            point, connector[0], connector[1]
                        ) + 1.0 < via_envelope
                        for point, via_layers in planned_vias):
                    continue
                if is_via and any(
                        set(layers).intersection(lead_layers)
                        and point_segment_distance(
                            candidate, lead[0], lead[1]
                        ) + 1.0 < via_envelope
                        for lead, lead_layers in planned_leads):
                    continue
                same_layer_conflict = False
                for lead, lead_layers in planned_leads:
                    if not set(layers).intersection(lead_layers):
                        continue
                    # Different requests on the same layer must not intersect
                    # or run close enough to bypass the winding.
                    if segment_distance(
                            connector[0], connector[1],
                            lead[0], lead[1]) + 1.0 < no_touch:
                        same_layer_conflict = True
                        break
                if same_layer_conflict:
                    continue
                yield (int(candidate[0]), int(candidate[1]))

    def place_transition_group(transitions, group_index=0):
        if group_index >= len(transitions):
            return True
        transition = transitions[group_index]
        endpoint_index = connector_endpoint_index(transition)
        layers = (transition, transition + 1)
        anchor = endpoints[transition][endpoint_index]
        candidate_count = 0
        for point in candidate_points(anchor, endpoint_index, layers, True):
            candidate_count += 1
            via_points[transition] = point
            # A normal plated through-hole has copper on every board layer,
            # so later leads must keep clear even when they target a different
            # adjacent winding pair.
            planned_vias.append((point, all_copper_layers))
            planned_leads.append(((anchor, point), frozenset(layers)))
            if place_transition_group(transitions, group_index + 1):
                return True
            planned_leads.pop()
            planned_vias.pop()
            del via_points[transition]
            if candidate_count >= 180:
                break
        return False

    for endpoint_index in (0, 1):
        transitions = tuple(
            transition for transition in range(layer_count - 1)
            if connector_endpoint_index(transition) == endpoint_index
        )
        if transitions and not place_transition_group(transitions):
            raise GeometryError(
                "motor_sector_connection_space",
                endpoint=endpoint_index, layers=layer_count, via=True,
            )

    return {
        "via_points": via_points,
        "terminal_routes": terminal_routes,
    }


def connector_via_points(center, inner_endpoint, outer_endpoint, outer_radius,
                         layer_count, via_diameter, via_clearance, track_width):
    """Return transition-via positions from the shared multilayer layout."""
    return multilayer_connection_layout(
        center, inner_endpoint, outer_endpoint, outer_radius,
        layer_count, via_diameter, via_clearance, track_width,
    )["via_points"]

