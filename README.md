# CoilForge v0.2.6

[简体中文](README.zh-CN.md) | [Documentation index](docs/README.md)

CoilForge is an open-source KiCad PCB coil and planar-motor winding generator by **askstar / 问星**. It supports the legacy `pcbnew` ActionPlugin API and the KiCad IPC plugin entry point.

## Highlights

- Circular single- and multilayer planar spirals.
- Elliptical, racetrack, tapered-trapezoid, annular-sector, radial and linear motor arrays.
- Scenario-driven workflow: irrelevant pages and parameters are hidden instead of forcing a fixed seven-step wizard.
- Electrical target modes for resistance, inductance and current capacity.
- Rotary motor sizing from DC bus voltage, RPM, torque, phase-current limit, copper temperature rise, magnetic loading and PCB rules.
- Linear motor sizing from DC bus voltage, thrust, translator speed, pole pitch and phase-current limit.
- Collision-safe motor placement. Radial spacing accounts for each rotated coil support envelope plus track width, clearance, vias and terminal fan-out.
- Live preview built from the same resolved geometry used for KiCad output.
- Through-hole vias only; no blind-via process is required.
- English and Simplified Chinese UI, validation messages and documentation.

> Electrical, magnetic and thermal results are preliminary engineering estimates. Validate production designs with KiCad DRC, manufacturer DFM, field/thermal simulation and hardware testing.

## Quick start

1. Choose an application preset and manufacturing capability.
2. Select a design basis. Use voltage/RPM/torque for rotary motors, or thrust/linear speed for linear motors.
3. Enter the usable PCB envelope and winding/array constraints.
4. Review the resolved turns, width, clearance, voltage, current and loss summary.
5. Select copper layers and a net, create the winding, then run KiCad DRC.

## Installation

The **v0.2.7+ release ZIP is a PCM IPC installation package**, not a source-code ZIP.
Target: **KiCad 10.0+**, with the IPC API enabled and **Python 3.10+ with tkinter**.
The release is marked `testing`; see the [installation and compatibility guide](docs/installation.en.md)
for the verification boundary and troubleshooting.

1. Download the versioned `kicad_CoilForge_plugin-v<version>.zip` release asset; do not use GitHub's **Source code (zip)**.
2. Open KiCad's project manager → **Plugin and Content Manager** → **Install from File…**, and select the ZIP without extracting it.
3. Enable the API server and select a working Python interpreter in **Preferences → Plugins**.
4. Restart the PCB editor, open a board, and launch **CoilForge** from the IPC plugin controls/toolbar.

KiCad manages the plugin's Python environment and installs `requirements.txt`. First-time dependency
setup needs network access (or a configured package mirror); offline ZIP installation does **not**
bundle Python dependencies. `tkinter` must be supplied by the selected Python installation.

Legacy ActionPlugin users must install the **source directory** into their KiCad Python scripting
plugin directory instead. Do not install the IPC release ZIP that way or keep two active copies.

## Development and packaging

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python package_plugin.py
```

The current output is `dist/kicad_CoilForge_plugin-v0.2.7.zip`. Every build validates both manifests
against vendored official KiCad schemas before atomically replacing the release file. Runtime
requirements remain separate from the build/test-only `jsonschema` dependency.

See the [packaging contract and release checklist](docs/packaging.en.md). Geometry, electrical
calculations, and the UI are not changed by the PCM packaging migration.

## Repository layout

- `coilforge/geometry.py` — spiral, shaped-coil, array, via and clearance geometry.
- `coilforge/electrical.py` — resistance, inductance, back-EMF and motor target solvers.
- `coilforge/workflow.py` — shared scenario visibility and step locking.
- `coilforge/interface.py` — wxPython UI.
- `coilforge/ipc_ui.py` / `ipc_backend.py` — IPC UI and KiCad backend.
- `coilforge/preview.py` — output-equivalent preview scene.
- `tests/` — geometry, electrical, UI, preset, i18n and packaging regression tests.
- `pcm/` — PCM metadata template and pinned official PCM/IPC schemas.
- `package_plugin.py` — deterministic, schema-validated PCM IPC ZIP builder.

## Documentation

See the [bilingual documentation index](docs/README.md), including configuration, architecture, rotary/sector motor sizing and linear motor sizing.

## License and contributions

See [LICENSE](LICENSE). Issues and pull requests are welcome. Please include reproducible parameters, KiCad version, expected geometry and a DRC screenshot for geometry defects.
