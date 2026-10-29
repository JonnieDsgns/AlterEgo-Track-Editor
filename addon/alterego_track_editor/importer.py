"""Import one chosen AC layout; failures remove only newly created data."""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import uuid
from collections import Counter

import bpy
from mathutils import Matrix
import numpy as np

from .kn5 import read
from .source import layouts, models
from .surfaces import load as load_surfaces, suggest
from . import marker_ui, collection_layout, routes, materials as ac_materials, ui_cache
from .markers import validate as validate_markers
from .assets import prepare_terrain


def placement(entry):
    # Layout ROTATION is yaw/pitch/roll, not Blender's X/Y/Z Euler order.
    yaw, pitch, roll = (math.radians(value) for value in entry["rotation"])
    rotation = (Matrix.Rotation(yaw, 4, "Y") @ Matrix.Rotation(pitch, 4, "X")
                @ Matrix.Rotation(roll, 4, "Z"))
    return Matrix.Translation(entry["position"]) @ rotation


def load(context, folder, manifest):
    from .jobs import drain
    return drain(load_steps(context, folder, manifest))


class ImportTransaction:
    kinds = ("objects", "collections", "meshes", "materials", "images", "curves", "texts")

    def __init__(self):
        self.owned = {kind: set() for kind in self.kinds}
        self.resume()

    def resume(self):
        self.before = {kind: set(getattr(bpy.data, kind)) for kind in self.kinds}
        self.paused = False

    def pause(self):
        for kind in self.kinds:
            self.owned[kind].update(set(getattr(bpy.data, kind))-self.before[kind])
        self.paused = True

    def rollback(self):
        if not self.paused:
            self.pause()
        for kind in self.kinds:
            collection = getattr(bpy.data, kind)
            for item in self.owned[kind]:
                try:
                    if item.name in collection and collection[item.name] == item:
                        collection.remove(item, do_unlink=True)
                except ReferenceError:
                    pass


