# Installation, compatibility and troubleshooting

[简体中文](installation.md) · [Documentation index](README.md) · [Packaging and online releases](packaging.en.md)

## One package for KiCad 6–10.99

Use **`kicad_CoilForge_plugin-v0.2.8-PCM.zip`** on every supported version.
The existing v0.2.6 ActionPlugin/wxPython and IPC/Tk interfaces, coil algorithms and manual-install
entrypoint are preserved. This change adapts PCM layout, metadata and startup selection rather than
requiring separate runtime downloads.

| KiCad | Launch path | Requirements |
|---|---|---|
| 6, 7, 8 | Existing ActionPlugin / wxPython | Bundled pcbnew and wxPython; no IPC or Tk |
| 9, 10.0, API disabled | Existing ActionPlugin / wxPython | Same as above |
| 9, 10.0, API enabled | Existing IPC / Tk | Working API and the Python prerequisites below |
| 10.99 | Existing IPC / Tk | API enabled and Python with `_tkinter` |

A PCM-only registration shim selects the runtime using the host version and API setting, avoiding
duplicate entrypoints. **Restart the PCB editor after changing the API setting.** If the API is enabled
but Python is incomplete, repair that environment rather than expecting a silent switch to another UI.
KiCad 4/5 and future KiCad 11 are outside the declared range.

## Install from file

1. Close PCB editors. Uninstall an earlier split-runtime or v0.2.7 package through PCM first when
   replacing it. Move loadable manual duplicates aside without deleting user settings.
2. Open KiCad's project manager → **Plugin and Content Manager** → **Install from File…**.
3. Select `kicad_CoilForge_plugin-v0.2.8-PCM.zip` directly. Do not extract, recompress or add a wrapper directory.
4. Reopen the PCB editor and a board, then click CoilForge's toolbar icon. The ActionPlugin path also
   provides a **Tools → External Plugins** action; labels differ by version/language.
5. If an older version hides the toolbar icon, enable/refresh it in Action Plugin management.

GitHub's **Source code (zip)** is not a PCM package. Do not copy files into KiCad's `site-packages`;
PCM owns installation, update and removal directories.

## Online repository and updates

Standard PCM indexes are provided in `pcm/repository/repository.json` and `packages.json`.
**Publish these files and the ZIP to their matching URLs before using the online service. This change
only generates local files; it does not upload them.** Once published, the repository URL is:

```text
https://raw.githubusercontent.com/AskStr/kicad_CoilForge_plugin/main/pcm/repository/repository.json
```

1. Add that URL in PCM's **Manage repositories / Manage**, then refresh.
2. Install CoilForge from that repository so its installation record is associated with the repository.
3. Enable PCM update checking where the host provides it, or open PCM and click **Refresh** manually.
4. **KiCad 7–10.99:** PCM offers an update when a higher compatible version with an acceptable stability
   level becomes available.
5. **KiCad 6.0.11:** repository refresh retrieves newer version metadata, but this native PCM does not
   provide the newer update state/one-click update action. Close editors, back up settings, uninstall
   the old package through PCM and install the newer version from the same repository.

**Install from File** creates a local installation record; do not assume it automatically follows an
online repository. To enable repository tracking, close editors, uninstall the local package in PCM
and reinstall from that repository. Replacing bytes under the same `0.2.8` version does not create a
version update: releases must increment the version and regenerate the indexes. See [release commands](packaging.en.md).

## IPC Python, including `_tkinter` on KiCad 10.99

Keep a previously working interpreter. Where available, enable the API and choose Python in
**Preferences → Plugins**. Python 3.10+ must include `tkinter`, `_tkinter`, Tcl/Tk, venv and pip.
KiCad also prepares `kicad-python>=0.7.1,<0.9` in its managed environment; initial setup needs a
working package index, mirror or cache. `_tkinter` is a native Python extension, not a package fixed
by `pip install tkinter`. Never mix DLLs from different Python versions.

Test complete initialization using KiCad's selected interpreter, not just an import:

```text
python -c "import tkinter as tk, _tkinter, venv, pip; r=tk.Tk(); r.withdraw(); print('Tk OK', r.tk.call('info', 'patchlevel')); r.destroy()"
```

For a `pythonw.exe` setting, use the adjacent `python.exe` for this check. After changing interpreters,
restart the editor and confirm KiCad prepares the plugin environment with the new interpreter.

The checked KiCad 10.0.4 bundled Python lacked `_tkinter`. Previously both the IPC UI and its error
dialog required Tk; pythonw also had no visible console, making a click appear to do nothing. The
original Tk UI remains, with localized startup diagnostics and a native Windows error fallback that
does not require Tk and identifies the actual interpreter. A narrowly matched settings-path API error
on KiCad 9.0.7/10.0.4 is handled without hiding other failures.

## Verification boundary (September 6, 2026)

Actual Windows applications under `D:\KiCad` were tested using temporary boards and separate settings;
production boards were not modified. Online checks used a local HTTP repository, **not a published
GitHub service**.

| Actual version | Native PCM online installation of the same ZIP | PCB toolbar launch | New online version check |
|---|---|---|---|
| 6.0.11 | Passed | ActionPlugin passed | New index retrieved; no native one-click update |
| 7.0.11 | Passed | ActionPlugin passed | Native Update action passed |
| 8.0.9 | Passed | ActionPlugin passed | Native Update action passed |
| 9.0.7 | Passed | API off: ActionPlugin; API on: IPC, both passed | Native Update action passed |
| 10.0.4 | Passed | API off: ActionPlugin; API on: IPC, both passed | Native Update action passed |
| 10.99.0-2335-g1899bad41c | Passed | IPC/Tk passed | Native Update action passed |

- 6.0.11 and 10.99 additionally passed native **Install from File**, persisted installation records
  after normal manager exit, and subsequent toolbar launch.
- Installed runtime files were compared byte-for-byte with the ZIP; online records retained repository IDs.
- Update discovery used a temporary `0.2.9` fixture only. That fixture was not installed, uploaded or released.
- IPC used Python 3.13.2, `_tkinter` and Tk 8.6.15. No legacy duplicate was registered with the API enabled.
- Bundled Python/pcbnew/wxPython on 6–10.0 also passed registration-request, UI initialization and
  repeated-click reuse checks. Standalone Python intercepts registration; the native editor tests above
  cover real C++ registration and toolbar invocation.
- Unit tests cover both schemas, layout, startup selection, diagnostics, settings compatibility and
  repository history/hashes/timestamps.
- `legacy_plugin.py`, `interface.py`, `ipc_ui.py`, `geometry.py` and `electrical.py` remain unchanged from v0.2.6.

These are representative Windows builds, not every patch release or macOS/Linux verification.
Applying real upgrades, post-uninstall data retention and exhaustive generation/undo/redo checks on all
platforms remain release acceptance work. Metadata stays `testing`; passing installation tests does
not imply every operation is verified.

## Troubleshooting

- ZIP rejected: select `-PCM.zip`; `metadata.json` and `plugins/` must be at its root.
- Missing/duplicate icon: restart, check manual duplicates, API settings and plugin enablement.
- IPC action not ready: wait for environment preparation; check Python, pip access and API status.
- Tk startup failure: run the full check above and inspect the interpreter path in the error message.
- Repository failure: confirm publication, accessible URLs and matching index/ZIP hashes.
- No update: check repository association, higher version number, compatibility and stability;
  use the manual upgrade workflow on KiCad 6.

Include the full KiCad version, OS, installation method, API setting, interpreter path and error text
when reporting a startup issue.
