import math
import unittest

from coilforge.ipc_backend import IpcBoardBackend, mm_to_nm, nm_to_mm
from kipy.proto.board.board_types_pb2 import BoardLayer, ViaType


class FakeVersion(object):
    major = 10
    minor = 99
    patch = 0
    full_version = "10.99.0-test"


class FakeBoard(object):
    def __init__(self):
        self.created_batches = []
        self.pushed = []
        self.dropped = []

    def begin_commit(self):
        return object()

    def create_items(self, items):
        batch = list(items) if not hasattr(items, "proto") else [items]
        self.created_batches.append(batch)
        return batch

    def push_commit(self, commit, message):
        self.pushed.append((commit, message))

    def drop_commit(self, commit):
        self.dropped.append(commit)

    def get_nets(self):
        return []

    def get_enabled_layers(self):
        return [BoardLayer.BL_F_Cu, BoardLayer.BL_B_Cu]

    def get_selection(self):
        return []


class FakeKiCad(object):
    def __init__(self):
        self.board = FakeBoard()

    def get_board(self):
        return self.board

    def get_version(self):
        return FakeVersion()

    @staticmethod
    def get_plugin_settings_path(_identifier):
        return "/tmp/coilforge"


class IpcBackendTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeKiCad()
        self.backend = IpcBoardBackend(self.client)
        self.values = {
            "center_x_mm": 0.0,
            "center_y_mm": 0.0,
            "start_radius_mm": 1.0,
            "track_width_mm": 0.25,
            "spacing_mm": 0.5,
            "spacing_mode": "pitch",
            "turns": 1.0,
            "arcs_per_turn": 8,
            "segments_per_turn": 32,
            "additional_segments": 0,
            "coil_shape": "circular",
            "shape_aspect_ratio": 1.6,
            "shape_taper_ratio": 0.45,
            "angle_degrees": 0.0,
            "direction": "clockwise",
            "via_diameter_mm": 0.8,
            "via_drill_mm": 0.4,
            "via_clearance_mm": 0.25,
            "create_group": False,
            "group_name": "spiral",
        }

    def test_unit_conversion_uses_ipc_nanometers(self):
        self.assertEqual(1250000, mm_to_nm(1.25))
        self.assertEqual(1.25, nm_to_mm(1250000))

    def test_single_layer_arc_coil_is_one_commit(self):
        created = self.backend.create_spiral(
            self.values, [BoardLayer.BL_F_Cu], None, "arc"
        )
        self.assertEqual(8, len(created))
        self.assertEqual(1, len(self.client.board.created_batches))
        self.assertEqual(1, len(self.client.board.pushed))
        self.assertFalse(self.client.board.dropped)

    def test_motor_ellipse_uses_shaped_segment_geometry(self):
        values = dict(self.values)
        values.update({
            "coil_shape": "motor_ellipse",
            "shape_aspect_ratio": 1.6,
            "shape_taper_ratio": 0.0,
        })
        created = self.backend.create_spiral(
            values, [BoardLayer.BL_F_Cu], None, "segment"
        )
        self.assertEqual(32, len(created))
        self.assertEqual(1600000, created[0].start.x)
        self.assertEqual(2400000, created[-1].end.x)

    def test_radial_motor_array_creates_all_pole_coils(self):
        values = dict(self.values)
        values.update({
            "coil_shape": "motor_ellipse",
            "shape_aspect_ratio": 1.6,
            "shape_taper_ratio": 0.0,
            "motor_layout": "radial",
            "motor_pole_pairs": 2,
            "motor_array_radius_mm": 20.0,
            "motor_array_angle_degrees": 0.0,
            "motor_orientation": "radial",
            "motor_alternate_winding": True,
        })
        created = self.backend.create_spiral(
            values, [BoardLayer.BL_F_Cu], None, "segment"
        )
        self.assertEqual(4 * values["segments_per_turn"], len(created))
        starts = {(item.start.x, item.start.y) for item in created[::32]}
        self.assertEqual(4, len(starts))

    def test_motor_sector_generates_every_slot_inside_board(self):
        values = dict(self.values)
        values.update({
            "coil_shape": "motor_sector",
            "turns": 3,
            "track_width_mm": 0.4,
            "spacing_mm": 0.7,
            "motor_board_outer_diameter_mm": 100.0,
            "motor_board_inner_diameter_mm": 40.0,
            "motor_slot_count": 12,
            "motor_pole_pairs": 6,
            "motor_edge_clearance_mm": 1.0,
            "motor_slot_gap_mm": 0.8,
            "motor_array_angle_degrees": 0.0,
            "motor_alternate_winding": True,
        })
        created = self.backend.create_spiral(
            values, [BoardLayer.BL_F_Cu], None, "segment"
        )
        self.assertEqual(
            12 * values["turns"] * values["segments_per_turn"], len(created)
        )
        maximum_radius = max(
            math.hypot(point.x, point.y)
            for track in created for point in (track.start, track.end)
        )
        self.assertLess(maximum_radius, 50_000_000)

    def test_four_layer_sector_uses_plated_through_vias(self):
        values = dict(self.values)
        values.update({
            "coil_shape": "motor_sector",
            "turns": 3,
            "track_width_mm": 0.4,
            "spacing_mm": 0.7,
            "motor_board_outer_diameter_mm": 100.0,
            "motor_board_inner_diameter_mm": 40.0,
            "motor_slot_count": 12,
            "motor_pole_pairs": 6,
            "motor_edge_clearance_mm": 1.0,
            "motor_slot_gap_mm": 0.8,
            "motor_array_angle_degrees": 0.0,
            "motor_alternate_winding": True,
        })
        layers = [
            BoardLayer.BL_F_Cu, BoardLayer.BL_In1_Cu,
            BoardLayer.BL_In2_Cu, BoardLayer.BL_B_Cu,
        ]
        created = self.backend.create_spiral(
            values, layers, None, "segment"
        )
        vias = [item for item in created if type(item).__name__ == "Via"]
        self.assertEqual(12 * 3, len(vias))
        self.assertTrue(all(
            via.type == ViaType.VT_THROUGH for via in vias
        ))
        self.assertTrue(all(not via.padstack.layers for via in vias))

    def test_four_layer_motor_fanout_places_outer_via_beyond_shape(self):
        values = dict(self.values)
        values.update({
            "start_radius_mm": 2.0,
            "coil_shape": "motor_trapezoid",
            "shape_aspect_ratio": 1.65,
            "shape_taper_ratio": 0.45,
        })
        layers = [
            BoardLayer.BL_F_Cu, BoardLayer.BL_In1_Cu,
            BoardLayer.BL_In2_Cu, BoardLayer.BL_B_Cu,
        ]
        created = self.backend.create_spiral(
            values, layers, None, "segment"
        )
        spiral_tracks = created[:values["segments_per_turn"] * len(layers)]
        shape_radius = max(
            math.hypot(point.x, point.y)
            for track in spiral_tracks
            for point in (track.start, track.end)
        )
        via_radii = [
            math.hypot(item.position.x, item.position.y)
            for item in created
            if type(item).__name__ == "Via"
        ]
        self.assertEqual(3, len(via_radii))
        self.assertGreater(max(via_radii), shape_radius)

    def test_default_via_dimensions_are_generated_exactly(self):
        values = dict(self.values)
        values["start_radius_mm"] = 2.0
        values["via_diameter_mm"] = 0.6
        values["via_drill_mm"] = 0.4
        created = self.backend.create_spiral(
            values,
            [BoardLayer.BL_F_Cu, BoardLayer.BL_B_Cu],
            None,
            "arc",
        )
        vias = [item for item in created if type(item).__name__ == "Via"]
        self.assertEqual(1, len(vias))
        self.assertEqual(mm_to_nm(0.6), vias[0].diameter)
        self.assertEqual(mm_to_nm(0.4), vias[0].drill_diameter)
    def test_two_layer_coil_adds_inner_transition_and_two_outer_leads(self):
        values = dict(self.values)
        values["start_radius_mm"] = 2.0
        created = self.backend.create_spiral(
            values,
            [BoardLayer.BL_F_Cu, BoardLayer.BL_B_Cu],
            None,
            "arc",
        )
        self.assertEqual(21, len(created))
        self.assertEqual(1, len(self.client.board.created_batches))

    def test_group_is_created_after_copper_objects(self):
        values = dict(self.values)
        values["create_group"] = True
        self.backend.create_spiral(
            values, [BoardLayer.BL_F_Cu], None, "segment"
        )
        self.assertEqual(2, len(self.client.board.created_batches))
        group = self.client.board.created_batches[1][0]
        self.assertEqual("spiral", group.name)


if __name__ == "__main__":
    unittest.main()

