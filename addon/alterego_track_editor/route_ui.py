"""Blender previews of native routes and editable gameplay track-markup intervals."""
import hashlib
import json
import bpy
from mathutils import Matrix, Vector
from . import jobs, marker_ui, project_store
from .native_project import TrackDocument
from .native_routes import Spline, SECTORS

AXES = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
COLOURS = {'sector': (1.0, 0.85, 0.1, 1), 'drs': (0.1, 0.8, 1.0, 1), 'ers': (0.6, 0.3, 1.0, 1), 'x_mode': (0.9, 0.3, 0.9, 1),
           'pit': (1.0, 0.4, 0.1, 1), 'other': (0.8, 0.8, 0.8, 1)}


def to_blender(point):
    return AXES @ Vector(point)


def to_native(point):
    return list(AXES.inverted() @ Vector(point))


def routes_collection(root):
    return next((c for c in root.children if c.get('ate_routes')), None)


def colour(types):
    key = next((k for k in ('sector', 'drs', 'ers', 'x_mode', 'pit') if any(t.startswith(k) or k in t for t in types)), 'other')
    return COLOURS[key]


def curve_object(name, points, collection, root, bevel=0.0, cyclic=False):
    data = bpy.data.curves.new(name, 'CURVE')
    data.dimensions = '3D'
    data.bevel_depth = bevel
    spline = data.splines.new('POLY')
    spline.points.add(len(points) - 1)
    for target, point in zip(spline.points, points):
        target.co = (*to_blender(point), 1.0)
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj['tw_project_id'] = root['tw_project_id']
    obj['ate_reference_only'] = True
    obj.hide_render = True
    return obj


def stored_spline(collection, name):
    knots = json.loads(collection['ate_route_splines'])[name]
    return Spline(name, knots['points'], knots['closed'])


def refresh_marker(obj, collection):
    spline = stored_spline(collection, obj['ate_tm_spline'])
    points = spline.segment(float(obj['ate_tm_start']), float(obj['ate_tm_end']))
    data = obj.data
    data.splines.clear()
    target = data.splines.new('POLY')
    target.points.add(len(points) - 1)
    for point, value in zip(target.points, points):
        point.co = (*to_blender(value), 1.0)


def load_routes(context, root, document):
    routes = document.routes()
    collection = routes_collection(root)
    edits = {}
    if collection is not None:
        # Keep authored interval values; rebuild previews from the current source.
        edits = {o['ate_tm_index']: (o['ate_tm_start'], o['ate_tm_end']) for o in collection.objects if 'ate_tm_index' in o}
        for obj in list(collection.objects):
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                bpy.data.curves.remove(data)
    else:
        collection = bpy.data.collections.new('Native Routes and Markup')
        collection['ate_routes'] = True
        collection['tw_collection_owner'] = root['tw_project_id']
        root.children.link(collection)
    collection['ate_route_splines'] = json.dumps({n: {'points': s.points, 'closed': s.closed} for n, s in routes.splines.items()})
    collection['ate_route_tm_hash'] = hashlib.sha256(routes.tm_raw).hexdigest()
    for name, spline in routes.splines.items():
        curve_object('Route '+name, spline.points, collection, root, cyclic=spline.closed)
    if routes.ai:
        for route in ('track', 'pit'):
            for waypoint in ('racing_line', 'left_track_limit', 'right_track_limit'):
                try:
                    points = routes.ai_line(route, waypoint)
                except StopIteration:
                    continue
                if len(points) > 1:
                    curve_object(f'AI {route} {waypoint}', points, collection, root)
    count = 0
    for row in routes.markup:
        if not row['gameplay'] or row['spline'] not in routes.splines:
            continue
        start, end = edits.get(row['index'], (row['start'], row['end']))
        obj = curve_object('Markup '+row['name'], [[0, 0, 0], [0, 0, 1]], collection, root, bevel=0.6)
        obj['ate_tm_index'] = row['index']
        obj['ate_tm_spline'] = row['spline']
        obj['ate_tm_types'] = json.dumps(row['types'])
        obj['ate_tm_original'] = json.dumps([row['start'], row['end']])
        obj['ate_tm_start'] = float(start)
        obj['ate_tm_end'] = float(end)
        obj.color = colour(row['types'])
        refresh_marker(obj, collection)
        count += 1
    return collection, count


def markup_edits(root, document):
    """Changed gameplay intervals {element index: (start, end)}; refuses stale route sources."""
    collection = routes_collection(root)
    if collection is None:
        return {}
    edits = {}
    for obj in collection.objects:
        if 'ate_tm_index' not in obj:
            continue
        values = (float(obj['ate_tm_start']), float(obj['ate_tm_end']))
        if [round(v, 6) for v in values] != [round(v, 6) for v in json.loads(obj['ate_tm_original'])]:
            edits[int(obj['ate_tm_index'])] = values
    if edits and hashlib.sha256(document.routes().tm_raw).hexdigest() != collection.get('ate_route_tm_hash'):
        raise ValueError('Track markup source changed; use Load Native Routes again before exporting')
    return edits


