"""An explicitly opened material-preview workspace; never applied at startup."""
from pathlib import Path

import bpy
from bpy.props import StringProperty


DEFAULT_HDRI = ""


def hdri_path(context):
    addon = context.preferences.addons.get(__package__)
    path = addon.preferences.hdri if addon else DEFAULT_HDRI
    return Path(bpy.path.abspath(path)).resolve()


def environment(context):
    path = hdri_path(context)
    if not path.is_file() or path.suffix.lower() not in (".exr", ".hdr"):
        raise ValueError("Choose an existing EXR or HDR environment in Track Workshop preferences.")
    lights = context.preferences.studio_lights
    for light in lights:
        if light.type == "WORLD" and Path(light.path).resolve() == path:
            return light
    light = lights.load(str(path), 'WORLD')
    if light is None:
        raise ValueError("Blender could not load the HDRI environment.")
    return light


def configure(workspace, light):
    for screen in workspace.screens:
        areas = [area for area in screen.areas if area.type == "VIEW_3D"]
        if not areas:
            candidates = ([area for area in screen.areas if area.type not in ("OUTLINER", "PROPERTIES")]
                          or list(screen.areas))
            if candidates:
                area = max(candidates, key=lambda area: area.width * area.height)
                area.type = "VIEW_3D"
                areas = [area]
        for area in areas:
            space = area.spaces.active
            space.overlay.show_floor = False
            space.clip_end = 10000.0
            space.show_region_ui = True
            space.shading.type = "SOLID"
            if light is not None:
                space.shading.type = "MATERIAL"
                space.shading.use_scene_world = False
                space.shading.use_scene_lights = False
                space.shading.studio_light = light.name
                space.shading.studiolight_intensity = 1.0
                space.shading.studiolight_background_alpha = 1.0
                space.shading.studiolight_background_blur = 0.0


def ensure(context, activate=False):
    windows = [window for window in context.window_manager.windows
               if window.screen is not None and not window.screen.is_temporary]
    window = context.window if context.window in windows else next(iter(windows), None)
    if window is None:
        raise ValueError("Open a Blender main window to create the workspace.")
    # Material preview loads the HDRI only after an explicit viewport-mode choice.
    warning, light = None, None
    workspace = next((workspace for workspace in bpy.data.workspaces if workspace.get("tw_workspace")), None)
    if workspace is None:
        before = set(bpy.data.workspaces)
        with context.temp_override(window=window):
            result = bpy.ops.workspace.duplicate()
        created = set(bpy.data.workspaces) - before
        if result != {"FINISHED"} or len(created) != 1:
            raise ValueError("Could not create the Track Workshop workspace.")
        workspace = created.pop()
        workspace.name = "AlterEgo Track Editor"
        workspace["tw_workspace"] = True
    configure(workspace, light)
    workspace["tw_hdri_path"] = str(hdri_path(context))
    workspace["tw_environment_warning"] = warning or ""
    if activate:
        window.workspace = workspace
    return workspace, warning


class TW_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    hdri: StringProperty(name="HDRI Environment", subtype="FILE_PATH", default=DEFAULT_HDRI)
    backend: StringProperty(name="Native Backend", subtype="FILE_PATH",
        description="Optional TrackWorkshop.Native.dll override; otherwise use the bundled backend")

    def draw(self, context):
        self.layout.prop(self, "hdri")
        self.layout.prop(self, "backend")
        self.layout.operator("track_workshop.open_workspace", icon="WORKSPACE")


class TW_OT_open_workspace(bpy.types.Operator):
    bl_idname = "track_workshop.open_workspace"
    bl_label = "Open Workspace"
    bl_description = "Open the optional workspace in Solid mode, with floor off and clip end 10000"

    def execute(self, context):
        try:
            _, warning = ensure(context, activate=True)
        except (RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        if warning:
            self.report({"WARNING"}, warning)
        return {"FINISHED"}


class TW_OT_environment_world(bpy.types.Operator):
    bl_idname = "track_workshop.environment_world"
    bl_label = "Use HDRI for Scene World"
    bl_description = "Assign a new World with an Environment Texture; affects rendering throughout this scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        path = hdri_path(context)
        if not path.is_file() or path.suffix.lower() not in (".exr", ".hdr"):
            self.report({"ERROR"}, "Choose an existing EXR or HDR environment in Track Workshop preferences")
            return {"CANCELLED"}
        current = context.scene.world
        if current is not None and current.get("tw_hdri_path") == str(path) and current.use_nodes:
            for node in current.node_tree.nodes:
                if (node.type == "TEX_ENVIRONMENT" and node.image is not None
                        and Path(bpy.path.abspath(node.image.filepath)).resolve() == path
                        and any(link.to_node.type == "BACKGROUND" and link.to_socket.name == "Color"
                                for link in node.outputs["Color"].links)):
                    return {"FINISHED"}
        world = None
        try:
            image = bpy.data.images.load(str(path), check_existing=True)
            world = bpy.data.worlds.new("Track Workshop Environment")
            world["tw_hdri_path"] = str(path)
            world.use_nodes = True
            tree = world.node_tree
            texture = tree.nodes.new("ShaderNodeTexEnvironment")
            texture.image = image
            texture.location = (-300, 0)
            background = next(node for node in tree.nodes if node.type == "BACKGROUND")
            tree.links.new(texture.outputs["Color"], background.inputs["Color"])
            # Keep the former World available even after saving the .blend.
            if context.scene.world is not None:
                context.scene["tw_previous_world"] = context.scene.world
            context.scene.world = world
        except (OSError, RuntimeError) as error:
            if world is not None:
                bpy.data.worlds.remove(world)
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


CLASSES = (TW_Preferences, TW_OT_open_workspace, TW_OT_environment_world)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
