# -*- coding: utf-8 -*-
"""Persistent plug-in settings with conservative schema validation."""

import json
from math import isfinite
import os
import sys
import tempfile

try:
    from .kicad_paths import (
        platform_kicad_config_root, preferred_settings_directory,
    )
    from .metadata import (
        CONFIG_DIRECTORY_NAME, PROFILES_FILENAME, SETTINGS_FILENAME,
    )
except ImportError:
    from kicad_paths import (
        platform_kicad_config_root, preferred_settings_directory,
    )
    from metadata import (
        CONFIG_DIRECTORY_NAME, PROFILES_FILENAME, SETTINGS_FILENAME,
    )


DEFAULTS = {
    "schema_version": 11,
    "group_name": "spiral",
    "application_preset": "custom",
    "manufacturing_preset": "custom",
    "net_name": "",
    "layer_name": "F.Cu",
    "layer_count": 1,
    "center_x_mm": 0.0,
    "center_y_mm": 0.0,
    "start_radius_mm": 0.0,
    "turns": 10.0,
    "segments_per_turn": 64,
    "additional_segments": 0,
    "arcs_per_turn": 16,
    "primitive_mode": "auto",
    "coil_shape": "circular",
    "shape_aspect_ratio": 1.6,
    "shape_taper_ratio": 0.45,
    "motor_layout": "single",
    "motor_pole_pairs": 3,
    "motor_slot_count": 0,
    "motor_phase_count": 3,
    "motor_array_radius_mm": 0.0,
    "motor_linear_pitch_mm": 0.0,
    "motor_array_angle_degrees": 0.0,
    "motor_orientation": "radial",
    "motor_alternate_winding": True,
    "motor_parameters_auto": True,
    "quality_preset": "balanced",
    "sizing_mode": "manual",
    "available_diameter_mm": 50.0,
    "target_length_mm": 1000.0,
    "fill_ratio": 0.5,
    "minimum_track_width_mm": 0.1,
    "minimum_clearance_mm": 0.1,
    "copper_thickness_um": 35.0,
    "target_current_a": 1.0,
    "target_torque_nm": 0.0,
    "motor_target_force_n": 5.0,
    "motor_target_linear_speed_mps": 1.0,
    "air_gap_flux_density_t": 0.45,
    "electrical_loading_a_per_m": 12000.0,
    "winding_factor": 0.90,
    "motor_inner_ratio": 0.58,
    "motor_board_outer_diameter_mm": 100.0,
    "motor_board_inner_diameter_mm": 40.0,
    "motor_edge_clearance_mm": 1.0,
    "motor_slot_gap_mm": 1.0,
    "motor_supply_voltage_v": 24.0,
    "motor_target_speed_rpm": 1000.0,
    "motor_max_phase_current_a": 5.0,
    "allowed_temperature_rise_c": 30.0,
    "target_resistance_ohm": 0.0,
    "target_inductance_uh": 0.0,
    "motor_connection": "star",
    "design_mode": "manual",
    "show_advanced_parameters": False,
    "track_width_mm": 0.25,
    "spacing_mm": 0.5,
    "via_diameter_mm": 0.6,
    "via_drill_mm": 0.4,
    "via_clearance_mm": 0.25,
    "spacing_mode": "pitch",
    "angle_degrees": 0.0,
    "angle_unit": "degrees",
    "direction": "clockwise",
    "create_group": True,
    "close_after_create": False,
    "max_segments": 200000,
}

