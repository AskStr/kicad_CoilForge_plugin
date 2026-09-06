import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from zipfile import ZipFile, ZIP_DEFLATED

from jsonschema import Draft7Validator
from package_plugin import build_archive
from package_repository import build_repository

ROOT = Path(__file__).resolve().parents[1]


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.base = Path(self.workspace.name)
        self.archive = build_archive(output_path=self.base / "release-PCM.zip")
        self.output = self.base / "repository"
        self.base_url = "https://example.com/coilforge"
        self.download = "https://example.com/releases/v0.2.8/release-PCM.zip"

    def generate(self, archive=None, **kwargs):
        return build_repository(archive or self.archive, self.output, self.base_url, self.download, **kwargs)

    def read(self, name):
        return json.loads((self.output / name).read_text(encoding="utf-8"))

    def fixture_release(self, version):
        # Local synthetic update fixture only; never published as a real release.
        target = self.base / (version + "-fixture.zip")
        with ZipFile(self.archive) as source, ZipFile(target, "w", ZIP_DEFLATED) as archive:
            for name in source.namelist():
                data = source.read(name)
                if name == "metadata.json":
                    metadata = json.loads(data)
                    metadata["versions"][0]["version"] = version
                    data = json.dumps(metadata).encode("utf-8")
                archive.writestr(name, data)
        return target

    def test_indexes_and_download_integrity_match_completed_archive(self):
        before = self.archive.read_bytes()
        path = self.generate(timestamp=1788693600)
        self.assertEqual(self.output / "repository.json", path)
        repository = self.read("repository.json")
        packages = self.read("packages.json")
        for schema_name in ("pcm.v1.schema.json", "pcm.v2.schema.json"):
            for definition, value in (("Repository", repository), ("PackageArray", packages)):
                schema = json.loads((ROOT / "pcm/schemas" / schema_name).read_text(encoding="utf-8"))
                schema["$ref"] = "#/definitions/" + definition
                Draft7Validator(schema).validate(value)
        self.assertEqual(self.base_url + "/packages.json", repository["packages"]["url"])
        self.assertEqual(hashlib.sha256((self.output / "packages.json").read_bytes()).hexdigest(), repository["packages"]["sha256"])
        release = packages["packages"][0]["versions"][0]
        self.assertEqual(self.download, release["download_url"])
        self.assertEqual(len(before), release["download_size"])
        self.assertEqual(hashlib.sha256(before).hexdigest(), release["download_sha256"])
        self.assertEqual(before, self.archive.read_bytes())
        with ZipFile(self.archive) as archive:
            self.assertNotIn("download_url", json.loads(archive.read("metadata.json"))["versions"][0])

    def test_same_inputs_are_reproducible_and_do_not_trigger_false_updates(self):
        self.generate(timestamp=1788693600)
        before = [(self.output / name).read_bytes() for name in ("packages.json", "repository.json")]
        self.generate()
        self.assertEqual(before, [(self.output / name).read_bytes() for name in ("packages.json", "repository.json")])

    def test_new_version_preserves_history_and_advances_cache_timestamp(self):
        self.generate(timestamp=1788693600)
        old_hash = self.read("repository.json")["packages"]["sha256"]
        fixture = self.fixture_release("0.2.9")
        with mock.patch("package_repository.time.time", return_value=1788693600):
            self.generate(fixture)
        self.assertEqual(["0.2.9", "0.2.8"], [v["version"] for v in self.read("packages.json")["packages"][0]["versions"]])
        resource = self.read("repository.json")["packages"]
        self.assertEqual(1788693601, resource["update_timestamp"])
        self.assertNotEqual(old_hash, resource["sha256"])
        self.assertEqual("testing", self.read("packages.json")["packages"][0]["versions"][0]["status"])

    def test_versions_sort_numerically_and_keep_newer_releases_when_backfilling(self):
        self.generate(timestamp=1788693600)
        self.generate(self.fixture_release("0.2.10"))
        self.generate(self.fixture_release("0.2.9"))
        self.assertEqual(["0.2.10", "0.2.9", "0.2.8"],
                         [v["version"] for v in self.read("packages.json")["packages"][0]["versions"]])

    def test_epoch_takes_precedence_over_numeric_version(self):
        from package_repository import _version_key
        self.assertGreater(_version_key({"version": "0.1", "version_epoch": 1}),
                           _version_key({"version": "99.0.0"}))
        self.assertEqual(_version_key({"version": "1.2"}), _version_key({"version": "1.2.0"}))

    def test_same_version_with_different_bytes_is_rejected_without_changing_indexes(self):
        self.generate(timestamp=1788693600)
        before = (self.output / "packages.json").read_bytes()
        with ZipFile(self.archive, "a") as archive:
            archive.comment = b"changed release"
        with self.assertRaisesRegex(ValueError, "bump PLUGIN_VERSION"):
            self.generate()
        self.assertEqual(before, (self.output / "packages.json").read_bytes())

    def test_old_timestamp_cannot_hide_an_update(self):
        self.generate(timestamp=1788693600)
        with self.assertRaisesRegex(ValueError, "increasing"):
            self.generate(self.fixture_release("0.2.9"), timestamp=1788693600)
        self.assertEqual("0.2.8", self.read("packages.json")["packages"][0]["versions"][0]["version"])

    def test_invalid_urls_do_not_create_output(self):
        for url in ("file:///tmp/repo", "https://user:password@example.com/repo", "https://example.com/repo#fragment"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                build_repository(self.archive, self.output, url, self.download)
        self.assertFalse(self.output.exists())

    def test_previous_history_and_invalid_history_are_explicit(self):
        self.generate(timestamp=1788693600)
        history = self.output / "packages.json"
        second = self.base / "second"
        build_repository(self.fixture_release("0.2.9"), second, self.base_url, self.download,
                         previous_packages=history, timestamp=1788693601)
        self.assertEqual(2, len(json.loads((second / "packages.json").read_text(encoding="utf-8"))["packages"][0]["versions"]))
        with self.assertRaises(FileNotFoundError):
            self.generate(previous_packages=self.base / "missing.json")


if __name__ == "__main__":
    unittest.main()
