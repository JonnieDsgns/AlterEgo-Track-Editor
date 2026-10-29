import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("workshop_surfaces", Path(__file__).parents[1] / "surfaces.py")
surfaces = importlib.util.module_from_spec(spec)
spec.loader.exec_module(surfaces)


def definition(key, **values):
    return {"section": "SURFACE_0", "key": key, "values": values}


class SurfaceTests(unittest.TestCase):
    def test_longest_key_and_numbered_meshes(self):
        rows = [definition("ROAD"), definition("ROAD2")]
        for name in ("1ROAD2_003", "12road2001"):
            result = surfaces.suggest(name, rows)
            self.assertEqual(result["key"], "ROAD2")
            self.assertEqual(result["surface"], "ASPHALT")
            self.assertTrue(result["collision"])
        self.assertEqual(surfaces.suggest("ROAD2_003", rows)["status"], "VISUAL_ONLY")

    def test_unknown_is_not_asphalt(self):
        rows = [definition("MYSTERY", is_valid_track="1", friction="1")]
        result = surfaces.suggest("1MYSTERY_0", rows)
        self.assertEqual(result["surface"], "UNASSIGNED")
        self.assertEqual(result["status"], "NEEDS_REVIEW")
        self.assertEqual(result["definition"]["values"]["friction"], "1")
        self.assertEqual(surfaces.suggest("1ROAD", [])["status"], "NEEDS_REVIEW")
        self.assertEqual(surfaces.suggest("grass_visual", rows)["status"], "VISUAL_ONLY")

    def test_duplicate_keys_are_ambiguous(self):
        result = surfaces.suggest("1ROAD", [definition("ROAD"), definition("road")])
        self.assertEqual(result["surface"], "UNASSIGNED")
        self.assertIn("Ambiguous", result["reason"])

    def test_known_names_and_no_physics_parameter_conversion(self):
        for key, expected in (("CURB", "KERB"), ("GRAVEL", "GRAVEL"), ("PITS", "ASPHALT"),
                              ("GRASS", "GRASS"), ("CONCRETE", "CONCRETE"), ("ASTRO", "ASTROTURF")):
            result = surfaces.suggest("1" + key, [definition(key, friction="0.9", is_pitlane="1")])
            self.assertEqual(result["surface"], expected)
            self.assertNotIn("friction", result)
        numbers = [item[3] for item in surfaces.SURFACES]
        self.assertEqual(len(numbers), len(set(numbers)))

    def test_layout_priority_and_shared_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            (root / "data/surfaces.ini").write_text("[SURFACE_0]\nKEY=ROAD\n")
            self.assertEqual(surfaces.load(root, "short")["definitions"][0]["key"], "ROAD")
            (root / "short/data").mkdir(parents=True)
            path = root / "short/data/surfaces.ini"
            path.write_text("[SURFACE_0]\nKEY=GRASS ; comment\nFRICTION=0.6\n", encoding="utf-8-sig")
            data = surfaces.load(root, "short")
            self.assertEqual(data["definitions"][0]["key"], "GRASS")
            self.assertEqual(data["definitions"][0]["values"]["friction"], "0.6")
            path.unlink()
            self.assertEqual(surfaces.load(root, "short")["definitions"], [])

    def test_packed_missing_malformed_and_encoding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "short").mkdir()
            (root / "short/data.acd").touch()
            self.assertIn("packed", surfaces.load(root, "short")["warnings"][0])
            (root / "data").mkdir()
            path = root / "data/surfaces.ini"
            path.write_text("not an ini")
            self.assertTrue(surfaces.load(root, "default")["warnings"])
            path.write_bytes(b"[SURFACE_0]\nKEY=ROAD\nWAV=stra\xdfe.wav\n[SURFACE_1]\nFRICTION=1\n")
            data = surfaces.load(root, "default")
            self.assertEqual(len(data["definitions"]), 1)
            self.assertTrue(data["warnings"])
            with self.assertRaises(ValueError):
                surfaces.load(root, "../escape")


if __name__ == "__main__":
    unittest.main()