def markers(collection):
    return [o for o in collection.objects if 'ate_tm_index' in o]


class ATE_OT_load_routes(bpy.types.Operator):
    bl_idname = 'alterego_track.load_native_routes'
    bl_label = 'Load Native Routes'
    bl_description = 'Show native main/pit splines, AI lines and editable gameplay markup intervals; existing interval edits are kept'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        root = marker_ui.ui_project(context)
        return root is not None and bool(root.get('ate_native_source')) and context.mode == 'OBJECT' and not jobs.busy(context)

    def execute(self, context):
        root = marker_ui.project(context)
        document = None
        try:
            if project_store.check_sources(json.loads(root['ate_sources'])):
                raise ValueError('Source files changed or are missing; reimport first')
            document = TrackDocument(root['ate_native_source'], root.get('ate_native_base') or None)
            _, count = load_routes(context, root, document)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            if document:
                document.close()
        self.report({'INFO'}, f'Loaded routes and {count} editable markup intervals; route geometry is preview only')
        return {'FINISHED'}


class ATE_OT_markup_at_cursor(bpy.types.Operator):
    bl_idname = 'alterego_track.markup_at_cursor'
    bl_label = 'Set Markup Position at 3D Cursor'
    bl_description = 'Set the active interval start or end to the closest spline position; sector boundaries stay linked'
    bl_options = {'REGISTER', 'UNDO'}
    side: bpy.props.EnumProperty(items=[('START', 'Start', ''), ('END', 'End', '')])

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and 'ate_tm_index' in obj

    def execute(self, context):
        obj = context.active_object
        collection = next(c for c in obj.users_collection if c.get('ate_routes'))
        spline = stored_spline(collection, obj['ate_tm_spline'])
        fraction, distance = spline.nearest(to_native(context.scene.cursor.location))
        fraction = round(fraction, 6)
        types = json.loads(obj['ate_tm_types'])
        sector = next((t for t in types if t in SECTORS), None)
        if sector and ((sector == 'sector_1' and self.side == 'START') or (sector == 'sector_3' and self.side == 'END')):
            self.report({'ERROR'}, 'The lap start is fixed; move sector boundaries only')
            return {'CANCELLED'}
        obj['ate_tm_start' if self.side == 'START' else 'ate_tm_end'] = fraction
        changed = [obj]
        if sector:
            # Boundary shared with the neighbouring sector.
            index = SECTORS.index(sector) + (1 if self.side == 'END' else -1)
            neighbour = next((o for o in markers(collection) if SECTORS[index] in json.loads(o['ate_tm_types'])), None)
            if neighbour is not None:
                neighbour['ate_tm_end' if self.side == 'START' else 'ate_tm_start'] = fraction
                changed.append(neighbour)
        for item in changed:
            refresh_marker(item, collection)
        self.report({'INFO'}, f'{self.side.title()} = {fraction} ({distance:.1f} m from cursor; spline position approximate)')
        return {'FINISHED'}


class ATE_OT_refresh_markup(bpy.types.Operator):
    bl_idname = 'alterego_track.refresh_markup_preview'
    bl_label = 'Refresh Markup Preview'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        root = marker_ui.ui_project(context)
        return root is not None and routes_collection(root) is not None

    def execute(self, context):
        collection = routes_collection(marker_ui.project(context))
        try:
            for obj in markers(collection):
                refresh_marker(obj, collection)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class ATE_PT_routes(bpy.types.Panel):
    bl_label = 'Native Routes and Markup'
    bl_idname = 'ATE_PT_routes'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'AlterEgo Track Editor'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        root = marker_ui.ui_project(context)
        return root is not None and bool(root.get('ate_native_source'))

    def draw(self, context):
        layout = self.layout
        layout.operator('alterego_track.load_native_routes', icon='CURVE_PATH')
        obj = context.active_object
        if obj is not None and 'ate_tm_index' in obj:
            box = layout.box()
            box.label(text=obj.name[len('Markup '):] if obj.name.startswith('Markup ') else obj.name)
            box.label(text=', '.join(json.loads(obj['ate_tm_types'])) + ' on ' + obj['ate_tm_spline'])
            box.prop(obj, '["ate_tm_start"]', text='Start')
            box.prop(obj, '["ate_tm_end"]', text='End')
            row = box.row(align=True)
            row.operator('alterego_track.markup_at_cursor', text='Start at Cursor').side = 'START'
            row.operator('alterego_track.markup_at_cursor', text='End at Cursor').side = 'END'
            box.operator('alterego_track.refresh_markup_preview', icon='FILE_REFRESH')
        layout.label(text='Fractions are exact; spline positions are approximate', icon='INFO')
        layout.label(text='Route and AI geometry are preview only')


CLASSES = (ATE_OT_load_routes, ATE_OT_markup_at_cursor, ATE_OT_refresh_markup, ATE_PT_routes)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
