#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate standard PCM repository indexes from a completed release ZIP.

This is an offline release tool: it does not upload files or contact KiCad.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

from coilforge.metadata import PCM_PACKAGE_IDENTIFIER
from package_plugin import _validate_schema

ROOT = Path(__file__).resolve().parent


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _http_url(value):
    url = urlsplit(value)
    if (url.scheme not in ("https", "http") or not url.hostname
            or url.username is not None or url.password is not None or url.fragment):
        raise ValueError("Expected an HTTP(S) URL without credentials or fragment: " + value)
    return value


def _version_key(version):
    numbers = tuple(map(int, version["version"].split(".")))
    return (version.get("version_epoch", 0),) + numbers + (0,) * (3 - len(numbers))


def _write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + "-", suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
        except BaseException:
            stream.close()
            temporary.unlink()
            raise
    try:
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_repository(archive_path, output_dir, base_url, download_url,
                     previous_packages=None, timestamp=None):
    """Merge a release into packages.json and publish repository.json locally.

    Existing release bytes are immutable: bump PLUGIN_VERSION for a changed ZIP.
    The existing output packages.json is used as history unless explicitly overridden.
    """
    _http_url(base_url)
    _http_url(download_url)
    if urlsplit(base_url).query:
        raise ValueError("Repository base URL must not have a query string")
    archive_path = Path(archive_path).resolve()
    output = Path(output_dir).resolve()
    with ZipFile(archive_path) as archive:
        metadata = json.loads(archive.read("metadata.json"))
    _validate_schema(ROOT, metadata, "pcm.v1.schema.json", "archive metadata")
    _validate_schema(ROOT, metadata, "pcm.v2.schema.json", "archive metadata")
    if metadata["identifier"] != PCM_PACKAGE_IDENTIFIER or len(metadata["versions"]) != 1:
        raise ValueError("Expected a single-version CoilForge PCM archive")
    version = metadata["versions"][0]
    if version.get("runtime") != "ipc" or version["kicad_version"] != "6.0":
        raise ValueError("Repository releases must use the unified PCM archive")
    digest = hashlib.sha256()
    with archive_path.open("rb") as archive:
        for block in iter(lambda: archive.read(1024 * 1024), b""):
            digest.update(block)
    version.update(download_url=download_url, download_size=archive_path.stat().st_size,
                   download_sha256=digest.hexdigest())

    packages_path = output / "packages.json"
    repository_path = output / "repository.json"
    history_path = Path(previous_packages) if previous_packages is not None else packages_path
    packages = {"packages": []}
    if previous_packages is not None or history_path.exists():
        packages = json.loads(history_path.read_text(encoding="utf-8"))
        _validate_schema(ROOT, packages, "pcm.v1.schema.json", "previous packages", "PackageArray")
    existing = next((p for p in packages["packages"] if p["identifier"] == metadata["identifier"]), None)
    if existing is not None:
        for old in existing["versions"]:
            if _version_key(old) == _version_key(version):
                if old.get("download_sha256") != version["download_sha256"]:
                    raise ValueError("Release " + version["version"] + " already has different bytes; bump PLUGIN_VERSION")
            else:
                metadata["versions"].append(old)
        packages["packages"].remove(existing)
    metadata["versions"].sort(key=_version_key, reverse=True)
    packages["packages"].append(metadata)
    packages["packages"].sort(key=lambda p: p["identifier"])
    packages_data = _json_bytes(packages)
    packages_hash = hashlib.sha256(packages_data).hexdigest()

    old_resource = {}
    if repository_path.exists():
        old_resource = json.loads(repository_path.read_text(encoding="utf-8")).get("packages", {})
    old_time = old_resource.get("update_timestamp", 0)
    changed = old_resource.get("sha256") != packages_hash
    if timestamp is None:
        timestamp = max(int(time.time()), old_time + 1) if changed else old_time
    if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp < 0:
        raise ValueError("Timestamp must be a nonnegative Unix timestamp")
    if changed and old_resource and timestamp <= old_time:
        raise ValueError("Changed packages require an increasing update timestamp")
    repository = {
        "$schema": "https://go.kicad.org/pcm/schemas/v1",
        "name": "CoilForge PCM repository",
        "maintainer": metadata["author"],
        "packages": {
            "url": base_url.rstrip("/") + "/packages.json",
            "sha256": packages_hash,
            "update_timestamp": timestamp,
            "update_time_utc": datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        },
    }
    for schema in ("pcm.v1.schema.json", "pcm.v2.schema.json"):
        _validate_schema(ROOT, packages, schema, "packages.json", "PackageArray")
        _validate_schema(ROOT, repository, schema, "repository.json", "Repository")
    # Validate everything before writing; update the root pointer last.
    _write_atomic(packages_path, packages_data)
    _write_atomic(repository_path, _json_bytes(repository))
    return repository_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, help="Completed *-PCM.zip release")
    parser.add_argument("--output", default="pcm/repository", help="Local repository output directory")
    parser.add_argument("--base-url", required=True, help="Public HTTP(S) directory that will contain the indexes")
    parser.add_argument("--download-url", required=True, help="Direct URL of the versioned release ZIP")
    parser.add_argument("--previous-packages", help="Existing packages.json to retain historical versions")
    parser.add_argument("--timestamp", type=int, help="Explicit UTC Unix timestamp for reproducible generation")
    args = parser.parse_args(argv)
    try:
        result = build_repository(args.archive, args.output, args.base_url, args.download_url,
                                  args.previous_packages, args.timestamp)
    except (OSError, ValueError, RuntimeError, KeyError, BadZipFile) as error:
        parser.exit(1, "Repository build failed: {}\n".format(error))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
