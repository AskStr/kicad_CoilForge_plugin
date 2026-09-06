"""Run with KiCad's bundled Python and a PCM-extracted plugin directory.

Usage: <KiCad>/bin/python.exe tests/smoke_legacy_kicad.py <installed-plugin-root>
Use an isolated KICAD_CONFIG_HOME with API disabled; this opens and closes the real wx UI.
It does not modify a user's board or require an IPC server.
"""

import importlib
import json
from pathlib import Path
import sys


def main():
    installed = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(installed.parent))
    # The legacy route must not import IPC or Tk, even in the unified PCM package.
    sys.modules["kipy"] = None
    sys.modules["tkinter"] = None
    import pcbnew
    import wx

    app = wx.App(False)
    board = pcbnew.BOARD()
    pcbnew.GetBoard = lambda: board

    def fail_dialog(message, *_args, **_kwargs):
        raise AssertionError(message)

    wx.MessageBox = fail_dialog
    # Native registration requires a running PCB editor (PgmOrNull). Capture
    # the registration request here; native discovery is a separate GUI check.
    registered = []
    pcbnew.ActionPlugin.register = lambda plugin: registered.append(plugin)
    package = importlib.import_module(installed.name)
    assert len(registered) == 1
    plugin = registered[0]
    assert isinstance(plugin, package.SpiralPlugin)
    assert plugin.show_toolbar_button
    assert Path(plugin.icon_file_name).is_file()
    plugin.Run()
    dialog = plugin._dialog
    assert dialog is not None and dialog.IsShown()
    app.Yield()
    plugin.Run()
    assert plugin._dialog is dialog, "Second click must reuse the open dialog"
    result = {
        "kicad": pcbnew.GetBuildVersion(),
        "python": sys.version.split()[0],
        "wx": wx.version(),
        "title": dialog.GetTitle(),
        "layers": len(dialog.layers),
        "status": "passed",
    }
    dialog.Destroy()
    app.Yield()
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