_FLOAT_KEYS = {
    "center_x_mm", "center_y_mm", "start_radius_mm", "turns",
    "track_width_mm", "spacing_mm", "via_diameter_mm", "via_drill_mm",
    "via_clearance_mm", "angle_degrees", "available_diameter_mm",
    "target_length_mm", "fill_ratio", "minimum_track_width_mm",
    "minimum_clearance_mm", "copper_thickness_um", "target_current_a",
    "target_torque_nm", "motor_target_force_n",
    "motor_target_linear_speed_mps", "air_gap_flux_density_t",
    "electrical_loading_a_per_m", "winding_factor", "motor_inner_ratio",
    "shape_aspect_ratio", "shape_taper_ratio", "motor_array_radius_mm",
    "motor_linear_pitch_mm", "motor_array_angle_degrees",
    "motor_board_outer_diameter_mm", "motor_board_inner_diameter_mm",
    "motor_edge_clearance_mm", "motor_slot_gap_mm",
    "motor_supply_voltage_v", "motor_target_speed_rpm",
    "motor_max_phase_current_a", "allowed_temperature_rise_c",
    "target_resistance_ohm", "target_inductance_uh",
}
_INT_KEYS = {
    "schema_version", "layer_count", "segments_per_turn",
    "arcs_per_turn", "additional_segments", "max_segments",
    "motor_pole_pairs", "motor_slot_count", "motor_phase_count",
}
_BOOL_KEYS = {
    "create_group", "close_after_create", "motor_alternate_winding",
    "motor_parameters_auto", "show_advanced_parameters",
}
_STRING_KEYS = {"group_name", "net_name", "layer_name"}
_ENUMS = {
    "application_preset": (
        "custom", "general", "compact_sensor", "nfc_rfid",
        "wireless_power", "heating", "long_trace",
        "motor_axial_ellipse", "motor_racetrack", "motor_trapezoid",
        "motor_linear", "motor_sector",
    ),
    "manufacturing_preset": (
        "custom", "standard", "conservative", "fine", "heavy_copper",
    ),
    "primitive_mode": ("auto", "arc", "segment"),
    "coil_shape": (
        "circular", "motor_ellipse", "motor_racetrack", "motor_trapezoid",
        "motor_sector",
    ),
    "quality_preset": ("fast", "balanced", "smooth", "custom"),
    "sizing_mode": ("manual", "fit_turns", "fit_length"),
    "spacing_mode": ("pitch", "clearance"),
    "angle_unit": ("degrees", "radians"),
    "direction": ("clockwise", "counterclockwise"),
    "motor_layout": ("single", "radial", "linear"),
    "motor_orientation": ("radial", "tangential"),
    "motor_connection": ("star", "delta"),
    "design_mode": (
        "manual", "fit_turns", "fit_length", "target_resistance",
        "target_inductance", "target_current", "motor_target",
    ),
}


