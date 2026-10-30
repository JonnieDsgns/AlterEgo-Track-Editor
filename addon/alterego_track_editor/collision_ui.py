"""Native collision surface editing and explicitly legacy authored collision tests."""
import colorsys,hashlib,json,math,struct
from pathlib import Path
import bpy
from bpy.props import EnumProperty,FloatProperty,IntProperty,StringProperty
from mathutils import Vector
from . import marker_ui,jobs,project_store
from .native_project import TrackDocument
from .native_ui import AXES,matrix,native_values
from .physics_terrain import PhysicsTerrain,KNOWN_CODES,build_legacy

CODE_ITEMS=[('UNASSIGNED','Choose native physics code','No automatic mapping from visual materials')]+[(c,c,'Explicit native physics identifier; runtime behavior is not certified here') for c in KNOWN_CODES]
_CODE_CACHE={'keys':None,'items':CODE_ITEMS}


def code_items(self,context):
    """Fixed authoring codes first (stable stored indices), then printable codes found in loaded native collision."""
    root=marker_ui.ui_project(context) if context else None
    extra=[c for c in json.loads(root.get('ate_native_physics_codes','[]')) if c not in KNOWN_CODES and not c.startswith('HEX_')] if root else []
    keys=tuple(extra)
    if keys!=_CODE_CACHE['keys']:
        _CODE_CACHE['keys']=keys
        _CODE_CACHE['items']=[(*item,i) for i,item in enumerate(CODE_ITEMS)]+[(c,c,'Native code used by this track collision',len(CODE_ITEMS)+i) for i,c in enumerate(extra)]
    return _CODE_CACHE['items']


def geometry_signature(data):
    digest=hashlib.sha256()
    digest.update(struct.pack('<II',len(data.vertices),len(data.polygons)))
    for v in data.vertices:digest.update(struct.pack('<3f',*v.co))
    for p in data.polygons:
        digest.update(struct.pack('<I',len(p.vertices)));digest.update(struct.pack('<'+'I'*len(p.vertices),*p.vertices))
    return digest.hexdigest()


def physical_material(code):
    found=next((m for m in bpy.data.materials if m.get('ate_physics_code')==code),None)
    if found:return found
    result=bpy.data.materials.new('Physics '+code);result['ate_physics_code']=code
    hue=int(hashlib.sha256(code.encode()).hexdigest()[:4],16)/65535
    result.diffuse_color=(*colorsys.hsv_to_rgb(hue,.45,.7),1.)
    return result


def collision_group(root,obj):
    if obj is None or 'ate_collision_cell' not in obj:return None
    return next((c for c in root.children if c.get('ate_collision_uri')==obj.get('ate_collision_uri') and any(o==obj for o in c.objects)),None)


def choose_record(context,root,document):
    obj=context.active_object
    if obj:
        record=document.by_id.get(obj.get('ate_native_id'))
        if record and record['physics']:return record
        group=collision_group(root,obj)
        if group:return document.by_id[group['ate_collision_record']]
    variant=context.scene.ate_native_view
    records=[r for r in document.records if r['physics'] and (variant=='ALL' or 'common' in r['variants'] or variant in r['variants'])]
    choices={(r['physics'],tuple(r['world'])):r for r in records}
    if len(choices)!=1:raise ValueError('Choose one preview variant or select its native terrain object')
    return next(iter(choices.values()))


def native_payload(document,uri):
    _,resource=document.catalog.get(uri)
    if resource.type_name!='TRN~' or len(resource.fragments)!=1:raise ValueError('Unsupported native physics resource layout')
    return document.catalog.read(uri)


