# Architecture and workflow

Both UI implementations share the same pure-Python geometry, electrical, preset, settings, workflow and preview modules. The wxPython runtime is implemented in `legacy_plugin.py`; the IPC runtime uses `ipc_ui.py` and `ipc_backend.py`.

`parameter_visibility()` is the single source of truth for scenario-specific controls. `WorkflowLocks` records only visible completed-step values, so hidden manual turns or widths cannot accidentally disable an electrical solver.

Motor arrangement uses a support-envelope separation test. For radial arrays the support direction includes the angular difference between adjacent rotated coils. Connector/via/terminal extension is added to the copper envelope before the minimum array radius is accepted.

## Installation and runtime boundary

The default release is a PCM IPC ZIP. Root `metadata.json` describes installation and versioning;
`plugins/plugin.json` describes IPC execution. PCM inserts the package-id directory itself.
Relative imports and icon paths remain relative to the installed IPC plugin root.

`coilforge/metadata.py` owns the version, unified PCM/IPC identity and legacy settings identity. `package_plugin.py`
generates PCM metadata from `pcm/metadata.template.json` and validates both manifests against
`pcm/schemas/`. Build tools and schemas are not shipped in the default runtime archive.

The source-root legacy registration files are excluded from the IPC ZIP. Passive legacy modules
inside `coilforge/` do not register themselves. IPC settings continue to use
`get_plugin_settings_path()` with a narrowly scoped KiCad 10.0 workaround and in-place access to
legacy settings, outside the PCM installation tree. See the [packaging guide](packaging.en.md).
