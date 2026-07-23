# -*- coding: utf-8 -*-
"""Python-standard-library (tkinter/ttk) UI for KiCad 10.99 IPC."""

from math import isfinite
import os
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from .electrical import (
        solve_motor_sector_design, solve_motor_spiral_design,
        solve_spiral_electrical_design,
    )
    from .geometry import (
        GeometryError,
        axial_flux_motor_dimensions, estimate_axial_flux_motor_torque,
        estimate_dc_metrics, motor_inner_trace_dfm,
        multilayer_track_count,
        required_inner_radius,
        resolve_motor_spiral_parameters,
        shape_endpoint_scale,
    )
    from .i18n import localize_error
    from .presets import (
        MANUFACTURING_PRESETS, QUALITY_PRESETS, build_preset_values,
        manufacturing_violation, recommend_copper_fill_ratio,
        recommend_motor_parameters,
    )
    from .preview import (
        build_preview_scene, build_safe_preview_scene,
        coerce_preview_values, fit_preview_scene,
    )
    from .settings import (
        DEFAULTS, UserProfileStore, shared_profiles_path,
    )
    from .workflow import (
        WorkflowLocks, parameter_visibility, workflow_page_keys,
        workflow_step_fields,
    )
    from .ui_layout import (
        WORKSPACE_MAIN_WEIGHT, WORKSPACE_SIDEBAR_WEIGHT,
        centered_geometry, fitted_window_size,
    )
except ImportError:
    from electrical import (
        solve_motor_sector_design, solve_motor_spiral_design,
        solve_spiral_electrical_design,
    )
    from geometry import (
        GeometryError,
        axial_flux_motor_dimensions, estimate_axial_flux_motor_torque,
        estimate_dc_metrics, motor_inner_trace_dfm,
        multilayer_track_count,
        required_inner_radius,
        resolve_motor_spiral_parameters,
        shape_endpoint_scale,
    )
    from i18n import localize_error
    from presets import (
        MANUFACTURING_PRESETS, QUALITY_PRESETS, build_preset_values,
        manufacturing_violation, recommend_copper_fill_ratio,
        recommend_motor_parameters,
    )
    from preview import (
        build_preview_scene, build_safe_preview_scene,
        coerce_preview_values, fit_preview_scene,
    )
    from settings import (
        DEFAULTS, UserProfileStore, shared_profiles_path,
    )
    from workflow import (
        WorkflowLocks, parameter_visibility, workflow_page_keys,
        workflow_step_fields,
    )
    from ui_layout import (
        WORKSPACE_MAIN_WEIGHT, WORKSPACE_SIDEBAR_WEIGHT,
        centered_geometry, fitted_window_size,
    )


class ValidationError(ValueError):
    pass


def _format_number(value):
    return ("{:.6f}".format(float(value))).rstrip("0").rstrip(".") or "0"


_NUMERIC_SETTING_KEYS = (
    "center_x_mm", "center_y_mm", "start_radius_mm", "turns",
    "arcs_per_turn", "segments_per_turn", "additional_segments",
    "track_width_mm", "spacing_mm", "available_diameter_mm",
    "target_length_mm", "minimum_track_width_mm",
    "minimum_clearance_mm", "via_diameter_mm", "via_drill_mm",
    "via_clearance_mm", "copper_thickness_um", "target_current_a",
    "target_torque_nm", "motor_target_force_n",
    "motor_target_linear_speed_mps", "air_gap_flux_density_t",
    "electrical_loading_a_per_m", "winding_factor", "motor_inner_ratio",
    "angle_degrees", "shape_aspect_ratio", "motor_pole_pairs",
    "motor_slot_count", "motor_phase_count",
    "motor_array_radius_mm", "motor_linear_pitch_mm",
    "motor_array_angle_degrees", "motor_board_outer_diameter_mm",
    "motor_board_inner_diameter_mm", "motor_edge_clearance_mm",
    "motor_slot_gap_mm", "motor_supply_voltage_v",
    "motor_target_speed_rpm", "motor_max_phase_current_a",
    "allowed_temperature_rise_c", "target_resistance_ohm",
    "target_inductance_uh",
)


def formatted_entry_settings(values):
    """Return text-entry values without coercing string settings to floats."""
    result = {
        key: _format_number(values[key]) for key in _NUMERIC_SETTING_KEYS
    }
    result["group_name"] = str(values.get("group_name") or "spiral")
    result["fill_ratio_percent"] = _format_number(
        float(values["fill_ratio"]) * 100.0
    )
    result["shape_taper_percent"] = _format_number(
        float(values.get("shape_taper_ratio", 0.0)) * 100.0
    )
    return result


