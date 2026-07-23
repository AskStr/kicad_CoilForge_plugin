import unittest

from coilforge.ipc_ui import (
    SpiralIpcWindow, _NUMERIC_SETTING_KEYS, formatted_entry_settings,
)
from coilforge.settings import DEFAULTS, _FLOAT_KEYS, _INT_KEYS


class IpcUiTests(unittest.TestCase):
    def test_string_group_name_is_not_formatted_as_a_number(self):
        values = dict(DEFAULTS)
        values["group_name"] = "spiral"
        formatted = formatted_entry_settings(values)
        self.assertEqual("spiral", formatted["group_name"])
        self.assertEqual("50", formatted["fill_ratio_percent"])
        self.assertEqual("35", formatted["copper_thickness_um"])
        self.assertEqual("1.6", formatted["shape_aspect_ratio"])
        self.assertEqual("45", formatted["shape_taper_percent"])
        self.assertEqual("5", formatted["motor_target_force_n"])
        self.assertEqual("1", formatted["motor_target_linear_speed_mps"])

    def test_all_persisted_numeric_entries_are_initialized(self):
        represented_separately = {
            "schema_version", "layer_count", "max_segments",
            "fill_ratio", "shape_taper_ratio",
        }
        expected = (set(_FLOAT_KEYS) | set(_INT_KEYS)) - represented_separately
        self.assertEqual(set(), expected - set(_NUMERIC_SETTING_KEYS))

    def test_preset_selection_applies_immediately(self):
        window = SpiralIpcWindow.__new__(SpiralIpcWindow)
        window._updating = False
        window._motor_parameters_auto = False
        window.settings = {}
        calls = []
        window._apply_selected_presets = (
            lambda **_options: calls.append("applied")
        )
        window._preset_selection_changed()
        self.assertEqual(["applied"], calls)

    def test_validation_feedback_controls_create_state(self):
        class Variable(object):
            value = None

            def set(self, value):
                self.value = value

        class Widget(object):
            options = None

            def configure(self, **options):
                self.options = options

        window = SpiralIpcWindow.__new__(SpiralIpcWindow)
        window.validation_summary = Variable()
        window.validation_label = Widget()
        window.create_button = Widget()
        window._set_validation_feedback("bad value", False)
        self.assertEqual("bad value", window.validation_summary.value)
        self.assertEqual("disabled", window.create_button.options["state"])
        self.assertEqual(
            "CoilForge.Error.TLabel", window.validation_label.options["style"]
        )
        window._set_validation_feedback("ready", True)
        self.assertEqual("normal", window.create_button.options["state"])

    def test_noncustom_motor_edit_is_kept_as_constraint(self):
        window = SpiralIpcWindow.__new__(SpiralIpcWindow)
        window._updating = False
        window._motor_parameters_auto = False
        window.settings = {}
        window._motor_shape_active = lambda: True
        window._application_is_custom = lambda: False
        window.tr = lambda key, **_values: key
        calls = []
        window._refresh_motor_recommendation = (
            lambda **options: calls.append(options)
        )
        window._schedule_preview = lambda: calls.append("preview")
        window._motor_parameter_edited("fill_ratio", "fill_ratio")
        self.assertTrue(window._motor_parameters_auto)
        self.assertTrue(window.settings["motor_parameters_auto"])
        self.assertEqual(("fill_ratio",), calls[0]["preserve_keys"])
        self.assertEqual("fill_ratio", calls[0]["preserved_field"])

    def test_custom_motor_edit_switches_to_manual_lock(self):
        window = SpiralIpcWindow.__new__(SpiralIpcWindow)
        window._updating = False
        window._motor_parameters_auto = True
        window.settings = {}
        window._motor_shape_active = lambda: True
        window._application_is_custom = lambda: True
        calls = []
        window._refresh_motor_recommendation = (
            lambda **options: calls.append(options)
        )
        window._schedule_preview = lambda: None
        window._motor_parameter_edited("fill_ratio", "fill_ratio")
        self.assertFalse(window._motor_parameters_auto)
        self.assertFalse(window.settings["motor_parameters_auto"])
        self.assertFalse(calls[0]["apply"])

    def test_unicode_group_name_is_preserved(self):
        values = dict(DEFAULTS)
        values["group_name"] = "测试线圈"
        self.assertEqual(
            "测试线圈", formatted_entry_settings(values)["group_name"]
        )

    def test_full_preset_values_are_preserved_from_auto_recommendation(self):
        class Variable(object):
            def __init__(self, value=""):
                self.value = value
            def get(self):
                return self.value
            def set(self, value):
                self.value = value

        window = SpiralIpcWindow.__new__(SpiralIpcWindow)
        window._updating = False
        window._motor_parameters_auto = True
        window.settings = dict(DEFAULTS)
        window.layers = [(0, "F.Cu"), (31, "B.Cu")]
        window.vars = {
            key: Variable()
            for key, value in DEFAULTS.items()
            if not isinstance(value, bool)
        }
        window.vars.update({
            "shape_taper_percent": Variable(),
            "fill_ratio_percent": Variable(),
            "arcs_per_turn": Variable(),
            "segments_per_turn": Variable(),
        })
        window.bool_vars = {
            key: Variable(value)
            for key, value in DEFAULTS.items()
            if isinstance(value, bool)
        }
        choices = {
            "application_preset": "motor_linear",
            "manufacturing_preset": "standard",
        }
        window._choice_maps = {
            key: {}
            for key, value in DEFAULTS.items()
            if isinstance(value, str)
        }
        window._choice_maps["layer_count"] = {}
        window._choice_code = lambda key, default=None: choices.get(key, default)
        window._set_choice = lambda key, value: choices.__setitem__(key, value)
        window._layer_index = lambda: 0
        calls = []
        window._apply_application_fill_recommendation = (
            lambda: calls.append("fill")
        )
        window._refresh_motor_recommendation = (
            lambda **options: calls.append(options)
        )
        window._update_preview = lambda: None
        window._update_preset_summary = lambda *_args: None

        window._apply_selected_presets()

        recommendation = next(item for item in calls if isinstance(item, dict))
        self.assertNotIn("fill", calls)
        self.assertIn("turns", recommendation["preserve_keys"])
        self.assertIn("fill_ratio", recommendation["preserve_keys"])
        self.assertEqual("3", window.vars["turns"].get())
        self.assertEqual("55", window.vars["fill_ratio_percent"].get())
        self.assertTrue(window.bool_vars["motor_alternate_winding"].get())


if __name__ == "__main__":
    unittest.main()

