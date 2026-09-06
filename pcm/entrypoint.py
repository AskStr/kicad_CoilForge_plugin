# -*- coding: utf-8 -*-
"""PCM-only registration shim; keep the manual-install entrypoint unchanged."""

import json

from .coilforge.metadata import PLUGIN_VERSION

__version__ = PLUGIN_VERSION
SpiralPlugin = None


def _ipc_enabled(pcbnew_module):
    from .coilforge.compat import KiCadCompat
    from .coilforge.kicad_paths import active_kicad_common_path, settings_version

    version = settings_version(KiCadCompat(pcbnew_module).version_string())
    if not version or tuple(map(int, version.split("."))) < (9, 0):
        return False
    path = active_kicad_common_path(pcbnew_module=pcbnew_module)
    try:
        with open(path, "r", encoding="utf-8") as config:
            return json.load(config).get("api", {}).get("enable_server") is True
    except (OSError, ValueError, TypeError, AttributeError):
        return False


try:
    import pcbnew
except ImportError:
    pass  # IPC-only KiCad discovers plugin.json instead.
else:
    if not _ipc_enabled(pcbnew):
        from .kicad_spiral_plugin import SpiralPlugin
        SpiralPlugin().register()
