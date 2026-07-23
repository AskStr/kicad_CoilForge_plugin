import ast
from pathlib import Path
import unittest

from coilforge.ui_layout import (
    WORKSPACE_MAIN_WEIGHT, WORKSPACE_SIDEBAR_WEIGHT,
    centered_geometry, fitted_window_size, workspace_main_width,
)


class UiLayoutTests(unittest.TestCase):
    def test_legacy_parameter_grid_uses_two_stacked_fields_per_row(self):
        source = Path(__file__).resolve().parents[1] / "coilforge" / "interface.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        grid = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_grid"
        )
        self.assertEqual(2, grid.args.defaults[0].value)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "_grid" or not node.args:
                continue
            self.assertNotEqual(6, getattr(node.args[0], "value", None))

    def test_parameter_pages_do_not_show_scrollbars(self):
        project_root = Path(__file__).resolve().parents[1]
        legacy_source = (project_root / "coilforge" / "interface.py").read_text(
            encoding="utf-8"
        )
        legacy_tree = ast.parse(legacy_source)
        add_page = next(
            node for node in ast.walk(legacy_tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_add_page"
        )
        self.assertFalse(any(
            isinstance(node, ast.Attribute)
            and node.attr == "ScrolledWindow"
            for node in ast.walk(add_page)
        ))
        ipc_source = (project_root / "coilforge" / "ipc_ui.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("vertical_scroll.grid", ipc_source)
        self.assertNotIn("horizontal_scroll.grid", ipc_source)

    def test_wx_controls_follow_the_scenario_workflow(self):
        source = Path(__file__).resolve().parents[1] / "coilforge" / "interface.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }

        def assigned_attributes(function_name):
            names = set()
            for node in ast.walk(functions[function_name]):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"):
                        names.add(target.attr)
            return names

        process = assigned_attributes("_build_board_section")
        sizing = assigned_attributes("_build_sizing_section")
        geometry = assigned_attributes("_build_geometry_section")
        placement = assigned_attributes("_build_placement_section")
        layers = assigned_attributes("_build_multilayer_section")
        options = assigned_attributes("_build_options_section")
        self.assertTrue({
            "manufacturing_preset_choice", "copper_thickness",
            "minimum_track_width", "minimum_clearance",
        }.issubset(process))
        self.assertTrue({
            "sizing_mode_choice", "available_diameter", "turns",
            "target_length", "fill_ratio", "start_radius",
            "track_width", "spacing", "spacing_mode_choice",
            "motor_board_outer_diameter", "motor_board_inner_diameter",
            "target_resistance", "target_inductance",
        }.issubset(sizing))
        self.assertTrue({
            "coil_shape_choice", "shape_aspect_ratio", "shape_taper",
            "angle_offset", "direction_choice",
        }.issubset(geometry))
        self.assertTrue({
            "motor_layout_choice", "motor_pole_pairs", "motor_slot_count",
            "motor_phase_count", "motor_edge_clearance", "motor_slot_gap",
        }.issubset(placement))
        self.assertTrue({
            "net_choice", "layer_choice", "layer_count_choice",
            "via_diameter", "via_drill", "via_clearance",
        }.issubset(layers))
        self.assertTrue({
            "group_name", "primitive_mode_choice", "quality_preset_choice",
            "arcs_per_turn", "segments_per_turn", "additional_segments",
            "center_x", "center_y",
        }.issubset(options))

    def test_wx_workspace_uses_a_locked_sixty_five_thirty_five_split(self):
        source = Path(__file__).resolve().parents[1] / "coilforge" / "interface.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        init_calls = [
            node for node in ast.walk(functions["__init__"])
            if isinstance(node, ast.Call)
        ]
        self.assertTrue(any(
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "SplitterWindow"
            for node in init_calls
        ))
        layout_calls = [
            node for node in ast.walk(functions["_layout_workspace_split"])
            if isinstance(node, ast.Call)
        ]
        self.assertTrue(any(
            isinstance(node.func, ast.Name)
            and node.func.id == "workspace_main_width"
            for node in layout_calls
        ))
        self.assertIn("SP_NOSASH", source.read_text(encoding="utf-8"))

    def test_tk_preview_sidebar_keeps_thirty_five_percent_width(self):
        source = Path(__file__).resolve().parents[1] / "coilforge" / "ipc_ui.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        build_ui = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_build_ui"
        )
        columns = {}
        for node in ast.walk(build_ui):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if not (
                    isinstance(function, ast.Attribute)
                    and function.attr == "columnconfigure"
                    and isinstance(function.value, ast.Name)
                    and function.value.id == "workspace"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)):
                continue
            columns[node.args[0].value] = {
                keyword.arg: keyword.value
                for keyword in node.keywords
            }

        self.assertEqual(
            "WORKSPACE_MAIN_WEIGHT", columns[0]["weight"].id
        )
        self.assertEqual(
            "WORKSPACE_SIDEBAR_WEIGHT", columns[1]["weight"].id
        )
        self.assertEqual(
            columns[0]["uniform"].value, columns[1]["uniform"].value
        )
        self.assertNotIn("minsize", columns[1])
        self.assertEqual(35, WORKSPACE_SIDEBAR_WEIGHT)
        self.assertEqual(65, WORKSPACE_MAIN_WEIGHT)

    def test_tk_controls_follow_the_scenario_workflow(self):
        source = Path(__file__).resolve().parents[1] / "coilforge" / "ipc_ui.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        build_ui = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_build_ui"
        )
        placements = set()
        for node in ast.walk(build_ui):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in ("_add_entry", "_add_choice"):
                continue
            if len(node.args) < 4:
                continue
            page, key = node.args[0], node.args[3]
            if isinstance(page, ast.Name) and isinstance(key, ast.Constant):
                placements.add((page.id, key.value))
        self.assertIn(("board", "manufacturing_preset"), placements)
        self.assertIn(("board", "minimum_track_width"), placements)
        self.assertIn(("sizing", "turns"), placements)
        self.assertIn(("sizing", "initial_radius"), placements)
        self.assertIn(("sizing", "track_width"), placements)
        self.assertIn(("geometry", "coil_shape"), placements)
        self.assertIn(("placement", "motor_layout"), placements)
        self.assertIn(("options", "center_x"), placements)
        self.assertIn(("multilayer", "net_name"), placements)
        self.assertIn(("multilayer", "via_diameter"), placements)
        self.assertIn(("options", "group_name"), placements)
        self.assertIn(("options", "primitive_mode"), placements)
        self.assertIn(("options", "quality_preset"), placements)
        self.assertIn(("options", "additional_segments"), placements)

    def test_workspace_widths_stay_at_sixty_five_thirty_five(self):
        self.assertEqual(650, workspace_main_width(1000))
        self.assertEqual(350, 1000 - workspace_main_width(1000))

    def test_preferred_size_is_used_on_large_display(self):
        self.assertEqual((1360, 880, 1040, 680), fitted_window_size(1920, 1080))

    def test_window_and_minimum_are_clamped_on_small_display(self):
        self.assertEqual((768, 528, 768, 528), fitted_window_size(800, 600))

    def test_tiny_display_never_produces_nonpositive_dimensions(self):
        width, height, min_width, min_height = fitted_window_size(20, 20)
        self.assertGreaterEqual(width, 1)
        self.assertGreaterEqual(height, 1)
        self.assertLessEqual(min_width, width)
        self.assertLessEqual(min_height, height)

    def test_centered_geometry_stays_on_screen(self):
        self.assertEqual("1360x880+280+100", centered_geometry(
            1360, 880, 1920, 1080
        ))


if __name__ == "__main__":
    unittest.main()