def sanitize_settings(values):
    clean = dict(DEFAULTS)
    if not isinstance(values, dict):
        return clean
    try:
        source_schema = int(values.get("schema_version", 0))
    except (TypeError, ValueError):
        source_schema = 0

    for key in _FLOAT_KEYS:
        try:
            value = float(values.get(key, clean[key]))
            if isfinite(value):
                clean[key] = value
        except (TypeError, ValueError):
            pass
    for key in _INT_KEYS:
        try:
            clean[key] = int(values.get(key, clean[key]))
        except (TypeError, ValueError):
            pass
    for key in _BOOL_KEYS:
        value = values.get(key, clean[key])
        clean[key] = value if isinstance(value, bool) else clean[key]
    for key in _STRING_KEYS:
        value = values.get(key, clean[key])
        if isinstance(value, str):
            clean[key] = value
    for key, allowed in _ENUMS.items():
        value = values.get(key, clean[key])
        if value in allowed:
            clean[key] = value

    if (
            source_schema < 6
            and clean["manufacturing_preset"] == "custom"
            and abs(clean["via_diameter_mm"] - 0.8) < 1e-12
            and abs(clean["via_drill_mm"] - 0.4) < 1e-12):
        clean["via_diameter_mm"] = DEFAULTS["via_diameter_mm"]
    clean["schema_version"] = DEFAULTS["schema_version"]
    clean["layer_count"] = min(12, max(1, clean["layer_count"]))
    clean["segments_per_turn"] = min(4096, max(4, clean["segments_per_turn"]))
    clean["arcs_per_turn"] = min(360, max(4, clean["arcs_per_turn"]))
    clean["additional_segments"] = max(0, clean["additional_segments"])
    clean["motor_pole_pairs"] = min(64, max(1, clean["motor_pole_pairs"]))
    clean["motor_slot_count"] = min(128, max(0, clean["motor_slot_count"]))
    if clean["motor_phase_count"] not in (1, 3):
        clean["motor_phase_count"] = DEFAULTS["motor_phase_count"]
    clean["motor_array_radius_mm"] = max(0.0, clean["motor_array_radius_mm"])
    clean["motor_linear_pitch_mm"] = max(0.0, clean["motor_linear_pitch_mm"])
    clean["fill_ratio"] = min(0.99, max(0.01, clean["fill_ratio"]))
    clean["minimum_track_width_mm"] = max(0.0, clean["minimum_track_width_mm"])
    clean["minimum_clearance_mm"] = max(0.0, clean["minimum_clearance_mm"])
    clean["copper_thickness_um"] = max(1.0, clean["copper_thickness_um"])
    clean["target_current_a"] = max(0.0, clean["target_current_a"])
    clean["target_torque_nm"] = max(0.0, clean["target_torque_nm"])
    clean["motor_target_force_n"] = max(0.0, clean["motor_target_force_n"])
    clean["motor_target_linear_speed_mps"] = max(
        0.0, clean["motor_target_linear_speed_mps"]
    )
    clean["motor_board_outer_diameter_mm"] = max(1.0,
        clean["motor_board_outer_diameter_mm"]
    )
    clean["motor_board_inner_diameter_mm"] = min(
        clean["motor_board_outer_diameter_mm"] * 0.95,
        max(0.0, clean["motor_board_inner_diameter_mm"]),
    )
    clean["motor_edge_clearance_mm"] = max(0.0,
        clean["motor_edge_clearance_mm"]
    )
    clean["motor_slot_gap_mm"] = max(0.0, clean["motor_slot_gap_mm"])
    clean["motor_supply_voltage_v"] = max(0.1,
        clean["motor_supply_voltage_v"]
    )
    clean["motor_target_speed_rpm"] = max(0.0,
        clean["motor_target_speed_rpm"]
    )
    clean["motor_max_phase_current_a"] = max(0.0,
        clean["motor_max_phase_current_a"]
    )
    clean["allowed_temperature_rise_c"] = min(200.0, max(1.0,
        clean["allowed_temperature_rise_c"]
    ))
    clean["target_resistance_ohm"] = max(0.0,
        clean["target_resistance_ohm"]
    )
    clean["target_inductance_uh"] = max(0.0,
        clean["target_inductance_uh"]
    )
    clean["air_gap_flux_density_t"] = min(2.0, max(0.01,
        clean["air_gap_flux_density_t"]
    ))
    clean["electrical_loading_a_per_m"] = min(100000.0, max(100.0,
        clean["electrical_loading_a_per_m"]
    ))
    clean["winding_factor"] = min(1.0, max(0.01, clean["winding_factor"]))
    clean["motor_inner_ratio"] = min(0.90, max(0.10,
        clean["motor_inner_ratio"]
    ))
    clean["shape_aspect_ratio"] = min(
        4.0, max(1.0, clean["shape_aspect_ratio"])
    )
    clean["shape_taper_ratio"] = min(
        0.75, max(-0.75, clean["shape_taper_ratio"])
    )
    clean["max_segments"] = max(1000, clean["max_segments"])
    return clean


def _plugin_config_path(base_path, filename):
    return os.path.abspath(os.path.join(
        base_path, "plugins", CONFIG_DIRECTORY_NAME, filename
    ))


def default_settings_path(pcbnew_module=None, kicad_version=None,
                          environ=None, platform_name=None, home=None):
    base_path = preferred_settings_directory(
        pcbnew_module=pcbnew_module,
        kicad_version=kicad_version,
        environ=environ,
        platform_name=platform_name,
        home=home,
    )
    return _plugin_config_path(base_path, SETTINGS_FILENAME)



def shared_profiles_path(environ=None, platform_name=None, home=None):
    """Return the cross-KiCad-version user profile store path."""
    env = os.environ if environ is None else environ
    base_path = env.get("KICAD_CONFIG_HOME")
    if not base_path:
        base_path = platform_kicad_config_root(
            environ=env, platform_name=platform_name, home=home
        )
    return _plugin_config_path(base_path, PROFILES_FILENAME)


