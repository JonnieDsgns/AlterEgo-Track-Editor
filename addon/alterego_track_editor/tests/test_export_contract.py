import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("export_contract", Path(__file__).resolve().parents[1]/"export_contract.py")
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


class ExportContractTests(unittest.TestCase):
    def test_imola_profile_and_output_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game, output = root/"game", root/"output"
            for path in contract.game_files(game).values():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            settings = dict(slot="imola", variant="2025_F1", game_root=str(game), output=str(output),
                            track_name="Test", author="Author", build_name="test")
            self.assertFalse(contract.validate_settings(settings))
            for path in (game, game/"export", root):
                with self.assertRaises(ValueError):
                    contract.require_output(str(path), str(game))
            self.assertTrue(contract.validate_settings(dict(settings, slot="spa")))
            self.assertTrue(contract.validate_settings(dict(settings, build_name="../game")))

    def test_native_test_never_certifies_a_track(self):
        rows = [dict(name="Road", render_role="TERRAIN", collision=True, triangles=3)]
        result = contract.finish({}, rows, [], [])
        self.assertTrue(result["geometry_test_ready"])
        self.assertFalse(result["track_export_ready"])
        self.assertFalse(result["game_verified"])
        self.assertTrue(any(issue["code"] == "TRACK_ASSEMBLY_PENDING" for issue in result["issues"]))

    def test_empty_and_large_native_tests_are_blocked(self):
        self.assertFalse(contract.finish({}, [], [], [])["geometry_test_ready"])
        rows = [dict(name="Road", render_role="TERRAIN", collision=True, triangles=50001)]
        self.assertFalse(contract.finish({}, rows, [], [])["geometry_test_ready"])

    def test_terrain_render_role_does_not_enable_collision(self):
        rows = [dict(name="Road", render_role="TERRAIN", collision=False, triangles=2)]
        result = contract.finish({}, rows, [], [])
        self.assertFalse(result["geometry_test_ready"])
        self.assertTrue(any(issue["code"] == "COLLISION_MISSING" for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main()
