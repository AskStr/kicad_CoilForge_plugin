import json
import os
import tempfile
import unittest

from coilforge.settings import (
    DEFAULTS, SettingsStore, UserProfileStore, default_settings_path,
    sanitize_settings, shared_profiles_path,
)


class SettingsTests(unittest.TestCase):
    def test_default_via_dimensions_match_common_manufacturing(self):
        self.assertEqual(0.6, DEFAULTS["via_diameter_mm"])
        self.assertEqual(0.4, DEFAULTS["via_drill_mm"])
        self.assertGreater(
            DEFAULTS["via_diameter_mm"], DEFAULTS["via_drill_mm"]
        )
    def test_old_custom_default_via_is_migrated(self):
        clean = sanitize_settings({
            "schema_version": 5,
            "manufacturing_preset": "custom",
            "via_diameter_mm": 0.8,
            "via_drill_mm": 0.4,
        })
        self.assertEqual(DEFAULTS["schema_version"], clean["schema_version"])
        self.assertEqual(0.6, clean["via_diameter_mm"])
        self.assertEqual(0.4, clean["via_drill_mm"])

    def test_old_manufacturing_preset_via_is_preserved(self):
        clean = sanitize_settings({
            "schema_version": 5,
            "manufacturing_preset": "standard",
            "via_diameter_mm": 0.8,
            "via_drill_mm": 0.4,
        })
        self.assertEqual(0.8, clean["via_diameter_mm"])
    def test_invalid_values_fall_back_to_defaults(self):
        clean = sanitize_settings({
            "segments_per_turn": "bad",
            "spacing_mode": "unknown",
            "create_group": "yes",
        })
        self.assertEqual(DEFAULTS["segments_per_turn"], clean["segments_per_turn"])
        self.assertEqual(DEFAULTS["spacing_mode"], clean["spacing_mode"])
        self.assertEqual(DEFAULTS["create_group"], clean["create_group"])

    def test_new_auto_and_arc_settings_are_sanitized(self):
        clean = sanitize_settings({
            "schema_version": 1,
            "primitive_mode": "arc",
            "sizing_mode": "fit_length",
            "quality_preset": "smooth",
            "arcs_per_turn": 2,
            "fill_ratio": 2.0,
        })
        self.assertEqual(DEFAULTS["schema_version"], clean["schema_version"])
        self.assertEqual("arc", clean["primitive_mode"])
        self.assertEqual("fit_length", clean["sizing_mode"])
        self.assertEqual("smooth", clean["quality_preset"])
        self.assertEqual(4, clean["arcs_per_turn"])
        self.assertEqual(0.99, clean["fill_ratio"])

    def test_motor_shape_settings_are_sanitized(self):
        clean = sanitize_settings({
            "application_preset": "motor_trapezoid",
            "coil_shape": "motor_trapezoid",
            "shape_aspect_ratio": 9.0,
            "shape_taper_ratio": -2.0,
        })
        self.assertEqual("motor_trapezoid", clean["application_preset"])
        self.assertEqual("motor_trapezoid", clean["coil_shape"])
        self.assertEqual(4.0, clean["shape_aspect_ratio"])
        self.assertEqual(-0.75, clean["shape_taper_ratio"])

    def test_preset_and_electrical_settings_are_sanitized(self):
        clean = sanitize_settings({
            "application_preset": "wireless_power",
            "manufacturing_preset": "heavy_copper",
            "copper_thickness_um": -1,
            "target_current_a": -2,
        })
        self.assertEqual("wireless_power", clean["application_preset"])
        self.assertEqual("heavy_copper", clean["manufacturing_preset"])
        self.assertEqual(1.0, clean["copper_thickness_um"])
        self.assertEqual(0.0, clean["target_current_a"])


    def test_motor_engineering_settings_are_sanitized(self):
        clean = sanitize_settings({
            "target_torque_nm": -1,
            "air_gap_flux_density_t": 5,
            "electrical_loading_a_per_m": 10,
            "winding_factor": 2,
            "motor_inner_ratio": 0.99,
            "motor_slot_count": 500,
            "motor_phase_count": 2,
        })
        self.assertEqual(0.0, clean["target_torque_nm"])
        self.assertEqual(2.0, clean["air_gap_flux_density_t"])
        self.assertEqual(100.0, clean["electrical_loading_a_per_m"])
        self.assertEqual(1.0, clean["winding_factor"])
        self.assertEqual(0.9, clean["motor_inner_ratio"])
        self.assertEqual(128, clean["motor_slot_count"])
        self.assertEqual(3, clean["motor_phase_count"])

    def test_motor_parameter_auto_mode_is_sanitized_and_persisted(self):
        self.assertTrue(DEFAULTS["motor_parameters_auto"])
        self.assertFalse(sanitize_settings({
            "motor_parameters_auto": False,
        })["motor_parameters_auto"])
        self.assertTrue(sanitize_settings({
            "motor_parameters_auto": "false",
        })["motor_parameters_auto"])

    def test_default_path_uses_active_kicad_version_directory(self):
        path = default_settings_path(
            kicad_version="10.99.0",
            environ={"KICAD_CONFIG_HOME": "/cfg"},
            platform_name="linux",
            home="/home/test",
        )
        self.assertEqual(
            os.path.abspath(
                "/cfg/10.99/plugins/CoilForge/coilforge-settings.json"
            ),
            path,
        )

    def test_missing_or_corrupt_settings_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "coilforge-settings.json")
            store = SettingsStore(path)
            self.assertEqual(DEFAULTS, store.load())
            with open(path, "w", encoding="utf-8") as output_file:
                output_file.write("{broken")
            self.assertEqual(DEFAULTS, store.load())

    def test_legacy_settings_are_ignored_when_new_config_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            current = os.path.join(directory, "coilforge-settings.json")
            legacy = os.path.join(directory, "settings.json")
            with open(legacy, "w", encoding="utf-8") as legacy_file:
                json.dump({"turns": 77}, legacy_file)
            loaded = SettingsStore(current).load()
            self.assertEqual(DEFAULTS["turns"], loaded["turns"])
            self.assertFalse(os.path.exists(current))

    def test_shared_profiles_path_is_not_version_scoped(self):
        path = shared_profiles_path(
            environ={"KICAD_CONFIG_HOME": "/cfg"},
            platform_name="linux", home="/home/test",
        )
        self.assertEqual(os.path.abspath(
            "/cfg/plugins/CoilForge/coilforge-profiles.json"
        ), path)

    def test_named_profiles_round_trip_rename_delete_and_import(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = os.path.join(directory, "profiles.json")
            export_path = os.path.join(directory, "export.json")
            imported_path = os.path.join(directory, "imported.json")
            store = UserProfileStore(source_path)
            values = dict(DEFAULTS)
            values.update({"turns": 8.5, "group_name": "motor-a"})
            store.save("常用电机", values)
            self.assertEqual(("常用电机",), store.names())
            self.assertEqual(8.5, store.load("常用电机")["turns"])
            store.rename("常用电机", "扇形电机")
            self.assertIsNone(store.load("常用电机"))
            self.assertEqual("motor-a", store.load("扇形电机")["group_name"])
            store.export_file(export_path)
            imported = UserProfileStore(imported_path)
            self.assertEqual(("扇形电机",), imported.import_file(export_path))
            self.assertTrue(imported.delete("扇形电机"))
            self.assertFalse(imported.delete("扇形电机"))

    def test_profile_names_are_unique_case_insensitively(self):
        with tempfile.TemporaryDirectory() as directory:
            store = UserProfileStore(os.path.join(directory, "profiles.json"))
            store.save("Motor", DEFAULTS)
            with self.assertRaisesRegex(ValueError, "profile_exists"):
                store.save("motor", DEFAULTS)
            store.save("motor", {"turns": 3}, overwrite=True)
            self.assertEqual(3.0, store.load("MOTOR")["turns"])

    def test_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            store = SettingsStore(path)
            values = dict(DEFAULTS)
            values.update({
                "turns": 2.5,
                "group_name": "测试",
                "layer_count": 12,
                "via_diameter_mm": 0.9,
            })
            store.save(values)
            loaded = store.load()
            self.assertEqual(2.5, loaded["turns"])
            self.assertEqual("测试", loaded["group_name"])
            self.assertEqual(12, loaded["layer_count"])
            self.assertEqual(0.9, loaded["via_diameter_mm"])
            with open(path, "r", encoding="utf-8") as settings_file:
                json.load(settings_file)


if __name__ == "__main__":
    unittest.main()





