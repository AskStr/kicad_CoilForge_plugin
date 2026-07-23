# Architecture and workflow

Both UI implementations share the same pure-Python geometry, electrical, preset, settings, workflow and preview modules. The wxPython runtime is implemented in `legacy_plugin.py`; the IPC runtime uses `ipc_ui.py` and `ipc_backend.py`.

`parameter_visibility()` is the single source of truth for scenario-specific controls. `WorkflowLocks` records only visible completed-step values, so hidden manual turns or widths cannot accidentally disable an electrical solver.

Motor arrangement uses a support-envelope separation test. For radial arrays the support direction includes the angular difference between adjacent rotated coils. Connector/via/terminal extension is added to the copper envelope before the minimum array radius is accepted.
