# -*- coding: utf-8 -*-
"""Stable public metadata for CoilForge."""

PLUGIN_BRAND = "CoilForge"
PLUGIN_VERSION = "0.2.8"
PLUGIN_AUTHOR_EN = "askstar"
PLUGIN_AUTHOR_ZH = "问星"
# Archive/legacy directory name; not a PCM package identifier.
PACKAGE_IDENTIFIER = "kicad_CoilForge_plugin"
PCM_PACKAGE_IDENTIFIER = "com.github.askstr.kicad-coilforge-plugin"
# Use a strict reverse-DNS ID for both PCM and the IPC runtime.
IPC_PLUGIN_IDENTIFIER = PCM_PACKAGE_IDENTIFIER
LEGACY_IPC_PLUGIN_IDENTIFIER = "org.coilforge.kicad_spiral_plugin"
MIN_KICAD_VERSION = "10.0"
MIN_LEGACY_KICAD_VERSION = "6.0"
MAX_LEGACY_KICAD_VERSION = "10.0"
CONFIG_DIRECTORY_NAME = PLUGIN_BRAND
SETTINGS_FILENAME = "coilforge-settings.json"
PROFILES_FILENAME = "coilforge-profiles.json"
ARCHIVE_BASENAME = PACKAGE_IDENTIFIER + "-v" + PLUGIN_VERSION

PCM_ARCHIVE_BASENAME = ARCHIVE_BASENAME + "-PCM"
MAX_PCM_KICAD_VERSION = "10.99"
