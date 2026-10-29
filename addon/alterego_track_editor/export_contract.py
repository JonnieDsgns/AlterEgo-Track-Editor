"""DatabaseEditor export policy, independent of Blender and native writers."""
from pathlib import Path
import re

VERSION = "TrackWorkshop.DatabaseEditorPlan.v1"
JOB_VERSION = "TrackWorkshop.NativeTest.v1"
MAX_TEST_TRIANGLES = 50000
MAX_OBJECT_TRIANGLES = 20000
SURFACE_CODES = {"ASPHALT": "SDT+", "KERB": "RMBL", "GRAVEL": "HDG+", "GRASS": "GRS+",
                 "CONCRETE": "CON+", "PAVING": "PDT+", "METAL": "METL", "OFFTRACK": "DDT+", "ASTROTURF": "ASTR"}
DONOR_POLICY = {
    "replacement": "imola", "variant": "2025_F1", "native_profile": "F1",
    "own": ["terrain", "static_geometry", "collision", "material_textures", "routes", "limits", "marker_transforms", "sectors"],
    "donor": ["native_resource_templates", "shader_templates", "environment_baseline", "functional_instance_templates", "vehicle_baseline"],
    "excluded": ["donor_track_geometry", "donor_route_geometry", "donor_collision_geometry", "local_light_probes"],
}


def game_files(game_root):
    base = Path(game_root)/"2025_asset_groups/environment_package/tracks/imola/wep"
    return {"common": base/"imola_common.erp", "variant": base/"imola_f1.erp"}


def require_output(path, game_root):
    if not path:
        raise ValueError("Choose an output folder.")
    output, game = Path(path).resolve(), Path(game_root).resolve()
    if output == game or output.is_relative_to(game) or game.is_relative_to(output):
        raise ValueError("Keep export output separate from the game installation.")
    if output.exists() and not output.is_dir():
        raise ValueError("Output folder is a file.")
    return output


def issue(code, message, objects=(), severity="ERROR", scope="GEOMETRY"):
    return {"code": code, "message": message, "objects": list(objects), "severity": severity, "scope": scope}


def validate_settings(settings):
    issues = []
    if settings["slot"] != "imola" or settings["variant"] != "2025_F1":
        issues.append(issue("TARGET", "The first native test supports Imola / F1 2025 only."))
    for name, path in game_files(settings["game_root"]).items():
        if not path.is_file():
            issues.append(issue("DONOR_MISSING", "Missing Imola " + name + " archive: " + str(path)))
    try:
        require_output(settings["output"], settings["game_root"])
    except ValueError as error:
        issues.append(issue("OUTPUT", str(error)))
    if not settings["track_name"].strip() or not settings["author"].strip():
        issues.append(issue("IDENTITY", "Enter a track name and author."))
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", settings["build_name"]):
        issues.append(issue("BUILD_NAME", "Build name must use lowercase letters, digits and underscores."))
    return issues


def finish(settings, objects, issues, skipped):
    if not objects:
        issues.append(issue("EMPTY", "No mesh belongs to Common or F1 2025 export collections."))
    if not any(row["render_role"] == "TERRAIN" for row in objects):
        issues.append(issue("TERRAIN_MISSING", "The native test needs at least one terrain mesh."))
    if not any(row["collision"] for row in objects):
        issues.append(issue("COLLISION_MISSING", "The native test needs explicit collision geometry."))
    triangles = sum(row["triangles"] for row in objects)
    if triangles > MAX_TEST_TRIANGLES:
        issues.append(issue("TEST_BUDGET", f"Native test budget is {MAX_TEST_TRIANGLES} triangles; plan contains {triangles}."))
    issues.append(issue("TRACK_ASSEMBLY_PENDING", "Full environment, facilities, vehicle bindings and installation audit are not connected yet.",
                        severity="ERROR", scope="TRACK"))
    return {"version": VERSION, "settings": settings, "policy": DONOR_POLICY, "objects": objects,
            "issues": issues, "skipped": skipped, "triangles": triangles,
            "geometry_test_ready": not any(item["severity"] == "ERROR" and item["scope"] == "GEOMETRY" for item in issues),
            "track_export_ready": False, "game_verified": False}
