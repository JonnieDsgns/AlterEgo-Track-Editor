import importlib
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest

from ai_fixture import payload

package = types.ModuleType("workshop_pure")
package.__path__ = [str(Path(__file__).parents[1])]
sys.modules.setdefault("workshop_pure", package)
ai = importlib.import_module("workshop_pure.ai")


class AITests(unittest.TestCase):
    def test_format_details_and_grid(self):
        positions = [(0, 0, 0), (10, 1, 0), (10, 0, 10)]
        for grid in (False, True):
            data = ai.parse(payload(positions, [(2, 3)]*3, grid))
            self.assertEqual(len(data["points"]), 3)
            self.assertEqual(data["points"][1]["position"], [10, 1, 0])
            self.assertEqual(data["points"][0]["hints"]["side_left"], 2)
            self.assertEqual(data["has_grid"], grid)
        self.assertNotIn("hints", ai.parse(payload(positions))["points"][0])

    def test_reject_bad_and_truncated_files(self):
        raw = payload([(0, 0, 0), (1, 0, 0)])
        for value in (raw[:3], raw[:-1], raw+b"extra", struct.pack("<i", 8)+raw[4:],
                      raw[:16]+struct.pack("<f", float("nan"))+raw[20:],
                      raw[:12]+raw[12:16]+raw[16:28]+struct.pack("<f", -1)+raw[32:]):
            with self.assertRaises(ValueError):
                ai.parse(value)

    def test_layout_isolation_and_axes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = ai.files(root, "short")
            self.assertEqual(paths[0][1], root / "short/ai/fast_lane.ai")
            self.assertEqual(ai.files(root, "default")[1][1], root / "ai/pit_lane.ai")
            with self.assertRaises(ValueError):
                ai.files(root, "../outside")
        self.assertEqual(ai.blender_position((1, 2, 3)), (1, -3, 2))

    def test_asymmetric_widths_and_reverse(self):
        points = [(0, 0, 0), (10, 0, 0), (20, 0, 0)]
        left, right = ai.boundaries(points, [(2, 3)]*3, [(0, 0, 1)]*3, False)
        self.assertEqual(left[1], (10, 2, 0))
        self.assertEqual(right[1], (10, -3, 0))
        reversed_left, reversed_right = ai.boundaries(points[::-1], [(3, 2)]*3, [(0, 0, 1)]*3, False)
        self.assertEqual(reversed_left, right[::-1])
        self.assertEqual(reversed_right, left[::-1])
        with self.assertRaises(ValueError):
            ai.boundaries(points, [(0, 0)]*3, [(0, 0, 1)]*3, False)

    def test_banked_normals_nearest_and_bad_geometry(self):
        left, _ = ai.boundaries([(0, 0, 0), (10, 0, 0)], [(2, 2)]*2, [(0, 1, 1)]*2, False)
        self.assertAlmostEqual(left[0][1], 2**0.5)
        self.assertAlmostEqual(left[0][2], -2**0.5)
        result = ai.nearest([(0, 0, 0), (10, 0, 0), (10, 10, 0)], (5, 2, 0), False)
        self.assertEqual(result["position"], [5, 0, 0])
        self.assertEqual(result["distance"], 2)
        self.assertEqual(result["progress"], 0.25)
        with self.assertRaises(ValueError):
            ai.lengths([(0, 0, 0), (0, 0, 0)], False)


if __name__ == "__main__":
    unittest.main()
