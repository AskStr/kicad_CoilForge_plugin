# Installation, compatibility and troubleshooting

[简体中文](installation.md) · [Documentation index](README.md) · [Packaging](packaging.en.md)

## Choose the right download

- **v0.2.7+ release asset** `kicad_CoilForge_plugin-v<version>.zip`: a PCM IPC installation package.
- **Old v0.2.6 ZIP**: a manually extracted directory archive, without PCM metadata.
- **GitHub Source code (zip)**: a source archive, not a PCM installation package. Extract and build it first.
- **Legacy ActionPlugin**: install the complete source directory, not the new IPC installation ZIP.

## Prerequisites

| Component | Requirement |
|---|---|
| KiCad | Target 10.0+; package status is currently `testing` |
| API | Enable the IPC API server in the Plugins preferences page |
| Python | 3.10+, with working tkinter, venv and pip |
| Python dependencies | `kicad-python>=0.7.1,<0.9`, managed by KiCad's plugin environment |
| Editor | Open a PCB before launching; the action scope is `pcb` |
| Initial dependency setup | Access to a Python package index, or a suitable mirror/cache |

The official IPC schema notes that Python `min_version` is not yet enforced by KiCad.
The manifest therefore does not replace checking the selected interpreter.

### Verification boundary (September 6, 2026)

- Windows: manifests were validated against the PCM v2 / IPC v1 schemas shipped with
  **KiCad 10.0.4** and **10.99.0-2335-g1899bad41c**. The vendored snapshots match them byte-for-byte.
- **KiCad 10.0.4**: native PCM **Install from File** installed the new ZIP in an isolated configuration.
  All 21 installed runtime files were compared byte-for-byte with the archive. After a normal manager
  exit, `installed_packages.json` correctly persisted version `0.2.7`, `runtime: ipc`, and local-file origin.
- Both versions passed live IPC backend checks using code extracted from the release ZIP: connection,
  settings path, nets, copper layers, selection, 8 arcs plus a group, 8 bounding boxes, and 69 two-layer
  objects including tracks and vias.
- The complete toolbar-to-UI workflow, complete upgrade/uninstall lifecycle, and macOS/Linux machines
  have not all been verified. These checks are not a claim that every OS or KiCad version has passed.
- KiCad 8/9 are outside this IPC package's compatibility declaration. Legacy ActionPlugin compatibility
  is a separate concern.

## Install through PCM

1. Download the versioned release asset, or follow the [build instructions](packaging.en.md).
2. Open KiCad's **project manager**, then **Plugin and Content Manager (PCM)**.
3. Choose **Install from File…** and select the ZIP directly. Do not extract or re-compress it.
4. In **Preferences → Plugins**, enable the API server and select a working Python interpreter.
5. Restart the PCB editor, open a test board, and allow plugin environment setup to finish.
6. Launch **CoilForge** through the IPC plugin controls/toolbar. Labels may vary by locale/version.

PCM manages its own installation directory. Do not add another package-name directory or install the
package into KiCad's bundled Python `site-packages`.

### Python environment

KiCad uses `plugins/requirements.txt` to prepare the IPC plugin environment. End users do not need
`requirements-dev.txt` or the build/test-only `jsonschema` dependency.

Check the same Python installation selected in KiCad:

```text
python --version
python -c "import tkinter, venv, pip; print('Python prerequisites OK')"
```

If Windows preferences point to `pythonw.exe`, use the adjacent `python.exe` for these console checks.
Some Linux Python distributions need a separate system Tk package. Do **not** run `pip install tkinter`.
For dependency failures, inspect plugin environment logs, the interpreter and package-index access
before reinstalling the ZIP.

## Upgrade and settings

### Upgrading a manually installed copy

1. Close the relevant PCB editors and back up settings/profiles.
2. Move the old manual plugin directory outside KiCad's plugin search paths to avoid duplicate copies.
3. Install the new ZIP through PCM. Do not extract it over the old plugin directory.

### Identity and existing settings

The new PCM and IPC identity is:

```text
com.github.askstr.kicad-coilforge-plugin
```

The old IPC identity, `org.coilforge.kicad_spiral_plugin`, contains underscores. Although accepted by
older schemas, it does not satisfy the stricter identifier check in updated KiCad runtime source.
It is no longer used by the new manifest.

Settings behavior:

- Normally use the new identity's settings directory returned by the API.
- If its `coilforge-settings.json` does not exist, but the sibling old identity has that file,
  continue reading and writing the old file **in place**. Nothing is copied, moved or deleted.
- If both files exist, prefer the new file and leave the old one untouched.
- Shared user profiles retain their existing storage logic.
- Settings are separate from PCM's installation directory; do not clear them to fix a packaging issue.

KiCad 10.0 has an inverted validity check in its plugin-settings-path handler, reproduced on 10.0.4.
Only when a **10.0-series server returns that specific error**, CoilForge resolves the settings path
using KiCad's directory convention, including `KICAD_CONFIG_HOME`. Other API and connection failures
are propagated rather than silently hidden.

### Uninstall

Use PCM to uninstall the new package and maintain its installation records. Remove old manual copies
separately. Settings and runtime files are separate; explicitly clearing personal data is a separate
user decision that should follow a backup and path verification.

## Troubleshooting

| Symptom | Check |
|---|---|
| No valid `metadata.json` | Use the new release asset, not v0.2.6 or a GitHub source ZIP |
| Installed but no action | API enabled, PCB open, editor restarted, plugin environment ready |
| Incompatible KiCad version | The package declares 10.0+; do not edit metadata to bypass the check |
| `No module named kipy` | Dependency setup failed in KiCad's managed environment; check interpreter/index/proxy |
| `No module named tkinter` | The selected Python lacks Tk; repair or replace that Python installation |
| Connection refused/timeout | Enable the API and launch through KiCad to receive its socket/token |
| Valid identifier rejected | Use v0.2.7+ compatibility handling; report the full KiCad version if it persists |
| Duplicate CoilForge actions | Look for older manually installed IPC or ActionPlugin copies |
| Local ZIP installs but dependencies fail | The ZIP does not bundle Python or third-party wheels |

When reporting issues, include OS, full KiCad version, archive filename, selected Python version,
error text, and the failing stage: PCM installation, discovery, dependency setup, or execution.
Do not publish tokens or other sensitive information.
