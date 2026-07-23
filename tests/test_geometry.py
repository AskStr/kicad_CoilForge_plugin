import math
import unittest

from coilforge.geometry import (
    GeometryError,
    iter_motor_sector_spiral_segments, motor_sector_dimensions,
    motor_sector_spiral_length, resolve_motor_sector_parameters,
    axial_flux_motor_dimensions,
    connector_endpoint_index,
    connector_via_points,
    estimate_axial_flux_motor_torque,
    estimate_dc_metrics,
    fit_spiral_by_length,
    fit_spiral_by_turns,
    iter_shaped_spiral_segments,
    iter_spiral_arcs,
    iter_spiral_segments,
    multilayer_connection_layout, motor_sector_connection_layout,
    multilayer_track_count,
    motor_array_instances,
    motor_inner_trace_dfm,
    required_inner_radius,
    resolve_motor_arrangement,
    resolve_motor_spiral_parameters,
    resolve_spiral_parameters,
    segment_count,
    shape_area_scale, shape_extent_scale,
    shaped_spiral_length,
    spiral_length,
)


class MotorSectorGeometryTests(unittest.TestCase):
    def test_sector_spiral_stays_inside_board_annulus_and_one_slot(self):
        scale = 1000.0
        dimensions = motor_sector_dimensions(
            100.0, 40.0, 12, 0.3, 0.15, 1.0, 0.8
        )
        turns = min(10.0, dimensions["max_turns"] * 0.9)
        segments = list(iter_motor_sector_spiral_segments(
            dimensions["array_radius"] * scale, 0,
            100.0 * scale, 40.0 * scale, 12,
            0.3 * scale, 0.15 * scale, turns, 64,
            edge_clearance=1.0 * scale, slot_gap=0.8 * scale,
        ))
        self.assertGreater(len(segments), 100)
        minimum_radius = 20.0 + 1.0
        maximum_radius = 50.0 - 1.0
        half_angle = dimensions["usable_half_angle"] + 1e-3
        for point in [point for segment in segments for point in segment]:
            x, y = point[0] / scale, point[1] / scale
            radius = math.hypot(x, y)
            self.assertGreaterEqual(radius, minimum_radius - 0.2)
            self.assertLessEqual(radius, maximum_radius + 0.2)
            self.assertLessEqual(abs(math.atan2(y, x)), half_angle)

    def test_larger_board_and_fewer_slots_allow_more_turns(self):
        compact = motor_sector_dimensions(
            80, 36, 18, 0.3, 0.15, 1.0, 0.8
        )
        large = motor_sector_dimensions(
            120, 36, 12, 0.3, 0.15, 1.0, 0.8
        )
        self.assertGreater(large["max_turns"], compact["max_turns"])
        self.assertGreater(large["outer_half_width"], compact["outer_half_width"])

    def test_sector_length_increases_with_turn_count(self):
        short = motor_sector_spiral_length(100, 40, 12, 0.25, 0.15, 4)
        long = motor_sector_spiral_length(100, 40, 12, 0.25, 0.15, 8)
        self.assertGreater(short, 0.0)
        self.assertGreater(long, short)

    def test_sector_fit_turns_uses_full_board_and_process_limits(self):
        resolved, arrangement = resolve_motor_sector_parameters(
            "fit_turns", 8, 0.25, 0.5, "pitch",
            100, 0, 0.60, 2, 0.20, 0.15,
            motor_pole_pairs=6, motor_slot_count=12,
            motor_inner_ratio=0.40, edge_clearance=1.0, slot_gap=0.8,
        )
        self.assertEqual(12, arrangement["count"])
        self.assertAlmostEqual(100.0, resolved["array_outer_diameter"])
        self.assertAlmostEqual(40.0, resolved["motor_board_inner_diameter"])
        self.assertGreaterEqual(resolved["track_width"], 0.20)
        self.assertGreaterEqual(resolved["clearance"], 0.15)
        self.assertAlmostEqual(8.0, resolved["turns"])

    def test_sector_rejects_turn_count_that_cannot_fit(self):
        with self.assertRaises(GeometryError) as raised:
            resolve_motor_sector_parameters(
                "manual", 50, 0.4, 0.2, "clearance",
                80, 0, 0.5, 1, 0.1, 0.1,
                motor_pole_pairs=9, motor_slot_count=18,
                motor_inner_ratio=0.55,
            )
        self.assertEqual("motor_sector_turns_too_large", raised.exception.code)


    def test_sector_short_arc_keeps_the_requested_turn_clearance(self):
        scale = 1_000_000.0
        width = 0.508848 * scale
        clearance = 0.15 * scale
        segments_per_turn = 128
        segments = list(iter_motor_sector_spiral_segments(
            0, 0, 100.0 * scale, 40.0 * scale, 12,
            width, clearance, 7, segments_per_turn, 0,
            1.0 * scale, 0.8 * scale,
        ))
        points = [segments[0][0]] + [end for _start, end in segments]
        one_turn_distances = [
            math.hypot(
                points[index + segments_per_turn][0] - points[index][0],
                points[index + segments_per_turn][1] - points[index][1],
            )
            for index in range(len(points) - segments_per_turn)
        ]
        self.assertGreaterEqual(
            min(one_turn_distances) + 2.0, width + clearance
        )

    def test_sector_through_vias_stay_outside_every_layer_winding(self):
        scale = 1_000_000.0
        width = 0.508848 * scale
        clearance = 0.15 * scale
        via_diameter = 0.8 * scale
        via_clearance = 0.25 * scale
        dimensions = motor_sector_dimensions(
            100.0 * scale, 40.0 * scale, 12, width, clearance,
            1.0 * scale, 0.8 * scale,
        )
        paths = []
        for layer in range(4):
            segments = list(iter_motor_sector_spiral_segments(
                0, 0, 100.0 * scale, 40.0 * scale, 12,
                width, clearance, 7, 128, 0,
                1.0 * scale, 0.8 * scale, 0.0, bool(layer % 2),
            ))
            paths.append([segments[0][0]] + [
                end for _start, end in segments
            ])
        layout = motor_sector_connection_layout(
            (-dimensions["array_radius"], 0), paths,
            dimensions["board_outer_radius"],
            dimensions["board_inner_radius"], 1.0 * scale,
            via_diameter, via_clearance, width, clearance,
        )
        envelope = width / 2.0 + via_diameter / 2.0 + via_clearance

        def point_segment_distance(point, start, end):
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length_squared = dx * dx + dy * dy
            projection = (
                (point[0] - start[0]) * dx
                + (point[1] - start[1]) * dy
            ) / float(length_squared)
            projection = min(1.0, max(0.0, projection))
            closest = (
                start[0] + projection * dx,
                start[1] + projection * dy,
            )
            return math.hypot(
                point[0] - closest[0], point[1] - closest[1]
            )

        self.assertEqual(3, len(layout["via_points"]))
        self.assertEqual(3, len(set(layout["via_points"].values())))
        for via_point in layout["via_points"].values():
            for path in paths:
                minimum = min(
                    point_segment_distance(via_point, start, end)
                    for start, end in zip(path, path[1:])
                )
                self.assertGreaterEqual(minimum + 2.0, envelope)
        points = list(layout["via_points"].values())
        for index, point in enumerate(points):
            for other in points[index + 1:]:
                self.assertGreaterEqual(
                    math.hypot(point[0] - other[0], point[1] - other[1])
                    + 2.0,
                    2.0 * envelope,
                )