def load_steps(context, folder, manifest):
    entries = models(folder, manifest)
    selected = next(row for row in layouts(folder) if row["id"] == manifest)
    surfaces = load_surfaces(folder, selected["layout"])
    transaction = ImportTransaction()

    def pause(progress, label):
        transaction.pause()
        yield progress, label
        transaction.resume()
    warnings = list(surfaces["warnings"])
    surface_counts = Counter()
    try:
        root = bpy.data.collections.new(selected["name"])
        context.scene.collection.children.link(root)
        root["tw_track_folder"] = str(Path(folder).resolve())
        root["tw_layout_manifest"] = manifest
        root["tw_schema_version"] = 3
        root["tw_project_id"] = str(uuid.uuid4())
        root["tw_import_pending"] = True
        root["tw_layout_name"] = "Default" if selected["layout"] == "default" else selected["layout"].replace("_", " ").title()
        root["tw_surface_source"] = json.dumps(surfaces, ensure_ascii=True)
        collections = collection_layout.ensure(root)
        axis = bpy.data.objects.new("AC coordinates", None)
        collections["SOURCE"].objects.link(axis)
        axis.rotation_euler.x = math.pi / 2
        axis.hide_render = True
        cache = {}
        payload_cache = {}
        with tempfile.TemporaryDirectory(prefix="track-workshop-") as temporary:
            for model_index, entry in enumerate(entries):
                yield from pause(.8*model_index/len(entries), "Reading " + entry["path"].name)
                try:
                    data = read(entry["path"])
                except (OSError, ValueError) as error:
                    raise ValueError(f"{entry['path'].name}: {error}") from error
                warnings.extend(entry["path"].name + ": " + warning for warning in data["warnings"])
                group = bpy.data.collections.new(entry["path"].name)
                collections["SOURCE"].children.link(group)
                origin = bpy.data.objects.new(entry["section"], None)
                group.objects.link(origin)
                origin.parent = axis
                origin.matrix_local = placement(entry)

                def image(name, noncolor):
                    payload = data["images"].get(name)
                    if not payload:
                        warnings.append("Missing texture: " + name)
                        return None
                    digest = hashlib.sha256(payload).hexdigest()
                    key = (digest, noncolor)
                    if key not in cache:
                        path = Path(temporary) / (digest + (Path(name).suffix or ".dds"))
                        path.write_bytes(payload)
                        try:
                            result = bpy.data.images.load(str(path), check_existing=False)
                            result.name = name
                            if noncolor:
                                result.colorspace_settings.name = "Non-Color"
                            result.pack()
                            cache[key] = result
                        except RuntimeError:
                            warnings.append("Texture preview unavailable: " + name)
                            cache[key] = None
                    return cache[key]

                model_source, material_contract = ac_materials.capture_model(folder, entry["path"], data, payload_cache)
                yield from pause(.8*(model_index+.15)/len(entries), "Materials: " + entry["path"].name)
                materials = []
                for material_index, row in enumerate(data["materials"]):
                    material = bpy.data.materials.new(row["name"])
                    material.use_nodes = True
                    material["tw_ac_shader"] = row["shader"]
                    ac_materials.attach(material, material_index, model_source, material_contract, folder)
                    nodes = material.node_tree.nodes
                    shader = nodes.get("Principled BSDF")
                    for mapping in row["textures"]:
                        if mapping["name"] not in ("txDiffuse", "txNormal"):
                            continue
                        texture = image(mapping["texture"], mapping["name"] == "txNormal")
                        if texture is None:
                            continue
                        node = nodes.new("ShaderNodeTexImage")
                        node.image = texture
                        if mapping["name"] == "txDiffuse":
                            node.location = (-550, 200)
                            material.node_tree.links.new(node.outputs["Color"], shader.inputs["Base Color"])
                            if row["cutout"] or row["blend"]:
                                material.node_tree.links.new(node.outputs["Alpha"], shader.inputs["Alpha"])
                                if hasattr(material, "surface_render_method"):
                                    material.surface_render_method = "DITHERED"
                        else:
                            node.location = (-550, -100)
                            normal = nodes.new("ShaderNodeNormalMap")
                            normal.location = (-250, -100)
                            material.node_tree.links.new(node.outputs["Color"], normal.inputs["Color"])
                            material.node_tree.links.new(normal.outputs["Normal"], shader.inputs["Normal"])
                    materials.append(material)
                    if material_index % 25 == 24:
                        yield from pause(.8*(model_index+.15+.1*(material_index+1)/len(data["materials"]))/len(entries), "Material previews")
                objects = []
                for index, row in enumerate(data["nodes"]):
                    if row["kind"] == 2:
                        vertices = np.frombuffer(row["vertices"], dtype="<f4").reshape((-1, 11))
                        if not np.isfinite(vertices).all():
                            raise ValueError("Non-finite mesh vertices: " + row["name"])
                        mesh = bpy.data.meshes.new(row["name"])
                        triangles = np.asarray(row["indices"], dtype=np.int32).reshape((-1, 3))
                        mesh.from_pydata(vertices[:, :3].tolist(), [], triangles.tolist())
                        if mesh.validate(clean_customdata=False):
                            warnings.append("Blender repaired invalid faces: " + row["name"])
                        if len(mesh.vertices) != len(vertices):
                            raise ValueError("Mesh repair changed vertex correspondence.")
                        mesh.update()
                        loops = np.empty(len(mesh.loops), dtype=np.int32)
                        mesh.loops.foreach_get("vertex_index", loops)
                        uv = vertices[loops, 6:8].copy()
                        uv[:, 1] = 1 - uv[:, 1]
                        mesh.uv_layers.new(name="UVMap").data.foreach_set("uv", uv.reshape(-1))
                        mesh.polygons.foreach_set("use_smooth", np.ones(len(mesh.polygons), dtype=np.bool_))
                        if len(mesh.loops):
                            mesh.normals_split_custom_set_from_vertices(vertices[:, 3:6].tolist())
                        mesh.materials.append(materials[row["material"]])
                        obj = bpy.data.objects.new(row["name"], mesh)
                        obj.hide_render = not (row["active"] and row["visible"] and row["renderable"])
                        obj.hide_viewport = not (row["active"] and row["visible"])
                    else:
                        obj = bpy.data.objects.new(row["name"], None)
                        obj.matrix_local = Matrix([row["matrix"][i:i + 4] for i in range(0, 16, 4)]).transposed()
                    group.objects.link(obj)
                    obj.parent = origin if row["parent"] is None else objects[row["parent"]]
                    obj["tw_source_model"] = str(entry["path"])
                    obj["tw_source_node"] = index
                    if row["kind"] == 2:
                        obj["tw_ac_material_index"] = row["material"]
                    obj["tw_source_name"] = row["name"]
                    obj["tw_source_section"] = entry["section"]
                    obj["tw_project_id"] = root["tw_project_id"]
                    identity = [Path(folder).name, manifest, entry["section"],
                                entry["path"].relative_to(Path(folder).resolve()).as_posix(), index]
                    obj["tw_source_id"] = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
                    if row["kind"] == 2:
                        assignment = suggest(row["name"], surfaces["definitions"])
                        obj["tw_surface_source"] = json.dumps(assignment, ensure_ascii=True)
                        obj["tw_surface_status"] = assignment["status"]
                        obj["tw_surface_suggestion"] = assignment["surface"]
                        obj["tw_collision_suggestion"] = assignment["collision"]
                        obj.tw_surface.surface = assignment["surface"]
                        obj.tw_surface.collision = assignment["collision"]
                        obj.tw_surface.surface_manual = False
                        obj.tw_surface.collision_manual = False
                        surface_counts[assignment["status"]] += 1
                    objects.append(obj)
                    if index % 100 == 99:
                        yield from pause(.8*(model_index+.25+.65*(index+1)/len(data["nodes"]))/len(entries), "Geometry: " + entry["path"].name)
                marker_ui.import_model(context, root, objects, data["nodes"])
                yield from pause(.8*(model_index+1)/len(entries), "Markers: " + entry["path"].name)
        yield from pause(.82, "Preparing terrain")
        prepare_terrain(context, root, collections)
        yield from pause(.92, "Importing AC lines")
        warnings.extend(routes.import_lines(context, root, folder, selected["layout"]))
        yield from pause(.97, "Final checks")
        context.view_layer.update()
        marker_rows = marker_ui.inventory(root)
        marker_issues = validate_markers(marker_rows)
        root["tw_marker_summary"] = json.dumps(dict(Counter(row["type"] for row in marker_rows)))
        root["tw_marker_validation"] = json.dumps(marker_issues)
        warnings.extend(marker_issues)
        root["tw_surface_summary"] = json.dumps(dict(surface_counts), sort_keys=True)
        if surface_counts["NEEDS_REVIEW"]:
            warnings.append(f"{surface_counts['NEEDS_REVIEW']} physical meshes need surface review.")
        root["tw_import_warnings"] = "\n".join(warnings)
        root.hide_viewport = False
        root["tw_import_pending"] = False
        context.scene.tw_marker_project = root
        ui_cache.invalidate("project")
        return root, warnings
    except BaseException:
        transaction.rollback()
        raise
