import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("workshop_source", Path(__file__).parents[1] / "source.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class LayoutTests(unittest.TestCase):
    def test_legacy_default_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / (root.name + ".kn5")).touch()
            self.assertEqual(source.layouts(root)[0]["id"], "@default_kn5")
            self.assertEqual(source.models(root, "@default_kn5")[0]["path"].stem, root.name)

    def test_layouts_and_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "models.ini").write_text("[MODEL_0]\nFILE=base.kn5\n")
            (root / "models_short.ini").write_text("[MODEL_0]\nFILE=short.kn5\n")
            (root / "base.kn5").touch()
            (root / "short.kn5").touch()
            (root / "ui/short").mkdir(parents=True)
            (root / "ui/short/ui_track.json").write_text(json.dumps({"name": "Short Circuit"}))
            rows = source.layouts(root)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["name"], "Short Circuit")
            self.assertEqual(source.models(root, rows[1]["id"])[0]["path"].name, "short.kn5")
            (root / "ui/short/ui_track.json").write_text("broken")
            self.assertEqual(source.layouts(root)[1]["name"], "short")

    def test_missing_and_unsafe_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ValueError):
                source.layouts(root)
            manifest = root / "models.ini"
            for text in ("[MODEL_0]\nFILE=missing.kn5\n", "[MODEL_0]\nFILE=../escape.kn5\n", "[OTHER]\nFILE=a.kn5\n"):
                manifest.write_text(text)
                with self.assertRaises(ValueError):
                    source.models(root, "models.ini")
            with self.assertRaises(ValueError):
                source.models(root, "../models.ini")

    def test_transform_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "a.kn5").touch()
            for values in ("POSITION=nan,0,0", "POSITION=0,0", "ROTATION=0,inf,0"):
                (root / "models.ini").write_text("[MODEL_0]\nFILE=a.kn5\n" + values)
                with self.assertRaises(ValueError):
                    source.models(root, "models.ini")
            (root / "models.ini").write_text("[MODEL_0]\nFILE=a.kn5\nPOSITION=10,0,0\nROTATION=90,20,10")
            self.assertEqual(source.models(root, "models.ini")[0]["rotation"], (90,20,10))


if __name__ == "__main__":
    unittest.main()