def load_collision(context,root,document,record,radius,max_cells):
    from .importer import ImportTransaction
    if not all(map(math.isfinite,record['world'])):raise ValueError('Non-finite native collision placement')
    uri=record['physics'];raw=native_payload(document,uri);parsed=PhysicsTerrain(raw);identity=hashlib.sha256(raw).hexdigest()
    existing=next((c for c in root.children if c.get('ate_collision_uri')==uri and json.loads(c.get('ate_collision_world','null'))==record['world']),None)
    if existing and existing.get('ate_collision_hash')!=identity:raise ValueError('Collision source changed; reimport into a fresh project')
    pose=AXES@matrix(record['world'])@AXES.inverted();native_pose=AXES@matrix(record['world'])
    center=context.scene.cursor.location;eligible=[]
    for cell in parsed.cells:
        corners=[native_pose@Vector((x,y,z)) for x in (cell.bounds[0],cell.bounds[3]) for y in (cell.bounds[1],cell.bounds[4]) for z in (cell.bounds[2],cell.bounds[5])]
        lower=[min(v[k] for v in corners) for k in range(3)];upper=[max(v[k] for v in corners) for k in range(3)]
        distance=sum(max(lower[k]-center[k],0.,center[k]-upper[k])**2 for k in range(3))
        if radius<=0 or distance<=radius*radius:eligible.append((distance,cell.index))
    eligible.sort();eligible=eligible[:max_cells]
    if not eligible:raise ValueError('No collision cells near the 3D cursor; move it or increase the radius')
    transaction=ImportTransaction()
    try:
        group=existing or bpy.data.collections.new('Collision '+uri.rsplit('/',1)[-1].split('?')[0])
        if existing is None:root.children.link(group)
        loaded=set(json.loads(group.get('ate_collision_cells','[]')));shown=[]
        for _,index in eligible:
            old=next((o for o in group.objects if o.get('ate_collision_cell')==index),None)
            if old:shown.append(old);continue
            cell=parsed.cells[index];faces=list(cell.faces())
            if any(len(set(f[:3]))!=3 for f in faces):raise ValueError('Native cell contains degenerate faces; choose a different preview region')
            data=bpy.data.meshes.new(cell.name);data.from_pydata([tuple(AXES.to_3x3()@Vector(p)) for p in cell.positions()],[],[f[:3] for f in faces])
            used={f[3] for f in faces}
            for i,code in enumerate(cell.palette):data.materials.append(physical_material(code) if i in used else None)
            for polygon,face in zip(data.polygons,faces):polygon.material_index=face[3]
            obj=bpy.data.objects.new(cell.name,data);group.objects.link(obj);obj.matrix_world=pose
            obj['tw_project_id']=root['tw_project_id'];obj['ate_reference_only']=True;obj.hide_render=True
            obj['ate_collision_cell']=index;obj['ate_collision_uri']=uri
            obj['ate_collision_geometry']=geometry_signature(data);obj['ate_collision_pose']=native_values(obj.matrix_world)
            loaded.add(index);shown.append(obj)
        group['ate_collision_uri']=uri;group['ate_collision_record']=record['id'];group['ate_collision_hash']=identity
        group['ate_collision_world']=json.dumps(record['world'])
        group['ate_collision_cells']=json.dumps(sorted(loaded));group['ate_collision_version']=parsed.version
        known=set(json.loads(root.get('ate_native_physics_codes','[]')))|{c for cell in parsed.cells for c in cell.codes()}
        root['ate_native_physics_codes']=json.dumps(sorted(known))
        for obj in list(context.selected_objects):obj.select_set(False)
        shown_set=set(shown)
        for obj in group.objects:obj.hide_set(obj not in shown_set)
        for obj in shown:obj.hide_set(False);obj.select_set(True)
        context.view_layer.objects.active=shown[0]
        return group,len(shown),len(parsed.cells)
    except BaseException:transaction.rollback();raise


def surface_changes(context,group,parsed):
    for obj in group.objects:obj.update_from_editmode()
    context.view_layer.update();found={};changes={}
    expected=set(json.loads(group['ate_collision_cells']))
    for obj in group.objects:
        index=obj.get('ate_collision_cell')
        if index not in expected or index in found:raise ValueError('Duplicated or unexpected collision preview cell')
        if obj.type!='MESH' or obj.modifiers or obj.data.shape_keys or obj.constraints or obj.animation_data:
            raise ValueError('Native collision geometry editing is not supported; only physical code assignment')
        if geometry_signature(obj.data)!=obj['ate_collision_geometry'] or max(abs(a-b) for a,b in zip(native_values(obj.matrix_world),obj['ate_collision_pose']))>1e-5:
            raise ValueError('Collision geometry or placement changed; native search rebuilding is not verified')
        found[index]=obj;codes=[]
        for polygon in obj.data.polygons:
            material=obj.material_slots[polygon.material_index].material if polygon.material_index<len(obj.material_slots) else None
            code=material.get('ate_physics_code') if material else None
            if not code:raise ValueError('Every collision face needs an explicit physics material')
            codes.append(code)
        if codes!=parsed.cells[index].codes():changes[index]=codes
    if set(found)!=expected:raise ValueError('A loaded collision cell was removed; geometry deletion is not supported')
    return changes


REBUILD_NOTE=('Experimental legacy 0x20002 rebuild of the whole track collision. Community Istanbul ports on Spa/Sepang '
              'bases reported this format working when only the base track\'s own codes were used; it is not verified for '
              'this track. Native 0x20004 search records are not reused.')


