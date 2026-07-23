import unittest
from math import cos, pi, sin

from coilforge.geometry import (
    iter_motor_sector_spiral_segments, motor_sector_dimensions,
)
from coilforge.preview import (
    build_preview_scene, build_safe_preview_scene,
    coerce_preview_values, fit_preview_scene,
)
from coilforge.settings import DEFAULTS


class PreviewTests(unittest.TestCase):
    def _values(self, shape="circular"):
        values = dict(DEFAULTS)
        values.update({
            "coil_shape": shape,
            "start_radius_mm": 2.0,
            "turns": 5.0,
            "track_width_mm": 0.3,
            "spacing_mm": 0.6,
            "spacing_mode": "pitch",
            "segments_per_turn": 64,
            "additional_segments": 0,
            "layer_count": 1,
        })
        return values

    def _assert_visual_center(self, fitted, width, height):
        points = [fitted["center"]]
        for collection in (
                fitted["coil_paths"], fitted["connector_paths"]):
            for path in collection:
                points.extend(path)
        points.extend(fitted["via_points"])
        points.extend(fitted["terminal_points"])
        min_x = min(point[0] for point in points)
        max_x = max(point[0] for point in points)
        min_y = min(point[1] for point in points)
        max_y = max(point[1] for point in points)
        self.assertAlmostEqual(width / 2.0, (min_x + max_x) / 2.0, places=6)
        self.assertAlmostEqual(height / 2.0, (min_y + max_y) / 2.0, places=6)

    def test_all_coil_shapes_build_visible_preview_paths(self):
        for shape in (
                "circular", "motor_ellipse", "motor_racetrack",
                "motor_trapezoid"):
            scene = build_preview_scene(self._values(shape))
            self.assertGreater(len(scene["coil_paths"][0]), 20)
            fitted = fit_preview_scene(scene, 320, 240)
            for path in fitted["coil_paths"]:
                for x, y in path:
                    self.assertGreaterEqual(x, 0)
                    self.assertLessEqual(x, 320)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(y, 240)

    def test_radial_and_linear_motor_arrays_preview_every_pole(self):
        for layout in ("radial", "linear"):
            values = {
                "coil_shape": "motor_trapezoid",
                "shape_aspect_ratio": 1.65,
                "shape_taper_ratio": 0.45,
                "motor_layout": layout,
                "motor_pole_pairs": 3,
                "motor_array_radius_mm": 40.0,
                "motor_linear_pitch_mm": 35.0,
                "motor_orientation": "radial",
                "motor_alternate_winding": True,
                "turns": 3,
                "start_radius_mm": 2.0,
                "spacing_mm": 0.5,
                "segments_per_turn": 64,
                "layer_count": 1,
            }
            scene = build_preview_scene(values)
            self.assertEqual(6, scene["motor_instance_count"])
            self.assertEqual(6, len(scene["coil_paths"]))
            self.assertEqual(12, len(scene["terminal_points"]))

    def test_motor_sector_preview_fills_and_centers_all_slots(self):
        values = self._values("motor_sector")
        values.update({
            "motor_board_outer_diameter_mm": 100.0,
            "motor_board_inner_diameter_mm": 40.0,
            "motor_slot_count": 12,
            "motor_pole_pairs": 6,
            "motor_edge_clearance_mm": 1.0,
            "motor_slot_gap_mm": 0.8,
            "turns": 5,
            "track_width_mm": 0.35,
            "spacing_mm": 0.65,
        })
        scene = build_preview_scene(values)
        self.assertEqual(12, scene["motor_instance_count"])
        self.assertEqual(12, len(scene["coil_paths"]))
        fitted = fit_preview_scene(scene, 420, 300)
        self._assert_visual_center(fitted, 420, 300)

    def test_multilayer_preview_includes_vias_connectors_and_terminals(self):
        values = self._values("motor_trapezoid")
        values.update({
            "layer_count": 4,
            "shape_aspect_ratio": 1.65,
            "shape_taper_ratio": 0.45,
        })
        scene = build_preview_scene(values)
        self.assertEqual(3, len(scene["via_points"]))
        self.assertEqual(8, len(scene["connector_paths"]))
        self.assertEqual(2, len(scene["terminal_points"]))
        self.assertEqual(4, len(scene["coil_paths"]))
        self.assertTrue(all(len(point) == 2 for point in scene["via_points"]))
        fitted = fit_preview_scene(scene, 400, 280)
        self.assertEqual(3, len(fitted["via_points"]))

    def test_asymmetric_preview_centers_the_complete_visible_scene(self):
        values = self._values("motor_trapezoid")
        values.update({
            "layer_count": 4,
            "shape_aspect_ratio": 1.65,
            "shape_taper_ratio": 0.45,
        })
        fitted = fit_preview_scene(build_preview_scene(values), 400, 220)
        self._assert_visual_center(fitted, 400, 220)
        for collection in (
                fitted["coil_paths"], fitted["connector_paths"]):
            for path in collection:
                for x, y in path:
                    self.assertGreaterEqual(x, 0)
                    self.assertLessEqual(x, 400)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(y, 220)

    def test_heating_then_other_preview_stays_centered(self):
        heating = self._values("circular")
        heating.update({
            "start_radius_mm": 3.0,
            "turns": 6.0,
            "track_width_mm": 3.2957746478873244,
            "spacing_mm": 0.9295774647887325,
            "spacing_mode": "clearance",
        })
        general = self._values("circular")
        for values in (heating, general, heating, general):
            fitted = fit_preview_scene(build_preview_scene(values), 459, 239, 22)
            self._assert_visual_center(fitted, 459, 239)
            for path in fitted["coil_paths"]:
                for x, y in path:
                    self.assertGreaterEqual(x, 22 - 1e-9)
                    self.assertLessEqual(x, 459 - 22 + 1e-9)
                    self.assertGreaterEqual(y, 22 - 1e-9)
                    self.assertLessEqual(y, 239 - 22 + 1e-9)

    def test_large_absolute_scene_center_does_not_shift_canvas_center(self):
        center = (1.0e12, -1.0e12)
        scene = {
            "center": center,
            "coil_shape": "circular",
            "layer_count": 1,
            "coil_paths": [[
                (center[0] - 30.0, center[1]),
                (center[0] + 30.0, center[1]),
            ]],
            "connector_paths": [],
            "via_points": [],
            "terminal_points": [],
        }
        fitted = fit_preview_scene(scene, 400, 220)
        self.assertEqual((200.0, 110.0), fitted["center"])
    def test_draft_values_keep_preview_alive_during_partial_input(self):
        values = self._values("motor_ellipse")
        values.update({
            "turns": "",
            "spacing_mm": "-",
            "shape_aspect_ratio": "bad",
            "layer_count": "4",
            "start_radius_mm": "0",
        })
        safe = coerce_preview_values(values)
        self.assertEqual("motor_ellipse", safe["coil_shape"])
        self.assertEqual(4, safe["layer_count"])
        scene = build_preview_scene(values)
        self.assertEqual(4, scene["layer_count"])
        self.assertGreater(len(scene["coil_paths"][0]), 20)


    def test_invalid_sector_draft_returns_no_scene_instead_of_crashing(self):
        values = self._values("motor_sector")
        values.update({
            "motor_board_outer_diameter_mm": 100.0,
            "motor_board_inner_diameter_mm": 40.0,
            "motor_slot_count": 12,
            "motor_edge_clearance_mm": 1.0,
            "motor_slot_gap_mm": 0.8,
            "turns": 1000,
        })
        self.assertIsNone(build_safe_preview_scene(values))

    def test_motor_sector_preview_matches_generated_instance_rotation(self):
        values = self._values("motor_sector")
        values.update({
            "motor_board_outer_diameter_mm": 100.0,
            "motor_board_inner_diameter_mm": 40.0,
            "motor_slot_count": 12,
            "motor_pole_pairs": 6,
            "motor_edge_clearance_mm": 1.0,
            "motor_slot_gap_mm": 0.8,
            "turns": 5,
            "track_width_mm": 0.35,
            "spacing_mm": 0.65,
        })
        scene = build_preview_scene(values)
        scale = 100000.0
        dimensions = motor_sector_dimensions(
            values["motor_board_outer_diameter_mm"] * scale,
            values["motor_board_inner_diameter_mm"] * scale,
            values["motor_slot_count"], values["track_width_mm"] * scale,
            (values["spacing_mm"] - values["track_width_mm"]) * scale,
            values["motor_edge_clearance_mm"] * scale,
            values["motor_slot_gap_mm"] * scale,
        )
        index = 1
        angle = 2.0 * pi * index / values["motor_slot_count"]
        center_x = dimensions["array_radius"] * cos(angle)
        center_y = dimensions["array_radius"] * sin(angle)
        expected_segments = list(iter_motor_sector_spiral_segments(
            center_x, center_y,
            values["motor_board_outer_diameter_mm"] * scale,
            values["motor_board_inner_diameter_mm"] * scale,
            values["motor_slot_count"], values["track_width_mm"] * scale,
            (values["spacing_mm"] - values["track_width_mm"]) * scale,
            values["turns"], values["segments_per_turn"], 0,
            values["motor_edge_clearance_mm"] * scale,
            values["motor_slot_gap_mm"] * scale, angle, True,
        ))
        expected = [expected_segments[0][0]] + [
            end for _start, end in expected_segments
        ]
        actual = scene["coil_paths"][index]
        self.assertEqual(len(expected), len(actual))
        for expected_point, actual_point in zip(expected[::17], actual[::17]):
            self.assertAlmostEqual(
                expected_point[0] / scale, actual_point[0], places=4
            )
            self.assertAlmostEqual(
                expected_point[1] / scale, actual_point[1], places=4
            )

    def test_fitted_preview_uses_physical_track_and_via_sizes(self):
        values = self._values("circular")
        values.update({
            "track_width_mm": 1.2, "via_diameter_mm": 2.0,
            "layer_count": 2,
        })
        fitted = fit_preview_scene(build_preview_scene(values), 400, 280)
        self.assertAlmostEqual(
            1.2 * fitted["scale"], fitted["track_width_px"]
        )
        self.assertAlmostEqual(
            2.0 * fitted["scale"], fitted["via_diameter_px"]
        )

    def test_large_turn_count_is_sampled_for_responsive_preview(self):
        values = self._values("motor_racetrack")
        values["turns"] = 10000
        scene = build_preview_scene(values)
        self.assertLessEqual(len(scene["coil_paths"][0]), 2000)


if __name__ == "__main__":
    unittest.main()



