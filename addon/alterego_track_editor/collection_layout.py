"""Project-local collection roles; names are labels, never identities."""
import bpy
from . import ui_cache


SPEC = (
    ("SOURCE", "AC Import", None), ("EXPORT", "F1 Export", None),
    ("MARKUP", "Track Markup", "EXPORT"),
    ("MARKERS", "Markers", "MARKUP"),
    ("GRID", "Starting Grid", "MARKERS"), ("PIT", "Pit Positions", "MARKERS"),
    ("HOTLAP", "Hotlap Starts", "MARKERS"),
    ("GATES", "Gates", "MARKUP"), ("TIMING", "Timing Gates", "GATES"),
    ("PIT_CONNECTIONS", "Pit Connections (Draft)", "GATES"),
    ("LINES", "AI Lines", "MARKUP"),
    ("RACING_LINE", "Racing Line", "LINES"), ("PIT_LINE", "Pit Line", "LINES"),
    ("LIMITS", "Track Limits", "MARKUP"),
    ("ROAD_EDGES", "Road Edges (Draft)", "LIMITS"), ("PIT_EDGES", "Pit Edges (Draft)", "LIMITS"),
    ("LEGAL_LIMITS", "Authored Track Limits", "LIMITS"),
    ("ZONES", "Zones", "MARKUP"),
    ("PIT_RULES", "Pit Rules", "ZONES"),
    ("DRS", "DRS Zones", "ZONES"), ("XMODE", "X-Mode Zones", "ZONES"),
    ("COMMON", "Common", "EXPORT"),
    ("COMMON_TERRAIN", "Terrain", "COMMON"), ("COMMON_OBJECTS", "Trackside Objects", "COMMON"),
    ("COMMON_FACILITIES", "Facilities", "COMMON"), ("COMMON_VEGETATION", "Vegetation", "COMMON"),
    ("CLASSIC", "Classic", "EXPORT"),
    ("YEAR_2026", "2026", "EXPORT"),
    ("2026_F1", "F1 2026", "YEAR_2026"), ("2026_MYTEAM", "MyTeam 2026", "YEAR_2026"),
    ("2026_F2", "F2 2026", "YEAR_2026"),
    ("YEAR_2025", "2025", "EXPORT"),
    ("2025_F1", "F1 2025", "YEAR_2025"), ("2025_MYTEAM", "MyTeam 2025", "YEAR_2025"),
    ("2025_F2", "F2 2025", "YEAR_2025"),
)
ASSET_TARGETS = (
    ("COMMON_TERRAIN", "Common / Terrain", "Terrain shared by all variants", 0),
    ("COMMON_OBJECTS", "Common / Trackside Objects", "Objects shared by all variants", 1),
    ("COMMON_FACILITIES", "Common / Facilities", "Facilities shared by all variants", 2),
    ("COMMON_VEGETATION", "Common / Vegetation", "Vegetation shared by all variants", 3),
    ("2026_F1", "2026 / F1", "F1 2026 only", 4),
    ("2026_MYTEAM", "2026 / MyTeam", "MyTeam 2026 only", 5),
    ("2026_F2", "2026 / F2", "F2 2026 only", 6),
    ("2025_F1", "2025 / F1", "F1 2025 only", 7),
    ("2025_MYTEAM", "2025 / MyTeam", "MyTeam 2025 only", 8),
    ("2025_F2", "2025 / F2", "F2 2025 only", 9),
    ("CLASSIC", "Classic", "Classic native world", 10),
)


def find(root, role):
    return next((collection for collection in root.children_recursive
                 if collection.get("tw_collection_role") == role
                 and collection.get("tw_collection_owner") == root["tw_project_id"]), None)


def ensure(root):
    ui_cache.invalidate("project")
    result = {}
    for role, label, parent_role in SPEC:
        parent = root if parent_role is None else result[parent_role]
        collection = find(root, role)
        if collection is None:
            collection = bpy.data.collections.new(label)
            collection["tw_collection_role"] = role
            collection["tw_collection_owner"] = root["tw_project_id"]
        if collection.name not in parent.children:
            parent.children.link(collection)
        result[role] = collection
    result["SOURCE"].hide_render = True
    root["tw_collection_layout_version"] = 2
    return result


def move(obj, target, root):
    """Relink only inside this project; leave unrelated collection links alone."""
    ui_cache.invalidate("project")
    local = {root, *root.children_recursive}
    if obj.name not in target.objects:
        target.objects.link(obj)
    for collection in list(obj.users_collection):
        if collection != target and collection in local:
            collection.objects.unlink(obj)


def place_marker(obj, root):
    collections = ensure(root)
    move(obj, collections[obj.tw_marker.kind], root)
