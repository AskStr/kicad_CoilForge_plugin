#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KiCad IPC action entrypoint for CoilForge."""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from coilforge.i18n import Translator, detect_language, localize_error
from coilforge.ipc_backend import IpcBoardBackend
from coilforge.metadata import PLUGIN_VERSION
from coilforge.settings import SettingsStore


def _show_fatal(message):
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("CoilForge", message, parent=root)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


def main():
    try:
        from kipy import KiCad
        from coilforge.ipc_ui import SpiralIpcWindow
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
        translator = Translator(detect_language())
        _show_fatal(translator(
            "ipc_start_failed", error=localize_error(translator, error)
        ))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