def rebuilt_collision(context,root,document):
    """Whole-track legacy collision: unloaded native cells, edited preview cells and authored collision meshes.

    Returns (physics uri, JPAK bytes, report). Codes are restricted to those the base collision uses.
    """
    from .physics_terrain import build_legacy,triangle_soup,code_words
    records=[r for r in document.records if r['physics']]
    uris=sorted({r['physics'] for r in records})
    if len(uris)!=1:raise ValueError('Collision rebuild needs exactly one native physics terrain; found '+str(len(uris)))
    uri=uris[0];record=next(r for r in records if r['physics']==uri)
    raw=native_payload(document,uri);parsed=PhysicsTerrain(raw);identity=hashlib.sha256(raw).hexdigest()
    allowed=sorted({code for cell in parsed.cells for code in cell.codes()});words=code_words(parsed)
    native_pose=AXES@matrix(record['world']);local=native_pose.inverted()
    for obj in context.view_layer.objects:
        if obj.mode=='EDIT':obj.update_from_editmode()
    context.view_layer.update()
    edited={};groups=[c for c in root.children if c.get('ate_collision_uri')==uri]
    for group in groups:
        if group.get('ate_collision_hash')!=identity:raise ValueError('Collision preview source changed; reimport before rebuilding')
        expected=set(json.loads(group['ate_collision_cells']));found=set()
        for obj in group.objects:
            index=obj.get('ate_collision_cell')
            if index not in expected or index in found or index in edited:raise ValueError('Duplicated or unexpected collision preview cell')
            if obj.type!='MESH' or obj.modifiers or obj.data.shape_keys or obj.constraints or obj.animation_data:
                raise ValueError('Apply modifiers/shape keys on collision previews before rebuilding: '+obj.name)
            found.add(index);cell=parsed.cells[index]
            native_words={tuple(p):struct.unpack_from('<I',cell.data,144+i*16+12)[0] for i,p in enumerate(cell.positions())}
            data=obj.data;data.calc_loop_triangles();transform=local@obj.matrix_world;faces=[]
            for triangle in data.loop_triangles:
                material=obj.material_slots[triangle.material_index].material if triangle.material_index<len(obj.material_slots) else None
                code=material.get('ate_physics_code') if material else None
                if not code:raise ValueError('Every collision face needs an explicit physics material: '+obj.name)
                points=[tuple(transform@data.vertices[i].co) for i in triangle.vertices]
                faces.append((*points,code,tuple(native_words.get(tuple(struct.unpack('<3f',struct.pack('<3f',*p))),words.get(code,0xff808080)) for p in points)))
            edited[index]=faces
        if found!=expected:raise ValueError('A loaded collision cell was removed; delete faces inside it instead')
    triangles=[]
    for cell in parsed.cells:
        if cell.index in edited:triangles.extend(edited[cell.index]);continue
        triangles.extend(triangle_soup([cell]))
    authored=0;objects=set()
    world=matrix(record['world']).inverted()
    for obj in root.all_objects:
        if obj.type!='MESH' or not obj.tw_surface.collision or obj.get('ate_reference_only') or 'ate_collision_cell' in obj:continue
        code=obj.ate_physics_code
        if code=='UNASSIGNED':raise ValueError('Choose an explicit native physics code for '+obj.name)
        if code not in allowed:raise ValueError(f'{obj.name}: {code} is not used by this track\'s collision; community ports lost whole chunks with foreign codes')
        if obj.animation_data or obj.constraints:raise ValueError('Animated/constrained collision is unsupported: '+obj.name)
        evaluated=obj.evaluated_get(context.evaluated_depsgraph_get());data=evaluated.to_mesh()
        try:
            data.calc_loop_triangles();transform=world@AXES.inverted()@obj.matrix_world
            if abs(transform.determinant())<1e-10:raise ValueError('Singular authored collision transform: '+obj.name)
            for face in data.loop_triangles:
                points=[tuple(transform@data.vertices[i].co) for i in face.vertices]
                if transform.determinant()<0:points[1],points[2]=points[2],points[1]
                triangles.append((*points,code));authored+=1
        finally:evaluated.to_mesh_clear()
        objects.add(obj.name)
    payload=build_legacy(triangles,codes=allowed,words=words)
    report={'uri':uri,'native_triangles':sum(c.triangles for c in parsed.cells),'edited_cells':sorted(edited),
        'authored_triangles':authored,'authored_objects':sorted(objects),'triangles':len(triangles),
        'cells':len(PhysicsTerrain(payload,0x20002).cells),'codes':allowed,'version':'0x20002','note':REBUILD_NOTE,'game_verified':False}
    return uri,payload,report


