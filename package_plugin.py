#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a cross-platform KiCad plug-in ZIP archive.

The archive always uses POSIX separators as required by the ZIP format, while
local paths are handled with ``pathlib`` on Windows, macOS and Linux.
"""

import argparse
import os
from pathlib import Path, PurePosixPath

from coilforge.metadata import ARCHIVE_BASENAME, PACKAGE_IDENTIFIER
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


PLUGIN_NAME = PACKAGE_IDENTIFIER
RUNTIME_FILES = (
    "__init__.py",
    "ipc_plugin.py",
    "kicad_spiral_plugin.py",
    "plugin.json",
    "requirements.txt",
    "assets/coilforge.png",
)
CORE_DIRECTORY = "coilforge"

# Keep runtime packages small. User/developer documentation stays in the
# repository; the license remains in the archive for redistribution compliance.
DOCUMENT_FILES = ("LICENSE",)


def _archive_name(relative_path):
    return PurePosixPath(PLUGIN_NAME, *relative_path.parts).as_posix()


def _write_file(archive, source, archive_name):
    info = ZipInfo(archive_name, date_time=(2020, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, source.read_bytes())


def build_archive(source_root=None, output_path=None, include_tests=False):
    """Build the plug-in archive and return its absolute path."""
    root = Path(source_root or Path(__file__).resolve().parent).resolve()
    output = Path(
        output_path or root / "dist" / (ARCHIVE_BASENAME + ".zip")
    ).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    relative_files = [Path(name) for name in RUNTIME_FILES + DOCUMENT_FILES]
    relative_files.extend(
        path.relative_to(root)
        for path in sorted((root / CORE_DIRECTORY).glob("*.py"))
    )
    if include_tests:
        relative_files.extend(
            path.relative_to(root)
            for path in sorted((root / "tests").glob("test_*.py"))
        )

    missing = [str(path) for path in relative_files if not (root / path).is_file()]
    if missing:
        raise FileNotFoundError("Missing package files: " + ", ".join(missing))

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=PLUGIN_NAME + "-", suffix=".zip.tmp", dir=str(output.parent)
    )
    os.close(descriptor)
    Path(temporary_name).unlink()
    try:
        with ZipFile(temporary_name, "w", compression=ZIP_DEFLATED) as archive:
            for relative_path in sorted(
                    relative_files, key=lambda value: value.as_posix()):
                _write_file(
                    archive,
                    root / relative_path,
                    _archive_name(relative_path),
                )
        Path(temporary_name).replace(output)
    finally:
        temporary_path = Path(temporary_name)
        if temporary_path.exists():
            temporary_path.unlink()
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the KiCad spiral plug-in ZIP archive."
    )
    parser.add_argument(
        "-o", "--output",
        help=("Output ZIP path (default: "
              "dist/kicad_CoilForge_plugin-v<version>.zip)"),
    )
    parser.add_argument(
        "--include-tests", action="store_true", help="Include unit tests"
    )
    arguments = parser.parse_args(argv)
    output = build_archive(
        output_path=arguments.output,
        include_tests=arguments.include_tests,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
