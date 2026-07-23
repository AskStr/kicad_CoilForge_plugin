import unittest

from coilforge.compat import KiCadCompat


class Point(tuple):
    def __new__(cls, x, y):
        return tuple.__new__(cls, (x, y))


class NewPcbnew(object):
    VECTOR2I = Point


class OldPcbnew(object):
    wxPoint = Point


class CompatTests(unittest.TestCase):
    def test_prefers_vector2i_for_newer_kicad(self):
        compat = KiCadCompat(NewPcbnew())
        self.assertEqual((1, 3), compat.make_point(1.2, 2.6))

    def test_falls_back_to_wxpoint_for_older_kicad(self):
        compat = KiCadCompat(OldPcbnew())
        self.assertEqual((1, 3), compat.make_point(1.2, 2.6))

    def test_newer_inches_enum_name_is_supported(self):
        class Pcbnew(object):
            EDA_UNITS_INCHES = 1

            @staticmethod
            def GetUserUnits():
                return 1

        self.assertEqual("inch", KiCadCompat(Pcbnew()).user_unit())

    def test_arc_creation_uses_cross_version_point_setters(self):
        class Arc(object):
            def __init__(self, board):
                self.board = board
                self.start = None
                self.mid = None
                self.end = None
                self.width = None
                self.layer = None
                self.net = None

            def SetStart(self, point):
                self.start = point

            def SetMid(self, point):
                self.mid = point

            def SetEnd(self, point):
                self.end = point

            def SetWidth(self, width):
                self.width = width

            def SetLayer(self, layer):
                self.layer = layer

            def SetNet(self, net):
                self.net = net

        class Pcbnew(object):
            VECTOR2I = Point
            wxPoint = Point
            PCB_ARC = Arc

            @staticmethod
            def GetMajorMinorVersion():
                return "10.0"

        compat = KiCadCompat(Pcbnew())
        self.assertTrue(compat.supports_arcs())
        self.assertEqual("10.0", compat.version_string())
        net = object()
        arc = compat.new_arc(
            "board", (1, 2), (3, 4), (5, 6), 250, net, 0
        )
        self.assertEqual((1, 2), arc.start)
        self.assertEqual((3, 4), arc.mid)
        self.assertEqual((5, 6), arc.end)
        self.assertEqual(250, arc.width)
        self.assertEqual(0, arc.layer)
        self.assertIs(net, arc.net)

    def test_via_creation_supports_current_api(self):
        class Via(object):
            def __init__(self, board):
                self.board = board
                self.position = None
                self.width = None
                self.drill = None
                self.layer_pair = None
                self.net = None
                self.via_type = None

            def SetPosition(self, position):
                self.position = position

            def SetWidth(self, width):
                self.width = width

            def SetDrill(self, drill):
                self.drill = drill

            def SetViaType(self, via_type):
                self.via_type = via_type

            def SetLayerPair(self, first, last):
                self.layer_pair = (first, last)

            def SetNet(self, net):
                self.net = net

        class Pcbnew(object):
            VECTOR2I = Point
            PCB_VIA = Via

            class VIATYPE(object):
                THROUGH = "through"

        net = object()
        via = KiCadCompat(Pcbnew()).new_via(
            "board", (10, 20), 800, 400, net, (0, 31)
        )
        self.assertEqual((10, 20), via.position)
        self.assertEqual(800, via.width)
        self.assertEqual(400, via.drill)
        self.assertEqual((0, 31), via.layer_pair)
        self.assertEqual("through", via.via_type)
        self.assertIs(net, via.net)

    def test_unit_conversion_is_independent_of_internal_unit_scale(self):
        compat = KiCadCompat(object())
        self.assertAlmostEqual(25.4, compat.user_to_mm(25.4))
        self.assertEqual(1000000, compat.from_mm(1.0))


if __name__ == "__main__":
    unittest.main()
