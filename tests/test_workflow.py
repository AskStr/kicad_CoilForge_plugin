import unittest

from coilforge.workflow import (
    WorkflowLocks, parameter_visibility, workflow_page_keys,
    workflow_step_fields,
)


class WorkflowTests(unittest.TestCase):
    def test_locked_earlier_values_are_not_overwritten(self):
        locks = WorkflowLocks((('board_diameter',), ('turns', 'width')))
        locks.lock_step(0, {'board_diameter': 100})
        merged = locks.merge_derived(
            {'board_diameter': 100, 'turns': 5},
            {'board_diameter': 120, 'turns': 8},
        )
        self.assertEqual(100, merged['board_diameter'])
        self.assertEqual(8, merged['turns'])
        conflicts = locks.conflicts({'board_diameter': 120})
        self.assertEqual(0, conflicts[0]['step'])
        self.assertEqual(100, conflicts[0]['locked'])

    def test_returning_to_step_unlocks_that_step_and_later(self):
        locks = WorkflowLocks((('a',), ('b',), ('c',)))
        locks.lock_step(0, {'a': 1})
        locks.lock_step(1, {'b': 2})
        locks.lock_step(2, {'c': 3})
        locks.unlock_from(1)
        self.assertEqual({'a': 1}, locks.fixed_values())

    def test_sector_motor_visibility_hides_manual_spiral_noise(self):
        visible = parameter_visibility({
            'coil_shape': 'motor_sector', 'application_preset': 'motor_sector',
            'design_mode': 'motor_target', 'layer_count': 1,
        })
        self.assertIn('motor_board_outer_diameter_mm', visible)
        self.assertIn('motor_supply_voltage_v', visible)
        self.assertNotIn('start_radius_mm', visible)
        self.assertNotIn('via_diameter_mm', visible)
        self.assertNotIn('air_gap_flux_density_t', visible)

    def test_advanced_and_multilayer_fields_are_conditional(self):
        visible = parameter_visibility({
            'coil_shape': 'motor_sector', 'layer_count': 4,
            'show_advanced_parameters': True,
        })
        self.assertIn('via_diameter_mm', visible)
        self.assertIn('air_gap_flux_density_t', visible)
        self.assertIn('segments_per_turn', visible)

    def test_scenario_workflows_remove_irrelevant_pages(self):
        general = workflow_page_keys({
            'application_preset': 'general', 'coil_shape': 'circular',
        })
        motor = workflow_page_keys({
            'application_preset': 'motor_sector',
            'coil_shape': 'motor_sector',
        })
        custom_motor = workflow_page_keys({
            'application_preset': 'custom',
            'coil_shape': 'motor_trapezoid',
        })
        self.assertEqual(5, len(general))
        self.assertNotIn('section_geometry', general)
        self.assertNotIn('section_placement', general)
        self.assertEqual(6, len(motor))
        self.assertNotIn('section_geometry', motor)
        self.assertIn('section_placement', motor)
        self.assertEqual(7, len(custom_motor))
        self.assertEqual(len(custom_motor), len(workflow_step_fields({
            'application_preset': 'custom',
            'coil_shape': 'motor_trapezoid',
        })))

    def test_hidden_manual_geometry_does_not_lock_electrical_solver(self):
        values = {
            'application_preset': 'motor_sector',
            'coil_shape': 'motor_sector', 'design_mode': 'motor_target',
            'layer_count': 4,
        }
        fields = workflow_step_fields(values)
        sizing_fields = fields[2]
        self.assertNotIn('turns', sizing_fields)
        self.assertNotIn('track_width_mm', sizing_fields)
        self.assertNotIn('spacing_mm', sizing_fields)
        self.assertIn('motor_board_outer_diameter_mm', sizing_fields)

    def test_visible_target_is_locked_without_stale_turn_count(self):
        values = {
            'application_preset': 'nfc_rfid', 'coil_shape': 'circular',
            'design_mode': 'target_inductance', 'layer_count': 1,
        }
        fields = workflow_step_fields(values)
        sizing_fields = fields[2]
        self.assertIn('target_inductance_uh', sizing_fields)
        self.assertNotIn('turns', sizing_fields)
        self.assertNotIn('track_width_mm', sizing_fields)

    def test_application_specific_electrical_targets_are_visible(self):
        motor = parameter_visibility({
            'application_preset': 'motor_sector',
            'coil_shape': 'motor_sector', 'design_mode': 'motor_target',
            'layer_count': 1,
        })
        self.assertTrue({
            'target_torque_nm', 'motor_supply_voltage_v',
            'motor_target_speed_rpm', 'motor_max_phase_current_a',
            'allowed_temperature_rise_c',
        }.issubset(motor))
        inductance = parameter_visibility({
            'application_preset': 'nfc_rfid', 'coil_shape': 'circular',
            'design_mode': 'target_inductance', 'layer_count': 1,
        })
        resistance = parameter_visibility({
            'application_preset': 'heating', 'coil_shape': 'circular',
            'design_mode': 'target_resistance', 'layer_count': 1,
        })
        self.assertIn('target_inductance_uh', inductance)
        self.assertIn('target_resistance_ohm', resistance)
        self.assertIn('fill_ratio_percent', inductance)

    def test_linear_motor_uses_geometry_inputs_not_rotary_targets(self):
        visible = parameter_visibility({
            "application_preset": "motor_linear",
            "coil_shape": "motor_racetrack",
            "motor_layout": "linear",
            "design_mode": "fit_turns",
            "layer_count": 2,
        })
        self.assertIn("turns", visible)
        self.assertIn("motor_linear_pitch_mm", visible)
        self.assertNotIn("target_torque_nm", visible)
        self.assertNotIn("motor_target_speed_rpm", visible)

    def test_linear_motor_target_shows_force_and_linear_speed(self):
        visible = parameter_visibility({
            "application_preset": "motor_linear",
            "coil_shape": "motor_racetrack",
            "motor_layout": "linear",
            "design_mode": "motor_target",
            "layer_count": 2,
        })
        self.assertIn("motor_target_force_n", visible)
        self.assertIn("motor_target_linear_speed_mps", visible)
        self.assertIn("motor_supply_voltage_v", visible)
        self.assertNotIn("target_torque_nm", visible)
        self.assertNotIn("motor_target_speed_rpm", visible)


if __name__ == "__main__":
    unittest.main()
