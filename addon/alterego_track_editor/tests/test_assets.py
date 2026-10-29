import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("workshop_assets", Path(__file__).parents[1] / "assets.py")
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


class Mesh(dict):
    def __init__(self):
        super().__init__(tw_source_id="source", tw_surface_status="SUGGESTED")
        self.type = "MESH"
        self.tw_surface = SimpleNamespace(surface="ASPHALT", collision=True)


class TerrainPolicyTests(unittest.TestCase):
    def test_known_physical_surface(self):
        obj = Mesh()
        self.assertTrue(assets.terrain_candidate(obj))
        for surface in ("KERB", "GRASS", "GRAVEL", "CONCRETE"):
            obj.tw_surface.surface = surface
            self.assertTrue(assets.terrain_candidate(obj))

    def test_unknown_visual_and_disabled_are_not_inferred(self):
        obj = Mesh()
        obj.tw_surface.surface = "UNASSIGNED"
        self.assertFalse(assets.terrain_candidate(obj))
        obj.tw_surface.surface = "ASPHALT"
        obj.tw_surface.collision = False
        self.assertFalse(assets.terrain_candidate(obj))
        obj.tw_surface.collision = True
        for status in ("NEEDS_REVIEW", "VISUAL_ONLY", None):
            obj["tw_surface_status"] = status
            self.assertFalse(assets.terrain_candidate(obj))

    def test_helpers_derivatives_and_missing_identity_are_excluded(self):
        for key in ("tw_is_marker", "tw_marker_helper", "tw_marker_source_only", "tw_asset_id"):
            obj = Mesh()
            obj[key] = True
            self.assertFalse(assets.terrain_candidate(obj))
        obj = Mesh()
        del obj["tw_source_id"]
        self.assertFalse(assets.terrain_candidate(obj))


if __name__ == "__main__":
    unittest.main()
