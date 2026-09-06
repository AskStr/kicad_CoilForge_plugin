import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from jsonschema import Draft7Validator
from coilforge.metadata import PCM_ARCHIVE_BASENAME, PCM_PACKAGE_IDENTIFIER
from package_plugin import build_archive

ROOT = Path(__file__).resolve().parents[1]


class UnifiedPcmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="CoilForge PCM ")
        cls.base = Path(cls.workspace.name)
        cls.archive = build_archive(output_path=cls.base / "release.zip")
        cls.installed = cls.base / "third-party/plugins" / PCM_PACKAGE_IDENTIFIER.replace(".", "_")
        with ZipFile(cls.archive) as archive:
            cls.metadata = json.loads(archive.read("metadata.json"))
            cls.names = archive.namelist()
            for name in cls.names:
                if name.startswith("plugins/"):
                    path = cls.installed / name[len("plugins/"):]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(archive.read(name))

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def test_requested_archive_name_and_version_range(self):
        self.assertEqual("kicad_CoilForge_plugin-v0.2.8-PCM", PCM_ARCHIVE_BASENAME)
        version = self.metadata["versions"][0]
        self.assertEqual("6.0", version["kicad_version"])
        self.assertEqual("10.99", version["kicad_version_max"])
        self.assertEqual("ipc", version["runtime"])
        self.assertFalse(any(key.startswith("download_") for key in version))

    def test_unified_metadata_validates_with_old_and_new_pcm_schemas(self):
        for name in ("pcm.v1.schema.json", "pcm.v2.schema.json"):
            schema = json.loads((ROOT / "pcm/schemas" / name).read_text(encoding="utf-8"))
            Draft7Validator(schema).validate(self.metadata)

    def test_both_discovery_entrypoints_exist_without_changing_manual_loader(self):
        for name in ("__init__.py", "kicad_spiral_plugin.py", "plugin.json", "ipc_plugin.py", "requirements.txt"):
            self.assertIn("plugins/" + name, self.names)
        self.assertEqual((ROOT / "pcm/entrypoint.py").read_bytes(), (self.installed / "__init__.py").read_bytes())
        self.assertNotEqual((ROOT / "__init__.py").read_bytes(), (self.installed / "__init__.py").read_bytes())
        for name in ("legacy_plugin.py", "interface.py", "ipc_ui.py", "geometry.py", "electrical.py"):
            self.assertEqual((ROOT / "coilforge" / name).read_bytes(), (self.installed / "coilforge" / name).read_bytes())

    def _registration(self, version, api, expected, config_text=None):
        config = self.base / "config" / version
        config.mkdir(parents=True, exist_ok=True)
        (config / "kicad_common.json").write_text(
            config_text if config_text is not None else json.dumps({"api": {"enable_server": api}}), encoding="utf-8"
        )
        code = r'''
import importlib, os, sys, types
from unittest.mock import MagicMock
sys.path.insert(0, sys.argv[1])
os.environ['KICAD_CONFIG_HOME'] = sys.argv[3]
sys.modules['kipy'] = None
sys.modules['tkinter'] = None
registered = []
class ActionPlugin:
    def __init__(self): self.defaults()
    def register(self): registered.append(self)
pcbnew = types.ModuleType('pcbnew')
pcbnew.ActionPlugin = ActionPlugin
pcbnew.GetBuildVersion = lambda: sys.argv[4] + '.7'
sys.modules['pcbnew'] = pcbnew
wx = MagicMock()
wx.Dialog = type('Dialog', (), {})
wx.Panel = type('Panel', (), {})
wx.ScrolledWindow = type('ScrolledWindow', (), {})
sys.modules['wx'] = wx
importlib.import_module(sys.argv[2])
print(len(registered))
'''
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code, str(self.installed.parent), self.installed.name,
             str(self.base / "config"), version], cwd=self.base, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(str(expected), result.stdout.strip())

    def test_runtime_selection_avoids_duplicate_registration(self):
        for version in ("6.0", "7.0", "8.0", "9.0", "10.0"):
            for api in (False, True):
                with self.subTest(version=version, api=api):
                    expected = 0 if api and int(version.split(".")[0]) >= 9 else 1
                    self._registration(version, api, expected)

    def test_bad_api_config_does_not_break_legacy_discovery(self):
        for text in ("invalid", "null", '{"api": null}'):
            self._registration("10.0", False, 1, config_text=text)

    def test_no_pcbnew_import_is_safe_for_ipc_only_hosts(self):
        code = "import sys, importlib; sys.path.insert(0,sys.argv[1]); sys.modules['pcbnew']=None; p=importlib.import_module(sys.argv[2]); assert p.SpiralPlugin is None"
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(self.installed.parent), self.installed.name],
                                cwd=self.base, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
