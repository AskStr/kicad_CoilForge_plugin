# -*- coding: utf-8 -*-
"""Version-aware KiCad configuration path discovery using only stdlib."""

import os
import re
import sys


KNOWN_SETTINGS_VERSIONS = (
    "10.99",
    "10.0",
    "9.0",
    "8.0",
    "7.0",
    "6.0",
)


def version_string_from_pcbnew(pcbnew_module):
    if pcbnew_module is None:
        return None
    for name in (
            "GetMajorMinorVersion", "GetBuildVersion", "FullVersion", "Version"):
        getter = getattr(pcbnew_module, name, None)
        if callable(getter):
            try:
                value = getter()
                if value:
                    return str(value)
            except Exception:
                pass
    return None


def settings_version(value):
    """Extract KiCad's major.minor settings directory name."""
    if value is None:
        return None
    match = re.search(r"(?<!\d)(\d+)\.(\d+)", str(value))
    if match:
        return "{}.{}".format(int(match.group(1)), int(match.group(2)))
    match = re.search(r"(?<!\d)(\d+)(?!\d)", str(value))
    if match:
        return "{}.0".format(int(match.group(1)))
    return None


def settings_path_from_pcbnew(pcbnew_module):
    """Return KiCad's already-versioned settings directory when exposed."""
    if pcbnew_module is None:
        return None
    manager = None
    getter = getattr(pcbnew_module, "GetSettingsManager", None)
    if callable(getter):
        try:
            manager = getter()
        except Exception:
            manager = None
    candidates = (manager, getattr(pcbnew_module, "SETTINGS_MANAGER", None))
    for candidate in candidates:
        path_getter = getattr(candidate, "GetUserSettingsPath", None)
        if callable(path_getter):
            try:
                value = str(path_getter())
                if value:
                    return value
            except Exception:
                pass
    return None


def platform_kicad_config_root(environ=None, platform_name=None, home=None):
    """Return the platform config root ending in the KiCad directory."""
    env = os.environ if environ is None else environ
    platform_value = sys.platform if platform_name is None else platform_name
    user_home = os.path.expanduser("~") if home is None else str(home)
    if platform_value == "win32" or platform_value == "nt":
        base = env.get("APPDATA") or os.path.join(
            user_home, "AppData", "Roaming"
        )
    elif platform_value == "darwin":
        base = os.path.join(user_home, "Library", "Preferences")
    else:
        base = env.get("XDG_CONFIG_HOME") or os.path.join(
            user_home, ".config"
        )
    return os.path.join(base, "kicad")


def _as_directory(path):
    if not path:
        return None
    value = os.path.abspath(os.path.expanduser(str(path)))
    if os.path.basename(value).lower() == "kicad_common.json":
        return os.path.dirname(value)
    return value


def settings_directory_candidates(pcbnew_module=None, kicad_version=None,
                                  environ=None, platform_name=None, home=None,
                                  explicit_path=None):
    """Return ordered possible settings directories for the active KiCad."""
    env = os.environ if environ is None else environ
    version = settings_version(
        kicad_version or version_string_from_pcbnew(pcbnew_module)
    )
    candidates = []

    def add(path):
        directory = _as_directory(path)
        if directory and directory not in candidates:
            candidates.append(directory)

    add(explicit_path)
    add(settings_path_from_pcbnew(pcbnew_module))

    configured_root = env.get("KICAD_CONFIG_HOME")
    roots = []
    if configured_root:
        roots.append(configured_root)
    roots.append(platform_kicad_config_root(
        environ=env, platform_name=platform_name, home=home
    ))

    versions = (version,) if version else KNOWN_SETTINGS_VERSIONS
    for root in roots:
        root_version = settings_version(os.path.basename(os.path.normpath(root)))
        if configured_root and root == configured_root and root_version == version:
            # Some existing scripts set KICAD_CONFIG_HOME to the final version
            # directory, even though KiCad documents it as the parent root.
            add(root)
            continue
        for candidate_version in versions:
            if candidate_version:
                add(os.path.join(root, candidate_version))
        if configured_root and root == configured_root:
            add(root)
    return candidates


def kicad_common_candidates(**kwargs):
    return [
        os.path.join(path, "kicad_common.json")
        for path in settings_directory_candidates(**kwargs)
    ]


def active_kicad_common_path(**kwargs):
    """Return the first existing common config file for the active version."""
    for path in kicad_common_candidates(**kwargs):
        if os.path.isfile(path):
            return path
    return None


def preferred_settings_directory(**kwargs):
    candidates = settings_directory_candidates(**kwargs)
    return candidates[0] if candidates else platform_kicad_config_root()
