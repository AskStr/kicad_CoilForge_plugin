#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KiCad IPC action entrypoint for CoilForge."""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from coilforge.i18n import Translator, detect_language, localize_error
from coilforge.metadata import PLUGIN_VERSION


def _show_fatal(message):
    # KiCad may launch pythonw.exe without stderr and without a working Tk.
    # A Tk-only error dialog would hide the very failure it needs to report.
    if sys.platform == "win32":
        try:
            import ctypes
            show = ctypes.WinDLL("user32", use_last_error=True).MessageBoxW
            show.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                             ctypes.c_wchar_p, ctypes.c_uint]
            show.restype = ctypes.c_int
            if show(None, message, "CoilForge", 0x10 | 0x10000):
                return
        except Exception:
            pass

    root = None
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("CoilForge", message, parent=root)
        return
    except Exception:
        if sys.stderr is not None:
            print(message, file=sys.stderr)
    finally:
        if root is not None:
            root.destroy()


def main():
    translator = Translator(detect_language())
    try:
        from coilforge.ipc_ui import SpiralIpcWindow
        from kipy import KiCad
        from coilforge.ipc_backend import IpcBoardBackend
        from coilforge.settings import SettingsStore

        client = KiCad()
        backend = IpcBoardBackend(client)
        language = detect_language(kicad_version=backend.version_text)
        translator = Translator(language)
        store = SettingsStore(backend.plugin_settings_file())
        SpiralIpcWindow(
            backend, store, translator, PLUGIN_VERSION
        ).run()
        return 0
    except Exception as error:
        detail = localize_error(translator, error)
        if isinstance(error, ImportError):
            if error.name in ("tkinter", "_tkinter"):
                detail = translator("ipc_tk_unavailable", error=detail)
            elif error.name == "kipy":
                detail = translator("ipc_kipy_unavailable", error=detail)
        message = translator("ipc_start_failed", error=detail)
        message += "\n\n" + translator(
            "ipc_python_executable", executable=sys.executable,
            base_executable=getattr(sys, "_base_executable", sys.executable),
        )
        _show_fatal(message)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