class SpiralIpcWindow(object):
    def __init__(self, backend, store, translator, plugin_version,
                 profile_store=None):
        self.backend = backend
        self.store = store
        self.profile_store = profile_store or UserProfileStore(
            shared_profiles_path()
        )
        self.tr = translator
        self.settings = store.load()
        self._motor_parameters_auto = bool(
            self.settings.get("motor_parameters_auto", True)
        )
        self.net_items = backend.net_items()
        self.layers = backend.copper_layers()
        self._choice_maps = {}
        self._choice_reverse = {}
        self._controls = {}
        self._field_frames = {}
        self._wrapped_labels = []
        self._workflow = WorkflowLocks()
        self._last_page = 0
        self._updating = False
        self._preview_job = None
        self._preview_scene = None
        self._all_tabs = []
        self._active_page_keys = []
        self._changing_workflow = False

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(self.tr("window_title", version=plugin_version))
        try:
            icon_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "assets", "coilforge.png",
            )
            self._icon = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, self._icon)
        except Exception:
            self._icon = None

        self.vars = {}
        self.bool_vars = {
            "create_group": tk.BooleanVar(),
            "close_after_create": tk.BooleanVar(),
            "motor_alternate_winding": tk.BooleanVar(),
            "show_advanced_parameters": tk.BooleanVar(),
        }
        self.preset_summary = tk.StringVar()
        self.validation_summary = tk.StringVar()
        self.result_summary = tk.StringVar()
        self.electrical_summary = tk.StringVar()
        self.object_summary = tk.StringVar()
        self.guide_hint = tk.StringVar()
        self.preview_caption = tk.StringVar()
        self.motor_recommendation_summary = tk.StringVar()

        self._build_ui()
        self._apply_settings(self.settings)
        center = self.backend.selected_center_mm()
        if center is not None:
            self.vars["center_x_mm"].set(_format_number(center[0]))
            self.vars["center_y_mm"].set(_format_number(center[1]))
        self._bind_preview()
        self._update_preset_summary()
        self._update_preview()
        self._configure_window()
        self.root.deiconify()

    def _configure_window(self):
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width, height, min_width, min_height = fitted_window_size(
            screen_width, screen_height
        )
        self.root.minsize(min_width, min_height)
        self.root.geometry(centered_geometry(
            width, height, screen_width, screen_height
        ))
        self.root.update_idletasks()
        self._on_content_configure()

    def _new_var(self, key):
        variable = tk.StringVar()
        self.vars[key] = variable
        return variable

    def _add_entry(self, frame, row, column, label_key, key, unit=""):
        field = ttk.Frame(frame)
        field.grid(
            row=row, column=column, columnspan=3,
            sticky="nsew", padx=8, pady=4,
        )
        field.columnconfigure(0, weight=1)
        self._wrapped_label(field, text=self.tr(label_key)).grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 3)
        )
        entry = ttk.Entry(field, textvariable=self._new_var(key), width=16)
        entry.grid(row=1, column=0, sticky="ew")
        self._controls[key] = entry
        self._field_frames[key] = field
        ttk.Label(field, text=unit).grid(
            row=1, column=1, sticky="w", padx=(4, 0)
        )
        return entry

    def _add_choice(self, frame, row, column, label_key, key, options):
        field = ttk.Frame(frame)
        field.grid(
            row=row, column=column, columnspan=3,
            sticky="nsew", padx=8, pady=4,
        )
        field.columnconfigure(0, weight=1)
        self._wrapped_label(field, text=self.tr(label_key)).grid(
            row=0, column=0, sticky="ew", pady=(0, 3)
        )
        labels = [label for _code, label in options]
        mapping = {label: code for code, label in options}
        reverse = {code: label for code, label in options}
        variable = self._new_var(key)
        choice = ttk.Combobox(
            field, textvariable=variable, values=labels,
            state="readonly", width=24,
        )
        choice.grid(row=1, column=0, sticky="ew")
        self._choice_maps[key] = mapping
        self._choice_reverse[key] = reverse
        self._controls[key] = choice
        self._field_frames[key] = field
        return choice

    def _wrapped_label(self, parent, **options):
        options.setdefault("justify", "left")
        options.setdefault("anchor", "w")
        label = ttk.Label(parent, **options)
        self._wrapped_labels.append(label)
        return label

    def _choice_code(self, key, default=None):
        return self._choice_maps.get(key, {}).get(
            self.vars[key].get(), default
        )

    def _set_choice(self, key, code):
        label = self._choice_reverse.get(key, {}).get(code)
        if label is not None:
            self.vars[key].set(label)

    def _page_label(self, key, index):
        label = self.tr(key)
        if "·" in label:
            label = label.split("·", 1)[1].strip()
        return "{} · {}".format(index + 1, label)

    def _tab(self, notebook, title_key):
        frame = ttk.Frame(notebook, padding=8)
        for column in (0, 3):
            frame.columnconfigure(column, weight=1, uniform="fields")
        notebook.add(
            frame, text=self._page_label(title_key, len(self._all_tabs))
        )
        self._all_tabs.append((title_key, frame))
        self._active_page_keys.append(title_key)
        return frame

    def _build_ui(self):
        root = ttk.Frame(self.root, padding=8)
        root.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)

        content_host = ttk.Frame(root)
        content_host.grid(row=0, column=0, sticky="nsew")
        content_host.rowconfigure(0, weight=1)
        content_host.columnconfigure(0, weight=1)
        self._content_canvas = tk.Canvas(
            content_host, borderwidth=0, highlightthickness=0,
            background=self.root.cget("background"),
        )
        vertical_scroll = ttk.Scrollbar(
            content_host, orient="vertical",
            command=self._content_canvas.yview,
        )
        horizontal_scroll = ttk.Scrollbar(
            content_host, orient="horizontal",
            command=self._content_canvas.xview,
        )
        self._content_canvas.configure(
            yscrollcommand=vertical_scroll.set,
            xscrollcommand=horizontal_scroll.set,
        )
        self._content_canvas.grid(row=0, column=0, sticky="nsew")
        # The compact field grid fits the default window, so scrollbars stay
        # hidden. The canvas remains as a small-screen mouse-wheel fallback.

        self._scroll_content = ttk.Frame(self._content_canvas)
        self._content_window = self._content_canvas.create_window(
            (0, 0), window=self._scroll_content, anchor="nw"
        )
        self._scroll_content.bind(
            "<Configure>", self._on_content_configure
        )
        self._content_canvas.bind(
            "<Configure>", self._on_canvas_configure
        )
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)

        guide = ttk.Frame(self._scroll_content)
        guide.pack(fill="x", pady=(0, 8))
        ttk.Label(
            guide, text=self.tr("guide_title"),
            font=("TkDefaultFont", 11, "bold"),
        ).pack(anchor="w")
        self._wrapped_label(
            guide, textvariable=self.guide_hint,
        ).pack(fill="x", pady=(3, 0))
        profile_row = ttk.Frame(guide)
        profile_row.pack(fill="x", pady=(6, 0))
        self.profile_choice_var = tk.StringVar()
        self.profile_name_var = tk.StringVar()
        self.profile_choice = ttk.Combobox(
            profile_row, textvariable=self.profile_choice_var,
            state="readonly", width=22,
        )
        self.profile_choice.pack(side="left")
        ttk.Entry(
            profile_row, textvariable=self.profile_name_var, width=20
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            profile_row, text=self.tr("profile_load"),
            command=self._load_user_profile,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            profile_row, text=self.tr("profile_save"),
            command=self._save_user_profile,
        ).pack(side="left", padx=(4, 0))
        ttk.Button(
            profile_row, text=self.tr("profile_delete"),
            command=self._delete_user_profile,
        ).pack(side="left", padx=(4, 0))
        self._refresh_profile_choices()

        workspace = ttk.Frame(self._scroll_content)
        workspace.pack(fill="both", expand=True)
        # The uniform group ignores changing child requested widths and keeps
        # the parameter/preview panes at a strict 65/35 split.
        workspace.columnconfigure(
            0, weight=WORKSPACE_MAIN_WEIGHT, uniform="coilforge-workspace"
        )
        workspace.columnconfigure(
            1, weight=WORKSPACE_SIDEBAR_WEIGHT, uniform="coilforge-workspace"
        )
        workspace.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(workspace)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        notebook = self.notebook

        sidebar = ttk.Frame(workspace, padding=(8, 0, 0, 0))
        sidebar.grid(row=0, column=1, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(0, weight=1)

        preview_box = ttk.LabelFrame(
            sidebar, text=self.tr("preview_title"), padding=8
        )
        preview_box.grid(row=0, column=0, sticky="nsew")
        preview_box.columnconfigure(0, weight=1)
        preview_box.rowconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(
            preview_box, width=340, height=220, background="#fafbfd",
            highlightthickness=1, highlightbackground="#d9dde3",
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", self._on_preview_resize)
        self._wrapped_label(
            preview_box, textvariable=self.preview_caption,
        ).grid(row=1, column=0, sticky="ew", pady=(6, 2))
        self._wrapped_label(
            preview_box, text=self.tr("preview_legend"),
        ).grid(row=2, column=0, sticky="ew")

        summary = ttk.LabelFrame(
            sidebar, text=self.tr("preview_summary"), padding=8
        )
        summary.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        style = ttk.Style(self.root)
        style.configure("CoilForge.Valid.TLabel", foreground="#1f7a48")
        style.configure("CoilForge.Error.TLabel", foreground="#b3261e")
        self.validation_label = self._wrapped_label(
            summary, textvariable=self.validation_summary,
            style="CoilForge.Valid.TLabel",
        )
        self.validation_label.pack(fill="x", pady=(2, 5))
        for variable in (
                self.result_summary, self.electrical_summary,
                self.object_summary):
            self._wrapped_label(
                summary, textvariable=variable,
            ).pack(fill="x", pady=2)
        self.author_label = ttk.Label(
            sidebar, text=self.tr("author_info")
        )
        self.author_label.grid(
            row=2, column=0, sticky="e", pady=(8, 0)
        )

        app_options = [
            (code, self.tr("application_" + code))
            for code in (
                "custom", "general", "compact_sensor", "nfc_rfid",
                "wireless_power", "heating", "long_trace",
                "motor_axial_ellipse", "motor_racetrack",
                "motor_trapezoid", "motor_sector", "motor_linear",
            )
        ]
        process_options = [
            (code, self.tr("manufacturing_" + code))
            for code in (
                "custom", "standard", "conservative", "fine",
                "heavy_copper",
            )
        ]
        net_options = [
            (name, name or self.tr("no_net")) for name, _net in self.net_items
        ]
        layer_options = [(layer, name) for layer, name in self.layers]
        count_options = [
            (count, self.tr("layer_count_option", count=count))
            for count in range(1, 13)
        ]

        quick = self._tab(notebook, "section_quick_setup")
        self._add_choice(
            quick, 0, 0, "application_preset", "application_preset",
            app_options,
        )
        self._add_choice(quick, 0, 3, "design_mode", "design_mode", (
            ("manual", self.tr("design_manual")),
            ("fit_turns", self.tr("design_fit_turns")),
            ("fit_length", self.tr("design_fit_length")),
            ("target_resistance", self.tr("design_target_resistance")),
            ("target_inductance", self.tr("design_target_inductance")),
            ("target_current", self.tr("design_target_current")),
            ("motor_target", self.tr("design_motor_target")),
        ))
        self._add_entry(
            quick, 1, 0, "target_current", "target_current_a", "A"
        )
        self._add_entry(
            quick, 1, 3, "target_torque", "target_torque_nm", "N·m"
        )
        self._add_entry(
            quick, 2, 0, "motor_target_force",
            "motor_target_force_n", "N",
        )
        self._add_entry(
            quick, 2, 3, "motor_target_linear_speed",
            "motor_target_linear_speed_mps", "m/s",
        )
        self._add_entry(
            quick, 3, 0, "motor_supply_voltage",
            "motor_supply_voltage_v", "V",
        )
        self._add_entry(
            quick, 3, 3, "motor_target_speed",
            "motor_target_speed_rpm", "rpm",
        )
        self._add_entry(
            quick, 4, 0, "motor_max_phase_current",
            "motor_max_phase_current_a", "A",
        )
        self._add_entry(
            quick, 4, 3, "allowed_temperature_rise",
            "allowed_temperature_rise_c", "°C",
        )
        self._add_choice(
            quick, 5, 0, "motor_connection", "motor_connection", (
                ("star", self.tr("motor_connection_star")),
                ("delta", self.tr("motor_connection_delta")),
            )
        )
        self._add_entry(
            quick, 5, 3, "air_gap_flux_density",
            "air_gap_flux_density_t", "T",
        )
        self._add_entry(
            quick, 6, 0, "electrical_loading",
            "electrical_loading_a_per_m", "A/m",
        )
        self._add_entry(
            quick, 6, 3, "winding_factor", "winding_factor"
        )
        self._add_entry(
            quick, 7, 0, "motor_inner_ratio", "motor_inner_ratio"
        )
        self._wrapped_label(
            quick, textvariable=self.preset_summary,
        ).grid(row=8, column=0, columnspan=6, sticky="ew", padx=8, pady=8)

        board = self._tab(notebook, "section_board")
        self._add_choice(
            board, 0, 0, "manufacturing_preset",
            "manufacturing_preset", process_options,
        )
        self._add_entry(
            board, 0, 3, "copper_thickness", "copper_thickness_um", "µm"
        )
        self._add_entry(
            board, 1, 0, "minimum_track_width",
            "minimum_track_width_mm", "mm",
        )
        self._add_entry(
            board, 1, 3, "minimum_clearance",
            "minimum_clearance_mm", "mm",
        )

        sizing = self._tab(notebook, "section_sizing")
        self._add_choice(sizing, 0, 0, "sizing_mode", "sizing_mode", (
            ("manual", self.tr("sizing_manual")),
            ("fit_turns", self.tr("sizing_fit_turns")),
            ("fit_length", self.tr("sizing_fit_length")),
        ))
        self._add_entry(
            sizing, 0, 3, "available_diameter", "available_diameter_mm", "mm"
        )
        self._add_entry(sizing, 1, 0, "turns", "turns")
        self._add_entry(
            sizing, 1, 3, "target_length", "target_length_mm", "mm"
        )
        self._add_entry(
            sizing, 2, 0, "fill_ratio", "fill_ratio_percent", "%"
        )
        self._add_entry(
            sizing, 2, 3, "initial_radius", "start_radius_mm", "mm"
        )
        self._add_entry(
            sizing, 3, 0, "track_width", "track_width_mm", "mm"
        )
        self._add_entry(sizing, 3, 3, "spacing", "spacing_mm", "mm")
        self._add_choice(sizing, 4, 0, "spacing_mode", "spacing_mode", (
            ("pitch", self.tr("spacing_pitch")),
            ("clearance", self.tr("spacing_clearance")),
        ))
        self._add_entry(
            sizing, 4, 3, "motor_board_outer_diameter",
            "motor_board_outer_diameter_mm", "mm",
        )
        self._add_entry(
            sizing, 5, 0, "motor_board_inner_diameter",
            "motor_board_inner_diameter_mm", "mm",
        )
        self._add_entry(
            sizing, 5, 3, "target_resistance",
            "target_resistance_ohm", "Ω",
        )
        self._add_entry(
            sizing, 6, 0, "target_inductance",
            "target_inductance_uh", "µH",
        )

        geometry = self._tab(notebook, "section_geometry")
        self._add_choice(geometry, 0, 0, "coil_shape", "coil_shape", (
            ("circular", self.tr("shape_circular")),
            ("motor_ellipse", self.tr("shape_motor_ellipse")),
            ("motor_racetrack", self.tr("shape_motor_racetrack")),
            ("motor_trapezoid", self.tr("shape_motor_trapezoid")),
            ("motor_sector", self.tr("shape_motor_sector")),
        ))
        self._add_entry(
            geometry, 0, 3, "shape_aspect_ratio", "shape_aspect_ratio"
        )
        self._add_entry(
            geometry, 1, 0, "shape_taper_percent",
            "shape_taper_percent", "%",
        )
        self._add_entry(
            geometry, 1, 3, "angle_offset", "angle_degrees", "°"
        )
        self._add_choice(geometry, 2, 0, "direction", "direction", (
            ("clockwise", self.tr("clockwise")),
            ("counterclockwise", self.tr("counterclockwise")),
        ))
        self._wrapped_label(
            geometry, textvariable=self.motor_recommendation_summary,
        ).grid(
            row=3, column=0, columnspan=4,
            sticky="ew", padx=8, pady=(8, 4),
        )
        self.apply_motor_recommendation_button = ttk.Button(
            geometry, text=self.tr("apply_motor_recommendation"),
            command=self._apply_motor_recommendation,
        )
        self.apply_motor_recommendation_button.grid(
            row=3, column=4, columnspan=2,
            sticky="e", padx=8, pady=(8, 4),
        )

        placement = self._tab(notebook, "section_placement")
        self._add_choice(placement, 0, 0, "motor_layout", "motor_layout", (
            ("single", self.tr("motor_layout_single")),
            ("radial", self.tr("motor_layout_radial")),
            ("linear", self.tr("motor_layout_linear")),
        ))
        self._add_entry(
            placement, 0, 3, "motor_pole_pairs", "motor_pole_pairs"
        )
        self._add_entry(
            placement, 1, 0, "motor_slot_count", "motor_slot_count"
        )
        self._add_entry(
            placement, 1, 3, "motor_phase_count", "motor_phase_count"
        )
        self._add_entry(
            placement, 2, 0, "motor_array_radius",
            "motor_array_radius_mm", "mm",
        )
        self._add_entry(
            placement, 2, 3, "motor_linear_pitch",
            "motor_linear_pitch_mm", "mm",
        )
        self._add_entry(
            placement, 3, 0, "motor_array_angle",
            "motor_array_angle_degrees", "°",
        )
        self._add_choice(
            placement, 3, 3, "motor_orientation", "motor_orientation", (
                ("radial", self.tr("motor_orientation_radial")),
                ("tangential", self.tr("motor_orientation_tangential")),
            )
        )
        motor_alternate = ttk.Checkbutton(
            placement, text=self.tr("motor_alternate_winding"),
            variable=self.bool_vars["motor_alternate_winding"],
            command=self._motor_parameter_edited,
        )
        motor_alternate.grid(
            row=4, column=0, columnspan=3, sticky="w", padx=8, pady=8
        )
        self._controls["motor_alternate_winding"] = motor_alternate
        self._add_entry(
            placement, 4, 3, "motor_edge_clearance",
            "motor_edge_clearance_mm", "mm",
        )
        self._add_entry(
            placement, 5, 0, "motor_slot_gap",
            "motor_slot_gap_mm", "mm",
        )

        multilayer = self._tab(notebook, "section_multilayer")
        self._add_choice(
            multilayer, 0, 0, "net_name", "net_name", net_options
        )
        self._add_choice(
            multilayer, 0, 3, "start_layer", "layer_code", layer_options
        )
        self._add_choice(
            multilayer, 1, 0, "layer_count", "layer_count", count_options
        )
        self._add_entry(
            multilayer, 1, 3, "via_diameter", "via_diameter_mm", "mm"
        )
        self._add_entry(
            multilayer, 2, 0, "via_drill", "via_drill_mm", "mm"
        )
        self._add_entry(
            multilayer, 2, 3, "via_clearance", "via_clearance_mm", "mm"
        )
        self._wrapped_label(
            multilayer, text=self.tr("multilayer_hint"),
        ).grid(row=3, column=0, columnspan=6, sticky="ew", padx=8, pady=12)

        options = self._tab(notebook, "section_options")
        self._add_entry(options, 0, 0, "group_name", "group_name")
        self._add_choice(options, 0, 3, "quality_preset", "quality_preset", (
            ("fast", self.tr("quality_fast")),
            ("balanced", self.tr("quality_balanced")),
            ("smooth", self.tr("quality_smooth")),
            ("custom", self.tr("quality_custom")),
        ))
        self._controls["quality_preset"].bind(
            "<<ComboboxSelected>>", self._quality_changed
        )
        self._add_choice(options, 1, 0, "primitive_mode", "primitive_mode", (
            ("auto", self.tr("primitive_auto")),
            ("arc", self.tr("primitive_arc")),
            ("segment", self.tr("primitive_segment")),
        ))
        self._add_entry(options, 1, 3, "arcs_per_turn", "arcs_per_turn")
        self._add_entry(
            options, 2, 0, "segments_per_turn", "segments_per_turn"
        )
        self._add_entry(
            options, 2, 3, "additional_segments", "additional_segments"
        )
        self._add_entry(options, 3, 0, "center_x", "center_x_mm", "mm")
        self._add_entry(options, 3, 3, "center_y", "center_y_mm", "mm")
        ttk.Button(
            options, text=self.tr("center_from_selection"),
            command=self._use_selection_center,
        ).grid(row=4, column=0, columnspan=6, pady=(4, 8))
        ttk.Checkbutton(
            options, text=self.tr("create_group"),
            variable=self.bool_vars["create_group"],
        ).grid(row=5, column=0, columnspan=3, sticky="w", padx=8, pady=8)
        ttk.Checkbutton(
            options, text=self.tr("close_after_create"),
            variable=self.bool_vars["close_after_create"],
        ).grid(row=5, column=3, columnspan=3, sticky="w", padx=8, pady=8)
        ttk.Checkbutton(
            options, text=self.tr("show_advanced_parameters"),
            variable=self.bool_vars["show_advanced_parameters"],
            command=self._advanced_visibility_changed,
        ).grid(row=6, column=0, columnspan=6, sticky="w", padx=8, pady=8)
        self._wrapped_label(
            options,
            text=self.tr(
                "ipc_backend_info", version=self.backend.version_text
            ),
        ).grid(row=7, column=0, columnspan=6, sticky="ew", padx=8, pady=12)

        buttons = ttk.Frame(root)
        buttons.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            buttons, text=self.tr("reset"), command=self._reset
        ).pack(side="left")
        self.previous_button = ttk.Button(
            buttons, text=self.tr("previous_step"),
            command=lambda: self._move_page(-1),
        )
        self.previous_button.pack(side="left", padx=(8, 0))
        self.next_button = ttk.Button(
            buttons, text=self.tr("next_step"),
            command=lambda: self._move_page(1),
        )
        self.next_button.pack(side="left", padx=(6, 0))
        ttk.Button(
            buttons, text=self.tr("cancel"), command=self.root.destroy
        ).pack(side="right")
        self.create_button = ttk.Button(
            buttons, text=self.tr("create"), command=self._create
        )
        self.create_button.pack(side="right", padx=(0, 8))
        self.notebook.bind("<<NotebookTabChanged>>", self._on_page_changed)
        self._update_navigation()

    def _refresh_profile_choices(self):
        if not hasattr(self, "profile_choice"):
            return
        names = self.profile_store.names()
        self.profile_choice.configure(values=names)
        if self.profile_choice_var.get() not in names:
            self.profile_choice_var.set(names[0] if names else "")

    def _load_user_profile(self):
        name = self.profile_choice_var.get().strip()
        values = self.profile_store.load(name) if name else None
        if values is None:
            messagebox.showwarning(
                self.tr("profile_title"), self.tr("profile_not_found"),
                parent=self.root,
            )
            return
        self.settings = values
        self._workflow.unlock_from(0)
        self._apply_settings(values)
        self._refresh_states()
        self._update_preview()

    def _save_user_profile(self):
        name = self.profile_name_var.get().strip()
        if not name:
            messagebox.showwarning(
                self.tr("profile_title"), self.tr("profile_name_required"),
                parent=self.root,
            )
            return
        try:
            values = self._read_values()[0]
        except ValidationError as error:
            messagebox.showwarning(
                self.tr("profile_title"), str(error), parent=self.root
            )
            return
        overwrite = self.profile_store.load(name) is not None
        if overwrite and not messagebox.askyesno(
                self.tr("profile_title"),
                self.tr("profile_overwrite", name=name), parent=self.root):
            return
        try:
            self.profile_store.save(name, values, overwrite=overwrite)
        except (IOError, OSError, ValueError) as error:
            messagebox.showwarning(
                self.tr("profile_title"), self._error_message(error),
                parent=self.root,
            )
            return
        self.profile_name_var.set("")
        self._refresh_profile_choices()
        self.profile_choice_var.set(name)

    def _delete_user_profile(self):
        name = self.profile_choice_var.get().strip()
        if not name:
            return
        if not messagebox.askyesno(
                self.tr("profile_title"),
                self.tr("profile_delete_confirm", name=name), parent=self.root):
            return
        self.profile_store.delete(name)
        self._refresh_profile_choices()

    def _current_form_snapshot(self):
        snapshot = dict(self.settings)
        for key, variable in self.vars.items():
            raw = variable.get()
            if key in _NUMERIC_SETTING_KEYS or key in (
                    "fill_ratio_percent", "shape_taper_percent"):
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    continue
                if key == "fill_ratio_percent":
                    snapshot["fill_ratio"] = value / 100.0
                elif key == "shape_taper_percent":
                    snapshot["shape_taper_ratio"] = value / 100.0
                else:
                    snapshot[key] = value
            elif key in self._choice_maps:
                snapshot[key] = self._choice_code(key, snapshot.get(key))
            else:
                snapshot[key] = raw
        for key, variable in self.bool_vars.items():
            snapshot[key] = bool(variable.get())
        return snapshot

    def _set_workflow_pages(self, page_keys):
        wanted = tuple(page_keys)
        if wanted == tuple(self._active_page_keys):
            return False
        current = self.notebook.index("current")
        current_key = (
            self._active_page_keys[current]
            if 0 <= current < len(self._active_page_keys) else None
        )
        self._changing_workflow = True
        try:
            for tab_id in tuple(self.notebook.tabs()):
                self.notebook.forget(tab_id)
            records = [
                (key, frame) for key, frame in self._all_tabs
                if key in wanted
            ]
            for index, (key, frame) in enumerate(records):
                self.notebook.add(
                    frame, text=self._page_label(key, index)
                )
            self._active_page_keys = [key for key, _frame in records]
            selection = (
                self._active_page_keys.index(current_key)
                if current_key in self._active_page_keys else 0
            )
            if records:
                self.notebook.select(records[selection][1])
        finally:
            self._changing_workflow = False
        self._update_navigation()
        return True

    def _apply_parameter_visibility(self):
        snapshot = self._current_form_snapshot()
        advanced = self.bool_vars["show_advanced_parameters"].get()
        pages = workflow_page_keys(snapshot, advanced)
        if self._set_workflow_pages(pages):
            self._workflow = WorkflowLocks(
                workflow_step_fields(snapshot, advanced)
            )
            self._last_page = self.notebook.index("current")
        visible = parameter_visibility(snapshot, advanced)
        for key, field in self._field_frames.items():
            if key in visible:
                field.grid()
            else:
                field.grid_remove()
        self._on_content_configure()

    def _advanced_visibility_changed(self):
        self.settings["show_advanced_parameters"] = bool(
            self.bool_vars["show_advanced_parameters"].get()
        )
        self._apply_parameter_visibility()

    def _move_page(self, offset):
        current = self.notebook.index("current")
        target = min(
            len(self.notebook.tabs()) - 1, max(0, current + int(offset))
        )
        self.notebook.select(target)
        self._update_navigation()

    def _on_page_changed(self, _event=None):
        if self._changing_workflow:
            return
        current = self.notebook.index("current")
        if current > self._last_page:
            snapshot = self._current_form_snapshot()
            for step in range(self._last_page, current):
                self._workflow.lock_step(step, snapshot)
        elif current < self._last_page:
            self._workflow.unlock_from(current)
        self._last_page = current
        self._update_navigation()

    def _update_navigation(self):
        if not hasattr(self, "previous_button"):
            return
        current = self.notebook.index("current")
        last = len(self.notebook.tabs()) - 1
        self.previous_button.configure(
            state="normal" if current > 0 else "disabled"
        )
        self.next_button.configure(
            state="normal" if current < last else "disabled"
        )
        page_key = self._active_page_keys[current]
        hint_key = "guide_hint_" + page_key.replace("section_", "")
        if page_key == "section_sizing":
            hint_key += "_" + self._choice_code(
                "sizing_mode", "manual"
            )
        self.guide_hint.set(self.tr(hint_key))

    def _on_preview_resize(self, _event=None):
        self._draw_preview()

    def _set_validation_feedback(self, message, valid):
        self.validation_summary.set(message)
        self.validation_label.configure(
            style=(
                "CoilForge.Valid.TLabel"
                if valid else "CoilForge.Error.TLabel"
            )
        )
        self.create_button.configure(
            state="normal" if valid else "disabled"
        )

    def _set_preview_scene(self, scene):
        self._preview_scene = scene
        if scene:
            shape_key = {
                "circular": "shape_circular",
                "motor_ellipse": "shape_motor_ellipse",
                "motor_racetrack": "shape_motor_racetrack",
                "motor_trapezoid": "shape_motor_trapezoid",
                "motor_sector": "shape_motor_sector",
            }.get(scene.get("coil_shape"), "shape_circular")
            self.preview_caption.set(self.tr(
                "preview_caption", shape=self.tr(shape_key),
                layers=scene.get("layer_count", 1),
            ))
        else:
            self.preview_caption.set("")
        self._draw_preview()

    def _draw_preview(self):
        if not hasattr(self, "preview_canvas"):
            return
        canvas = self.preview_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        if not self._preview_scene:
            canvas.create_text(
                width / 2.0, height / 2.0,
                text=self.tr("preview_empty"), fill="#5f6368",
                width=max(120, width - 32), justify="center",
            )
            return
        fitted = fit_preview_scene(
            self._preview_scene, width, height, 22
        )
        center_x, center_y = fitted["center"]
        canvas.create_line(10, center_y, width - 10, center_y, fill="#e1e4e8")
        canvas.create_line(center_x, 10, center_x, height - 10, fill="#e1e4e8")
        colours = ("#236fc4", "#6f42c1", "#00897b", "#c66800")
        track_width = max(1.0, fitted.get("track_width_px", 2.0))
        for index, path in enumerate(fitted["coil_paths"]):
            if len(path) < 2:
                continue
            coordinates = [value for point in path for value in point]
            canvas.create_line(
                *coordinates, fill=colours[index % len(colours)],
                width=track_width, joinstyle="round", capstyle="round",
            )
        for start, end in fitted["connector_paths"]:
            canvas.create_line(
                start[0], start[1], end[0], end[1],
                fill="#5f6368", width=track_width,
            )
        via_radius = max(3.0, fitted.get("via_diameter_px", 8.0) / 2.0)
        for x, y in fitted["via_points"]:
            canvas.create_oval(
                x - via_radius, y - via_radius,
                x + via_radius, y + via_radius,
                outline="#00798c", fill="#d5f5f9", width=2,
            )
        terminal_colours = ("#239142", "#e57a00")
        for index, (x, y) in enumerate(fitted["terminal_points"]):
            colour = terminal_colours[index % len(terminal_colours)]
            canvas.create_oval(
                x - 4, y - 4, x + 4, y + 4,
                outline=colour, fill=colour,
            )

    def _on_content_configure(self, _event=None):
        self._content_canvas.configure(
            scrollregion=self._content_canvas.bbox("all")
        )

    def _on_canvas_configure(self, event):
        available_width = max(320, event.width - 64)
        for label in self._wrapped_labels:
            parent_width = label.master.winfo_width()
            wraplength = (
                min(520, available_width, max(180, parent_width - 20))
                if parent_width > 40 else min(420, available_width)
            )
            label.configure(wraplength=wraplength)
        # Keep the guided two-column workspace stable. Using the frame's
        # current requested width here creates an expansion feedback loop
        # because both columns are growable. Narrow windows can still use the
        # outer horizontal scrollbar without clipping controls.
        content_width = max(event.width, 760)
        self._content_canvas.itemconfigure(
            self._content_window, width=content_width
        )
        self._on_content_configure()

    def _on_mousewheel(self, event):
        if event.delta:
            units = -3 if event.delta > 0 else 3
            self._content_canvas.yview_scroll(units, "units")

    def _motor_shape_active(self):
        return self._choice_code("coil_shape", "circular").startswith("motor_")

    def _application_is_custom(self):
        return self._choice_code(
            "application_preset", "custom"
        ) == "custom"

    def _apply_application_fill_recommendation(self):
        if self._application_is_custom():
            return

        def number(key, fallback):
            try:
                return float(self.vars[key].get())
            except (KeyError, TypeError, ValueError):
                return float(fallback)

        value = recommend_copper_fill_ratio(
            self._choice_code("application_preset", "custom"),
            self._choice_code("manufacturing_preset", "custom"),
            number("target_current_a", self.settings["target_current_a"]),
            number(
                "copper_thickness_um",
                self.settings["copper_thickness_um"],
            ),
            number("fill_ratio_percent", 55.0) / 100.0,
        )
        self._updating = True
        try:
            self.vars["fill_ratio_percent"].set(
                _format_number(value * 100.0)
            )
            self.settings["fill_ratio"] = value
        finally:
            self._updating = False

    def _current_motor_recommendation(self):
        shape = self._choice_code("coil_shape", "circular")
        if not shape.startswith("motor_"):
            return {}

        def number(key, fallback):
            try:
                return float(self.vars[key].get())
            except (KeyError, TypeError, ValueError):
                return float(fallback)

        try:
            pairs = int(number(
                "motor_pole_pairs", self.settings.get("motor_pole_pairs", 3)
            ))
        except (TypeError, ValueError):
            pairs = int(self.settings.get("motor_pole_pairs", 3))
        return recommend_motor_parameters(
            shape,
            self._choice_code("motor_layout", "single"),
            pairs,
            self._choice_code("manufacturing_preset", "custom"),
            int(self._choice_code("layer_count", 1)),
            number("via_diameter_mm", self.settings["via_diameter_mm"]),
            number("via_clearance_mm", self.settings["via_clearance_mm"]),
            number("track_width_mm", self.settings["track_width_mm"]),
            number(
                "minimum_track_width_mm",
                self.settings["minimum_track_width_mm"],
            ),
            number(
                "minimum_clearance_mm",
                self.settings["minimum_clearance_mm"],
            ),
            application_code=self._choice_code(
                "application_preset", "custom"
            ),
            target_current_a=number(
                "target_current_a", self.settings["target_current_a"]
            ),
            copper_thickness_um=number(
                "copper_thickness_um", self.settings["copper_thickness_um"]
            ),
            target_torque_nm=number(
                "target_torque_nm", self.settings["target_torque_nm"]
            ),
            air_gap_flux_density_t=number(
                "air_gap_flux_density_t", self.settings["air_gap_flux_density_t"]
            ),
            electrical_loading_a_per_m=number(
                "electrical_loading_a_per_m",
                self.settings["electrical_loading_a_per_m"],
            ),
            winding_factor=number(
                "winding_factor", self.settings["winding_factor"]
            ),
            motor_inner_ratio=number(
                "motor_inner_ratio", self.settings["motor_inner_ratio"]
            ),
            motor_slot_count=int(number(
                "motor_slot_count", self.settings["motor_slot_count"]
            )),
            motor_phase_count=int(number(
                "motor_phase_count", self.settings["motor_phase_count"]
            )),
        )

    def _show_motor_recommendation(self, recommendation,
                                   preserved_field=None):
        if not recommendation:
            self.motor_recommendation_summary.set(
                self.tr("motor_recommendation_not_applicable")
            )
            self.apply_motor_recommendation_button.configure(state="disabled")
            return
        if preserved_field:
            key = "motor_recommendation_constrained"
        else:
            key = (
                "motor_recommendation_auto"
                if self._motor_parameters_auto
                else "motor_recommendation_manual"
            )
        text = self.tr(
            key,
            field=preserved_field or "",
            layout=self.tr("motor_layout_" + recommendation["layout"]),
            poles=recommendation["pole_count"],
            aspect=_format_number(recommendation["shape_aspect_ratio"]),
            taper=_format_number(
                recommendation["shape_taper_ratio"] * 100.0
            ),
            radius=_format_number(recommendation["start_radius_mm"]),
            unit="mm",
            fill=_format_number(recommendation["fill_ratio"] * 100.0),
        )
        if "motor_outer_diameter_mm" in recommendation:
            text += " " + self.tr(
                "motor_dimensioning_recommendation",
                outer=_format_number(recommendation["motor_outer_diameter_mm"]),
                inner=_format_number(recommendation["motor_inner_diameter_mm"]),
                ratio=_format_number(recommendation["motor_inner_ratio"]),
                unit="mm",
            )
        self.motor_recommendation_summary.set(text)
        self.apply_motor_recommendation_button.configure(state="normal")

    def _apply_motor_recommendation_values(self, recommendation,
                                            preserve_keys=()):
        if not recommendation:
            return
        preserve = set(preserve_keys)
        self._updating = True
        try:
            if "shape_aspect_ratio" not in preserve:
                self.vars["shape_aspect_ratio"].set(_format_number(
                    recommendation["shape_aspect_ratio"]
                ))
            if "shape_taper_ratio" not in preserve:
                self.vars["shape_taper_percent"].set(_format_number(
                    recommendation["shape_taper_ratio"] * 100.0
                ))
            if "start_radius_mm" not in preserve:
                self.vars["start_radius_mm"].set(_format_number(
                    recommendation["start_radius_mm"]
                ))
            if "fill_ratio" not in preserve:
                self.vars["fill_ratio_percent"].set(_format_number(
                    recommendation["fill_ratio"] * 100.0
                ))
            if "spacing_mode" not in preserve:
                self._set_choice(
                    "spacing_mode", recommendation["spacing_mode"]
                )
            if "quality_preset" not in preserve:
                self._set_choice(
                    "quality_preset", recommendation["quality_preset"]
                )
                quality = QUALITY_PRESETS[recommendation["quality_preset"]]
                self.vars["arcs_per_turn"].set(str(quality[0]))
                self.vars["segments_per_turn"].set(str(quality[1]))
            if "additional_segments" not in preserve:
                self.vars["additional_segments"].set(str(
                    recommendation["additional_segments"]
                ))
            if "sizing_mode" in recommendation and "sizing_mode" not in preserve:
                self._set_choice("sizing_mode", recommendation["sizing_mode"])
            if ("available_diameter_mm" in recommendation
                    and "available_diameter_mm" not in preserve):
                self.vars["available_diameter_mm"].set(_format_number(
                    recommendation["available_diameter_mm"]
                ))
            if "motor_array_radius_mm" not in preserve:
                self.vars["motor_array_radius_mm"].set(_format_number(
                    recommendation["motor_array_radius_mm"]
                ))
            if "motor_linear_pitch_mm" not in preserve:
                self.vars["motor_linear_pitch_mm"].set(_format_number(
                    recommendation["motor_linear_pitch_mm"]
                ))
            if "motor_orientation" not in preserve:
                self._set_choice(
                    "motor_orientation", recommendation["motor_orientation"]
                )
            if "motor_alternate_winding" not in preserve:
                self.bool_vars["motor_alternate_winding"].set(
                    recommendation["motor_alternate_winding"]
                )
            self.settings.update({
                key: value for key, value in recommendation.items()
                if key not in (
                    "pole_count", "slot_count", "phase_count",
                    "phase_balanced", "layout", "motor_outer_diameter_mm",
                    "motor_inner_diameter_mm",
                )
                and key not in preserve
            })
            self._motor_parameters_auto = True
            self.settings["motor_parameters_auto"] = True
        finally:
            self._updating = False

    def _refresh_motor_recommendation(self, apply=False,
                                      update_preview=False,
                                      preserve_keys=(),
                                      preserved_field=None):
        recommendation = self._current_motor_recommendation()
        fixed_keys = tuple(self._workflow.fixed_values())
        preserve_keys = tuple(set(preserve_keys) | set(fixed_keys))
        if apply and recommendation:
            self._apply_motor_recommendation_values(
                recommendation, preserve_keys
            )
            recommendation = self._current_motor_recommendation()
        self._show_motor_recommendation(recommendation, preserved_field)
        if update_preview:
            self._update_preview()

    def _motor_parameter_edited(
            self, key="motor_alternate_winding",
            field_key="motor_alternate_winding", *_args):
        if self._updating or not self._motor_shape_active():
            return
        if self._application_is_custom():
            self._motor_parameters_auto = False
            self.settings["motor_parameters_auto"] = False
            self._refresh_motor_recommendation(apply=False)
        else:
            self._motor_parameters_auto = True
            self.settings["motor_parameters_auto"] = True
            self._refresh_motor_recommendation(
                apply=True,
                preserve_keys=(key,),
                preserved_field=self.tr(field_key),
            )
        self._schedule_preview()

    def _motor_driver_changed(self, *_args):
        if self._updating:
            return
        auto = self._motor_parameters_auto or not self._application_is_custom()
        self._refresh_motor_recommendation(
            apply=auto, update_preview=False
        )
        self._schedule_preview()

    def _apply_motor_recommendation(self):
        self._motor_parameters_auto = True
        self.settings["motor_parameters_auto"] = True
        self._refresh_motor_recommendation(apply=True, update_preview=True)

    def _electrical_driver_changed(self, *_args):
        if self._updating or self._application_is_custom():
            return
        self._apply_application_fill_recommendation()
        if self._motor_shape_active():
            self._refresh_motor_recommendation(
                apply=True, update_preview=False
            )
        self._schedule_preview()

    def _bind_preview(self):
        preview_keys = (
            "start_radius_mm", "turns", "arcs_per_turn",
            "segments_per_turn", "additional_segments",
            "track_width_mm", "spacing_mm", "available_diameter_mm",
            "target_length_mm", "fill_ratio_percent",
            "minimum_track_width_mm", "minimum_clearance_mm",
            "via_diameter_mm", "via_drill_mm", "via_clearance_mm",
            "copper_thickness_um", "target_current_a",
            "target_torque_nm", "motor_target_force_n",
            "motor_target_linear_speed_mps", "air_gap_flux_density_t",
            "electrical_loading_a_per_m", "winding_factor",
            "motor_inner_ratio", "motor_slot_count", "motor_phase_count",
            "angle_degrees", "shape_aspect_ratio",
            "shape_taper_percent", "sizing_mode", "primitive_mode",
            "quality_preset", "spacing_mode", "direction", "coil_shape",
            "layer_code", "layer_count", "motor_layout",
            "motor_pole_pairs", "motor_array_radius_mm",
            "motor_linear_pitch_mm", "motor_array_angle_degrees",
            "motor_board_outer_diameter_mm",
            "motor_board_inner_diameter_mm", "motor_edge_clearance_mm",
            "motor_slot_gap_mm", "motor_supply_voltage_v",
            "motor_target_speed_rpm", "motor_max_phase_current_a",
            "allowed_temperature_rise_c",
            "target_resistance_ohm", "target_inductance_uh",
            "motor_orientation", "design_mode", "motor_connection",
        )
        for key in preview_keys:
            self.vars[key].trace_add("write", self._schedule_preview)
        motor_fields = {
            "start_radius_mm": "initial_radius",
            "shape_aspect_ratio": "shape_aspect_ratio",
            "shape_taper_percent": "shape_taper_percent",
            "fill_ratio_percent": "fill_ratio",
            "additional_segments": "additional_segments",
            "motor_array_radius_mm": "motor_array_radius",
            "motor_linear_pitch_mm": "motor_linear_pitch",
        }
        recommendation_keys = {
            "shape_taper_percent": "shape_taper_ratio",
            "fill_ratio_percent": "fill_ratio",
        }
        for key, field_key in motor_fields.items():
            preserve_key = recommendation_keys.get(key, key)
            self.vars[key].trace_add(
                "write",
                lambda *args, pk=preserve_key, fk=field_key:
                    self._motor_parameter_edited(pk, fk, *args),
            )
        for key in (
                "motor_pole_pairs", "motor_slot_count", "motor_phase_count",
                "target_torque_nm", "motor_target_force_n",
            "motor_target_linear_speed_mps", "air_gap_flux_density_t",
                "electrical_loading_a_per_m", "winding_factor",
                "motor_inner_ratio"):
            self.vars[key].trace_add("write", self._motor_driver_changed)
        for key in ("target_current_a", "copper_thickness_um"):
            self.vars[key].trace_add(
                "write", self._electrical_driver_changed
            )
        for key in (
                "coil_shape", "layer_count", "layer_code", "direction",
                "sizing_mode", "design_mode", "spacing_mode",
                "primitive_mode", "motor_layout", "motor_orientation",
                "motor_connection"):
            control = self._controls.get(key)
            if control is not None:
                control.bind(
                    "<<ComboboxSelected>>",
                    self._preview_choice_changed, add="+",
                )
        for key in ("application_preset", "manufacturing_preset"):
            self._controls[key].bind(
                "<<ComboboxSelected>>",
                self._preset_selection_changed, add="+",
            )

    def _schedule_preview(self, *_args):
        if self._updating:
            return
        if self._preview_job is not None:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(60, self._update_preview)

    def _preset_selection_changed(self, event=None):
        if not self._updating:
            application_changed = (
                event is None
                or event.widget is self._controls["application_preset"]
            )
            if application_changed:
                self._motor_parameters_auto = True
                self.settings["motor_parameters_auto"] = True
            self._apply_selected_presets(
                manufacturing_only=not application_changed
            )

    def _preview_choice_changed(self, event=None):
        if self._updating:
            return
        widget = event.widget if event is not None else None
        controlled = {
            self._controls.get("spacing_mode"): (
                "spacing_mode", "spacing_mode"
            ),
            self._controls.get("motor_orientation"): (
                "motor_orientation", "motor_orientation"
            ),
        }
        if widget in controlled and self._motor_shape_active():
            key, field_key = controlled[widget]
            if self._application_is_custom():
                self._motor_parameters_auto = False
                self.settings["motor_parameters_auto"] = False
                self._refresh_motor_recommendation(apply=False)
            else:
                self._motor_parameters_auto = True
                self.settings["motor_parameters_auto"] = True
                self._refresh_motor_recommendation(
                    apply=True,
                    preserve_keys=(key,),
                    preserved_field=self.tr(field_key),
                )
        elif widget in (
                self._controls.get("coil_shape"),
                self._controls.get("motor_layout"),
                self._controls.get("layer_count")):
            self._refresh_motor_recommendation(
                apply=(self._motor_parameters_auto
                       or not self._application_is_custom()),
                update_preview=False,
            )
        else:
            self._refresh_motor_recommendation(apply=False)
        if self._preview_job is not None:
            self.root.after_cancel(self._preview_job)
            self._preview_job = None
        self._update_preview()
        self._update_navigation()

    def _apply_settings(self, values):
        self._motor_parameters_auto = bool(
            values.get("motor_parameters_auto", True)
        )
        self._updating = True
        try:
            for key, value in formatted_entry_settings(values).items():
                self.vars[key].set(value)
            for key in (
                    "application_preset", "manufacturing_preset",
                    "sizing_mode", "coil_shape", "primitive_mode",
                    "quality_preset", "spacing_mode", "direction",
                    "motor_layout", "motor_orientation",
                    "design_mode", "motor_connection"):
                self._set_choice(key, values[key])
            self._set_choice("net_name", values.get("net_name", ""))
            wanted_layer = values.get("layer_name", "F.Cu")
            layer_code = next(
                (code for code, name in self.layers if name == wanted_layer),
                self.layers[0][0] if self.layers else None,
            )
            self._set_choice("layer_code", layer_code)
            self._set_choice("layer_count", values.get("layer_count", 1))
            if values.get("application_preset", "custom") != "custom":
                self._motor_parameters_auto = True
                self.settings["motor_parameters_auto"] = True
            for key, variable in self.bool_vars.items():
                variable.set(bool(values[key]))
        finally:
            self._updating = False
        self._refresh_motor_recommendation(
            apply=False, update_preview=False,
        )
        self._apply_parameter_visibility()

    def _update_preset_summary(self, requested=None, actual=None):
        application = self._choice_code("application_preset", "custom")
        manufacturing = self._choice_code(
            "manufacturing_preset", "custom"
        )
        text = self.tr(
            "preset_summary",
            application=self.tr("application_" + application),
            manufacturing=self.tr("manufacturing_" + manufacturing),
            description=self.tr("preset_description_" + application),
        )
        if requested is not None and actual is not None and requested != actual:
            text += self.tr(
                "preset_layers_adjusted", requested=requested, actual=actual
            )
        self.preset_summary.set(text)

    def _apply_selected_presets(self, manufacturing_only=False):
        application = self._choice_code("application_preset", "custom")
        manufacturing = self._choice_code("manufacturing_preset", "custom")
        if manufacturing_only:
            values = {
                "application_preset": application,
                "manufacturing_preset": manufacturing,
            }
            values.update(MANUFACTURING_PRESETS.get(manufacturing, {}))
        else:
            values = build_preset_values(application, manufacturing)
        requested = values.get("layer_count")
        actual = requested
        self._updating = True
        try:
            for key, value in values.items():
                if key == "shape_taper_ratio":
                    self.vars["shape_taper_percent"].set(
                        _format_number(float(value) * 100.0)
                    )
                elif key in self.vars and key not in self._choice_maps:
                    if key == "fill_ratio":
                        continue
                    self.vars[key].set(_format_number(value))
                elif key in self._choice_maps:
                    self._set_choice(key, value)
                elif key in self.bool_vars:
                    self.bool_vars[key].set(bool(value))
            if "fill_ratio" in values:
                self.vars["fill_ratio_percent"].set(
                    _format_number(values["fill_ratio"] * 100.0)
                )
            quality_values = QUALITY_PRESETS.get(
                values.get("quality_preset")
            )
            if quality_values:
                self.vars["arcs_per_turn"].set(str(quality_values[0]))
                self.vars["segments_per_turn"].set(str(quality_values[1]))
            if requested is not None and self.layers:
                start = self._layer_index()
                actual = min(max(1, int(requested)), len(self.layers) - start)
                self._set_choice("layer_count", actual)
            self.settings.update(values)
            if actual is not None:
                self.settings["layer_count"] = actual
        finally:
            self._updating = False
        if "fill_ratio" not in values:
            self._apply_application_fill_recommendation()
        self._refresh_motor_recommendation(
            apply=(self._motor_parameters_auto
                   or not self._application_is_custom()),
            update_preview=False,
            preserve_keys=tuple(values),
        )
        self._update_preview()
        self._update_preset_summary(requested, actual)

    def _quality_changed(self, _event=None):
        quality = self._choice_code("quality_preset", "custom")
        values = QUALITY_PRESETS.get(quality)
        if values is not None:
            self._updating = True
            try:
                self.vars["arcs_per_turn"].set(str(values[0]))
                self.vars["segments_per_turn"].set(str(values[1]))
            finally:
                self._updating = False
        if not self._updating and self._motor_shape_active():
            if self._application_is_custom():
                self._motor_parameters_auto = False
                self.settings["motor_parameters_auto"] = False
                self._refresh_motor_recommendation(apply=False)
            else:
                self._refresh_motor_recommendation(
                    apply=True,
                    preserve_keys=("quality_preset",),
                    preserved_field=self.tr("quality_preset"),
                )
        self._update_preview()

    def _number(self, key, label_key):
        try:
            value = float(self.vars[key].get().strip())
        except (TypeError, ValueError):
            raise ValidationError(self.tr(
                "invalid_number", field=self.tr(label_key)
            ))
        if not isfinite(value):
            raise ValidationError(self.tr(
                "invalid_number", field=self.tr(label_key)
            ))
        return value

    def _integer(self, key, label_key):
        value = self._number(key, label_key)
        if not value.is_integer():
            raise ValidationError(self.tr(
                "invalid_number", field=self.tr(label_key)
            ))
        return int(value)

    def _layer_index(self):
        code = self._choice_code("layer_code")
        for index, (layer, _name) in enumerate(self.layers):
            if layer == code:
                return index
        return 0

    def _geometry_error(self, error):
        values = dict(error.values)
        for key in ("actual", "minimum"):
            if key in values:
                values[key] = _format_number(values[key])
        values.setdefault("unit", "mm")
        translated = self.tr(error.code, **values)
        return translated if translated != error.code else str(error)

    def _error_message(self, error):
        if isinstance(error, GeometryError):
            return self._geometry_error(error)
        return localize_error(self.tr, error)

    def _manufacturing_error_message(self, violation):
        return self.tr(
            violation["code"],
            process=self.tr("manufacturing_" + violation["process"]),
            actual=_format_number(violation["actual"]),
            minimum=_format_number(violation["minimum"]),
            unit="mm",
        )

    def _read_values(self):
        design_mode = self._choice_code("design_mode", "manual")
        sizing_mode = {
            "manual": "manual", "fit_turns": "fit_turns",
            "fit_length": "fit_length",
        }.get(design_mode, "fit_turns")
        coil_shape = self._choice_code("coil_shape", "circular")
        primitive_requested = self._choice_code("primitive_mode", "auto")
        primitive_mode = (
            "segment"
            if coil_shape != "circular" or primitive_requested == "segment"
            else "arc"
        )
        shape_aspect_ratio = self._number(
            "shape_aspect_ratio", "shape_aspect_ratio"
        )
        shape_taper_percent = self._number(
            "shape_taper_percent", "shape_taper_percent"
        )
        start_radius = self._number("start_radius_mm", "initial_radius")
        turns = self._number("turns", "turns")
        arcs_per_turn = self._integer("arcs_per_turn", "arcs_per_turn")
        segments_per_turn = self._integer(
            "segments_per_turn", "segments_per_turn"
        )
        additional = self._integer(
            "additional_segments", "additional_segments"
        )
        track_width = self._number("track_width_mm", "track_width")
        spacing = self._number("spacing_mm", "spacing")
        diameter = self._number(
            "available_diameter_mm", "available_diameter"
        )
        target_length = self._number("target_length_mm", "target_length")
        fill_percent = self._number("fill_ratio_percent", "fill_ratio")
        minimum_width = self._number(
            "minimum_track_width_mm", "minimum_track_width"
        )
        minimum_clearance = self._number(
            "minimum_clearance_mm", "minimum_clearance"
        )
        via_diameter = self._number("via_diameter_mm", "via_diameter")
        via_drill = self._number("via_drill_mm", "via_drill")
        via_clearance = self._number("via_clearance_mm", "via_clearance")
        copper_thickness = self._number(
            "copper_thickness_um", "copper_thickness"
        )
        target_current = self._number("target_current_a", "target_current")
        target_torque = self._number("target_torque_nm", "target_torque")
        target_force = self._number(
            "motor_target_force_n", "motor_target_force"
        )
        target_linear_speed = self._number(
            "motor_target_linear_speed_mps", "motor_target_linear_speed"
        )
        air_gap_flux_density = self._number(
            "air_gap_flux_density_t", "air_gap_flux_density"
        )
        electrical_loading = self._number(
            "electrical_loading_a_per_m", "electrical_loading"
        )
        winding_factor = self._number("winding_factor", "winding_factor")
        motor_inner_ratio = self._number(
            "motor_inner_ratio", "motor_inner_ratio"
        )
        motor_board_outer_diameter = self._number(
            "motor_board_outer_diameter_mm", "motor_board_outer_diameter"
        )
        motor_board_inner_diameter = self._number(
            "motor_board_inner_diameter_mm", "motor_board_inner_diameter"
        )
        motor_edge_clearance = self._number(
            "motor_edge_clearance_mm", "motor_edge_clearance"
        )
        motor_slot_gap = self._number("motor_slot_gap_mm", "motor_slot_gap")
        motor_supply_voltage = self._number(
            "motor_supply_voltage_v", "motor_supply_voltage"
        )
        motor_target_speed = self._number(
            "motor_target_speed_rpm", "motor_target_speed"
        )
        motor_max_phase_current = self._number(
            "motor_max_phase_current_a", "motor_max_phase_current"
        )
        allowed_temperature_rise = self._number(
            "allowed_temperature_rise_c", "allowed_temperature_rise"
        )
        target_resistance = self._number(
            "target_resistance_ohm", "target_resistance"
        )
        target_inductance = self._number(
            "target_inductance_uh", "target_inductance"
        )
        motor_connection = self._choice_code("motor_connection", "star")
        center_x = self._number("center_x_mm", "center_xy")
        center_y = self._number("center_y_mm", "center_xy")
        angle = self._number("angle_degrees", "angle_offset")
        motor_layout = self._choice_code("motor_layout", "single")
        motor_pole_pairs = self._integer("motor_pole_pairs", "motor_pole_pairs")
        motor_slot_count = self._integer("motor_slot_count", "motor_slot_count")
        motor_phase_count = self._integer(
            "motor_phase_count", "motor_phase_count"
        )
        motor_array_radius = self._number(
            "motor_array_radius_mm", "motor_array_radius"
        )
        motor_linear_pitch = self._number(
            "motor_linear_pitch_mm", "motor_linear_pitch"
        )
        motor_array_angle = self._number(
            "motor_array_angle_degrees", "motor_array_angle"
        )
        motor_orientation = self._choice_code("motor_orientation", "radial")
        spacing_mode = self._choice_code("spacing_mode", "pitch")
        layer_count = int(self._choice_code("layer_count", 1))
        if coil_shape == "motor_sector":
            diameter = motor_board_outer_diameter
            if motor_board_outer_diameter > 0.0:
                motor_inner_ratio = (
                    motor_board_inner_diameter / motor_board_outer_diameter
                )

        if shape_aspect_ratio < 1.0:
            raise ValidationError(self.tr(
                "must_be_at_least_one", field=self.tr("shape_aspect_ratio")
            ))
        if not -75.0 <= shape_taper_percent <= 75.0:
            raise ValidationError(self.tr(
                "shape_taper_out_of_range"
            ))
        if not self.layers:
            raise ValidationError(self.tr("no_layer"))
        layer_index = self._layer_index()
        selected_layers = self.layers[layer_index:layer_index + layer_count]
        if len(selected_layers) != layer_count:
            raise ValidationError(self.tr(
                "not_enough_layers", available=len(selected_layers),
                requested=layer_count, start=self.layers[layer_index][1],
            ))
        for value, field_key in (
                (start_radius, "initial_radius"),
                (additional, "additional_segments"),
                (minimum_width, "minimum_track_width"),
                (minimum_clearance, "minimum_clearance"),
                (target_current, "target_current"),
                (target_torque, "target_torque"),
                (motor_slot_count, "motor_slot_count")):
            if value < 0:
                raise ValidationError(self.tr(
                    "must_be_nonnegative", field=self.tr(field_key)
                ))
        for value, field_key in (
                (turns, "turns"),
                (copper_thickness, "copper_thickness")):
            if value <= 0:
                raise ValidationError(self.tr(
                    "must_be_positive", field=self.tr(field_key)
                ))
        if (air_gap_flux_density <= 0 or electrical_loading <= 0
                or not 0 < winding_factor <= 1
                or not 0 < motor_inner_ratio < 1
                or motor_phase_count not in (1, 3)):
            raise ValidationError(self.tr("motor_engineering_invalid"))
        if coil_shape == "motor_sector" and (
                motor_board_outer_diameter <= 0.0
                or motor_board_inner_diameter < 0.0
                or motor_board_inner_diameter >= motor_board_outer_diameter
                or motor_edge_clearance < 0.0 or motor_slot_gap < 0.0):
            raise ValidationError(self.tr("motor_sector_invalid"))
        if coil_shape.startswith("motor_") and (
                motor_supply_voltage <= 0.0 or motor_target_speed < 0.0
                or motor_max_phase_current <= 0.0
                or allowed_temperature_rise <= 0.0
                or target_resistance < 0.0 or target_inductance < 0.0):
            raise ValidationError(self.tr("motor_engineering_invalid"))
        if arcs_per_turn < 4:
            raise ValidationError(self.tr("arcs_per_turn_too_small"))
        if segments_per_turn < 4:
            raise ValidationError(self.tr("segments_too_small"))
        if layer_count > 1:
            if via_diameter <= 0:
                raise ValidationError(self.tr(
                    "must_be_positive", field=self.tr("via_diameter")
                ))
            if via_drill <= 0:
                raise ValidationError(self.tr(
                    "must_be_positive", field=self.tr("via_drill")
                ))
            if via_drill >= via_diameter:
                raise ValidationError(self.tr("via_drill_too_large"))
            if via_clearance < 0:
                raise ValidationError(self.tr(
                    "must_be_nonnegative", field=self.tr("via_clearance")
                ))
        if sizing_mode == "manual":
            if track_width <= 0:
                raise ValidationError(self.tr(
                    "must_be_positive", field=self.tr("track_width")
                ))
            if spacing < 0 or (spacing_mode == "pitch" and spacing == 0):
                raise ValidationError(self.tr(
                    "must_be_positive", field=self.tr("spacing")
                ))
            if spacing_mode == "pitch" and spacing < track_width:
                raise ValidationError(self.tr("pitch_smaller_than_width"))
        else:
            if diameter <= 0:
                raise ValidationError(self.tr("available_diameter_invalid"))
            if not 0 < fill_percent < 100:
                raise ValidationError(self.tr("fill_ratio_invalid"))
            if sizing_mode == "fit_length" and target_length <= 0:
                raise ValidationError(self.tr("target_length_invalid"))

        solver_result = None
        try:
            if (coil_shape.startswith("motor_") and design_mode in (
                    "motor_target", "target_resistance",
                    "target_inductance", "target_current")):
                fixed = self._workflow.fixed_values()
                if "spacing_mm" in fixed:
                    spacing_value = float(fixed["spacing_mm"])
                    fixed["clearance_mm"] = (
                        max(0.0, spacing_value - float(
                            fixed.get("track_width_mm", track_width)
                        )) if spacing_mode == "pitch" else spacing_value
                    )
                if coil_shape == "motor_sector":
                    solver_result = solve_motor_sector_design(
                        board_outer_diameter_mm=motor_board_outer_diameter,
                        board_inner_diameter_mm=motor_board_inner_diameter,
                        pole_pairs=motor_pole_pairs,
                        slot_count=motor_slot_count,
                        phase_count=motor_phase_count,
                        layer_count=layer_count,
                        supply_voltage_v=motor_supply_voltage,
                        target_speed_rpm=motor_target_speed,
                        target_torque_nm=target_torque,
                        max_phase_current_a=(
                            target_current if design_mode == "target_current"
                            and target_current > 0.0
                            else motor_max_phase_current
                        ),
                        copper_thickness_um=copper_thickness,
                        minimum_track_width_mm=minimum_width,
                        minimum_clearance_mm=minimum_clearance,
                        flux_density_t=air_gap_flux_density,
                        winding_factor=winding_factor,
                        connection=motor_connection,
                        edge_clearance_mm=motor_edge_clearance,
                        slot_gap_mm=motor_slot_gap,
                        fill_ratio=fill_percent / 100.0,
                        target_resistance_ohm=(
                            target_resistance
                            if design_mode == "target_resistance" else 0.0
                        ),
                        target_inductance_uh=(
                            target_inductance
                            if design_mode == "target_inductance" else 0.0
                        ),
                        allowed_temperature_rise_c=allowed_temperature_rise,
                        fixed=fixed,
                    )
                else:
                    solver_result = solve_motor_spiral_design(
                        available_diameter_mm=diameter,
                        start_radius_mm=start_radius,
                        coil_shape=coil_shape,
                        shape_aspect_ratio=shape_aspect_ratio,
                        shape_taper_ratio=shape_taper_percent / 100.0,
                        motor_layout=motor_layout,
                        pole_pairs=motor_pole_pairs,
                        slot_count=motor_slot_count,
                        phase_count=motor_phase_count,
                        motor_orientation=motor_orientation,
                        motor_array_radius_mm=motor_array_radius,
                        motor_linear_pitch_mm=motor_linear_pitch,
                        layer_count=layer_count,
                        supply_voltage_v=motor_supply_voltage,
                        target_speed_rpm=motor_target_speed,
                        target_torque_nm=target_torque,
                        max_phase_current_a=(
                            target_current if design_mode == "target_current"
                            and target_current > 0.0
                            else motor_max_phase_current
                        ),
                        copper_thickness_um=copper_thickness,
                        minimum_track_width_mm=minimum_width,
                        minimum_clearance_mm=minimum_clearance,
                        via_diameter_mm=via_diameter,
                        via_clearance_mm=via_clearance,
                        flux_density_t=air_gap_flux_density,
                        winding_factor=winding_factor,
                        connection=motor_connection,
                        fill_ratio=fill_percent / 100.0,
                        target_resistance_ohm=(
                            target_resistance
                            if design_mode == "target_resistance" else 0.0
                        ),
                        target_inductance_uh=(
                            target_inductance
                            if design_mode == "target_inductance" else 0.0
                        ),
                        allowed_temperature_rise_c=allowed_temperature_rise,
                        fixed=fixed,
                        target_force_n=target_force,
                        target_linear_speed_mps=target_linear_speed,
                    )
                if not solver_result["feasible"]:
                    raise GeometryError(
                        "motor_target_constraints_unmet",
                        required_voltage=solver_result[
                            "required_line_voltage_v"
                        ],
                        available_voltage=solver_result[
                            "available_line_voltage_rms_v"
                        ],
                        required_current=solver_result[
                            "required_phase_current_a"
                        ],
                        available_current=solver_result[
                            "effective_phase_current_limit_a"
                        ],
                    )
                resolved = solver_result["resolved"]
                arrangement = solver_result["arrangement"]
                resolved["motor_target"] = solver_result
            elif coil_shape == "circular" and design_mode in (
                    "target_resistance", "target_inductance",
                    "target_current"):
                electrical_target = solve_spiral_electrical_design(
                    design_mode=design_mode,
                    available_diameter_mm=diameter,
                    start_radius_mm=start_radius,
                    layer_count=layer_count,
                    copper_thickness_um=copper_thickness,
                    minimum_track_width_mm=minimum_width,
                    minimum_clearance_mm=minimum_clearance,
                    fill_ratio=fill_percent / 100.0,
                    target_resistance_ohm=target_resistance,
                    target_inductance_uh=target_inductance,
                    target_current_a=target_current,
                    allowed_temperature_rise_c=allowed_temperature_rise,
                    via_diameter_mm=via_diameter,
                    via_clearance_mm=via_clearance,
                    fixed=self._workflow.fixed_values(),
                )
                if not electrical_target["feasible"]:
                    raise GeometryError(
                        "electrical_target_constraints_unmet",
                        required_current=electrical_target["current_target_a"],
                        available_current=electrical_target[
                            "current_capacity_a"
                        ],
                    )
                resolved = electrical_target["resolved"]
                resolved["electrical_target"] = electrical_target
                arrangement = {
                    "layout": "single", "count": 1,
                    "array_radius": 0.0, "linear_pitch": 0.0,
                }
            else:
                resolved, arrangement = resolve_motor_spiral_parameters(
                    sizing_mode=sizing_mode,
                    start_radius=start_radius,
                    turns=turns,
                    track_width=track_width,
                    spacing=spacing,
                    spacing_mode=spacing_mode,
                    available_diameter=diameter,
                    target_length=target_length,
                    fill_ratio=fill_percent / 100.0,
                    layer_count=layer_count,
                    via_diameter=via_diameter,
                    via_clearance=via_clearance,
                    minimum_track_width=minimum_width,
                    minimum_clearance=minimum_clearance,
                    coil_shape=coil_shape,
                    shape_aspect_ratio=shape_aspect_ratio,
                    shape_taper_ratio=shape_taper_percent / 100.0,
                    motor_layout=motor_layout,
                    motor_pole_pairs=motor_pole_pairs,
                    motor_orientation=motor_orientation,
                    motor_array_radius=motor_array_radius,
                    motor_linear_pitch=motor_linear_pitch,
                    motor_slot_count=motor_slot_count,
                    motor_inner_ratio=motor_inner_ratio,
                    motor_edge_clearance=motor_edge_clearance,
                    motor_slot_gap=motor_slot_gap,
                )
        except GeometryError as error:
            raise ValidationError(self._geometry_error(error))

        turns = resolved["turns"]
        track_width = resolved["track_width"]
        start_radius = resolved["start_radius"]
        spacing = (
            resolved["pitch"]
            if spacing_mode == "pitch"
            else resolved["clearance"]
        )
        violation = manufacturing_violation(
            self._choice_code("manufacturing_preset", "custom"),
            resolved["track_width"], resolved["clearance"],
            layer_count, via_diameter, via_drill, via_clearance,
        )
        if violation is not None:
            raise ValidationError(
                self._manufacturing_error_message(violation)
            )
        if layer_count > 1:
            if not float(turns).is_integer() or additional != 0:
                raise ValidationError(self.tr("multilayer_integer_turns"))
            if coil_shape != "motor_sector":
                required = required_inner_radius(
                    layer_count, via_diameter, via_clearance, track_width
                ) / shape_endpoint_scale(
                    coil_shape, shape_aspect_ratio,
                    shape_taper_percent / 100.0,
                )
                if start_radius + 1e-9 < required:
                    raise ValidationError(self.tr(
                        "inner_radius_too_small",
                        required=_format_number(required), unit="mm",
                    ))

        motor_count = arrangement["count"]
        resolved["motor_count"] = motor_count
        resolved["motor_layout"] = arrangement["layout"]
        resolved["motor_array_radius_mm"] = arrangement["array_radius"]
        resolved["motor_linear_pitch_mm"] = arrangement["linear_pitch"]
        if (arrangement["layout"] == "radial"
                and motor_orientation == "radial"):
            if coil_shape == "motor_sector":
                outer_radius_mm = (
                    resolved["motor_board_outer_diameter"] / 2.0
                )
                inner_radius_mm = (
                    resolved["motor_board_inner_diameter"] / 2.0
                )
            else:
                half_span_mm = resolved["outer_diameter"] / 2.0
                outer_radius_mm = arrangement["array_radius"] + half_span_mm
                inner_radius_mm = arrangement["array_radius"] - half_span_mm
            if inner_radius_mm > 0.0:
                dfm = motor_inner_trace_dfm(
                    inner_radius_mm, motor_pole_pairs, turns,
                    resolved["track_width"], resolved["clearance"],
                    outer_radius_mm,
                )
                resolved["motor_engineering"] = {
                    "outer_radius_mm": outer_radius_mm,
                    "inner_radius_mm": inner_radius_mm,
                    "inner_ratio": inner_radius_mm / outer_radius_mm,
                    "estimated_torque_nm": estimate_axial_flux_motor_torque(
                        outer_radius_mm, inner_radius_mm,
                        air_gap_flux_density, electrical_loading,
                        winding_factor,
                    ),
                    "dfm": dfm,
                    "phase_balanced": motor_count % motor_phase_count == 0,
                }
        resolved["total_spiral_length"] *= motor_count
        primitives_per_turn = (
            arcs_per_turn if primitive_mode == "arc" else segments_per_turn
        )
        count = motor_count * multilayer_track_count(
            turns, primitives_per_turn, additional, layer_count
        )
        limit = int(self.settings.get("max_segments", DEFAULTS["max_segments"]))
        if count > limit:
            raise ValidationError(self.tr(
                "too_many_segments", count=count, limit=limit
            ))
        electrical = estimate_dc_metrics(
            resolved["total_spiral_length"], track_width,
            copper_thickness, target_current,
        )
        net_name = self._choice_code("net_name", "")
        net = next(
            (item for name, item in self.net_items if name == net_name), None
        )
        values = {
            "schema_version": DEFAULTS["schema_version"],
            "application_preset": self._choice_code(
                "application_preset", "custom"
            ),
            "manufacturing_preset": self._choice_code(
                "manufacturing_preset", "custom"
            ),
            "group_name": self.vars["group_name"].get().strip() or "spiral",
            "net_name": net_name,
            "layer_name": selected_layers[0][1],
            "layer_count": layer_count,
            "center_x_mm": center_x,
            "center_y_mm": center_y,
            "start_radius_mm": start_radius,
            "coil_shape": coil_shape,
            "shape_aspect_ratio": shape_aspect_ratio,
            "shape_taper_ratio": shape_taper_percent / 100.0,
            "motor_layout": arrangement["layout"],
            "motor_pole_pairs": motor_pole_pairs,
            "motor_slot_count": motor_slot_count,
            "motor_phase_count": motor_phase_count,
            "motor_array_radius_mm": arrangement["array_radius"],
            "motor_linear_pitch_mm": arrangement["linear_pitch"],
            "motor_array_angle_degrees": motor_array_angle,
            "motor_orientation": motor_orientation,
            "motor_alternate_winding": self.bool_vars[
                "motor_alternate_winding"
            ].get(),
            "motor_parameters_auto": self._motor_parameters_auto,
            "turns": turns,
            "arcs_per_turn": arcs_per_turn,
            "segments_per_turn": segments_per_turn,
            "additional_segments": additional,
            "primitive_mode": primitive_requested,
            "quality_preset": self._choice_code(
                "quality_preset", "custom"
            ),
            "sizing_mode": sizing_mode,
            "design_mode": design_mode,
            "available_diameter_mm": diameter,
            "target_length_mm": target_length,
            "fill_ratio": fill_percent / 100.0,
            "minimum_track_width_mm": minimum_width,
            "minimum_clearance_mm": minimum_clearance,
            "copper_thickness_um": copper_thickness,
            "target_current_a": target_current,
            "target_torque_nm": target_torque,
            "motor_target_force_n": target_force,
            "motor_target_linear_speed_mps": target_linear_speed,
            "air_gap_flux_density_t": air_gap_flux_density,
            "electrical_loading_a_per_m": electrical_loading,
            "winding_factor": winding_factor,
            "motor_inner_ratio": motor_inner_ratio,
            "motor_board_outer_diameter_mm": resolved.get(
                "motor_board_outer_diameter", diameter
            ),
            "motor_board_inner_diameter_mm": resolved.get(
                "motor_board_inner_diameter", diameter * motor_inner_ratio
            ),
            "motor_edge_clearance_mm": motor_edge_clearance,
            "motor_slot_gap_mm": motor_slot_gap,
            "motor_supply_voltage_v": motor_supply_voltage,
            "motor_target_speed_rpm": motor_target_speed,
            "motor_max_phase_current_a": motor_max_phase_current,
            "allowed_temperature_rise_c": allowed_temperature_rise,
            "motor_connection": motor_connection,
            "target_resistance_ohm": target_resistance,
            "target_inductance_uh": target_inductance,
            "show_advanced_parameters": self.bool_vars[
                "show_advanced_parameters"
            ].get(),
            "track_width_mm": track_width,
            "spacing_mm": spacing,
            "via_diameter_mm": via_diameter,
            "via_drill_mm": via_drill,
            "via_clearance_mm": via_clearance,
            "spacing_mode": spacing_mode,
            "angle_degrees": angle,
            "angle_unit": "degrees",
            "direction": self._choice_code("direction", "clockwise"),
            "create_group": self.bool_vars["create_group"].get(),
            "close_after_create": self.bool_vars["close_after_create"].get(),
            "max_segments": limit,
        }
        return (
            values, resolved, electrical, count,
            [layer for layer, _name in selected_layers], net, primitive_mode,
        )

    def _draft_preview_values(self):
        draft = dict(self.settings)
        for key in (
                "start_radius_mm", "turns", "track_width_mm",
                "spacing_mm", "segments_per_turn", "additional_segments",
                "shape_aspect_ratio", "angle_degrees", "motor_pole_pairs",
                "motor_slot_count", "motor_phase_count",
                "motor_array_radius_mm", "motor_linear_pitch_mm",
                "motor_array_angle_degrees",
                "motor_board_outer_diameter_mm",
                "motor_board_inner_diameter_mm", "motor_edge_clearance_mm",
                "motor_slot_gap_mm", "motor_supply_voltage_v",
                "motor_target_speed_rpm", "motor_max_phase_current_a",
                "motor_target_force_n", "motor_target_linear_speed_mps",
                "target_resistance_ohm", "target_inductance_uh",
                "via_diameter_mm", "via_clearance_mm"):
            variable = self.vars.get(key)
            if variable is not None:
                draft[key] = variable.get()
        try:
            draft["shape_taper_ratio"] = (
                float(self.vars["shape_taper_percent"].get()) / 100.0
            )
        except (TypeError, ValueError):
            pass
        draft.update({
            "coil_shape": self._choice_code("coil_shape", "circular"),
            "design_mode": self._choice_code("design_mode", "manual"),
            "layer_count": self._choice_code("layer_count", 1),
            "direction": self._choice_code("direction", "clockwise"),
            "spacing_mode": self._choice_code("spacing_mode", "pitch"),
            "motor_layout": self._choice_code("motor_layout", "single"),
            "motor_orientation": self._choice_code(
                "motor_orientation", "radial"
            ),
            "motor_alternate_winding": self.bool_vars[
                "motor_alternate_winding"
            ].get(),
        })
        return coerce_preview_values(draft, self.settings)

    def _refresh_states(self):
        design_mode = self._choice_code("design_mode", "manual")
        mode = {
            "manual": "manual", "fit_turns": "fit_turns",
            "fit_length": "fit_length",
        }.get(design_mode, "fit_turns")
        manual = mode == "manual"
        states = {
            "turns": mode != "fit_length",
            "track_width_mm": manual,
            "spacing_mm": manual,
            "spacing_mode": manual,
            "available_diameter_mm": not manual,
            "target_length_mm": mode == "fit_length",
            "fill_ratio_percent": not manual,
            "minimum_track_width_mm": not manual,
            "minimum_clearance_mm": not manual,
        }
        coil_shape = self._choice_code("coil_shape", "circular")
        motor_shape = coil_shape != "circular"
        if motor_shape and self._choice_code("primitive_mode", "auto") != "segment":
            previous_updating = self._updating
            self._updating = True
            try:
                self._set_choice("primitive_mode", "segment")
            finally:
                self._updating = previous_updating
        primitive = self._choice_code("primitive_mode", "auto")
        states["coil_shape"] = True
        for key in (
                "target_torque_nm", "motor_target_force_n",
            "motor_target_linear_speed_mps", "air_gap_flux_density_t",
                "electrical_loading_a_per_m", "winding_factor",
                "motor_inner_ratio"):
            states[key] = motor_shape
        states["shape_aspect_ratio"] = motor_shape
        states["shape_taper_percent"] = coil_shape == "motor_trapezoid"
        layout = self._choice_code("motor_layout", "single")
        arranged = motor_shape and layout in ("radial", "linear")
        states["motor_layout"] = motor_shape
        states["motor_pole_pairs"] = arranged
        states["motor_slot_count"] = arranged
        states["motor_phase_count"] = arranged
        states["motor_array_radius_mm"] = motor_shape and layout == "radial"
        states["motor_linear_pitch_mm"] = motor_shape and layout == "linear"
        states["motor_array_angle_degrees"] = arranged
        states["motor_orientation"] = arranged
        states["motor_alternate_winding"] = arranged
        states["primitive_mode"] = not motor_shape
        states["arcs_per_turn"] = not motor_shape and primitive != "segment"
        states["segments_per_turn"] = motor_shape or primitive == "segment"
        multilayer = int(self._choice_code("layer_count", 1)) > 1
        for key in ("via_diameter_mm", "via_drill_mm", "via_clearance_mm"):
            states[key] = multilayer
        for key, enabled in states.items():
            control = self._controls.get(key)
            if control is None:
                continue
            if isinstance(control, ttk.Combobox):
                control.configure(state="readonly" if enabled else "disabled")
            else:
                control.configure(state="normal" if enabled else "disabled")
        self._apply_parameter_visibility()

    def _apply_resolved_to_controls(self, values):
        if values["sizing_mode"] == "manual":
            return
        self._updating = True
        try:
            self.vars["start_radius_mm"].set(_format_number(
                values["start_radius_mm"]
            ))
            self.vars["turns"].set(_format_number(values["turns"]))
            self.vars["shape_aspect_ratio"].set(_format_number(
                values["shape_aspect_ratio"]
            ))
            self.vars["shape_taper_percent"].set(_format_number(
                values["shape_taper_ratio"] * 100.0
            ))
            self.vars["track_width_mm"].set(_format_number(
                values["track_width_mm"]
            ))
            self.vars["spacing_mm"].set(_format_number(
                values["spacing_mm"]
            ))
        finally:
            self._updating = False

    def _update_preview(self):
        self._preview_job = None
        self._refresh_states()
        preview_scene = build_safe_preview_scene(
            self._draft_preview_values()
        )
        self._update_preset_summary()
        try:
            values, resolved, electrical, count, layers, _net, primitive = (
                self._read_values()
            )
            key = (
                "resolved_manual"
                if values["sizing_mode"] == "manual"
                else "resolved_auto"
            )
            self.result_summary.set(self.tr(
                key,
                turns=_format_number(resolved["turns"]),
                width=_format_number(resolved["track_width"]),
                clearance=_format_number(resolved["clearance"]),
                diameter=_format_number(resolved.get(
                    "array_outer_diameter", resolved["outer_diameter"]
                )),
                length=_format_number(resolved["total_spiral_length"]),
                unit="mm",
            ))
            electrical_text = self.tr(
                "electrical_estimate",
                resistance=_format_number(electrical["resistance_ohm"]),
                current=_format_number(values["target_current_a"]),
                voltage=_format_number(electrical["voltage_drop_v"]),
                power=_format_number(electrical["power_w"]),
            )
            motor_target = resolved.get("motor_target")
            if motor_target:
                electrical_text = self.tr(
                    "motor_target_estimate",
                    turns=_format_number(motor_target["turns_per_slot"]),
                    emf=_format_number(motor_target["back_emf_line_v"]),
                    voltage=_format_number(
                        motor_target["required_line_voltage_v"]
                    ),
                    available_voltage=_format_number(
                        motor_target["available_line_voltage_rms_v"]
                    ),
                    current=_format_number(
                        motor_target["required_phase_current_a"]
                    ),
                    available_current=_format_number(
                        motor_target["effective_phase_current_limit_a"]
                    ),
                    resistance=_format_number(
                        motor_target["phase_resistance_ohm"]
                    ),
                    hot_resistance=_format_number(
                        motor_target["phase_resistance_hot_ohm"]
                    ),
                    inductance=_format_number(
                        motor_target["phase_inductance_uh"]
                    ),
                    loss=_format_number(motor_target["copper_loss_w"]),
                )
            engineering = resolved.get("motor_engineering")
            if engineering:
                dfm = engineering["dfm"]
                ratio_ok = 0.55 <= engineering["inner_ratio"] <= 0.62
                status = self.tr(
                    "motor_engineering_ok"
                    if dfm["passes"] and ratio_ok
                    and engineering["phase_balanced"]
                    else "motor_engineering_warning"
                )
                electrical_text += "\n" + self.tr(
                    "motor_engineering_estimate",
                    outer=_format_number(2.0 * engineering["outer_radius_mm"]),
                    inner=_format_number(2.0 * engineering["inner_radius_mm"]),
                    ratio=_format_number(engineering["inner_ratio"]),
                    torque=_format_number(engineering["estimated_torque_nm"]),
                    usage=_format_number(dfm["utilization"] * 100.0),
                    max_turns=dfm["maximum_turns_per_layer"],
                    outer_width=_format_number(
                        dfm["recommended_outer_width_mm"]
                    ), unit="mm", status=status,
                )
            self.electrical_summary.set(electrical_text)
            if values["application_preset"] != "custom":
                self._apply_resolved_to_controls(values)
            self.object_summary.set(self.tr(
                "estimated_objects", count=count, layers=len(layers),
                vias=max(0, len(layers) - 1) * int(
                    resolved.get("motor_count", 1)
                ),
                primitive=self.tr(
                    "primitive_label_arcs"
                    if primitive == "arc"
                    else "primitive_label_segments"
                ),
            ))
            preview_scene = build_preview_scene(values)
            self._set_validation_feedback(
                self.tr("validation_ready"), True
            )
        except Exception as error:
            self._set_validation_feedback(
                self.tr("validation_issue", error=self._error_message(error)),
                False,
            )
            self.result_summary.set("—")
            self.electrical_summary.set(self.tr("electrical_unavailable"))
            self.object_summary.set("—")
        self._set_preview_scene(preview_scene)

    def _use_selection_center(self):
        center = self.backend.selected_center_mm()
        if center is None:
            messagebox.showinfo(
                self.root.title(), self.tr("selection_not_found"),
                parent=self.root,
            )
            return
        self.vars["center_x_mm"].set(_format_number(center[0]))
        self.vars["center_y_mm"].set(_format_number(center[1]))

    def _reset(self):
        self.settings = dict(DEFAULTS)
        self._apply_settings(self.settings)
        self._update_preset_summary()
        self._update_preview()

    def _create(self):
        self.create_button.configure(state="disabled")
        self.root.update_idletasks()
        try:
            values, resolved, _electrical, count, layers, net, primitive = (
                self._read_values()
            )
            created = self.backend.create_spiral(
                values, layers, net, primitive
            )
            self.store.save(values)
            self.settings = values
        except Exception as error:
            messagebox.showerror(
                self.root.title(),
                self.tr("create_failed", error=self._error_message(error)),
                parent=self.root,
            )
            self.create_button.configure(state="normal")
            return
        messagebox.showinfo(
            self.root.title(),
            self.tr(
                "success_generated_multilayer"
                if len(layers) > 1
                else "success_generated",
                layers=len(layers), count=count,
                vias=(max(0, len(layers) - 1)
                      * int(resolved.get("motor_count", 1))),
                primitive=self.tr(
                    "primitive_label_arcs"
                    if primitive == "arc"
                    else "primitive_label_segments"
                ),
            ),
            parent=self.root,
        )
        if values["close_after_create"]:
            self.root.destroy()
        else:
            self._update_preview()

    def run(self):
        self.root.mainloop()
