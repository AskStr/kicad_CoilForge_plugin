import contextlib
import io
import sys
import types
import unittest
from unittest import mock

import ipc_plugin
from coilforge.i18n import Translator


class IpcStartupTests(unittest.TestCase):
    def test_windows_error_is_visible_without_tk_or_console(self):
        user32 = mock.Mock()
        user32.MessageBoxW.return_value = 1
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(sys, "stderr", None), \
                mock.patch.dict(sys.modules, {"tkinter": None}), \
                mock.patch("ctypes.WinDLL", return_value=user32, create=True):
            ipc_plugin._show_fatal("缺少 _tkinter")
        user32.MessageBoxW.assert_called_once_with(
            None, "缺少 _tkinter", "CoilForge", 0x10 | 0x10000
        )

    def test_error_dialog_destroys_tk_root_even_if_messagebox_fails(self):
        tk = mock.Mock()
        tk.messagebox.showerror.side_effect = RuntimeError("dialog failed")
        stderr = io.StringIO()
        with mock.patch.object(sys, "platform", "linux"), \
                mock.patch.dict(sys.modules, {"tkinter": tk}), \
                contextlib.redirect_stderr(stderr):
            ipc_plugin._show_fatal("startup failed")
        tk.Tk.return_value.destroy.assert_called_once_with()
        self.assertIn("startup failed", stderr.getvalue())

    def test_error_without_tk_or_stderr_does_not_raise(self):
        with mock.patch.object(sys, "platform", "linux"), \
                mock.patch.object(sys, "stderr", None), \
                mock.patch.dict(sys.modules, {"tkinter": None}):
            ipc_plugin._show_fatal("startup failed")

    def test_missing_tk_reports_interpreter_and_recovery_steps(self):
        original_import = __import__
        for name in ("tkinter", "_tkinter"):
            for language in ("en", "zh"):
                with self.subTest(module=name, language=language):
                    def missing_ui(module, *args, **kwargs):
                        if module == "coilforge.ipc_ui":
                            raise ModuleNotFoundError(
                                "No module named '" + name + "'", name=name
                            )
                        return original_import(module, *args, **kwargs)

                    with mock.patch("builtins.__import__", side_effect=missing_ui), \
                            mock.patch.object(ipc_plugin, "detect_language", return_value=language), \
                            mock.patch.object(ipc_plugin, "_show_fatal") as show:
                        self.assertEqual(1, ipc_plugin.main())
                    message = show.call_args.args[0]
                    self.assertIn(Translator(language)(
                        "ipc_tk_unavailable", error="No module named '" + name + "'"
                    ), message)
                    self.assertIn(sys.executable, message)

    def test_missing_kipy_is_not_misreported_as_tk(self):
        ui = types.ModuleType("coilforge.ipc_ui")
        ui.SpiralIpcWindow = mock.Mock()
        with mock.patch.dict(sys.modules, {"coilforge.ipc_ui": ui, "kipy": None}), \
                mock.patch.object(ipc_plugin, "detect_language", return_value="en"), \
                mock.patch.object(ipc_plugin, "_show_fatal") as show:
            self.assertEqual(1, ipc_plugin.main())
        self.assertIn("missing kicad-python", show.call_args.args[0])
        self.assertNotIn("does not provide working tkinter", show.call_args.args[0])

    def test_successful_entrypoint_runs_window(self):
        modules = {}
        for name, symbol in (
            ("kipy", "KiCad"), ("coilforge.ipc_ui", "SpiralIpcWindow"),
            ("coilforge.ipc_backend", "IpcBoardBackend"),
            ("coilforge.settings", "SettingsStore"),
        ):
            module = types.ModuleType(name)
            setattr(module, symbol, mock.Mock())
            modules[name] = module
        with mock.patch.dict(sys.modules, modules), \
                mock.patch.object(ipc_plugin, "detect_language", return_value="en"), \
                mock.patch.object(ipc_plugin, "_show_fatal") as show:
            self.assertEqual(0, ipc_plugin.main())
        modules["coilforge.ipc_ui"].SpiralIpcWindow.return_value.run.assert_called_once_with()
        show.assert_not_called()


if __name__ == "__main__":
    unittest.main()
