"""Run with Blender --background --factory-startup --python-exit-code 1."""
from pathlib import Path
from collections import Counter
import json
import sys
import tempfile

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))
import alterego_track_editor as TrackWorkshop
from alterego_track_editor import importer
from alterego_track_editor import marker_ui, collection_layout
from alterego_track_editor.tests.kn5_fixture import fixture


TrackWorkshop.register()
assert not issubclass(TrackWorkshop.TW_OT_choose_layout, TrackWorkshop.jobs.CooperativeJob)
assert issubclass(TrackWorkshop.TW_OT_import_layout, TrackWorkshop.jobs.CooperativeJob)
try:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        fixture(root / "a.kn5")
        fixture(root / "b.kn5")
        (root / "models.ini").write_text("[MODEL_0]\nFILE=a.kn5\nPOSITION=0,0,0")
        (root / "models_short.ini").write_text("[MODEL_0]\nFILE=b.kn5\nPOSITION=10,0,0\nROTATION=90,0,0")
        choices = TrackWorkshop.layouts(folder)
        TrackWorkshop._items[folder] = [(row["id"], row["name"], row["id"]) for row in choices]
        result = bpy.ops.track_workshop.choose_layout(directory=folder, selected_layout="models_short.ini")
        assert result == {"FINISHED"}
        assert len([c for c in bpy.context.scene.collection.children if c.get("tw_project_id")]) == 1
        imported = next(c for c in bpy.data.collections if c.get("tw_layout_manifest"))
        assert imported["ate_schema"] == "AlterEgo.TrackProject.v1"
        assert len(json.loads(imported["ate_sources"])) >= 2
        meshes = [o for o in imported.all_objects if o.type == "MESH"]
        assert len(meshes) == 1 and len(meshes[0].data.polygons) == 1
        bpy.context.view_layer.update()
        assert abs(meshes[0].matrix_world.translation.x - 10) < 1e-6
        vertex = meshes[0].matrix_world @ meshes[0].data.vertices[1].co
        assert (vertex - Vector((10,1,0))).length < 1e-5
        for angles, expected in (((0,90,0), (0,-1,0)), ((0,0,90), (0,1,0))):
            point = (0,0,1) if angles[1] else (1,0,0)
            matrix = importer.placement({"position": (0,0,0), "rotation": angles})
            assert (matrix @ Vector(point) - Vector(expected)).length < 1e-5
        assert Path(meshes[0]["tw_source_model"]).name == "b.kn5"
        assert len(meshes[0].data.uv_layers) == 1
        assert len(meshes[0].data.materials) == 1
        before = {kind: len(getattr(bpy.data, kind)) for kind in ("objects", "meshes", "collections", "materials", "images")}
        (root / "models_short.ini").write_text("[MODEL_0]\nFILE=a.kn5\n[MODEL_1]\nFILE=b.kn5\n")
        (root / "b.kn5").write_bytes(b"invalid")
        try:
            importer.load(bpy.context, folder, "models_short.ini")
            raise AssertionError("Invalid KN5 accepted")
        except ValueError:
            pass
        assert before == {kind: len(getattr(bpy.data, kind)) for kind in before}
        # Cancellation after the first yielded chunk must remove the partial root.
        (root / 'b.kn5').write_bytes((root / 'a.kn5').read_bytes())
        iterator = importer.load_steps(bpy.context, folder, 'models.ini')
        next(iterator)
        assert len([c for c in bpy.context.scene.collection.children if c.get('tw_project_id')]) == 2
        iterator.close()
        assert len([c for c in bpy.context.scene.collection.children if c.get('tw_project_id')]) == 1
        print("TRACK_WORKSHOP_SMOKE_PASS: registration, selected layout, geometry, transforms, UV, material, rollback")
finally:
    TrackWorkshop.unregister()
