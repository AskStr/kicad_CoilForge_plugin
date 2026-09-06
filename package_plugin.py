#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build and validate a deterministic KiCad PCM IPC installation archive."""

import argparse
import json
import os
import re
from pathlib import Path, PurePosixPath
import stat
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from coilforge.metadata import (
    ARCHIVE_BASENAME, IPC_PLUGIN_IDENTIFIER, MIN_KICAD_VERSION,
    PACKAGE_IDENTIFIER, PCM_PACKAGE_IDENTIFIER, PLUGIN_BRAND, PLUGIN_VERSION,
)


# Kept as the public archive/legacy name, not the PCM installation directory.
PLUGIN_NAME = PACKAGE_IDENTIFIER
RUNTIME_FILES = (
    "ipc_plugin.py",
    "plugin.json",
    "requirements.txt",
    "assets/coilforge.png",
    "coilforge/__init__.py",
    "coilforge/metadata.py",
    "coilforge/ipc_backend.py",
    "coilforge/ipc_ui.py",
)
CORE_DIRECTORY = "coilforge"
DOCUMENT_FILES = ("LICENSE",)


def _archive_name(relative_path):
    # PCM inserts its own package-id directory below plugins/ on installation.
    return PurePosixPath("plugins", *relative_path.parts).as_posix()


def _validate_schema(root, value, schema_name, label):
    try:
        from jsonschema import Draft7Validator
    except ImportError as error:
        raise RuntimeError(
            "Building requires jsonschema; run: "
            "python -m pip install -r requirements-dev.txt"
        ) from error
    schema = json.loads(
        (root / "pcm" / "schemas" / schema_name).read_text(encoding="utf-8")
    )
    Draft7Validator.check_schema(schema)
    errors = list(Draft7Validator(schema).iter_errors(value))
    if errors:
        error = errors[0]
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        raise ValueError("{} at {}: {}".format(label, location, error.message))


def _validate_plugin(root, entries):
    manifest = json.loads(entries["plugins/plugin.json"].decode("utf-8"))
    _validate_schema(root, manifest, "api.v1.schema.json", "plugin.json")
    if manifest["identifier"] != IPC_PLUGIN_IDENTIFIER:
        raise ValueError("plugin.json identifier must match IPC_PLUGIN_IDENTIFIER")
    # Runtime validation is stricter than the published IPC v1 JSON Schema.
    if not re.fullmatch(
            r"[A-Za-z]{2,}(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?){2,}",
            manifest["identifier"]):
        raise ValueError("IPC identifier must be a strict reverse-DNS name")
    if manifest["runtime"]["type"] != "python":
        raise ValueError("CoilForge requires the Python IPC runtime")
    if not manifest["actions"]:
        raise ValueError("plugin.json must contain an action")
    identifiers = [action["identifier"] for action in manifest["actions"]]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("plugin.json action identifiers must be unique")
    for action in manifest["actions"]:
        references = [action["entrypoint"]]
        for key in ("icons-light", "icons-dark"):
            references.extend(action.get(key, []))
        for reference in references:
            # Schema validates strings, not path safety or file existence.
            path = PurePosixPath(reference)
            if (path.is_absolute() or "\\" in reference or ":" in reference
                    or any(part in ("", ".", "..") for part in reference.split("/"))):
                raise ValueError("Unsafe IPC resource path: " + reference)
            if "plugins/" + reference not in entries:
                raise FileNotFoundError("Missing IPC resource: " + reference)


def _write_file(archive, data, archive_name):
    info = ZipInfo(archive_name, date_time=(2020, 1, 1, 0, 0, 0))
    info.create_system = 3  # Fixed Unix attributes, independent of build host.
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.compress_type = ZIP_DEFLATED
    archive.writestr(info, data, compresslevel=9)


def build_archive(source_root=None, output_path=None, include_tests=False):
    """Build a schema-validated PCM IPC ZIP and return its absolute path.

    include_tests retains the old diagnostic option; bundled test sources are
    for inspection, not a standalone development checkout.
    """
    root = Path(source_root or Path(__file__).resolve().parent).resolve()
    output = Path(
        output_path or root / "dist" / (ARCHIVE_BASENAME + ".zip")
    ).expanduser().resolve()
    if output.suffix.lower() != ".zip":
        raise ValueError("Output must be a .zip archive")

    relative_files = {Path(name) for name in RUNTIME_FILES + DOCUMENT_FILES}
    relative_files.update(
        path.relative_to(root)
        for path in (root / CORE_DIRECTORY).glob("*.py")
    )
    if include_tests:
        relative_files.update(
            path.relative_to(root)
            for path in (root / "tests").glob("test_*.py")
        )
    missing = sorted(str(path) for path in relative_files if not (root / path).is_file())
    if missing:
        raise FileNotFoundError("Missing package files: " + ", ".join(missing))

    entries = {
        _archive_name(path): (root / path).read_bytes()
        for path in sorted(relative_files)
    }
    _validate_plugin(root, entries)
    metadata = json.loads(
        (root / "pcm" / "metadata.template.json").read_text(encoding="utf-8")
    )
    metadata.update({
        "name": PLUGIN_BRAND,
        "identifier": PCM_PACKAGE_IDENTIFIER,
        "versions": [{
            "version": PLUGIN_VERSION,
            "status": "testing",
            "kicad_version": MIN_KICAD_VERSION,
            "runtime": "ipc",
            "install_size": sum(len(data) for data in entries.values()),
        }],
    })
    _validate_schema(root, metadata, "pcm.v2.schema.json", "metadata.json")
    if metadata["type"] != "plugin":
        raise ValueError("CoilForge PCM package type must be plugin")
    entries["metadata.json"] = (
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    # Validate before touching an existing release; replace only a complete ZIP.
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=PLUGIN_NAME + "-", suffix=".zip.tmp", dir=str(output.parent)
    )
    os.close(descriptor)
    try:
        with ZipFile(temporary_name, "w", compression=ZIP_DEFLATED) as archive:
            for name, data in sorted(entries.items()):
                _write_file(archive, data, name)
        Path(temporary_name).replace(output)
    finally:
        temporary_path = Path(temporary_name)
        if temporary_path.exists():
            temporary_path.unlink()
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a schema-validated KiCad PCM IPC installation ZIP."
    )
    parser.add_argument(
        "-o", "--output",
        help="Output ZIP path (default: dist/" + ARCHIVE_BASENAME + ".zip)",
    )
    parser.add_argument(
        "--include-tests", action="store_true",
        help="Include diagnostic test sources (not a standalone test environment)",
    )
    arguments = parser.parse_args(argv)
    try:
        output = build_archive(
            output_path=arguments.output,
            include_tests=arguments.include_tests,
        )
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, "Package build failed: {}\n".format(error))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
