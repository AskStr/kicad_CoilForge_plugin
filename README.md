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

Build a deterministic release archive:

```bash
python package_plugin.py
```

Install the generated ZIP through the supported KiCad plugin mechanism, or copy the complete directory to the KiCad Python scripting plugin directory for the legacy ActionPlugin. Restart KiCad after replacing plugin files.

## Repository layout

- `coilforge/geometry.py` — spiral, shaped-coil, array, via and clearance geometry.
- `coilforge/electrical.py` — resistance, inductance, back-EMF and motor target solvers.
- `coilforge/workflow.py` — shared scenario visibility and step locking.
- `coilforge/interface.py` — wxPython UI.
- `coilforge/ipc_ui.py` / `ipc_backend.py` — IPC UI and KiCad backend.
- `coilforge/preview.py` — output-equivalent preview scene.
- `tests/` — geometry, electrical, UI, preset, i18n and packaging regression tests.

## Documentation

See the [bilingual documentation index](docs/README.md), including configuration, architecture, rotary/sector motor sizing and linear motor sizing.

## License and contributions

See [LICENSE](LICENSE). Issues and pull requests are welcome. Please include reproducible parameters, KiCad version, expected geometry and a DRC screenshot for geometry defects.
