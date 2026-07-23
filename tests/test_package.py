import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from coilforge.metadata import ARCHIVE_BASENAME
from package_plugin import PLUGIN_NAME, build_archive


class PackageTests(unittest.TestCase):

    def test_public_package_name_is_kicad_coilforge_plugin(self):
        self.assertEqual("kicad_CoilForge_plugin", PLUGIN_NAME)
        self.assertEqual(
            "kicad_CoilForge_plugin-v0.2.6", ARCHIVE_BASENAME
        )

    def test_archive_has_plugin_root_and_posix_paths(self):
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "plugin.zip"
            result = build_archive(project_root, output, include_tests=True)
            self.assertEqual(output.resolve(), result)
            with ZipFile(result, "r") as archive:
                names = archive.namelist()
            self.assertIn(
                PLUGIN_NAME + "/kicad_spiral_plugin.py", names
            )
            self.assertIn(
                PLUGIN_NAME + "/coilforge/presets.py", names
            )
            self.assertIn(
                PLUGIN_NAME + "/plugin.json", names
            )
            self.assertIn(
                PLUGIN_NAME + "/ipc_plugin.py", names
            )
            self.assertIn(
                PLUGIN_NAME + "/requirements.txt", names
            )
            self.assertIn(
                PLUGIN_NAME + "/coilforge/electrical.py", names
            )
            self.assertIn(
                PLUGIN_NAME + "/coilforge/workflow.py", names
            )
            self.assertIn(
                PLUGIN_NAME + "/assets/coilforge.png", names
            )
            self.assertIn(
                PLUGIN_NAME + "/coilforge/ui_layout.py", names
            )
            self.assertIn(
                PLUGIN_NAME + "/coilforge/preview.py", names
            )
            self.assertIn(
                PLUGIN_NAME + "/tests/test_geometry.py", names
            )
            self.assertIn(PLUGIN_NAME + "/LICENSE", names)
            self.assertNotIn(PLUGIN_NAME + "/README.md", names)
            self.assertNotIn(PLUGIN_NAME + "/README.zh-CN.md", names)
            self.assertFalse(any(
                name.startswith(PLUGIN_NAME + "/docs/") for name in names
            ))
            self.assertTrue(all("\\" not in name for name in names))
            self.assertTrue(all(
                name.startswith(PLUGIN_NAME + "/") for name in names
            ))


if __name__ == "__main__":
    unittest.main()

