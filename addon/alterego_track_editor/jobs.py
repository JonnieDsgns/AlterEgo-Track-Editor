"""User-started, cooperative jobs. No idle polling and no Blender worker threads."""
import time

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, FloatProperty, StringProperty

_active = None
INTERVAL = 0.03


def busy(context):
    return _active is not None


class TW_OT_cancel_job(bpy.types.Operator):
    bl_idname = "track_workshop.cancel_job"
    bl_label = "Cancel Operation"
    bl_description = "Stop at the next safe step; individual Blender operations cannot be interrupted mid-call"

    def execute(self, context):
        if _active is not None:
            _active.scene.tw_job_cancel = True
        return {"FINISHED"}


class CooperativeJob:
    """Mixin for modal operators whose iterator owns its cancellation cleanup."""
    _timer = None
    _iterator = None

    def start(self, context, iterator):
        global _active
        if _active is not None:
            iterator.close()
            self.report({"WARNING"}, "Another Track Workshop operation is running.")
            return {"CANCELLED"}
        self.scene = context.scene
        self._stopped = False
        self._iterator = iterator
        self.scene.tw_job_running = True
        self.scene.tw_job_cancel = False
        self.scene.tw_job_progress = 0
        self.scene.tw_job_label = self.bl_label
        self._next_tick = time.perf_counter()+INTERVAL
        _active = self
        self._timer = context.window_manager.event_timer_add(INTERVAL, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def finish(self, context):
        global _active
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        self.scene.tw_job_running = False
        self.scene.tw_job_cancel = False
        _active = None
        self._stopped = True

    def modal(self, context, event):
        if self._stopped:
            return {"CANCELLED"}
        if event.type == "ESC" or self.scene.tw_job_cancel or context.scene != self.scene:
            try:
                self._iterator.close()
            finally:
                self.finish(context)
            self.report({"INFO"}, "Operation cancelled.")
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        before = time.perf_counter()
        # Blender Events do not expose the originating Timer. Limit the cadence
        # explicitly so other add-ons' timer events cannot accelerate this job.
        if before < self._next_tick:
            return {"PASS_THROUGH"}
        self._next_tick = before+INTERVAL
        try:
            while time.perf_counter()-before < 0.015:
                update = next(self._iterator)
                progress, label = update[:2]
                self.scene.tw_job_progress = max(0, min(1, progress))
                self.scene.tw_job_label = label
                if len(update) > 2 and update[2]:
                    break
        except StopIteration as done:
            self.finish(context)
            self.completed(context, done.value)
            return {"FINISHED"}
        except Exception as error:
            try:
                self._iterator.close()
            finally:
                self.finish(context)
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        if context.area is not None:
            for region in context.area.regions:
                if region.type == "UI":
                    region.tag_redraw()
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        try:
            if self._iterator is not None:
                self._iterator.close()
        finally:
            self.finish(context)


def drain(iterator):
    while True:
        try:
            next(iterator)
        except StopIteration as done:
            return done.value


@persistent
def reset(*args):
    global _active
    if _active is not None:
        active, _active = _active, None
        active._stopped = True
        try:
            if active._iterator is not None:
                active._iterator.close()
        finally:
            if active._timer is not None:
                bpy.context.window_manager.event_timer_remove(active._timer)
                active._timer = None
            try:
                active.scene.tw_job_running = False
                active.scene.tw_job_cancel = False
            except ReferenceError:
                pass


CLASSES = (TW_OT_cancel_job,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.tw_job_running = BoolProperty(default=False, options={"SKIP_SAVE"})
    bpy.types.Scene.tw_job_cancel = BoolProperty(default=False, options={"SKIP_SAVE"})
    bpy.types.Scene.tw_job_progress = FloatProperty(min=0, max=1, options={"SKIP_SAVE"})
    bpy.types.Scene.tw_job_label = StringProperty(options={"SKIP_SAVE"})
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        handlers.append(reset)


def unregister():
    reset()
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if reset in handlers:
            handlers.remove(reset)
    for name in ("tw_job_running", "tw_job_cancel", "tw_job_progress", "tw_job_label"):
        delattr(bpy.types.Scene, name)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
