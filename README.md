# CoilForge v0.2.8

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

Use **`kicad_CoilForge_plugin-v0.2.8-PCM.zip`** for **KiCad 6–10.99**.
This unified package preserves the two working v0.2.6 interfaces and the coil algorithms.

| KiCad / setting | Automatically selected runtime |
|---|---|
| 6–8; 9/10.0 with API disabled | Existing pcbnew / wxPython ActionPlugin |
| 9/10.0 with API enabled; 10.99 | Existing IPC / Tk interface |

1. Download the release asset, not GitHub's **Source code (zip)**.
2. Open KiCad's project manager → **Plugin and Content Manager** → **Install from File…** and select
   the ZIP directly, without extracting it.
3. Restart the PCB editor, open a board and click CoilForge's plugin toolbar icon.

**KiCad 10.99 requires an enabled API and Python 3.10+ with `tkinter`, `_tkinter`, Tcl/Tk, venv and pip.**
These prerequisites also apply when enabling IPC on 9/10.0. Keep a previously working interpreter;
PCM packaging does not replace the Tk UI or remove its dependencies. Restart after changing API
settings. Remove old loadable manual/split-package duplicates without deleting user settings.

### Online updates

Standard PCM indexes are generated under `pcm/repository/`. After the indexes and release ZIP are
published, add the repository in PCM and install from it to enable repository tracking. KiCad 7–10.99
can offer native updates; 6.0.11 refreshes the version index but requires manual uninstall/reinstall
for upgrades. A local-file installation does not automatically subscribe to a repository.

**The files are prepared locally, not uploaded by the build scripts.** See the
[installation guide, repository setup and tested version matrix](docs/installation.en.md).

## Development and packaging

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python package_plugin.py
```

The output is `dist/kicad_CoilForge_plugin-v0.2.8-PCM.zip`. Builds validate the unified metadata
against both vendored official PCM schemas and validate the IPC manifest before atomically replacing
the release file. `package_repository.py` generates version history, download hashes and update
indexes from the completed ZIP. `jsonschema` remains a build/test dependency only.

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
- `pcm/` — PCM registration shim, metadata template, online indexes and pinned official schemas.
- `package_plugin.py` — deterministic, schema-validated unified PCM ZIP builder.
- `package_repository.py` — standard PCM online repository index generator.

## Documentation

See the [bilingual documentation index](docs/README.md), including configuration, architecture, rotary/sector motor sizing and linear motor sizing.

## License and contributions

See [LICENSE](LICENSE). Issues and pull requests are welcome. Please include reproducible parameters, KiCad version, expected geometry and a DRC screenshot for geometry defects.
