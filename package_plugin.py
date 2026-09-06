#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build and validate a deterministic KiCad PCM installation archive."""

import argparse
import json
import os
import re
from pathlib import Path, PurePosixPath
import stat
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from coilforge.metadata import (
    ARCHIVE_BASENAME, PCM_ARCHIVE_BASENAME, MAX_PCM_KICAD_VERSION,
    IPC_PLUGIN_IDENTIFIER, MIN_KICAD_VERSION,
    MIN_LEGACY_KICAD_VERSION, MAX_LEGACY_KICAD_VERSION,
    PACKAGE_IDENTIFIER, PCM_PACKAGE_IDENTIFIER, PLUGIN_BRAND, PLUGIN_VERSION,
)


# Kept as the public archive/legacy name, not the PCM installation directory.
PLUGIN_NAME = PACKAGE_IDENTIFIER
IPC_RUNTIME_FILES = (
    "ipc_plugin.py",
    "plugin.json",
    "requirements.txt",
    "assets/coilforge.png",
    "coilforge/__init__.py",
    "coilforge/metadata.py",
    "coilforge/ipc_backend.py",
    "coilforge/ipc_ui.py",
)
LEGACY_RUNTIME_FILES = (
    "__init__.py", "kicad_spiral_plugin.py", "assets/coilforge.png",
    "coilforge/__init__.py", "coilforge/metadata.py",
    "coilforge/legacy_plugin.py", "coilforge/interface.py", "coilforge/compat.py",
)
CORE_DIRECTORY = "coilforge"
DOCUMENT_FILES = ("LICENSE",)


def _archive_name(relative_path):
    # PCM inserts its own package-id directory below plugins/ on installation.
    return PurePosixPath("plugins", *relative_path.parts).as_posix()


def _validate_schema(root, value, schema_name, label, definition=None):
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
    if definition is not None:
        schema["$ref"] = "#/definitions/" + definition
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


def build_archive(source_root=None, output_path=None, include_tests=False, runtime="pcm"):
    """Build a schema-validated PCM ZIP and return its absolute path.

    include_tests retains the old diagnostic option; bundled test sources are
    for inspection, not a standalone development checkout.
    """
    if runtime not in ("pcm", "swig", "ipc"):
        raise ValueError("Unsupported plugin runtime: " + str(runtime))
    basename = (PCM_ARCHIVE_BASENAME if runtime == "pcm" else
                ARCHIVE_BASENAME + ("-ipc" if runtime == "ipc" else ""))
    root = Path(source_root or Path(__file__).resolve().parent).resolve()
    output = Path(
        output_path or root / "dist" / (basename + ".zip")
    ).expanduser().resolve()
    if output.suffix.lower() != ".zip":
        raise ValueError("Output must be a .zip archive")

    runtime_files = (IPC_RUNTIME_FILES + LEGACY_RUNTIME_FILES if runtime == "pcm"
                     else IPC_RUNTIME_FILES if runtime == "ipc" else LEGACY_RUNTIME_FILES)
    relative_files = {Path(name) for name in runtime_files + DOCUMENT_FILES}
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
    if runtime == "pcm":
        entries["plugins/__init__.py"] = (root / "pcm" / "entrypoint.py").read_bytes()
    if runtime in ("pcm", "ipc"):
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
            "kicad_version": (MIN_KICAD_VERSION if runtime == "ipc"
                              else MIN_LEGACY_KICAD_VERSION),
            "install_size": sum(len(data) for data in entries.values()),
        }],
    })
    if runtime == "ipc":
        metadata["versions"][0]["runtime"] = "ipc"
        schema_name = "pcm.v2.schema.json"
    else:
        # PCM v1 (KiCad 6+) predates the runtime field and means SWIG.
        schema_name = "pcm.v1.schema.json"
        metadata["$schema"] = "https://go.kicad.org/pcm/schemas/v1"
        # KiCad 6 PCM only accepts its older license vocabulary. LICENSE is unchanged.
        if metadata["license"] == "GPL-3.0-or-later":
            metadata["license"] = "GPL-3.0"
        metadata["versions"][0]["kicad_version_max"] = MAX_LEGACY_KICAD_VERSION
        metadata["description_full"] = (
            "CoilForge creates configurable PCB spiral coils and planar-motor "
            "windings with an English and Simplified Chinese interface. "
            "Uses the existing pcbnew and wxPython ActionPlugin on KiCad 6–10.0; "
            "no IPC API server, external Python, tkinter or pip dependencies required. "
            "For KiCad 10.99, install the IPC package to use the existing Tk interface."
        )
    if runtime == "pcm":
        # Older PCM v1 readers ignore this forward-compatible field. IPC-only
        # KiCad requires it; the installed shim still supports SWIG hosts.
        metadata["versions"][0]["runtime"] = "ipc"
        metadata["versions"][0]["kicad_version_max"] = MAX_PCM_KICAD_VERSION
        metadata["description_full"] = (
            "CoilForge creates PCB coils with the existing ActionPlugin and IPC/Tk interfaces. "
            "One PCM package supports KiCad 6–10.99. With the API disabled, SWIG-capable "
            "versions use built-in pcbnew/wxPython. With the API enabled, KiCad 9+ uses IPC "
            "and requires Python 3.10+ with tkinter, _tkinter, Tcl/Tk, venv and pip. "
            "KiCad 10.99 requires the API. IPC dependencies may need a package index."
        )
        _validate_schema(root, metadata, "pcm.v2.schema.json", "metadata.json")
    _validate_schema(root, metadata, schema_name, "metadata.json")
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
        description="Build one PCM installation ZIP for KiCad 6–10.99."
    )
    parser.add_argument(
        "-o", "--output",
        help="Output ZIP path (default: dist/" + PCM_ARCHIVE_BASENAME + ".zip)",
    )
    parser.add_argument(
        "--runtime", choices=("pcm", "swig", "ipc"), default="pcm",
        help="pcm: unified installation (default); swig/ipc: runtime-specific diagnostic builds",
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
            runtime=arguments.runtime,
        )
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, "Package build failed: {}\n".format(error))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