class ShapeAreaTests(unittest.TestCase):
    def test_shape_area_scales_match_basic_profiles(self):
        self.assertAlmostEqual(math.pi, shape_area_scale(
            "circular", 1.0, 0.0
        ), places=3)
        self.assertAlmostEqual(1.6 * math.pi, shape_area_scale(
            "motor_ellipse", 1.6, 0.0
        ), places=3)
        self.assertGreater(
            shape_area_scale("motor_racetrack", 1.8, 0.0), math.pi
        )


class GeometryTests(unittest.TestCase):
    def test_motor_radial_array_uses_pole_pairs_and_alternating_winding(self):
        instances = motor_array_instances(
            10.0, 20.0, "motor_trapezoid", "radial", 3,
            array_radius=30.0, array_angle_radians=0.0,
            orientation="radial", alternate_winding=True,
        )
        self.assertEqual(6, len(instances))
        self.assertAlmostEqual(40.0, instances[0][0])
        self.assertAlmostEqual(20.0, instances[0][1])
        self.assertEqual([False, True, False, True, False, True], [
            instance[3] for instance in instances
        ])

    def test_explicit_motor_slot_count_overrides_two_poles_per_pair(self):
        arrangement = resolve_motor_arrangement(
            "motor_trapezoid", "radial", 7, "radial",
            50.0, 0.0, 5.0, 0.2, slot_count=12,
        )
        self.assertEqual(12, arrangement["count"])
        instances = motor_array_instances(
            0.0, 0.0, "motor_trapezoid", "radial", 7,
            arrangement["array_radius"], 0.0, slot_count=12,
        )
        self.assertEqual(12, len(instances))

    def test_motor_linear_array_is_centered_and_can_rotate_across_axis(self):
        instances = motor_array_instances(
            0.0, 0.0, "motor_racetrack", "linear", 2,
            linear_pitch=10.0, array_angle_radians=0.0,
            orientation="tangential", alternate_winding=False,
        )
        self.assertEqual([-15.0, -5.0, 5.0, 15.0], [
            instance[0] for instance in instances
        ])
        self.assertTrue(all(abs(instance[2] - math.pi / 2.0) < 1e-12
                            for instance in instances))

    def test_motor_arrangement_auto_spacing_prevents_overlap(self):
        radial = resolve_motor_arrangement(
            "motor_trapezoid", "radial", 6, "radial", 0.0, 0.0,
            10.0, 0.3, 0.2, 1.65, 0.45,
        )
        linear = resolve_motor_arrangement(
            "motor_racetrack", "linear", 3, "radial", 0.0, 0.0,
            8.0, 0.3, 0.2, 1.8, 0.0,
        )
        self.assertEqual(12, radial["count"])
        self.assertGreater(radial["array_radius"], 0.0)
        self.assertEqual(6, linear["count"])
        self.assertGreater(linear["linear_pitch"], 0.0)

    def test_motor_fit_turns_uses_total_twenty_mm_array_diameter(self):
        resolved, arrangement = resolve_motor_spiral_parameters(
            sizing_mode="fit_turns",
            start_radius=0.0,
            turns=5.0,
            track_width=0.25,
            spacing=0.5,
            spacing_mode="pitch",
            available_diameter=20.0,
            target_length=1000.0,
            fill_ratio=0.5,
            layer_count=1,
            via_diameter=0.6,
            via_clearance=0.25,
            minimum_track_width=0.1,
            minimum_clearance=0.1,
            coil_shape="motor_trapezoid",
            shape_aspect_ratio=1.65,
            shape_taper_ratio=0.45,
            motor_layout="radial",
            motor_pole_pairs=3,
            motor_orientation="radial",
            motor_slot_count=12,
        )
        self.assertEqual(12, arrangement["count"])
        self.assertLess(resolved["outer_diameter"], 20.0)
        self.assertLessEqual(resolved["array_outer_diameter"], 20.0 + 1e-6)
        self.assertAlmostEqual(20.0, resolved["array_outer_diameter"], places=5)
        self.assertGreaterEqual(resolved["track_width"], 0.1)
        self.assertGreaterEqual(resolved["clearance"], 0.1)

    def test_manual_motor_array_reports_unconstrained_total_diameter(self):
        resolved, arrangement = resolve_motor_spiral_parameters(
            sizing_mode="manual",
            start_radius=1.0,
            turns=5.0,
            track_width=0.2,
            spacing=0.4,
            spacing_mode="pitch",
            available_diameter=20.0,
            target_length=1000.0,
            fill_ratio=0.5,
            layer_count=1,
            via_diameter=0.6,
            via_clearance=0.25,
            coil_shape="motor_trapezoid",
            shape_aspect_ratio=1.65,
            shape_taper_ratio=0.45,
            motor_layout="radial",
            motor_pole_pairs=3,
            motor_orientation="radial",
        )
        self.assertEqual(6, arrangement["count"])
        self.assertGreater(
            resolved["array_outer_diameter"], resolved["outer_diameter"]
        )

    def test_fractional_turns_are_supported(self):
        self.assertEqual(15, segment_count(1.5, 10, 0))
        self.assertEqual(17, segment_count(1.5, 10, 2))

    def test_segments_are_contiguous(self):
        segments = list(iter_spiral_segments(0, 0, 100, 40, 1, 4, 0))
        self.assertEqual(4, len(segments))
        for previous, current in zip(segments, segments[1:]):
            self.assertEqual(previous[1], current[0])

    def test_one_turn_increases_radius_by_pitch(self):
        segments = list(iter_spiral_segments(0, 0, 100, 40, 1, 4, 0))
        start = segments[0][0]
        end = segments[-1][1]
        self.assertEqual((100, 0), start)
        self.assertEqual((140, 0), end)

    def test_incremental_rotation_stays_aligned_on_large_spiral(self):
        turns = 20
        per_turn = 257
        pitch = 1000
        segments = list(iter_spiral_segments(10, -20, 500, pitch, turns, per_turn, 0))
        end = segments[-1][1]
        angle = 2.0 * math.pi * turns
        radius = 500 + pitch * turns
        direct = (
            int(round(10 + radius * math.cos(angle))),
            int(round(-20 + radius * math.sin(angle))),
        )
        self.assertEqual(direct, end)

    def test_arc_primitives_are_contiguous_and_close_whole_turn(self):
        arcs = list(iter_spiral_arcs(0, 0, 1000, 400, 2, 16, 0))
        self.assertEqual(32, len(arcs))
        for previous, current in zip(arcs, arcs[1:]):
            self.assertEqual(previous[2], current[0])
        self.assertEqual((1000, 0), arcs[0][0])
        self.assertEqual((1800, 0), arcs[-1][2])

    def test_exact_spiral_length_is_longer_than_radial_growth(self):
        length = spiral_length(1.0, 0.5, 10)
        self.assertGreater(length, 5.0)

    def test_shaped_circular_segments_match_original_generator(self):
        expected = list(iter_spiral_segments(
            10, -20, 1000, 400, 1.5, 32, 3, 0.25, True
        ))
        actual = list(iter_shaped_spiral_segments(
            10, -20, 1000, 400, 1.5, 32, 3, 0.25, True,
            "circular", 2.0, 0.5,
        ))
        self.assertEqual(expected, actual)

    def test_motor_shapes_are_contiguous_and_share_whole_turn_endpoints(self):
        for shape, aspect, taper in (
                ("motor_ellipse", 1.6, 0.0),
                ("motor_racetrack", 1.8, 0.0),
                ("motor_trapezoid", 1.65, 0.45)):
            clockwise = list(iter_shaped_spiral_segments(
                0, 0, 1000, 400, 2, 128, 0, 0.0, False,
                shape, aspect, taper,
            ))
            counterclockwise = list(iter_shaped_spiral_segments(
                0, 0, 1000, 400, 2, 128, 0, 0.0, True,
                shape, aspect, taper,
            ))
            self.assertEqual(256, len(clockwise))
            for previous, current in zip(clockwise, clockwise[1:]):
                self.assertEqual(previous[1], current[0])
            self.assertEqual(clockwise[0][0], counterclockwise[0][0])
            self.assertEqual(clockwise[-1][1], counterclockwise[-1][1])

    def test_racetrack_and_tapered_pole_use_smooth_straight_runs(self):
        for shape, taper, minimum_straight_vertices in (
                ("motor_racetrack", 0.0, 120),
                ("motor_trapezoid", 0.45, 70)):
            segments = list(iter_shaped_spiral_segments(
                0, 0, 1000000, 0, 1, 512, 0, 0.0, False,
                shape, 1.65, taper,
            ))
            points = [segments[0][0]] + [end for _start, end in segments]
            straight_vertices = 0
            maximum_direction_change = 0.0
            for first, middle, last in zip(
                    points, points[1:], points[2:]):
                before = (
                    middle[0] - first[0], middle[1] - first[1]
                )
                after = (last[0] - middle[0], last[1] - middle[1])
                before_length = math.hypot(*before)
                after_length = math.hypot(*after)
                cross = abs(
                    before[0] * after[1] - before[1] * after[0]
                ) / (before_length * after_length)
                if cross < 1e-4:
                    straight_vertices += 1
                cosine = (
                    before[0] * after[0] + before[1] * after[1]
                ) / (before_length * after_length)
                direction_change = math.acos(max(-1.0, min(1.0, cosine)))
                maximum_direction_change = max(
                    maximum_direction_change, direction_change
                )
            self.assertGreaterEqual(
                straight_vertices, minimum_straight_vertices, shape
            )
            self.assertLess(maximum_direction_change, 0.04, shape)

    def test_all_motor_shapes_avoid_abrupt_sampled_corners(self):
        for shape, aspect, taper in (
                ("motor_ellipse", 1.65, 0.0),
                ("motor_racetrack", 1.65, 0.0),
                ("motor_trapezoid", 1.65, 0.45),
                ("motor_trapezoid", 1.65, -0.45)):
            segments = list(iter_shaped_spiral_segments(
                0, 0, 3000000, 250000, 1, 128, 0, 0.0, False,
                shape, aspect, taper,
            ))
            points = [segments[0][0]] + [end for _start, end in segments]
            maximum_direction_change = 0.0
            for first, middle, last in zip(
                    points, points[1:], points[2:]):
                before = (
                    middle[0] - first[0], middle[1] - first[1]
                )
                after = (last[0] - middle[0], last[1] - middle[1])
                denominator = math.hypot(*before) * math.hypot(*after)
                cosine = (
                    before[0] * after[0] + before[1] * after[1]
                ) / denominator
                maximum_direction_change = max(
                    maximum_direction_change,
                    math.acos(max(-1.0, min(1.0, cosine))),
                )
            self.assertLess(maximum_direction_change, 0.16, shape)

    def test_tapered_pole_keeps_a_rounded_fan_silhouette(self):
        for taper, expected_side in ((0.45, 1), (-0.45, -1)):
            segments = list(iter_shaped_spiral_segments(
                0, 0, 1000000, 0, 1, 512, 0, 0.0, False,
                "motor_trapezoid", 1.65, taper,
            ))
            points = [segments[0][0]] + [
                end for _start, end in segments
            ]
            top = max(points, key=lambda point: point[1])
            horizontal_extent = max(abs(point[0]) for point in points)
            self.assertGreater(
                expected_side * top[0], 0.60 * horizontal_extent
            )
            self.assertLess(abs(top[0]), horizontal_extent)

    def test_motor_shape_envelopes_and_taper_are_directional(self):
        self.assertAlmostEqual(1.6, shape_extent_scale(
            "motor_ellipse", 1.6, 0.0
        ), places=6)
        segments = list(iter_shaped_spiral_segments(
            0, 0, 1000, 0, 1, 128, 0, 0.0, False,
            "motor_trapezoid", 1.65, 0.45,
        ))
        points = [segments[0][0]] + [end for _start, end in segments]
        self.assertGreater(abs(points[16][1]), abs(points[48][1]))

    def test_tapered_shape_never_compresses_nominal_radial_pitch(self):
        pitch = 400
        segments = list(iter_shaped_spiral_segments(
            0, 0, 1000, pitch, 2, 128, 0, 0.0, False,
            "motor_trapezoid", 1.65, 0.75,
        ))
        points = [segments[0][0]] + [end for _start, end in segments]
        for index in range(129):
            inner = points[index]
            outer = points[index + 128]
            self.assertGreaterEqual(
                math.hypot(outer[0] - inner[0], outer[1] - inner[1]),
                pitch - 2.0,
            )

    def test_motor_fit_length_uses_actual_shaped_centerline_length(self):
        result = resolve_spiral_parameters(
            sizing_mode="fit_length", start_radius=2.0, turns=6.0,
            track_width=0.25, spacing=0.5, spacing_mode="clearance",
            available_diameter=60.0, target_length=1000.0,
            fill_ratio=0.6, layer_count=1, via_diameter=0.8,
            via_clearance=0.25, minimum_track_width=0.1,
            minimum_clearance=0.1, coil_shape="motor_racetrack",
            shape_aspect_ratio=1.8, shape_taper_ratio=0.0,
        )
        self.assertAlmostEqual(
            1000.0, result["total_spiral_length"], places=5
        )
        self.assertAlmostEqual(
            shaped_spiral_length(
                result["start_radius"], result["pitch"], result["turns"],
                "motor_racetrack", 1.8, 0.0,
            ),
            result["length_per_layer"],
            places=6,
        )
        self.assertLessEqual(result["outer_diameter"], 60.0 + 1e-6)

    def test_fit_by_turns_uses_requested_diameter_and_fill_ratio(self):
        result = fit_spiral_by_turns(40.0, 2.0, 10.0, 0.5)
        self.assertAlmostEqual(40.0, result["outer_diameter"], places=9)
        self.assertAlmostEqual(
            0.5, result["track_width"] / result["pitch"], places=9
        )
        self.assertAlmostEqual(
            result["pitch"],
            result["track_width"] + result["clearance"],
            places=9,
        )

    def test_fit_by_length_solves_total_multilayer_length(self):
        result = fit_spiral_by_length(
            50.0, 2.0, 2000.0, 0.5, layer_count=4,
            integer_turns=False,
        )
        self.assertAlmostEqual(
            2000.0, result["total_spiral_length"], places=6
        )

    def test_multilayer_length_fit_rounds_to_whole_turns(self):
        result = fit_spiral_by_length(
            50.0, 2.0, 2000.0, 0.5, layer_count=4,
            integer_turns=True,
        )
        self.assertTrue(float(result["turns"]).is_integer())

    def test_auto_sizing_expands_center_for_inner_vias(self):
        result = resolve_spiral_parameters(
            sizing_mode="fit_turns",
            start_radius=0.0,
            turns=8,
            track_width=0.25,
            spacing=0.5,
            spacing_mode="pitch",
            available_diameter=50.0,
            target_length=1000.0,
            fill_ratio=0.5,
            layer_count=12,
            via_diameter=0.8,
            via_clearance=0.25,
            minimum_track_width=0.1,
            minimum_clearance=0.1,
        )
        required = required_inner_radius(
            12, 0.8, 0.25, result["track_width"]
        )
        self.assertGreaterEqual(result["start_radius"] + 1e-8, required)
        self.assertAlmostEqual(50.0, result["outer_diameter"], places=8)

    def test_auto_diameter_includes_outer_via_fanout(self):
        result = resolve_spiral_parameters(
            sizing_mode="fit_turns",
            start_radius=0.0,
            turns=8,
            track_width=0.25,
            spacing=0.5,
            spacing_mode="pitch",
            available_diameter=50.0,
            target_length=1000.0,
            fill_ratio=0.5,
            layer_count=12,
            via_diameter=0.8,
            via_clearance=0.25,
            minimum_track_width=0.0,
            minimum_clearance=0.0,
        )
        scale = 1000000.0
        layout = multilayer_connection_layout(
            (0.0, 0.0),
            (result["start_radius"] * scale, 0.0),
            (result["outer_radius"] * scale, 0.0),
            result["outer_radius"] * scale,
            12,
            0.8 * scale,
            0.25 * scale,
            result["track_width"] * scale,
        )
        outer_extent = max(
            [
                (math.hypot(*point) + 0.4 * scale) / scale
                for point in layout["via_points"].values()
            ]
            + [
                (math.hypot(*route[2])
                 + result["track_width"] * scale / 2.0) / scale
                for route in layout["terminal_routes"]
            ]
        )
        self.assertLessEqual(outer_extent, 25.0 + 1e-6)
        self.assertAlmostEqual(50.0, result["outer_diameter"], places=8)

    def test_auto_sizing_enforces_minimum_track_width(self):
        with self.assertRaises(GeometryError) as context:
            resolve_spiral_parameters(
                sizing_mode="fit_turns",
                start_radius=1.0,
                turns=100,
                track_width=0.25,
                spacing=0.5,
                spacing_mode="pitch",
                available_diameter=20.0,
                target_length=1000.0,
                fill_ratio=0.5,
                layer_count=1,
                via_diameter=0.8,
                via_clearance=0.25,
                minimum_track_width=0.1,
                minimum_clearance=0.0,
            )
        self.assertEqual("track_width_below_minimum", context.exception.code)

    def test_multilayer_count_includes_connector_tracks(self):
        self.assertEqual(7704, multilayer_track_count(10, 64, 0, 12))

    def test_alternating_whole_turn_arc_spirals_share_endpoints(self):
        clockwise = list(iter_spiral_arcs(
            0, 0, 1000, 500, 3, 16, 0, 0.3, False
        ))
        counterclockwise = list(iter_spiral_arcs(
            0, 0, 1000, 500, 3, 16, 0, 0.3, True
        ))
        self.assertEqual(clockwise[0][0], counterclockwise[0][0])
        self.assertEqual(clockwise[-1][2], counterclockwise[-1][2])

    def test_alternating_whole_turn_spirals_share_endpoints(self):
        clockwise = list(iter_spiral_segments(0, 0, 1000, 500, 3, 64, 0, 0.3, False))
        counterclockwise = list(iter_spiral_segments(0, 0, 1000, 500, 3, 64, 0, 0.3, True))
        self.assertEqual(clockwise[0][0], counterclockwise[0][0])
        self.assertEqual(clockwise[-1][1], counterclockwise[-1][1])

    def test_twelve_layer_via_fanout_is_unique_and_outside_coil(self):
        layer_count = 12
        via_diameter = 800
        clearance = 250
        track_width = 250
        start_radius = int(required_inner_radius(
            layer_count, via_diameter, clearance, track_width
        )) + 100
        outer_radius = start_radius + 5000
        points = connector_via_points(
            (0, 0),
            (start_radius, 0),
            (outer_radius, 0),
            outer_radius,
            layer_count,
            via_diameter,
            clearance,
            track_width,
        )
        self.assertEqual(11, len(points))
        self.assertEqual(11, len(set(points.values())))
        for transition, point in points.items():
            radius = math.hypot(*point)
            if connector_endpoint_index(transition) == 0:
                self.assertLess(radius, start_radius)
            else:
                self.assertGreater(radius, outer_radius)

    def test_fanout_connectors_clear_unrelated_through_vias(self):
        layer_count = 12
        via_diameter = 800
        clearance = 250
        track_width = 250
        clearance_envelope = track_width / 2.0 + via_diameter / 2.0 + clearance
        start_radius = int(required_inner_radius(
            layer_count, via_diameter, clearance, track_width
        ))
        outer_radius = start_radius + 50000
        inner_endpoint = (start_radius, 0)
        outer_endpoint = (outer_radius, 0)
        points = connector_via_points(
            (0, 0), inner_endpoint, outer_endpoint, outer_radius,
            layer_count, via_diameter, clearance, track_width,
        )

        def point_to_segment_distance(point, start, end):
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length_squared = dx * dx + dy * dy
            projection = (
                (point[0] - start[0]) * dx
                + (point[1] - start[1]) * dy
            ) / float(length_squared)
            projection = min(1.0, max(0.0, projection))
            closest = (
                start[0] + projection * dx,
                start[1] + projection * dy,
            )
            return math.hypot(point[0] - closest[0], point[1] - closest[1])

        for transition, via_point in points.items():
            endpoint = (
                inner_endpoint
                if connector_endpoint_index(transition) == 0
                else outer_endpoint
            )
            for other_transition, other_via in points.items():
                if other_transition == transition:
                    continue
                distance = point_to_segment_distance(
                    other_via, endpoint, via_point
                )
                self.assertGreaterEqual(distance + 1.0, clearance_envelope)

    def test_even_layer_layout_places_both_free_terminals_outside(self):
        layer_count = 4
        via_diameter = 800
        clearance = 250
        track_width = 250
        start_radius = int(required_inner_radius(
            layer_count, via_diameter, clearance, track_width
        )) + 100
        outer_radius = start_radius + 10000
        layout = multilayer_connection_layout(
            (0, 0), (start_radius, 0), (outer_radius, 0), outer_radius,
            layer_count, via_diameter, clearance, track_width,
        )
        self.assertEqual(0, connector_endpoint_index(0))
        self.assertEqual(1, connector_endpoint_index(1))
        self.assertEqual((0, 1), layout["terminal_routes"][0][:2])
        self.assertEqual((layer_count - 1, 1),
                         layout["terminal_routes"][1][:2])
        terminal_points = [route[2] for route in layout["terminal_routes"]]
        self.assertEqual(2, len(set(terminal_points)))
        for point in terminal_points:
            self.assertGreater(math.hypot(*point), outer_radius)

    def test_odd_layer_layout_keeps_one_outer_and_one_inner_terminal(self):
        layer_count = 3
        via_diameter = 800
        clearance = 250
        track_width = 250
        start_radius = int(required_inner_radius(
            layer_count, via_diameter, clearance, track_width
        )) + 100
        outer_radius = start_radius + 10000
        layout = multilayer_connection_layout(
            (0, 0), (start_radius, 0), (outer_radius, 0), outer_radius,
            layer_count, via_diameter, clearance, track_width,
        )
        first, last = layout["terminal_routes"]
        self.assertEqual((0, 1), first[:2])
        self.assertEqual((layer_count - 1, 0), last[:2])
        self.assertGreater(math.hypot(*first[2]), outer_radius)
        self.assertLess(math.hypot(*last[2]), start_radius)

    def test_terminal_fanout_tracks_clear_transition_vias(self):
        layer_count = 12
        via_diameter = 800
        clearance = 250
        track_width = 250
        envelope = track_width / 2.0 + via_diameter / 2.0 + clearance
        start_radius = int(required_inner_radius(
            layer_count, via_diameter, clearance, track_width
        )) + 100
        outer_radius = start_radius + 50000
        inner_endpoint = (start_radius, 0)
        outer_endpoint = (outer_radius, 0)
        layout = multilayer_connection_layout(
            (0, 0), inner_endpoint, outer_endpoint, outer_radius,
            layer_count, via_diameter, clearance, track_width,
        )

        def point_to_segment_distance(point, start, end):
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length_squared = dx * dx + dy * dy
            projection = (
                (point[0] - start[0]) * dx
                + (point[1] - start[1]) * dy
            ) / float(length_squared)
            projection = min(1.0, max(0.0, projection))
            closest = (
                start[0] + projection * dx,
                start[1] + projection * dy,
            )
            return math.hypot(point[0] - closest[0], point[1] - closest[1])

        for _layer, endpoint_index, terminal_point in layout["terminal_routes"]:
            endpoint = inner_endpoint if endpoint_index == 0 else outer_endpoint
            for via_point in layout["via_points"].values():
                self.assertGreaterEqual(
                    point_to_segment_distance(
                        via_point, endpoint, terminal_point
                    ) + 1.0,
                    envelope,
                )

    def test_inner_fanout_rejects_small_start_radius(self):
        with self.assertRaises(ValueError):
            connector_via_points(
                (0, 0), (100, 0), (10000, 0), 10000,
                12, 800, 250, 250,
            )

    def test_axial_flux_dimensioning_round_trips_target_torque(self):
        dimensions = axial_flux_motor_dimensions(
            0.05, 0.45, 12000.0, 0.90, 0.58
        )
        self.assertAlmostEqual(0.58, dimensions["inner_ratio"])
        self.assertGreater(dimensions["outer_diameter_mm"], 50.0)
        self.assertAlmostEqual(
            0.05,
            estimate_axial_flux_motor_torque(
                dimensions["outer_radius_mm"],
                dimensions["inner_radius_mm"],
                0.45, 12000.0, 0.90,
            ),
            places=12,
        )

    def test_motor_inner_trace_dfm_reports_capacity_and_taper_width(self):
        result = motor_inner_trace_dfm(
            14.5, 7, 6, 0.15, 0.15, outer_radius_mm=25.0
        )
        self.assertTrue(result["passes"])
        self.assertGreaterEqual(result["maximum_turns_per_layer"], 6)
        self.assertAlmostEqual(
            0.15 * 25.0 / 14.5,
            result["recommended_outer_width_mm"],
        )
        failing = motor_inner_trace_dfm(5.8, 4, 12, 0.2, 0.2)
        self.assertFalse(failing["passes"])

    def test_dc_metrics_use_total_copper_length_and_cross_section(self):
        metrics = estimate_dc_metrics(1000.0, 1.0, 35.0, 2.0)
        self.assertAlmostEqual(0.4925714286, metrics["resistance_ohm"])
        self.assertAlmostEqual(0.9851428571, metrics["voltage_drop_v"])
        self.assertAlmostEqual(1.9702857143, metrics["power_w"])

    def test_dc_metrics_reject_invalid_cross_section(self):
        with self.assertRaises(GeometryError):
            estimate_dc_metrics(1000.0, 0.0, 35.0, 1.0)

    def test_angle_offset_preserves_historical_clockwise_convention(self):
        first = next(iter_spiral_segments(0, 0, 100, 40, 1, 4, 0, math.pi / 2, False))[0]
        self.assertEqual((0, -100), first)

    def test_radial_racetrack_spacing_includes_rotation_and_connectors(self):
        arrangement = resolve_motor_arrangement(
            "motor_racetrack", "radial", 3, "radial",
            0.0, 0.0, 8.0, 0.4, 0.2, 1.8, 0.0, 6,
            overall_radius=16.0,
        )
        chord = 2.0 * arrangement["array_radius"] * math.sin(math.pi / 6.0)
        self.assertGreaterEqual(
            chord + 1e-9, arrangement["minimum_spacing"]
        )
        self.assertGreater(arrangement["array_radius"], 16.0)


if __name__ == "__main__":
    unittest.main()


