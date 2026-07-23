# Configuration and user profiles

CoilForge stores version-scoped settings in `CoilForge/coilforge-settings.json` and shared named profiles in `CoilForge/coilforge-profiles.json`. Invalid or corrupt values fall back to built-in defaults. Writes use a temporary file followed by atomic replacement.

The workflow is scenario-driven. Loading a profile clears previous step locks and rebuilds only the pages needed by the selected application. Hidden fields never become solver constraints.

Linear motor profiles include `motor_target_force_n` and `motor_target_linear_speed_mps`. Rotary profiles use `target_torque_nm` and `motor_target_speed_rpm`.
