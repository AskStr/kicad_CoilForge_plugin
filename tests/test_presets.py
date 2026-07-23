import unittest

from coilforge.geometry import (
    resolve_motor_spiral_parameters, resolve_spiral_parameters,
)
from coilforge.electrical import (
    solve_motor_sector_design, solve_motor_spiral_design,
)
from coilforge.settings import DEFAULTS

from coilforge.presets import (
    APPLICATION_PRESET_CODES,
    APPLICATION_PRESETS,
    MANUFACTURING_PRESET_CODES,
    MANUFACTURING_PRESETS,
    build_preset_values,
    manufacturing_violation,
    recommend_copper_fill_ratio,
    recommend_motor_parameters,
)


class PresetTests(unittest.TestCase):
    def test_combines_application_and_manufacturing_profiles(self):
        values = build_preset_values("wireless_power", "heavy_copper")
        self.assertEqual("fit_turns", values["sizing_mode"])
        self.assertEqual(2, values["layer_count"])
        self.assertEqual(0.3, values["minimum_track_width_mm"])
        self.assertEqual(70.0, values["copper_thickness_um"])

    def test_application_presets_select_relevant_design_targets(self):
        self.assertEqual(
            "target_inductance",
            build_preset_values("nfc_rfid", "standard")["design_mode"],
        )
        self.assertGreater(
            build_preset_values("nfc_rfid", "standard")["target_inductance_uh"],
            0.0,
        )
        self.assertEqual(
            "target_resistance",
            build_preset_values("heating", "standard")["design_mode"],
        )
        self.assertEqual(
            "motor_target",
            build_preset_values("motor_trapezoid", "standard")["design_mode"],
        )

    def test_unknown_profiles_fall_back_to_custom(self):
        values = build_preset_values("missing", "also_missing")
        self.assertEqual({
            "application_preset": "custom",
            "manufacturing_preset": "custom",
        }, values)

    def test_every_noncustom_combination_resolves_to_manufacturable_geometry(self):
        for application in APPLICATION_PRESET_CODES:
            if application == "custom":
                continue
            for manufacturing in MANUFACTURING_PRESET_CODES:
                if manufacturing == "custom":
                    continue
                values = dict(DEFAULTS)
                values.update(build_preset_values(application, manufacturing))
                result = resolve_spiral_parameters(
                    sizing_mode=values["sizing_mode"],
                    start_radius=values["start_radius_mm"],
                    turns=values["turns"],
                    track_width=values["track_width_mm"],
                    spacing=values["spacing_mm"],
                    spacing_mode=values["spacing_mode"],
                    available_diameter=values["available_diameter_mm"],
                    target_length=values["target_length_mm"],
                    fill_ratio=values["fill_ratio"],
                    layer_count=values["layer_count"],
                    via_diameter=values["via_diameter_mm"],
                    via_clearance=values["via_clearance_mm"],
                    minimum_track_width=values["minimum_track_width_mm"],
                    minimum_clearance=values["minimum_clearance_mm"],
                    coil_shape=values["coil_shape"],
                    shape_aspect_ratio=values["shape_aspect_ratio"],
                    shape_taper_ratio=values["shape_taper_ratio"],
                )
                self.assertLessEqual(
                    result["outer_diameter"],
                    values["available_diameter_mm"] + 1e-6,
                )

    def test_motor_and_general_presets_select_expected_shapes(self):
        motor = build_preset_values("motor_trapezoid", "standard")
        general = build_preset_values("general", "standard")
        self.assertEqual("motor_trapezoid", motor["coil_shape"])
        self.assertEqual("segment", motor["primitive_mode"])
        self.assertEqual("circular", general["coil_shape"])

    def test_motor_presets_fit_the_complete_default_array_envelope(self):
        for application in (
                "motor_axial_ellipse", "motor_racetrack",
                "motor_trapezoid", "motor_linear"):
            values = dict(DEFAULTS)
            values.update(build_preset_values(application, "custom"))
            resolved, _arrangement = resolve_motor_spiral_parameters(
                sizing_mode=values["sizing_mode"],
                start_radius=values["start_radius_mm"],
                turns=values["turns"],
                track_width=values["track_width_mm"],
                spacing=values["spacing_mm"],
                spacing_mode=values["spacing_mode"],
                available_diameter=values["available_diameter_mm"],
                target_length=values["target_length_mm"],
                fill_ratio=values["fill_ratio"],
                layer_count=values["layer_count"],
                via_diameter=values["via_diameter_mm"],
                via_clearance=values["via_clearance_mm"],
                minimum_track_width=values["minimum_track_width_mm"],
                minimum_clearance=values["minimum_clearance_mm"],
                coil_shape=values["coil_shape"],
                shape_aspect_ratio=values["shape_aspect_ratio"],
                shape_taper_ratio=values["shape_taper_ratio"],
                motor_layout=values["motor_layout"],
                motor_pole_pairs=values["motor_pole_pairs"],
                motor_orientation=values["motor_orientation"],
                motor_array_radius=values["motor_array_radius_mm"],
                motor_linear_pitch=values["motor_linear_pitch_mm"],
                motor_slot_count=values["motor_slot_count"],
            )
            self.assertLessEqual(
                resolved["array_outer_diameter"],
                values["available_diameter_mm"] + 1e-6,
                application,
            )


    def test_single_motor_coil_uses_shape_defaults(self):
        ellipse = recommend_motor_parameters(
            "motor_ellipse", "single", 12, "standard", 1
        )
        racetrack = recommend_motor_parameters(
            "motor_racetrack", "single", 12, "standard", 1
        )
        trapezoid = recommend_motor_parameters(
            "motor_trapezoid", "single", 12, "standard", 1
        )
        self.assertEqual(1, ellipse["pole_count"])
        self.assertEqual(1.55, ellipse["shape_aspect_ratio"])
        self.assertEqual(1.8, racetrack["shape_aspect_ratio"])
        self.assertEqual(1.65, trapezoid["shape_aspect_ratio"])
        self.assertEqual(0.45, trapezoid["shape_taper_ratio"])
        self.assertEqual(3.0, trapezoid["start_radius_mm"])

    def test_radial_geometry_adapts_to_pole_count(self):
        few = recommend_motor_parameters(
            "motor_trapezoid", "radial", 3, "standard", 4,
            0.8, 0.25, 0.3, 0.2, 0.2,
        )
        many = recommend_motor_parameters(
            "motor_trapezoid", "radial", 12, "standard", 4,
            0.8, 0.25, 0.3, 0.2, 0.2,
        )
        self.assertEqual(6, few["pole_count"])
        self.assertEqual(24, many["pole_count"])
        self.assertLess(few["shape_aspect_ratio"], many["shape_aspect_ratio"])
        self.assertGreater(few["shape_taper_ratio"], many["shape_taper_ratio"])
        self.assertEqual(0.0, few["motor_array_radius_mm"])
        self.assertEqual("radial", few["motor_orientation"])

    def test_process_capability_adjusts_fill_and_safe_inner_radius(self):
        fine = recommend_motor_parameters(
            "motor_racetrack", "radial", 6, "fine", 2,
            0.6, 0.2, 0.2, 0.15, 0.15,
        )
        heavy = recommend_motor_parameters(
            "motor_racetrack", "radial", 6, "heavy_copper", 8,
            1.2, 0.35, 0.3, 0.3, 0.3,
        )
        self.assertGreater(fine["fill_ratio"], heavy["fill_ratio"])
        self.assertGreater(heavy["start_radius_mm"], fine["start_radius_mm"])
        self.assertEqual("smooth", heavy["quality_preset"])
        self.assertEqual("clearance", heavy["spacing_mode"])

    def test_torque_target_dimensions_radial_motor_annulus(self):
        result = recommend_motor_parameters(
            "motor_trapezoid", "radial", 7,
            target_torque_nm=0.05, air_gap_flux_density_t=0.45,
            electrical_loading_a_per_m=12000.0, winding_factor=0.9,
            motor_inner_ratio=0.58, motor_slot_count=12,
            motor_phase_count=3,
        )
        self.assertEqual("fit_turns", result["sizing_mode"])
        self.assertEqual(12, result["pole_count"])
        self.assertTrue(result["phase_balanced"])
        self.assertGreater(result["motor_outer_diameter_mm"], 50.0)
        self.assertAlmostEqual(
            result["motor_outer_diameter_mm"],
            result["available_diameter_mm"],
            places=3,
        )
        self.assertGreater(result["motor_array_radius_mm"], 0.0)

    def test_linear_motor_recommendation_uses_auto_pitch(self):
        values = recommend_motor_parameters(
            "motor_racetrack", "linear", 5, "standard", 2
        )
        self.assertEqual(10, values["pole_count"])
        self.assertEqual(0.0, values["motor_linear_pitch_mm"])
        self.assertEqual("tangential", values["motor_orientation"])


    def test_general_fill_recommendation_balances_current_and_process(self):
        light = recommend_copper_fill_ratio(
            "general", "standard", 0.2, 35.0
        )
        heavy = recommend_copper_fill_ratio(
            "general", "standard", 4.0, 35.0
        )
        thick = recommend_copper_fill_ratio(
            "general", "standard", 4.0, 70.0
        )
        conservative = recommend_copper_fill_ratio(
            "general", "conservative", 4.0, 35.0
        )
        self.assertGreater(heavy, light)
        self.assertLessEqual(thick, heavy)
        self.assertLess(conservative, heavy)
        self.assertAlmostEqual(heavy * 100.0, round(heavy * 100.0))

    def test_current_aware_recommendation_balances_loss_and_clean_geometry(self):
        light = recommend_motor_parameters(
            "motor_racetrack", "radial", 6, "standard", 2,
            application_code="motor_racetrack", target_current_a=0.2,
            copper_thickness_um=35.0,
        )
        heavy = recommend_motor_parameters(
            "motor_racetrack", "radial", 6, "standard", 2,
            application_code="motor_racetrack", target_current_a=4.0,
            copper_thickness_um=35.0,
        )
        thick_copper = recommend_motor_parameters(
            "motor_racetrack", "radial", 6, "heavy_copper", 2,
            application_code="motor_racetrack", target_current_a=4.0,
            copper_thickness_um=70.0,
        )
        self.assertGreater(heavy["fill_ratio"], light["fill_ratio"])
        self.assertLessEqual(thick_copper["fill_ratio"], heavy["fill_ratio"])
        self.assertAlmostEqual(
            heavy["shape_aspect_ratio"] * 20.0,
            round(heavy["shape_aspect_ratio"] * 20.0),
        )
        self.assertAlmostEqual(
            heavy["fill_ratio"] * 100.0,
            round(heavy["fill_ratio"] * 100.0),
        )

    def test_manufacturing_violation_reports_actionable_process_limits(self):
        width = manufacturing_violation(
            "standard", 0.15, 0.25, layer_count=1
        )
        clearance = manufacturing_violation(
            "standard", 0.25, 0.15, layer_count=1
        )
        via = manufacturing_violation(
            "standard", 0.25, 0.25, layer_count=2,
            via_diameter_mm=0.6, via_drill_mm=0.4,
            via_clearance_mm=0.25,
        )
        self.assertEqual("manufacturing_track_width_too_small", width["code"])
        self.assertEqual("manufacturing_clearance_too_small", clearance["code"])
        self.assertEqual("manufacturing_via_diameter_too_small", via["code"])
        self.assertIsNone(manufacturing_violation(
            "custom", 0.01, 0.01, layer_count=8,
        ))
        self.assertIsNone(manufacturing_violation(
            "fine", 0.15, 0.15, layer_count=2,
            via_diameter_mm=0.6, via_drill_mm=0.3,
            via_clearance_mm=0.2,
        ))

    def test_result_does_not_mutate_preset_definitions(self):
        values = build_preset_values("general", "standard")
        values["turns"] = 999
        values["via_diameter_mm"] = 999
        self.assertEqual(10.0, APPLICATION_PRESETS["general"]["turns"])
        self.assertEqual(
            0.8, MANUFACTURING_PRESETS["standard"]["via_diameter_mm"]
        )

    def test_all_motor_target_presets_are_electrically_feasible(self):
        for application in (
                "motor_axial_ellipse", "motor_racetrack",
                "motor_trapezoid", "motor_sector", "motor_linear"):
            values = dict(DEFAULTS)
            values.update(build_preset_values(application, "standard"))
            if values["coil_shape"] == "motor_sector":
                result = solve_motor_sector_design(
                    values["motor_board_outer_diameter_mm"],
                    values["motor_board_inner_diameter_mm"],
                    values["motor_pole_pairs"], values["motor_slot_count"],
                    values["motor_phase_count"], values["layer_count"],
                    values["motor_supply_voltage_v"],
                    values["motor_target_speed_rpm"],
                    values["target_torque_nm"],
                    values["motor_max_phase_current_a"],
                    values["copper_thickness_um"],
                    values["minimum_track_width_mm"],
                    values["minimum_clearance_mm"],
                    edge_clearance_mm=values["motor_edge_clearance_mm"],
                    slot_gap_mm=values["motor_slot_gap_mm"],
                    fill_ratio=values["fill_ratio"],
                )
            else:
                result = solve_motor_spiral_design(
                    values["available_diameter_mm"],
                    values["start_radius_mm"], values["coil_shape"],
                    values["shape_aspect_ratio"],
                    values["shape_taper_ratio"], values["motor_layout"],
                    values["motor_pole_pairs"], values["motor_slot_count"],
                    values["motor_phase_count"],
                    values["motor_orientation"],
                    values["motor_array_radius_mm"],
                    values["motor_linear_pitch_mm"], values["layer_count"],
                    values["motor_supply_voltage_v"],
                    values["motor_target_speed_rpm"],
                    values["target_torque_nm"],
                    values["motor_max_phase_current_a"],
                    values["copper_thickness_um"],
                    values["minimum_track_width_mm"],
                    values["minimum_clearance_mm"],
                    values["via_diameter_mm"], values["via_clearance_mm"],
                    fill_ratio=values["fill_ratio"],
                    target_force_n=values["motor_target_force_n"],
                    target_linear_speed_mps=values[
                        "motor_target_linear_speed_mps"
                    ],
                )
            self.assertTrue(result["feasible"], application)


if __name__ == "__main__":
    unittest.main()