class ATE_OT_load_collision(bpy.types.Operator):
    bl_idname='alterego_track.load_collision';bl_label='Load Native Collision';bl_options={'REGISTER','UNDO'}
    radius:FloatProperty(name='Radius around 3D cursor (m)',default=250,min=0,description='Zero includes all cells within the preview budget')
    max_cells:IntProperty(name='Preview cell limit',default=500,min=1,max=5000)
    @classmethod
    def poll(cls,context):
        root=marker_ui.ui_project(context);return root is not None and bool(root.get('ate_native_source')) and not jobs.busy(context)
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self)
    def execute(self,context):
        document=None
        try:
            root=marker_ui.project(context)
            if project_store.check_sources(json.loads(root['ate_sources'])):raise ValueError('Source changed; reimport before editing')
            document=TrackDocument(root['ate_native_source'],root.get('ate_native_base') or None)
            group,count,total=load_collision(context,root,document,choose_record(context,root,document),self.radius,self.max_cells)
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        finally:
            if document:document.close()
        self.report({'INFO'},f'{count} of {total} collision cells shown; geometry is read-only, physical codes are editable')
        return {'FINISHED'}


class ATE_OT_assign_collision_code(bpy.types.Operator):
    bl_idname='alterego_track.assign_collision_code';bl_label='Assign Physics Code';bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return context.active_object is not None and 'ate_collision_cell' in context.active_object and not jobs.busy(context)
    def execute(self,context):
        obj=context.active_object;code=context.scene.ate_collision_code
        if code=='UNASSIGNED':self.report({'ERROR'},'Choose an explicit native code');return {'CANCELLED'}
        material=physical_material(code)
        objects=context.objects_in_mode_unique_data if obj.mode=='EDIT' else context.selected_objects
        count=0
        for target in objects:
            if 'ate_collision_cell' not in target or target.get('tw_project_id')!=obj.get('tw_project_id'):continue
            index=next((i for i,s in enumerate(target.material_slots) if s.material==material),None)
            if index is None:index=len(target.data.materials);target.data.materials.append(material)
            if target.mode=='EDIT':
                import bmesh
                mesh=bmesh.from_edit_mesh(target.data)
                for face in mesh.faces:
                    if face.select:face.material_index=index;count+=1
                bmesh.update_edit_mesh(target.data)
            else:
                for face in target.data.polygons:face.material_index=index;count+=1
        self.report({'INFO'},f'Assigned {code} to {count} selected collision faces')
        return {'FINISHED'}


class ATE_OT_export_collision_surfaces(bpy.types.Operator):
    bl_idname='alterego_track.export_collision_surfaces';bl_label='Export Collision Surface Update'
    filepath:StringProperty(subtype='FILE_PATH')
    def draw(self,context):
        self.layout.label(text='Track folder source: filename stem becomes a new folder.')
        self.layout.label(text='Addon source: choose a new ZIP filename.')
        self.layout.label(text='Only collision code edits are included; geometry stays unchanged.')
    @classmethod
    def poll(cls,context):
        root=marker_ui.ui_project(context)
        return root is not None and context.active_object is not None and collision_group(root,context.active_object) is not None and not jobs.busy(context)
    def invoke(self,context,event):context.window_manager.fileselect_add(self);return {'RUNNING_MODAL'}
    def execute(self,context):
        document=None
        try:
            root=marker_ui.project(context);group=collision_group(root,context.active_object)
            if project_store.check_sources(json.loads(root['ate_sources'])):raise ValueError('Source changed; reimport before exporting')
            document=TrackDocument(root['ate_native_source'],root.get('ate_native_base') or None)
            uri=group['ate_collision_uri'];raw=native_payload(document,uri)
            if hashlib.sha256(raw).hexdigest()!=group['ate_collision_hash']:raise ValueError('Collision source changed; reimport')
            parsed=PhysicsTerrain(raw);changes={}
            for candidate in root.children:
                if candidate.get('ate_collision_uri')!=uri:continue
                if candidate.get('ate_collision_hash')!=group['ate_collision_hash']:raise ValueError('A shared collision preview has stale source data')
                for index,codes in surface_changes(context,candidate,parsed).items():
                    if index in changes and changes[index]!=codes:raise ValueError('Conflicting assignments in shared collision previews')
                    changes[index]=codes
            edited=parsed.edit_codes(changes)
            output=Path(bpy.path.abspath(self.filepath));output=output if document.is_addon else output.with_suffix('')
            document.write_updated(output,{uri:edited})
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        finally:
            if document:document.close()
        self.report({'INFO'},f'Updated physical codes in {len(changes)} cells; native geometry/search data preserved; game verification pending')
        return {'FINISHED'}


