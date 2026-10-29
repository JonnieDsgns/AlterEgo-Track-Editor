import importlib
from pathlib import Path
import sys
import types
import unittest

package = types.ModuleType("workshop_pure")
package.__path__ = [str(Path(__file__).parents[1])]
sys.modules.setdefault("workshop_pure", package)
geometry = importlib.import_module("workshop_pure.rule_geometry")


class RuleGeometryTests(unittest.TestCase):
    def test_arc_length_not_point_index(self):
        points = [(0, 0, 0), (2, 0, 0), (2, 8, 0)]
        self.assertEqual(geometry.at_progress(points, 0), ((0, 0, 0), (1, 0, 0)))
        self.assertEqual(geometry.at_progress(points, 0.5), ((2, 3, 0), (0, 1, 0)))
        self.assertEqual(geometry.at_progress(points, 1), ((2, 8, 0), (0, 1, 0)))
        for progress in (-1, 1.01, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                geometry.at_progress(points, progress)
        with self.assertRaises(ValueError):
            geometry.at_progress([(0, 0, 0)]*2, 0)

    def test_rule_order_partial_and_equal(self):
        good = dict(ENTRY=0, LIMITER_START=0.2, LIMITER_END=0.8, EXIT=1)
        self.assertFalse(geometry.order_issues(good))
        self.assertFalse(geometry.order_issues(dict(ENTRY=0.2, LIMITER_START=0.2, LIMITER_END=0.8, EXIT=0.8)))
        self.assertTrue(geometry.order_issues(dict(LIMITER_START=0.8, LIMITER_END=0.2)))
        self.assertTrue(geometry.order_issues(dict(LIMITER_START=0.2, LIMITER_END=0.2)))
        self.assertTrue(geometry.order_issues(dict(ENTRY=0.8, EXIT=0.2)))
        self.assertFalse(geometry.order_issues(dict(ENTRY=0.2)))
