import importlib
from pathlib import Path
import sys
import types
import unittest

package = types.ModuleType("workshop_pure")
package.__path__ = [str(Path(__file__).parents[1])]
sys.modules.setdefault("workshop_pure", package)
timing = importlib.import_module("workshop_pure.timing_geometry")


class TimingGeometryTests(unittest.TestCase):
    square = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]

    def test_finite_crossing_and_vertex_deduplication(self):
        self.assertAlmostEqual(timing.crossing(self.square, (5, -1, 0), (5, 1, 0))["progress"], .125)
        self.assertEqual(timing.crossing(self.square, (-1, 1, 0), (1, -1, 0))["progress"], 0)
        with self.assertRaisesRegex(ValueError, "does not cross"):
            timing.crossing(self.square, (5, 3, 0), (5, 7, 0))
        with self.assertRaisesRegex(ValueError, "more than once"):
            timing.crossing(self.square, (5, -1, 0), (5, 11, 0))

    def test_height_and_overlaps(self):
        with self.assertRaisesRegex(ValueError, "height tolerance"):
            timing.crossing(self.square, (5, -1, 4), (5, 1, 4))
        with self.assertRaisesRegex(ValueError, "overlaps"):
            timing.crossing(self.square, (2, 0, 0), (8, 0, 0))
        with self.assertRaises(ValueError):
            timing.crossing(self.square, (2, 0, 0), (2, 0, 3))
        with self.assertRaises(ValueError):
            timing.crossing(self.square, (float("nan"), 0, 0), (2, 3, 0))

    def test_cyclic_order_not_curve_start(self):
        self.assertEqual(timing.sector_order(.75, 0, .25, 40), (.25, .5))
        for values in ((0, .7, .3, 40), (0, 0, .4, 40), (.5, .6, .6, 40)):
            with self.assertRaises(ValueError):
                timing.sector_order(*values)
