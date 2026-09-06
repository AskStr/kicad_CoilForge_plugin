import contextlib
import hashlib
import io
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock
from zipfile import ZipFile

from jsonschema import Draft7Validator

from coilforge.metadata import (
    ARCHIVE_BASENAME, IPC_PLUGIN_IDENTIFIER, LEGACY_IPC_PLUGIN_IDENTIFIER, MIN_KICAD_VERSION,
    PCM_PACKAGE_IDENTIFIER, PLUGIN_VERSION,
)
from package_plugin import PLUGIN_NAME, build_archive, main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.workspace.name)
        cls.archive = build_archive(
            PROJECT_ROOT, cls.directory / "nested" / "plugin.zip", runtime="ipc"
        )
        with ZipFile(cls.archive) as archive:
            cls.entries = {name: archive.read(name) for name in archive.namelist()}
        cls.metadata = json.loads(cls.entries["metadata.json"])
        cls.manifest = json.loads(cls.entries["plugins/plugin.json"])

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def copy_source(self, directory):
        root = Path(directory) / "source"
        root.mkdir()
        for name in ("coilforge", "assets", "pcm"):
            shutil.copytree(
                PROJECT_ROOT / name, root / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        for name in ("ipc_plugin.py", "plugin.json", "requirements.txt", "LICENSE"):
            shutil.copyfile(PROJECT_ROOT / name, root / name)
        return root

    def test_public_archive_name_is_preserved_with_new_version(self):
        self.assertEqual("kicad_CoilForge_plugin", PLUGIN_NAME)
        self.assertEqual(PLUGIN_NAME + "-v" + PLUGIN_VERSION, ARCHIVE_BASENAME)
        self.assertNotEqual("0.2.6", PLUGIN_VERSION)
        self.assertEqual(self.archive.resolve(), self.archive)

    def test_pcm_and_ipc_manifests_pass_official_schemas(self):
        for filename, value in (
            ("pcm.v2.schema.json", self.metadata),
            ("api.v1.schema.json", self.manifest),
        ):
            with self.subTest(schema=filename):
                schema = json.loads(
                    (PROJECT_ROOT / "pcm" / "schemas" / filename).read_text(encoding="utf-8")
                )
                Draft7Validator.check_schema(schema)
                Draft7Validator(schema).validate(value)
                self.assertEqual(schema["$id"], value["$schema"])

    def test_pcm_metadata_has_one_local_ipc_version(self):
        self.assertEqual(PCM_PACKAGE_IDENTIFIER, self.metadata["identifier"])
        self.assertNotIn("_", self.metadata["identifier"])
        self.assertEqual("plugin", self.metadata["type"])
        self.assertEqual("GPL-3.0-or-later", self.metadata["license"])
        self.assertEqual(1, len(self.metadata["versions"]))
        version = self.metadata["versions"][0]
        self.assertEqual(PLUGIN_VERSION, version["version"])
        self.assertEqual(MIN_KICAD_VERSION, version["kicad_version"])
        self.assertEqual("testing", version["status"])
        self.assertEqual("ipc", version["runtime"])
        self.assertFalse(any(key.startswith("download_") for key in version))
        self.assertEqual(
            sum(len(data) for name, data in self.entries.items() if name != "metadata.json"),
            version["install_size"],
        )

    def test_ipc_identity_settings_and_unicode_are_preserved(self):
        from coilforge.ipc_backend import PLUGIN_IDENTIFIER
        self.assertEqual("org.coilforge.kicad_spiral_plugin", LEGACY_IPC_PLUGIN_IDENTIFIER)
        self.assertEqual(PCM_PACKAGE_IDENTIFIER, IPC_PLUGIN_IDENTIFIER)
        self.assertNotIn("_", IPC_PLUGIN_IDENTIFIER)
        self.assertEqual(IPC_PLUGIN_IDENTIFIER, self.manifest["identifier"])
        self.assertEqual(PLUGIN_IDENTIFIER, self.manifest["identifier"])
        self.assertEqual("python", self.manifest["runtime"]["type"])
        self.assertEqual("3.10", self.manifest["runtime"]["min_version"])
        self.assertIn("问星", self.manifest["description"])
        self.assertEqual(
            (PROJECT_ROOT / "plugin.json").read_bytes(),
            self.entries["plugins/plugin.json"],
        )

    def test_archive_has_pcm_root_and_only_safe_runtime_paths(self):
        with ZipFile(self.archive) as archive:
            names = archive.namelist()
            self.assertIsNone(archive.testzip())
        self.assertEqual(sorted(names), names)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(1, names.count("metadata.json"))
        for name in names:
            self.assertNotIn("\\", name)
            self.assertFalse(PurePosixPath(name).is_absolute())
            self.assertNotIn("..", PurePosixPath(name).parts)
            self.assertTrue(name == "metadata.json" or name.startswith("plugins/"))
            self.assertFalse(name.startswith(PLUGIN_NAME + "/"))
        for name in (
            "plugins/ipc_plugin.py", "plugins/plugin.json", "plugins/requirements.txt",
            "plugins/coilforge/__init__.py", "plugins/coilforge/metadata.py",
            "plugins/coilforge/ipc_backend.py", "plugins/coilforge/ipc_ui.py",
            "plugins/assets/coilforge.png", "plugins/LICENSE",
        ):
            self.assertIn(name, names)
        # Do not register a second, legacy ActionPlugin from the IPC package.
        for name in ("plugins/__init__.py", "plugins/kicad_spiral_plugin.py"):
            self.assertNotIn(name, names)
        for name in names:
            self.assertFalse(any(part in name for part in (
                "__pycache__", ".pyc", "tests/", "docs/", "pcm/", "README",
                "package_plugin.py", "requirements-dev.txt", "settings.json",
                "profiles.json", ".venv/", ".git/",
            )))

    def test_all_ipc_action_paths_resolve_inside_plugins(self):
        self.assertTrue(self.manifest["actions"])
        for action in self.manifest["actions"]:
            self.assertIn("pcb", action["scopes"])
            self.assertIn("plugins/" + action["entrypoint"], self.entries)
            for key in ("icons-light", "icons-dark"):
                for path in action[key]:
                    self.assertTrue(self.entries["plugins/" + path].startswith(b"\x89PNG\r\n\x1a\n"))

    def test_pcm_install_layout_imports_without_checkout_or_swig(self):
        # Mirror PCM's insertion of the sanitized package identifier.
        with tempfile.TemporaryDirectory(prefix="coilforge installed ") as directory:
            third_party = Path(directory)
            package_id = self.metadata["identifier"].replace(".", "_")
            for name, data in self.entries.items():
                if name == "metadata.json":
                    continue
                top, relative = name.split("/", 1)
                destination = third_party / top / package_id / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            plugin_root = third_party / "plugins" / package_id
            code = """
import sys
sys.path.insert(0, sys.argv[1])
sys.modules['pcbnew'] = None
import ipc_plugin
import coilforge.ipc_ui
from coilforge.metadata import PLUGIN_VERSION, IPC_PLUGIN_IDENTIFIER
from coilforge.ipc_backend import PLUGIN_IDENTIFIER
assert PLUGIN_IDENTIFIER == IPC_PLUGIN_IDENTIFIER
assert callable(ipc_plugin.main)
assert 'coilforge.legacy_plugin' not in sys.modules
print(PLUGIN_VERSION)
"""
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-c", code, str(plugin_root)],
                cwd=third_party, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(PLUGIN_VERSION, result.stdout.strip())

    def test_swig_archive_uses_pcm_v1_and_only_legacy_discovery(self):
        output = build_archive(PROJECT_ROOT, self.directory / "legacy.zip", runtime="swig")
        with ZipFile(output) as archive:
            names = set(archive.namelist())
            metadata = json.loads(archive.read("metadata.json"))
            schema = json.loads((
                PROJECT_ROOT / "pcm/schemas/pcm.v1.schema.json"
            ).read_text(encoding="utf-8"))
            Draft7Validator(schema).validate(metadata)
            self.assertEqual(schema["$id"], metadata["$schema"])
            version = metadata["versions"][0]
            self.assertEqual("6.0", version["kicad_version"])
            self.assertEqual("10.0", version["kicad_version_max"])
            self.assertNotIn("runtime", version)  # PCM v1 implicitly uses SWIG.
            self.assertEqual("GPL-3.0", metadata["license"])
            self.assertEqual(
                (PROJECT_ROOT / "LICENSE").read_bytes(), archive.read("plugins/LICENSE")
            )
            self.assertEqual(PCM_PACKAGE_IDENTIFIER, metadata["identifier"])
            self.assertEqual(
                sum(len(archive.read(name)) for name in names if name != "metadata.json"),
                version["install_size"],
            )
            for name in (
                "__init__.py", "kicad_spiral_plugin.py", "assets/coilforge.png",
                "coilforge/legacy_plugin.py", "coilforge/interface.py", "coilforge/compat.py",
            ):
                self.assertIn("plugins/" + name, names)
            for name in (
                "plugin.json", "ipc_plugin.py", "requirements.txt",
            ):
                self.assertNotIn("plugins/" + name, names)

    def test_both_pcm_packages_preserve_all_existing_core_modules(self):
        # Runtime selection only changes discovery entrypoints/PCM metadata,
        # never substitutes or removes either existing UI implementation.
        for runtime in ("pcm", "swig", "ipc"):
            with self.subTest(runtime=runtime):
                output = build_archive(
                    PROJECT_ROOT, self.directory / (runtime + "-core.zip"), runtime=runtime
                )
                with ZipFile(output) as archive:
                    for source in (PROJECT_ROOT / "coilforge").glob("*.py"):
                        self.assertEqual(
                            source.read_bytes(), archive.read("plugins/coilforge/" + source.name)
                        )

    def test_ipc_pcm_version_range_includes_kicad_1099(self):
        version = self.metadata["versions"][0]
        self.assertEqual("ipc", version["runtime"])
        self.assertLessEqual(tuple(map(int, version["kicad_version"].split("."))), (10, 99))
        self.assertNotIn("kicad_version_max", version)
        self.assertIn("plugins/coilforge/ipc_ui.py", self.entries)
        self.assertIn(b"import tkinter as tk", self.entries["plugins/coilforge/ipc_ui.py"])

    def test_legacy_pcm_registration_from_installed_layout_without_ipc(self):
        output = build_archive(PROJECT_ROOT, self.directory / "legacy-import.zip", runtime="swig")
        with tempfile.TemporaryDirectory(prefix="coilforge legacy installed ") as directory:
            with ZipFile(output) as archive:
                installed = Path(directory) / "plugins" / PCM_PACKAGE_IDENTIFIER.replace(".", "_")
                for name in archive.namelist():
                    if name.startswith("plugins/"):
                        path = installed / name[len("plugins/"):]
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(archive.read(name))
            code = """
import importlib, pathlib, sys, types
from unittest.mock import MagicMock
sys.path.insert(0, sys.argv[1])
sys.modules['kipy'] = None
sys.modules['tkinter'] = None
registered = []
class ActionPlugin:
    def __init__(self):
        self.defaults()
    def register(self):
        registered.append(self)
pcbnew = types.ModuleType('pcbnew')
pcbnew.ActionPlugin = ActionPlugin
sys.modules['pcbnew'] = pcbnew
wx = MagicMock()
wx.Dialog = type('Dialog', (), {})
wx.Panel = type('Panel', (), {})
wx.ScrolledWindow = type('ScrolledWindow', (), {})
sys.modules['wx'] = wx
package = importlib.import_module(sys.argv[2])
assert len(registered) == 1
plugin = registered[0]
assert isinstance(plugin, package.SpiralPlugin)
assert plugin.show_toolbar_button and callable(plugin.Run)
assert pathlib.Path(plugin.icon_file_name).is_file()
print(package.__version__)
"""
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-c", code, str(installed.parent), installed.name],
                cwd=directory, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(PLUGIN_VERSION, result.stdout.strip())

    def test_legacy_archive_is_reproducible(self):
        first = build_archive(PROJECT_ROOT, self.directory / "legacy-first.zip", runtime="swig")
        second = build_archive(PROJECT_ROOT, self.directory / "legacy-second.zip", runtime="swig")
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_missing_legacy_entrypoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy_source(directory)
            with self.assertRaisesRegex(FileNotFoundError, "__init__.py"):
                build_archive(root, Path(directory) / "invalid.zip")

    def test_unknown_runtime_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported plugin runtime"):
            build_archive(PROJECT_ROOT, runtime="unknown")

    def test_ipc_cli_is_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "ipc.zip"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(["--runtime", "ipc", "--output", str(output)]))
            with ZipFile(output) as archive:
                self.assertIn("plugins/plugin.json", archive.namelist())
                self.assertNotIn("plugins/__init__.py", archive.namelist())

    def test_build_is_byte_reproducible(self):
        second = build_archive(PROJECT_ROOT, self.directory / "second.zip", runtime="ipc")
        self.assertEqual(
            hashlib.sha256(self.archive.read_bytes()).digest(),
            hashlib.sha256(second.read_bytes()).digest(),
        )
        with ZipFile(second) as archive:
            for info in archive.infolist():
                self.assertEqual((2020, 1, 1, 0, 0, 0), info.date_time)
                self.assertEqual(3, info.create_system)
                self.assertEqual(stat.S_IFREG | 0o644, info.external_attr >> 16)

    def test_include_tests_remains_an_explicit_diagnostic_option(self):
        output = build_archive(
            PROJECT_ROOT, self.directory / "diagnostic.zip", include_tests=True, runtime="ipc"
        )
        with ZipFile(output) as archive:
            self.assertIn("plugins/tests/test_geometry.py", archive.namelist())
            self.assertIn("plugins/tests/test_package.py", archive.namelist())
            self.assertIn("metadata.json", archive.namelist())
            self.assertNotIn("plugins/package_plugin.py", archive.namelist())

    def test_invalid_ipc_manifest_fails_before_replacing_release(self):
        cases = {
            "schema": lambda m: m.update(runtime={"type": "invalid"}),
            "identifier": lambda m: m.update(identifier="org.example.different"),
            "no actions": lambda m: m.update(actions=[]),
            "duplicate action": lambda m: m["actions"].append(m["actions"][0].copy()),
            "missing entrypoint": lambda m: m["actions"][0].update(entrypoint="missing.py"),
            "missing icon": lambda m: m["actions"][0].update(**{"icons-light": ["missing.png"]}),
        }
        for path in ("../outside.py", "/absolute.py", "C:/drive.py", "dir\\entry.py", "./ipc_plugin.py", ""):
            cases[path or "empty path"] = lambda m, p=path: m["actions"][0].update(entrypoint=p)
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy_source(directory)
            output = Path(directory) / "release.zip"
            for label, mutate in cases.items():
                with self.subTest(case=label):
                    manifest = json.loads((PROJECT_ROOT / "plugin.json").read_text(encoding="utf-8"))
                    mutate(manifest)
                    (root / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
                    output.write_bytes(b"previous release")
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        build_archive(root, output, runtime="ipc")
                    self.assertEqual(b"previous release", output.read_bytes())
                    self.assertEqual([], list(output.parent.glob("*.zip.tmp")))

    def test_schema_valid_legacy_identifier_is_rejected_by_runtime_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy_source(directory)
            path = root / "plugin.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["identifier"] = LEGACY_IPC_PLUGIN_IDENTIFIER
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with mock.patch("package_plugin.IPC_PLUGIN_IDENTIFIER", LEGACY_IPC_PLUGIN_IDENTIFIER):
                with self.assertRaisesRegex(ValueError, "strict reverse-DNS"):
                    build_archive(root, Path(directory) / "invalid.zip", runtime="ipc")

    def test_invalid_pcm_template_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy_source(directory)
            path = root / "pcm/metadata.template.json"
            original = json.loads(path.read_text(encoding="utf-8"))
            for field, value in (("author", {"name": "missing contact"}), ("type", "library")):
                with self.subTest(field=field):
                    metadata = dict(original)
                    metadata[field] = value
                    path.write_text(json.dumps(metadata), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        build_archive(root, Path(directory) / "invalid.zip", runtime="ipc")

    def test_missing_runtime_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy_source(directory)
            (root / "requirements.txt").unlink()
            with self.assertRaisesRegex(FileNotFoundError, "requirements.txt"):
                build_archive(root, Path(directory) / "invalid.zip", runtime="ipc")

    def test_write_failure_preserves_release_and_cleans_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release.zip"
            output.write_bytes(b"previous release")
            with mock.patch("package_plugin._write_file", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    build_archive(PROJECT_ROOT, output)
            self.assertEqual(b"previous release", output.read_bytes())
            self.assertEqual([output], list(output.parent.iterdir()))

    def test_cli_builds_pcm_zip_and_reports_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "from-cli.zip"
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(0, main(["--output", str(output)]))
            self.assertEqual(str(output), stdout.getvalue().strip())
            with ZipFile(output) as archive:
                self.assertIn("metadata.json", archive.namelist())
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as error:
                    main(["--output", str(Path(directory) / "not-a-zip.txt")])
            self.assertEqual(1, error.exception.code)
            self.assertIn("Output must be a .zip", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