def _atomic_write_json(path, data, prefix):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    descriptor, temp_path = tempfile.mkstemp(
        prefix=prefix, suffix=".json", dir=directory or None
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output_file:
            json.dump(
                data, output_file, ensure_ascii=False, indent=2, sort_keys=True
            )
            output_file.write("\n")
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


class SettingsStore(object):
    def __init__(self, path):
        self.path = path

    @property
    def exists(self):
        return os.path.isfile(self.path)

    @staticmethod
    def _load_path(path):
        with open(path, "r", encoding="utf-8") as settings_file:
            return sanitize_settings(json.load(settings_file))

    def load(self):
        try:
            return self._load_path(self.path)
        except (IOError, OSError, ValueError, TypeError):
            return dict(DEFAULTS)

    def save(self, values):
        _atomic_write_json(
            self.path, sanitize_settings(values), "coilforge-settings-"
        )


class UserProfileStore(object):
    """Cross-version named parameter combinations with safe JSON handling."""

    SCHEMA_VERSION = 1

    def __init__(self, path):
        self.path = path

    @staticmethod
    def _clean_name(name):
        clean = str(name).strip()
        if not clean or len(clean) > 80 or any(
                ord(character) < 32 for character in clean):
            raise ValueError("invalid_profile_name")
        return clean

    def _load_records(self):
        try:
            with open(self.path, "r", encoding="utf-8") as profile_file:
                raw = json.load(profile_file)
        except (IOError, OSError, ValueError, TypeError):
            return []
        records = raw.get("profiles", []) if isinstance(raw, dict) else []
        clean = []
        seen = set()
        for record in records if isinstance(records, list) else []:
            if not isinstance(record, dict):
                continue
            try:
                name = self._clean_name(record.get("name", ""))
            except ValueError:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            clean.append({
                "name": name,
                "values": sanitize_settings(record.get("values", {})),
            })
        return clean

    def _save_records(self, records):
        _atomic_write_json(self.path, {
            "schema_version": self.SCHEMA_VERSION,
            "profiles": records,
        }, "coilforge-profiles-")

    def names(self):
        return tuple(record["name"] for record in self._load_records())

    def load(self, name):
        key = self._clean_name(name).casefold()
        for record in self._load_records():
            if record["name"].casefold() == key:
                return dict(record["values"])
        return None

    def save(self, name, values, overwrite=False):
        clean_name = self._clean_name(name)
        key = clean_name.casefold()
        records = self._load_records()
        for record in records:
            if record["name"].casefold() != key:
                continue
            if not overwrite:
                raise ValueError("profile_exists")
            record["name"] = clean_name
            record["values"] = sanitize_settings(values)
            self._save_records(records)
            return clean_name
        records.append({
            "name": clean_name, "values": sanitize_settings(values)
        })
        records.sort(key=lambda record: record["name"].casefold())
        self._save_records(records)
        return clean_name

    def delete(self, name):
        key = self._clean_name(name).casefold()
        records = self._load_records()
        kept = [
            record for record in records
            if record["name"].casefold() != key
        ]
        if len(kept) == len(records):
            return False
        self._save_records(kept)
        return True

    def rename(self, old_name, new_name):
        values = self.load(old_name)
        if values is None:
            raise ValueError("profile_not_found")
        new_clean = self._clean_name(new_name)
        if (str(old_name).casefold() != new_clean.casefold()
                and self.load(new_clean) is not None):
            raise ValueError("profile_exists")
        self.delete(old_name)
        self.save(new_clean, values)
        return new_clean

    def export_file(self, destination):
        _atomic_write_json(destination, {
            "schema_version": self.SCHEMA_VERSION,
            "profiles": self._load_records(),
        }, "coilforge-export-")

    def import_file(self, source, overwrite=False):
        imported_store = UserProfileStore(source)
        imported = []
        for record in imported_store._load_records():
            try:
                self.save(
                    record["name"], record["values"], overwrite=overwrite
                )
            except ValueError as error:
                if str(error) == "profile_exists":
                    continue
                raise
            imported.append(record["name"])
        return tuple(imported)
