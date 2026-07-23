import unittest

from coilforge.electrical import (
    estimate_external_trace_current_capacity_a, estimate_motor_linear_emf,
    estimate_motor_sector_emf,
    estimate_planar_spiral_inductance_uh, solve_motor_sector_design,
    solve_motor_spiral_design, solve_spiral_electrical_design,
)


class ElectricalTests(unittest.TestCase):
    def test_planar_inductance_increases_with_turns(self):
        low = estimate_planar_spiral_inductance_uh(5, 40, 10)
        high = estimate_planar_spiral_inductance_uh(10, 40, 10)
        self.assertGreater(low, 0.0)
        self.assertGreater(high, low * 3.5)

    def test_spiral_target_resistance_selects_nearby_manufacturable_result(self):
        result = solve_spiral_electrical_design(
            "target_resistance", 40, 2, 1, 35, 0.15, 0.15,
            target_resistance_ohm=2.0,
        )
        self.assertGreater(result["resistance_ohm"], 0.0)
        self.assertGreaterEqual(result["track_width_mm"], 0.15)
        self.assertGreaterEqual(result["clearance_mm"], 0.15)

    def test_spiral_target_current_uses_temperature_limited_capacity(self):
        result = solve_spiral_electrical_design(
            "target_current", 60, 2, 1, 70, 0.2, 0.2,
            target_current_a=2.0, allowed_temperature_rise_c=40,
        )
        self.assertGreater(result["current_capacity_a"], 0.0)
        self.assertGreater(result["track_width_mm"], 0.0)

    def test_motor_emf_increases_with_speed_and_turns(self):
        base = estimate_motor_sector_emf(
            100, 40, 12, 6, 3, 4, 2, 1000, 0.45
        )
        faster = estimate_motor_sector_emf(
            100, 40, 12, 6, 3, 8, 2, 2000, 0.45
        )
        self.assertGreater(faster["line_rms_v"], base["line_rms_v"] * 3.9)

    def test_motor_solver_respects_board_process_voltage_and_current(self):
        result = solve_motor_sector_design(
            100, 40, 6, 12, 3, 2, 24, 1000, 0.15, 5.0,
            35, 0.15, 0.15, connection="star",
            edge_clearance_mm=1.0, slot_gap_mm=0.8,
        )
        self.assertTrue(result["feasible"])
        self.assertLessEqual(
            result["required_line_voltage_v"],
            result["available_line_voltage_rms_v"],
        )
        self.assertAlmostEqual(24.0 / 2.0 ** 0.5,
                               result["available_line_voltage_rms_v"])
        self.assertLessEqual(result["required_phase_current_a"], 5.0)
        self.assertGreaterEqual(result["track_width_mm"], 0.15)
        self.assertGreaterEqual(result["clearance_mm"], 0.15)

    def test_allowed_temperature_rise_changes_trace_current_limit(self):
        cool = estimate_external_trace_current_capacity_a(0.5, 35, 10)
        warm = estimate_external_trace_current_capacity_a(0.5, 35, 40)
        self.assertGreater(cool, 0.0)
        self.assertGreater(warm, cool)

    def test_motor_solver_honors_locked_turn_count(self):
        result = solve_motor_sector_design(
            100, 40, 6, 12, 3, 2, 24, 1000, 0.05, 5.0,
            35, 0.15, 0.15, fixed={"turns": 4},
        )
        self.assertEqual(4, result["turns_per_slot"])

    def test_motor_turns_follow_voltage_speed_and_torque(self):
        common = dict(
            board_outer_diameter_mm=100, board_inner_diameter_mm=40,
            pole_pairs=6, slot_count=12, phase_count=3, layer_count=2,
            max_phase_current_a=5.0, copper_thickness_um=35,
            minimum_track_width_mm=0.15, minimum_clearance_mm=0.15,
        )
        low_voltage = solve_motor_sector_design(
            supply_voltage_v=12, target_speed_rpm=1000,
            target_torque_nm=0.05, **common
        )
        high_voltage = solve_motor_sector_design(
            supply_voltage_v=48, target_speed_rpm=1000,
            target_torque_nm=0.05, **common
        )
        high_speed = solve_motor_sector_design(
            supply_voltage_v=24, target_speed_rpm=2000,
            target_torque_nm=0.05, **common
        )
        high_torque = solve_motor_sector_design(
            supply_voltage_v=24, target_speed_rpm=1000,
            target_torque_nm=0.12, **common
        )
        self.assertGreater(
            high_voltage["turns_per_slot"], low_voltage["turns_per_slot"]
        )
        self.assertLess(
            high_speed["turns_per_slot"], high_voltage["turns_per_slot"]
        )
        self.assertLess(
            high_torque["turns_per_slot"], high_voltage["turns_per_slot"]
        )

    def test_motor_zero_speed_torque_still_requires_current(self):
        result = solve_motor_sector_design(
            100, 40, 6, 12, 3, 2, 24, 0, 0.05, 5.0,
            35, 0.15, 0.15,
        )
        self.assertGreater(result["required_phase_current_a"], 0.0)
        self.assertEqual(0.0, result["back_emf_line_v"])

    def test_motor_hot_resistance_and_actual_turn_area_are_used(self):
        idealized = estimate_motor_sector_emf(
            100, 40, 12, 6, 3, 6, 2, 1000, 0.45
        )
        actual = estimate_motor_sector_emf(
            100, 40, 12, 6, 3, 6, 2, 1000, 0.45,
            track_width_mm=0.5, clearance_mm=0.2,
            edge_clearance_mm=1.0, slot_gap_mm=0.8,
        )
        result = solve_motor_sector_design(
            100, 40, 6, 12, 3, 2, 24, 1000, 0.05, 5.0,
            35, 0.15, 0.15, allowed_temperature_rise_c=40,
        )
        self.assertLess(actual["flux_linkage_area_m2"],
                        idealized["flux_linkage_area_m2"])
        self.assertGreater(result["phase_resistance_hot_ohm"],
                           result["phase_resistance_ohm"])

    def test_rotary_shaped_motor_uses_electrical_solver(self):
        result = solve_motor_spiral_design(
            80, 2, "motor_trapezoid", 1.65, 0.45, "radial",
            6, 12, 3, "radial", 0, 0, 2, 24, 1000, 0.005, 5,
            35, 0.2, 0.2,
        )
        self.assertTrue(result["feasible"])
        self.assertGreater(result["turns_per_slot"], 0)
        self.assertGreater(result["required_phase_current_a"], 0.0)
        self.assertLessEqual(result["required_line_voltage_v"],
                             result["available_line_voltage_rms_v"])

    def test_electrical_targets_reject_insufficient_trace_current(self):
        result = solve_spiral_electrical_design(
            "target_inductance", 40, 2, 1, 35, 0.15, 0.15,
            target_inductance_uh=10.0, target_current_a=50.0,
        )
        self.assertFalse(result["feasible"])
        self.assertIn("trace_current", result["violations"])

    def test_linear_motor_solver_uses_force_and_linear_speed(self):
        result = solve_motor_spiral_design(
            60, 2, "motor_racetrack", 1.5, 0.0, "linear",
            3, 6, 3, "tangential", 0, 0, 2, 12, 0, 0, 3,
            35, 0.2, 0.2, target_force_n=0.1,
            target_linear_speed_mps=0.5,
        )
        faster = estimate_motor_linear_emf(
            3, 2, 1, "motor_racetrack", 1.5, 0, 6, 3, 2,
            1.0, 10.0, 0.45,
        )
        slower = estimate_motor_linear_emf(
            3, 2, 1, "motor_racetrack", 1.5, 0, 6, 3, 2,
            0.5, 10.0, 0.45,
        )
        self.assertTrue(result["feasible"])
        self.assertGreater(result["required_phase_current_a"], 0.0)
        self.assertGreater(faster["line_rms_v"], slower["line_rms_v"] * 1.9)


if __name__ == "__main__":
    unittest.main()