def authored_faces(context):
    count=0
    for obj in context.selected_objects:
        if obj.type!='MESH' or not obj.tw_surface.collision:continue
        if obj.get('ate_reference_only') or obj.get('tw_is_marker') or obj.animation_data or obj.constraints:
            raise ValueError('Select static authored collision meshes, not native preview/reference objects')
        code=obj.ate_physics_code
        if code=='UNASSIGNED':raise ValueError('Choose an explicit native physics code for '+obj.name)
        obj.update_from_editmode();context.view_layer.update()
        evaluated=obj.evaluated_get(context.evaluated_depsgraph_get());data=evaluated.to_mesh()
        try:
            data.calc_loop_triangles();transform=AXES.inverted()@obj.matrix_world
            if not all(math.isfinite(v) for row in transform for v in row):raise ValueError('Non-finite authored collision transform')
            determinant=transform.determinant()
            if abs(determinant)<1e-10:raise ValueError('Singular authored collision transform')
            for face in data.loop_triangles:
                points=[tuple(transform@data.vertices[i].co) for i in face.vertices]
                if determinant<0:points[1],points[2]=points[2],points[1]
                count+=1;yield (*points,code)
        finally:evaluated.to_mesh_clear()
    if not count:raise ValueError('Select meshes with Collision enabled and explicit native physics codes')


class ATE_OT_export_legacy_collision(bpy.types.Operator):
    bl_idname='alterego_track.export_legacy_collision';bl_label='Export Legacy Collision Test'
    filepath:StringProperty(subtype='FILE_PATH')
    filter_glob:StringProperty(default='*.jpak',options={'HIDDEN'})
    def draw(self,context):
        self.layout.label(text='Legacy construction test only.')
        self.layout.label(text='Not a native F1 25 replacement or installable track.')
    @classmethod
    def poll(cls,context):
        obj=context.active_object
        return obj is not None and obj.type=='MESH' and obj.tw_surface.collision and not obj.get('ate_reference_only') and not jobs.busy(context)
    def invoke(self,context,event):context.window_manager.fileselect_add(self);return {'RUNNING_MODAL'}
    def execute(self,context):
        try:
            output=Path(bpy.path.abspath(self.filepath)).resolve()
            if output.exists() or output.suffix.lower()!='.jpak':raise ValueError('Choose a new .jpak test filename')
            if any((p/'F1_25.exe').exists() for p in output.parents):raise ValueError('Export outside the game installation')
            payload=build_legacy(authored_faces(context));output.parent.mkdir(parents=True,exist_ok=True)
            with output.open('xb') as file:
                try:file.write(payload)
                except BaseException:
                    file.close();output.unlink(missing_ok=True);raise
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},'Legacy 0x20002 collision test only; not a native F1 25 replacement or a game-ready package')
        return {'FINISHED'}


class ATE_PT_collision(bpy.types.Panel):
    bl_label='Collision';bl_idname='ATE_PT_collision';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='AlterEgo Track Editor'
    @classmethod
    def poll(cls,context):return marker_ui.ui_project(context) is not None
    def draw(self,context):
        layout=self.layout;root=marker_ui.ui_project(context);obj=context.active_object
        if root.get('ate_native_source'):
            layout.operator('alterego_track.load_collision')
            if obj and 'ate_collision_cell' in obj:
                layout.prop(context.scene,'ate_collision_code');layout.operator('alterego_track.assign_collision_code')
                layout.label(text='Edit: selected faces; Object: selected cells')
                layout.operator('alterego_track.export_collision_surfaces')
                layout.label(text='Native geometry/search data is read-only')
        if obj and 'ate_collision_cell' in obj:
            layout.label(text='Geometry edits apply only with the collision rebuild option')
        if obj and obj.type=='MESH' and not obj.get('ate_reference_only'):
            layout.prop(obj.tw_surface,'collision');layout.prop(obj,'ate_physics_code')
        layout.operator('alterego_track.export_legacy_collision')
        layout.label(text='Whole-track rebuild: Export Updated Native Track option')
        layout.label(text='Experimental legacy format; not verified for this track')


CLASSES=(ATE_OT_load_collision,ATE_OT_assign_collision_code,ATE_OT_export_collision_surfaces,ATE_OT_export_legacy_collision,ATE_PT_collision)
def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.Scene.ate_collision_code=EnumProperty(name='Native physics code',items=code_items,default=0)
    bpy.types.Object.ate_physics_code=EnumProperty(name='Authored physics code',items=code_items,default=0)
def unregister():
    del bpy.types.Object.ate_physics_code;del bpy.types.Scene.ate_collision_code
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
