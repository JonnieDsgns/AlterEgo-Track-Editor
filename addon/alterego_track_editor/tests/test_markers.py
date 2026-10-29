import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("workshop_markers", Path(__file__).parents[1] / "markers.py")
markers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(markers)


def row(name, parent=None, kind=1):
    return {"name": name, "parent": parent, "kind": kind}


class MarkerTests(unittest.TestCase):
    def test_names_indices_and_sides(self):
        for name, kind, number in (("ac_start_0", "GRID", 1), ("AC_PIT_23", "PIT", 24),
                                   ("AC_HOTLAP_START_0", "HOTLAP", 1), ("AC_TIME_2_R", "TIMING", 3)):
            marker = markers.describe(name)
            self.assertEqual((marker["type"], marker["number"]), (kind, number))
            self.assertEqual(marker["source_index"], number - 1)
        self.assertEqual(markers.describe("AC_TIME_0_R")["side"], "RIGHT")
        for name in ("AC_START_1_mesh", "AC_PIT_-1", "AC_TIME_0", "AC_TIME_0_X", "ROAD"):
            self.assertIsNone(markers.describe(name))

    def test_transform_display_and_standalone_mesh(self):
        nodes = [row("AC_START_0"), row("AC_START_0", 0), row("AC_START_0", 1, 2), row("AC_PIT_0", kind=2)]
        result = markers.plan(nodes)
        self.assertEqual(set(result["anchors"]), {0, 3})
        self.assertEqual(result["displays"], {1: 0, 2: 0})

    def test_different_markers_remain_independent(self):
        result = markers.plan([row("AC_START_0"), row("AC_START_1", 0), row("AC_START_1", 1, 2)])
        self.assertEqual(set(result["anchors"]), {0, 1})
        self.assertEqual(result["displays"], {2: 1})

    def test_checks_duplicates_pairs_missing_and_orientation(self):
        rows = [dict(markers.describe(name), name=name) for name in
                ("AC_START_0", "AC_PIT_0", "AC_TIME_0_L", "AC_TIME_0_R", "AC_HOTLAP_START_0")]
        self.assertEqual(markers.validate(rows), [])
        self.assertEqual(len(markers.validate([])), 3)
        issues = markers.validate(rows + [dict(rows[0])])
        self.assertIn("Duplicate starting grid 1", issues[0])
        issues = markers.validate(rows[:3])
        self.assertIn("missing right", issues[0])
        rows[0].update(position=[float("nan"), 0, 0], forward=[0, 0, 1])
        issues = markers.validate(rows)
        self.assertEqual(len(issues), 2)

    def test_finding_targets_are_explicit_not_parsed_from_messages(self):
        rows = [dict(markers.describe(name), name=name) for name in
                ("AC_START_0", "AC_PIT_0", "AC_TIME_0_L")]
        rows[0]["name"] = "Renamed: Grid"
        rows[0]["forward"] = [0, 0, 1]
        rows.append(dict(rows[0], name="Second Grid"))
        issues = markers.findings(rows)
        self.assertEqual(markers.validate(rows), [issue["message"] for issue in issues])
        self.assertEqual(next(issue["objects"] for issue in issues if issue["message"].startswith("Duplicate")),
                         ["Renamed: Grid", "Second Grid"])
        self.assertEqual(issues[-1]["objects"], ["AC_TIME_0_L"])
        self.assertEqual(issues[0]["objects"], ["Renamed: Grid"])
        self.assertTrue(all(not issue["objects"] for issue in markers.findings([])))


if __name__ == "__main__":
    unittest.main()
