"""Debounced sidebar snapshots; operators always use uncached validators."""
import time
from collections import OrderedDict

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, IntProperty, StringProperty

_cache = OrderedDict()
_pending = OrderedDict()
_versions = {"project": 0, "material": 0, "export": 0}
_changed = {"project": 0.0, "material": 0.0, "export": 0.0}
_enabled = False
_message_owner = object()
_light = OrderedDict()
_collections = {}
_structure_version = 0
DEBOUNCE = 0.18
AUTHORING_FLAGS = ("tw_is_route", "tw_route_helper", "tw_track_limit", "tw_pit_rule", "tw_is_marker")
PAGE_SCOPES = ("markers", "lines", "limits", "rules", "gates", "timing", "capture_warnings",
               "parameters", "textures", "material_warnings")


class TW_OT_ui_page(bpy.types.Operator):
    bl_idname = "track_workshop.ui_page"
    bl_label = "List Page"
    scope: StringProperty(options={"HIDDEN"})
    page: IntProperty(min=0, options={"HIDDEN"})

    def execute(self, context):
        if self.scope not in PAGE_SCOPES:
            return {"CANCELLED"}
        setattr(context.scene, "tw_page_" + self.scope, self.page)
        return {"FINISHED"}


def page(layout, scene, values, scope, size=12):
    """Bound native button creation even for thousands of cached findings."""
    count = len(values)
    pages = max(1, (count+size-1)//size)
    index = min(getattr(scene, "tw_page_" + scope), pages-1)
    if pages > 1:
        row = layout.row(align=True)
        previous = row.row(align=True)
        previous.enabled = index > 0
        button = previous.operator("track_workshop.ui_page", text="", icon="TRIA_LEFT")
        button.scope, button.page = scope, max(0, index-1)
        row.label(text=f"{index+1} / {pages} ({count})")
        following = row.row(align=True)
        following.enabled = index+1 < pages
        button = following.operator("track_workshop.ui_page", text="", icon="TRIA_RIGHT")
        button.scope, button.page = scope, min(pages-1, index+1)
    return values[index*size:(index+1)*size]


class Failure:
    def __init__(self, error):
        self.message = str(error)


def invalidate(group=None, *, structure=True):
    groups = tuple(_versions) if group is None else (group,)
    for name in groups:
        if name == "project" and structure:
            clear_light()
        _versions[name] += 1
        _changed[name] = time.monotonic()
        for mapping in (_cache, _pending):
            for key in list(mapping):
                if key[0] == name:
                    del mapping[key]


def light(scope, owner, build):
    """Cheap UI inventories shared by draw and operator poll, never validators.

    Graph and property notifications invalidate the inventories. Even counting
    Blender ID collections walks their lists, so no scene-size probe runs here.
    No timer is scheduled for these synchronous structural snapshots.
    """
    key = (scope, owner.as_pointer())
    stamp = _structure_version
    record = _light.get(key)
    if record is None or record[0] != stamp:
        record = (stamp, build())
        _light[key] = record
    _light.move_to_end(key)
    while len(_light) > 128:
        _light.popitem(last=False)
    return record[1]


def clear_light():
    global _structure_version
    _structure_version += 1
    _light.clear()


def changed(self=None, context=None):
    invalidate("project")


def content_changed(self=None, context=None):
    invalidate("project", structure=False)


def live_checks():
    scene = bpy.context.scene
    return scene is not None and getattr(scene, "tw_live_checks", False)


def get(scope, owner, build, group="project"):
    key = (group, scope, owner.as_pointer())
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    if group == "project" and not live_checks():
        return None
    _pending.setdefault(key, build)
    if _enabled and not bpy.app.background and not bpy.app.timers.is_registered(refresh_pending):
        bpy.app.timers.register(refresh_pending, first_interval=DEBOUNCE)
    return None


def put(scope, owner, value, group="project"):
    key = (group, scope, owner.as_pointer())
    _pending.pop(key, None)
    _cache[key] = value
    while len(_cache) > 128:
        _cache.popitem(last=False)


def resolve(scope, owner, build, group="material"):
    """Reuse parsed source data inside jobs, never call costly builders in draw."""
    key = (group, scope, owner.as_pointer())
    if key not in _cache:
        put(scope, owner, build(), group)
    _cache.move_to_end(key)
    return _cache[key]


def ready(layout, value, group="project"):
    if value is None:
        automatic = group != "project" or live_checks()
        layout.label(text="Updating checks..." if automatic else "Not checked", icon="TIME" if automatic else "INFO")
        return False
    if isinstance(value, Failure):
        layout.label(text="Check unavailable", icon="ERROR")
        return False
    return True


def refresh_pending(force=False):
    now = time.monotonic()
    updated = False
    processed = 0
    for key in list(_pending):
        group = key[0]
        if not force and now-_changed[group] < DEBOUNCE:
            continue
        if not force and processed >= 1:
            break
        processed += 1
        build = _pending.pop(key)
        version = _versions[group]
        try:
            value = build()
        except ReferenceError:
            continue  # The owning ID was removed before this queued job ran.
        except Exception as error:
            print("Track Workshop sidebar update:", error)
            value = Failure(error)
        if version == _versions[group]:
            _cache[key] = value
            updated = True
    while len(_cache) > 128:
        _cache.popitem(last=False)
    if updated and not bpy.app.background:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    for region in area.regions:
                        if region.type == "UI":
                            region.tag_redraw()
    return DEBOUNCE if _pending else None


@persistent
def on_graph(scene, depsgraph):
    project, material, export = False, False, False
    scene_changed, collections_changed = False, []
    for update in depsgraph.updates:
        data = update.id
        if isinstance(data, bpy.types.Scene):
            scene_changed = True
        if isinstance(data, bpy.types.Collection):
            collections_changed.append(data.original)
        if (isinstance(data, bpy.types.Object) and (update.is_updated_transform or update.is_updated_geometry)
                and (any(data.get(flag) for flag in AUTHORING_FLAGS) or data.get("tw_asset_id"))):
            project = True
        if isinstance(data, (bpy.types.Material, bpy.types.NodeTree, bpy.types.Image, bpy.types.Mesh)):
            export = True
        if isinstance(data, bpy.types.Curve):
            project = True
        # Source inventories are immutable snapshots. Shader edits and image loads
        # do not change them; capture/attach explicitly invalidates their cache.
        if isinstance(data, bpy.types.Text):
            material = True
    # Child transforms tag collection geometry too. Selection tags Scene alone.
    # Check memberships only for the Scene+Collection relation-change candidates;
    # unrelated Scene UI properties can be coalesced with a transform update.
    structure = False
    if scene_changed:
        for collection in collections_changed:
            pointer = collection.as_pointer()
            signature = (frozenset(obj.as_pointer() for obj in collection.objects),
                         frozenset(child.as_pointer() for child in collection.children))
            if _collections.get(pointer) != signature:
                structure = True
            _collections[pointer] = signature
    project = project or structure
    if project:
        invalidate("project", structure=structure)
    if material:
        invalidate("material")
    if export:
        invalidate("export")


@persistent
def on_reset(*args):
    _collections.clear()
    invalidate()


@persistent
def subscribe_names(*args):
    bpy.msgbus.clear_by_owner(_message_owner)
    bpy.msgbus.subscribe_rna(key=(bpy.types.Object, "name"), owner=_message_owner,
                             args=(), notify=changed, options={"PERSISTENT"})


def register():
    global _enabled
    _enabled = True
    _collections.clear()
    invalidate()
    bpy.utils.register_class(TW_OT_ui_page)
    for scope in PAGE_SCOPES:
        setattr(bpy.types.Scene, "tw_page_" + scope, IntProperty(default=0, min=0))
    bpy.types.Scene.tw_live_checks = BoolProperty(name="Live Checks", default=False, update=changed,
        description="Automatically recompute line, timing and rule checks after changes; can pause Blender on large tracks")
    subscribe_names()
    for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, on_graph),
                               (bpy.app.handlers.load_pre, on_reset),
                               (bpy.app.handlers.load_post, subscribe_names),
                               (bpy.app.handlers.undo_pre, on_reset),
                               (bpy.app.handlers.redo_pre, on_reset)):
        if callback not in handlers:
            handlers.append(callback)


def unregister():
    global _enabled
    _enabled = False
    _collections.clear()
    for scope in PAGE_SCOPES:
        delattr(bpy.types.Scene, "tw_page_" + scope)
    bpy.utils.unregister_class(TW_OT_ui_page)
    del bpy.types.Scene.tw_live_checks
    bpy.msgbus.clear_by_owner(_message_owner)
    if bpy.app.timers.is_registered(refresh_pending):
        bpy.app.timers.unregister(refresh_pending)
    for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, on_graph),
                               (bpy.app.handlers.load_pre, on_reset),
                               (bpy.app.handlers.load_post, subscribe_names),
                               (bpy.app.handlers.undo_pre, on_reset),
                               (bpy.app.handlers.redo_pre, on_reset)):
        if callback in handlers:
            handlers.remove(callback)
    invalidate()
