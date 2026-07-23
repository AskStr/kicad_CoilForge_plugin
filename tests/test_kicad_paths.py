import os
import tempfile
import unittest

from coilforge.kicad_paths import (
    active_kicad_common_path,
    settings_directory_candidates,
    settings_version,
)


class KiCadPathTests(unittest.TestCase):
    def test_extracts_release_and_nightly_settings_versions(self):
        self.assertEqual("6.0", settings_version("6.0.11"))
        self.assertEqual("10.0", settings_version("KiCad 10.0.2"))
        self.assertEqual("10.99", settings_version("10.99.0-123-gabcdef"))

    def test_kicad_6_through_10_and_1099_use_distinct_directories(self):
        for version in ("6.0", "7.0", "8.0", "9.0", "10.0", "10.99"):
            paths = settings_directory_candidates(
                kicad_version=version,
                environ={"XDG_CONFIG_HOME": "/cfg"},
                platform_name="linux",
                home="/home/test",
            )
            self.assertEqual(
                os.path.abspath("/cfg/kicad/" + version), paths[0]
            )

    def test_windows_release_path_is_versioned(self):
        paths = settings_directory_candidates(
            kicad_version="8.0.4",
            environ={"APPDATA": r"C:\Users\test\AppData\Roaming"},
            platform_name="win32",
            home=r"C:\Users\test",
        )
        self.assertIn(
            os.path.abspath(
                r"C:\Users\test\AppData\Roaming\kicad\8.0"
            ),
            paths,
        )

    def test_linux_release_path_is_versioned(self):
        paths = settings_directory_candidates(
            kicad_version="9.0.1",
            environ={"XDG_CONFIG_HOME": "/tmp/config"},
            platform_name="linux",
            home="/home/test",
        )
        self.assertEqual(
            os.path.abspath("/tmp/config/kicad/9.0"), paths[0]
        )

    def test_config_home_is_a_root_and_gets_version_appended(self):
        with tempfile.TemporaryDirectory() as directory:
            versioned = os.path.join(directory, "10.99")
            os.makedirs(versioned)
            expected = os.path.join(versioned, "kicad_common.json")
            with open(expected, "w", encoding="utf-8") as config_file:
                config_file.write("{}")
            found = active_kicad_common_path(
                kicad_version="10.99.0",
                environ={"KICAD_CONFIG_HOME": directory},
                platform_name="linux",
                home=directory,
            )
            self.assertEqual(expected, found)

    def test_already_versioned_config_home_is_not_duplicated(self):
        paths = settings_directory_candidates(
            kicad_version="10.99.0",
            environ={"KICAD_CONFIG_HOME": "/cfg/10.99"},
            platform_name="linux",
            home="/home/test",
        )
        self.assertEqual(os.path.abspath("/cfg/10.99"), paths[0])

    def test_settings_manager_path_has_highest_runtime_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            class Manager(object):
                @staticmethod
                def GetUserSettingsPath():
                    return directory

            class Pcbnew(object):
                SETTINGS_MANAGER = Manager

                @staticmethod
                def GetBuildVersion():
                    return "7.0.10"

            paths = settings_directory_candidates(
                pcbnew_module=Pcbnew,
                environ={},
                platform_name="linux",
                home="/home/test",
            )
            self.assertEqual(os.path.abspath(directory), paths[0])


if __name__ == "__main__":
    unittest.main()
