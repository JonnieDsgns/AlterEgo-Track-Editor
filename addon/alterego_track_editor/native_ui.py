"""Blender native track placement editing with explicit export boundaries."""
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import uuid
import bpy
from bpy.props import StringProperty, EnumProperty, BoolProperty
from mathutils import Matrix
from . import collection_layout, marker_ui, project_ui, project_store, ui_cache, jobs, variants, native_project
from .importer import ImportTransaction
from .native_project import TrackDocument

AXES = Matrix(((1,0,0,0),(0,0,-1,0),(0,1,0,0),(0,0,0,1)))


def matrix(values):
    return Matrix([values[i::4] for i in range(4)])


def native_values(value):
    return [float(value[r][c]) for c in range(4) for r in range(4)]


def mesh_signature(mesh):
    h = hashlib.sha256()
    for v in mesh.vertices:
        h.update(struct.pack('<3f', *v.co))
    for face in mesh.polygons:
        h.update(struct.pack('<I', len(face.vertices)))
        h.update(struct.pack('<'+'I'*len(face.vertices), *face.vertices))
        h.update(struct.pack('<I?', face.material_index, face.use_smooth))
    for normal in mesh.corner_normals:
        h.update(struct.pack('<3f',*(round(float(n),5) for n in normal.vector)))
    for uv in mesh.uv_layers:
        for v in uv.data:
            h.update(struct.pack('<2f', *v.uv))
    return h.hexdigest()


def create_mesh(key, geometry):
    import numpy as np
    pos = np.frombuffer(geometry.positions, dtype='<f4').reshape(-1,3)
    if not np.isfinite(pos).all():
        raise ValueError('Non-finite native vertices cannot be previewed')
    positions = [(float(x),float(-z),float(y)) for x,y,z in pos]
    indices = np.frombuffer(geometry.indices, dtype='<u4').reshape(-1,3)
    data = bpy.data.meshes.new(key.rsplit('/',1)[-1][:60])
    data.from_pydata(positions, [], indices.tolist())
    if data.validate(clean_customdata=False):
        bpy.data.meshes.remove(data)
        raise ValueError('Native topology needs Blender repairs; source preserved without a mesh preview')
    data.update()
    for index, raw in enumerate(geometry.uvs):
        uv = np.frombuffer(raw,dtype='<f4').reshape(-1,2)
        layer = data.uv_layers.new(name=f'UV{index}')
        # Image coordinates follow the existing glTF/TrackView preview contract.
        layer.data.foreach_set('uv', [float(n) for loop in data.loops for n in uv[loop.vertex_index]])
    if geometry.normals:
        normals = np.frombuffer(geometry.normals, dtype='<f4').reshape(-1,3)
        if len(normals)!=len(data.vertices) or not np.isfinite(normals).all():
            bpy.data.meshes.remove(data)
            raise ValueError('Invalid native normals; source preserved')
        converted=[(float(x),float(-z),float(y)) for x,y,z in normals]
        if data.loops:
            data.normals_split_custom_set([converted[loop.vertex_index] for loop in data.loops])
    data['ate_original_geometry'] = mesh_signature(data)
    return data


def native_collection(root, collections, keys):
    targets = []
    if 'common' in keys:
        return [collections['COMMON_OBJECTS']]
    for key in keys:
        role, label = variants.role(key)
        if role in collections:
            targets.append(collections[role])
            continue
        container = collection_layout.find(root, 'NATIVE_VARIANTS')
        if container is None:
            container = bpy.data.collections.new('Additional Native Variants')
            container['tw_collection_role']='NATIVE_VARIANTS'
            container['tw_collection_owner']=root['tw_project_id']
            collections['EXPORT'].children.link(container)
        target = collection_layout.find(root, role)
        if target is None:
            target = bpy.data.collections.new(label)
            target['tw_collection_role']=role
            target['tw_collection_owner']=root['tw_project_id']
            container.children.link(target)
        targets.append(target)
    return targets


_VIEW_ITEMS=[]
_VIEW_KEYS=None

def view_items(self,context):
    global _VIEW_ITEMS,_VIEW_KEYS
    root=marker_ui.ui_project(context) if context else None
    extra=json.loads(root.get('ate_native_variants','{}')).get('additional',[]) if root else []
    keys=tuple(dict.fromkeys(['ALL',*variants.CORE,*extra]))
    if keys!=_VIEW_KEYS:
        _VIEW_KEYS=keys
        _VIEW_ITEMS=[(key,'All Variants' if key=='ALL' else variants.role(key)[1],
                      'Preview visibility only; export still preserves all variants',index) for index,key in enumerate(keys)]
    return _VIEW_ITEMS


def select_view(self,context):
    root=marker_ui.ui_project(context)
    if root is None or not root.get('ate_native_source'):return
    selected=self.ate_native_view
    selected_role=variants.role(selected)[0]
    def walk(layer,inside=False):
        inside=inside or layer.collection==root
        if inside:
            role=layer.collection.get('tw_collection_role','')
            if role in ('YEAR_2025','YEAR_2026','NATIVE_VARIANTS'):
                layer.hide_viewport=False
            elif role in {r[0] for k,r in variants.CORE.items() if k!='common'} or role.startswith('NATIVE_'):
                layer.hide_viewport=selected!='ALL' and role!=selected_role
        for child in layer.children:walk(child,inside)
    walk(context.view_layer.layer_collection)


def import_steps(context, source, base=''):
    document = TrackDocument(source, base or None)
    transaction = ImportTransaction()
    root = None
    meshes = {}
    mesh_groups = {}
    from .native_materials import PreviewMaterials
    previews = PreviewMaterials(document.catalog)
    warnings = list(document.warnings)
    try:
        root = bpy.data.collections.new(document.code)
        context.scene.collection.children.link(root)
        project_ui.initialize(root)
        root['ate_track_code']=document.code
        root['tw_import_pending']=True
        root['ate_native_source']=str(document.source)
        root['ate_native_base']=document.base
        root['ate_native_variants']=json.dumps(variants.inventory(document.worlds))
        collections = collection_layout.ensure(root)
        root['ate_native_identities']=json.dumps({r['id']:r['layer_hash'] for r in document.records})
        for index, record in enumerate(document.records):
            key_geometry = None
            try:
                if record['model']:
                    known_key=record['model'].removesuffix('?context=render')+'?lod=0&mesh'
                    if known_key in meshes and not record['render_error']:
                        key_geometry=(known_key,mesh_groups.get(known_key))
                    else:
                        key_geometry = document.geometry(record)
            except (ValueError, KeyError) as exc:
                warnings.append({'name':record['name'],'reason':str(exc)})
            data = None
            if key_geometry:
                key, geometry = key_geometry
                if key not in meshes:
                    mesh_groups[key]=SimpleNamespace(groups=geometry.groups or [{'first':0,'count':len(geometry.indices)//4,'slot':'Default'}],indices=b'')
                    try:
                        meshes[key] = create_mesh(key,geometry)
                    except ValueError as exc:
                        meshes[key] = None
                        warnings.append({'name':record['name'],'reason':str(exc)})
                data = meshes[key]
            obj = bpy.data.objects.new(record['name'], data)
            targets = native_collection(root,collections,record['variants'])
            for target in targets:
                target.objects.link(obj)
            obj['tw_project_id']=root['tw_project_id']
            obj['tw_asset_id']=record['id']
            obj['ate_native_id']=record['id']
            obj['ate_native_template']=record['template']
            obj['ate_native_world']=record['world']
            obj['ate_native_render']=record['render']
            obj['ate_native_editable']=record['editable'] and not bool(record['render_error'])
            obj['ate_native_cloneable']=not record['clone_reason'] and not record['render_error']
            obj['ate_native_race']=not record['race_reason']
            obj['ate_native_binding']=record['binding'] or ''
            obj['ate_native_surface_snapshot']=json.dumps([obj.tw_surface.surface,obj.tw_surface.collision])
            obj['ate_imported_roles']=json.dumps(sorted(c['tw_collection_role'] for c in targets))
            obj.matrix_world=AXES @ matrix(record['world']) @ matrix(record['render']) @ AXES.inverted()
            obj['ate_imported_pose']=native_values(obj.matrix_world)
            if data is not None:
                previews.assign(obj,geometry,record['binding'])
            if data is None:
                obj.empty_display_type='PLAIN_AXES'
                obj.empty_display_size=1.0
            if record['terrain']:
                try:
                    for key,g in document.terrain_geometry(record):
                        from .native.terrain_materials import surface_world_uvs,bake_terrain
                        appearance=previews.native.resolve(None,'',g.groups[0]['material'])
                        appearance=surface_world_uvs(g,appearance)
                        appearance=bake_terrain(previews.native,g,appearance,key,lambda:g,size=128)
                        g.groups[0]['appearance']=appearance
                        if key not in meshes:
                            meshes[key]=create_mesh(key,g)
                        child=bpy.data.objects.new('Terrain '+key.rsplit('#',1)[-1],meshes[key])
                        for target in targets:
                            target.objects.link(child)
                        child.parent=obj
                        child['ate_native_preview']=True
                        child['tw_project_id']=root['tw_project_id']
                        child['ate_imported_pose']=native_values(child.matrix_basis)
                        previews.assign(child,g,None)
                        if '#'+str(appearance.get('base','')) in appearance.get('id',''):
                            previews.native.textures.pop(appearance.get('base'),None)
                except (ValueError,KeyError) as exc:
                    warnings.append({'name':record['name'],'reason':str(exc)})
            if index%40==0:
                transaction.pause()
                yield index/max(1,len(document.records)),f'Importing native objects: {index+1}/{len(document.records)}'
                transaction.resume()
        transient=[]
        if document.addon_scene:
            transient.extend(Path(t.name) for t in document.addon_scene._addon_temp if t)
        if document.package_temporary:
            transient.append(Path(document.package_temporary.name))
        persistent=lambda p: not any(Path(p).is_relative_to(t) for t in transient)
        paths={a.path for a in document.catalog.archives if persistent(a.path)}
        paths.update(p for p in previews.native.source_identities if persistent(p))
        identities = [project_store.fingerprint(p) for p in sorted(paths, key=str)]
        if document.source.is_file():
            identities.append(project_store.fingerprint(document.source))
        root['ate_sources']=json.dumps(identities)
        warnings.extend(previews.warnings)
        warnings.extend({'material':key,'reason':value} for key,value in previews.native.warnings.items())
        root['ate_native_warnings']=json.dumps(warnings)
        root['ate_native_stats']=json.dumps({'instances':len(document.records),'mesh_objects':sum(o.type=='MESH' for o in root.all_objects),'warnings':len(warnings)})
        report=bpy.data.texts.new(document.code+' Native Import Report')
        report.write(json.dumps({'variants':variants.inventory(document.worlds),'warnings':warnings},indent=2))
        root['ate_import_report']=report.name
        root['tw_import_pending']=False
        context.scene.tw_marker_project=root
        context.scene.tw_project_pinned=True
        ui_cache.invalidate('project')
        context.scene.ate_native_view='f1' if 'f1' in document.worlds else next((k for k in variants.REQUIRED if k in document.worlds),'common')
        ui_cache.invalidate('project')
        return root,warnings
    except BaseException:
        transaction.rollback()
        raise
    finally:
        document.close()


def collect_changes(root, document, insertions=None, deletions=None, retargets=None):
    """Existing placement matrices by native id.

    Explicit duplicates are appended to insertions, deleted original objects to deletions and
    existing props using an edited asset to retargets; callers that pass None reject those edits.
    """
    bpy.context.view_layer.update()
    insert_ids=set()
    original=json.loads(root['ate_native_identities'])
    if original != {r['id']:r['layer_hash'] for r in document.records}:
        raise ValueError('Source layers changed; reimport before exporting an update')
    objects={}
    changes={}
    checked_meshes=set()
    checked_materials=set()
    checked_images=set()
    for obj in root.all_objects:
        identity=obj.get('ate_native_id')
        if obj.get('ate_native_surface_snapshot') and json.loads(obj['ate_native_surface_snapshot'])!=[obj.tw_surface.surface,obj.tw_surface.collision]:
            raise ValueError('Native collision/surface changes require the physics writer: '+obj.name)
        if obj.get('ate_imported_materials') and not obj.get('ate_asset_source'):
            from .native_materials import signature
            names=[m.material.get('ate_native_material') if m.material else None for m in obj.material_slots]
            if names!=json.loads(obj['ate_imported_materials']):
                raise ValueError('Material reassignment needs native binding export: '+obj.name)
            for slot in obj.material_slots:
                material=slot.material
                if not material or material in checked_materials:continue
                checked_materials.add(material)
                if signature(material)!=material.get('ate_preview_signature'):
                    raise ValueError('Edited preview material needs native material export: '+material.name)
                if material.use_nodes:
                    for node in material.node_tree.nodes:
                        image=node.image if node.type=='TEX_IMAGE' else None
                        if image is None or image in checked_images:continue
                        checked_images.add(image)
                        if image.is_dirty or (image.packed_file and hashlib.sha256(image.packed_file.data).hexdigest()!=image.get('ate_original_packed_hash')):
                            raise ValueError('Edited texture needs native texture export: '+image.name)
        if obj.type=='MESH' and obj.data.get('ate_original_geometry'):
            if obj.modifiers or obj.data.shape_keys:
                raise ValueError('Modifiers/shape keys require native geometry baking: '+obj.name)
            if obj.data not in checked_meshes and mesh_signature(obj.data)!=obj.data['ate_original_geometry']:
                raise ValueError('Mesh edits require native geometry export, which is still in development: '+obj.name)
            checked_meshes.add(obj.data)
        if obj.get('ate_native_preview'):
            if native_values(obj.matrix_basis)!=list(obj['ate_imported_pose']):
                raise ValueError('Move the terrain parent instead of an individual preview draw: '+obj.name)
            continue
        roles=sorted(c.get('tw_collection_role','') for c in obj.users_collection if c.get('tw_collection_owner')==root['tw_project_id'])
        clone_of=obj.get('ate_native_clone_of')
        if clone_of:
            if insertions is None:
                raise ValueError('New placements are written by Export Updated Native Track: '+obj.name)
            source=document.by_id.get(clone_of)
            if source is None:
                raise ValueError('Source of this new placement is no longer in the native track: '+obj.name)
            if obj['ate_native_insert_id'] in insert_ids:
                raise ValueError('Copied new placements share an identity; use Duplicate as New Placement: '+obj.name)
            insert_ids.add(obj['ate_native_insert_id'])
            if roles!=json.loads(obj['ate_imported_roles']):
                raise ValueError('New placements stay in their source layer and variants: '+obj.name)
            if obj.constraints or obj.animation_data:
                raise ValueError('Animated/constrained placement must use a validated native animation exporter')
            native=AXES.inverted() @ obj.matrix_world @ AXES @ matrix(source['render']).inverted()
            spec={'id':obj['ate_native_insert_id'],'source':clone_of,'world':native_values(native)}
            if obj.get('ate_race'):
                spec.update(race=True,order=obj.get('ate_insert_order',0))
            if obj.get('ate_asset_source'):
                spec['asset_key']=(obj['ate_asset_source'],obj['ate_asset_name'])
            insertions.append(spec)
            continue
        if not identity:
            if obj.get('ate_reference_only'):
                continue
            raise ValueError('Only explicit native duplicates can be inserted; use Duplicate as New Placement: '+obj.name)
        if identity in objects:
            raise ValueError('Copied native object; use Duplicate as New Placement for explicit insertion: '+obj.name)
        objects[identity]=obj
        if obj.get('ate_asset_source'):
            if retargets is None:
                raise ValueError('Edited-asset replacements are written by Export Updated Native Track: '+obj.name)
            retargets.append({'id':identity,'asset_key':(obj['ate_asset_source'],obj['ate_asset_name'])})
        if roles!=json.loads(obj['ate_imported_roles']):
            raise ValueError('Moving native objects between layers/variants requires layer insertion support: '+obj.name)
        r=document.by_id[identity]
        if obj.constraints or obj.animation_data:
            raise ValueError('Animated/constrained placement must use a validated native animation exporter')
        now=native_values(obj.matrix_world)
        if max(abs(a-b) for a,b in zip(now,obj['ate_imported_pose']))<1e-5:
            continue
        if not r['editable'] or r['render_error']:
            raise ValueError('This native placement cannot be edited yet: '+obj.name)
        native=AXES.inverted() @ obj.matrix_world @ AXES @ matrix(r['render']).inverted()
        changes[identity]=native_values(native)
    missing=set(original)-set(objects)
    if missing:
        if deletions is None:
            raise ValueError('Deleted native instances are written by Export Updated Native Track; restore them here')
        deletions.extend(sorted(missing))
    return changes


class ATE_OT_native_import(bpy.types.Operator):
    bl_idname='alterego_track.import_native'
    bl_label='Open F1 / Swofty Track'
    filepath:StringProperty(subtype='FILE_PATH')
    base:StringProperty(name='Optional base track folder',subtype='DIR_PATH')

    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT' and not jobs.busy(context)

    def invoke(self,context,event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self,context):
        self.layout.prop(self,'base')
        self.layout.label(text='Select a track .erp archive or Swofty addon file')

    def execute(self,context):
        result=bpy.ops.alterego_track.import_native_worker('INVOKE_DEFAULT',filepath=self.filepath,base=self.base)
        return {'CANCELLED'} if result=={'CANCELLED'} else {'FINISHED'}


class ATE_OT_native_import_worker(jobs.CooperativeJob,bpy.types.Operator):
    bl_idname='alterego_track.import_native_worker'
    bl_label='Import Native Track'
    bl_options={'REGISTER','UNDO'}
    filepath:StringProperty(subtype='FILE_PATH')
    base:StringProperty(subtype='DIR_PATH')

    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and not jobs.busy(context)

    def invoke(self,context,event):return self.execute(context)

    def execute(self,context):
        path=Path(bpy.path.abspath(self.filepath))
        if path.is_file() and path.suffix=='.erp':
            path=path.parent.parent if path.parent.name=='wep' else path.parent
        iterator=import_steps(context,str(path),bpy.path.abspath(self.base) if self.base else '')
        try:
            if not bpy.app.background:
                return self.start(context,iterator)
            self.completed(context,jobs.drain(iterator))
        except Exception as exc:
            iterator.close()
            self.report({'ERROR'},str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}

    def completed(self,context,result):
        root,warnings=result
        self.report({'WARNING'} if warnings else {'INFO'},f'Opened {root.name}; {len(warnings)} preview warnings')


class ATE_OT_native_duplicate(bpy.types.Operator):
    bl_idname='alterego_track.duplicate_native_placement'
    bl_label='Duplicate as New Placement'
    bl_description='Add explicit new native placements sharing the selected static props\' models; visual only, no collision'
    bl_options={'REGISTER','UNDO'}

    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT' and marker_ui.ui_project(context) is not None and not jobs.busy(context)

    def execute(self,context):
        root=marker_ui.project(context)
        sources=[o for o in context.selected_objects if o.get('tw_project_id')==root['tw_project_id']
                 and (o.get('ate_native_id') or o.get('ate_native_clone_of'))]
        refused=[o.name for o in sources if not o.get('ate_native_cloneable',True)]
        sources=[o for o in sources if o.get('ate_native_cloneable',True)]
        if not sources:
            self.report({'ERROR'},'Select imported native static props (RenderModel placements)')
            return {'CANCELLED'}
        created=[]
        for obj in sources:
            new=obj.copy()  # Shares mesh/material data; geometry is not duplicated.
            for key in ('ate_native_id','ate_imported_pose'):
                if key in new:del new[key]
            new['ate_native_clone_of']=obj.get('ate_native_clone_of') or obj['ate_native_id']
            new['ate_native_insert_id']=uuid.uuid4().hex
            new['tw_asset_id']=new['ate_native_insert_id']
            for collection in obj.users_collection:
                collection.objects.link(new)
            created.append(new)
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in created:
            obj.select_set(True)
        context.view_layer.objects.active=created[-1]
        ui_cache.invalidate('project')
        message=f'Added {len(created)} new placements; move them, then export. Visual only: no collision'
        if refused:
            message+=f'; skipped {len(refused)} functional/unsupported objects'
        self.report({'WARNING'} if refused else {'INFO'},message)
        return {'FINISHED'}


class ATE_OT_native_race_placement(bpy.types.Operator):
    bl_idname='alterego_track.add_race_placement'
    bl_label='Add Next Race Placement'
    bl_description='Copy the selected grid slot, pit box, pit garage or F1 garage as the next number in its layer; numbers and garage links are assigned at export'
    bl_options={'REGISTER','UNDO'}

    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT' and marker_ui.ui_project(context) is not None and not jobs.busy(context)

    def execute(self,context):
        root=marker_ui.project(context)
        sources=[o for o in context.selected_objects if o.get('tw_project_id')==root['tw_project_id']
                 and (o.get('ate_native_id') or o.get('ate_race')) and o.get('ate_native_race',bool(o.get('ate_race')))]
        if not sources:
            self.report({'ERROR'},'Select imported numbered grid slots, pit boxes or garages (not number 1)')
            return {'CANCELLED'}
        created=[]
        for obj in sources:
            new=obj.copy()
            for key in ('ate_native_id','ate_imported_pose'):
                if key in new:del new[key]
            new['ate_native_clone_of']=obj.get('ate_native_clone_of') or obj['ate_native_id']
            new['ate_native_insert_id']=uuid.uuid4().hex
            new['tw_asset_id']=new['ate_native_insert_id']
            new['ate_race']=True
            root['ate_insert_counter']=root.get('ate_insert_counter',0)+1
            new['ate_insert_order']=root['ate_insert_counter']
            new.name=obj.name.rsplit('$',1)[-1].rstrip('0123456789.')+' (next number)'
            for collection in obj.users_collection:
                collection.objects.link(new)
            created.append(new)
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in created:
            obj.select_set(True)
        context.view_layer.objects.active=created[-1]
        self.report({'INFO'},f'Added {len(created)} race placements; numbers are assigned at export in creation order')
        return {'FINISHED'}


class ATE_OT_native_export(bpy.types.Operator):
    bl_idname='alterego_track.export_native_update'
    bl_label='Export Updated Native Track'
    bl_description='Write placement edits and explicit new static placements to a new native track folder or update addon; not a release-ready track generator'
    filepath:StringProperty(subtype='FILE_PATH')
    mode:EnumProperty(name='Output',items=[('FULL','Updated Native Files','Preserve the complete source structure'),('PATCH','Swofty Update Addon','Changed layers for a stock-track source')],default='FULL')
    allow_pvs_deletions:BoolProperty(name='Allow deleting PVS-listed objects',
        description='Delete static props named in precomputed visibility data; in-game effect is unverified',default=False)
    edit_format:EnumProperty(name='Layer edits',items=[
        ('PKG','Composable Edits','Launcher patch-pkg set/clone edits that combine with other addons editing the same layers'),
        ('REPLACE','Whole Layers','Replace each changed layer; conflicts with other addons replacing or editing it')],default='PKG')

    def draw(self,context):
        self.layout.prop(self,'mode')
        if self.mode=='PATCH':
            self.layout.prop(self,'edit_format')
        self.layout.prop(self,'allow_pvs_deletions')
        self.layout.label(text='Placements only; new placements have no collision')
        self.layout.label(text='Review visibility, lighting and game behaviour separately')

    @classmethod
    def poll(cls,context):
        root=marker_ui.ui_project(context)
        return root is not None and bool(root.get('ate_native_source')) and not jobs.busy(context)

    def invoke(self,context,event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self,context):
        root=marker_ui.project(context)
        document=None
        try:
            findings=project_store.check_sources(json.loads(root['ate_sources']))
            if findings:
                raise ValueError('Source files have changed or are missing; reimport before export')
            document=TrackDocument(root['ate_native_source'],root.get('ate_native_base') or None)
            insertions,deletions,retargets=[],[],[]
            changes=collect_changes(root,document,insertions,deletions,retargets)
            from .static_geometry_ui import compile_placed_assets
            assets=compile_placed_assets(context,root,document,insertions+retargets)
            replacements=document.apply(changes,insertions,deletions,{r['id']:r['asset'] for r in retargets},self.allow_pvs_deletions)
            if self.mode=='PATCH':
                fmt='patch-pkg' if self.edit_format=='PKG' else 'replace'
                document.write_patch(bpy.path.abspath(self.filepath),replacements,fmt)
            else:
                document.write_updated(bpy.path.abspath(self.filepath),replacements)
            root['ate_last_export']=str(Path(bpy.path.abspath(self.filepath)))
            write_report(root,{'output':root['ate_last_export'],'mode':self.mode,'changed_layers':len(replacements),
                'moved_placements':len(changes),'inserted_placements':document.inserted,'game_verified':False,
                'new_assets':{a['name']:{'family':a['family'],'resources':len(a['resources'])} for a in assets.values()},
                'deleted_placements':document.deleted,'asset_replacements':[r['id'] for r in retargets],
                'limitations':document.inserted and native_project.INSERT_LIMITS or ''})
        except Exception as exc:
            self.report({'ERROR'},str(exc))
            return {'CANCELLED'}
        finally:
            if document:
                document.close()
        self.report({'INFO'},f'Exported {len(replacements)} changed layers, {len(insertions)} new, {len(deletions)} deleted placements; game verification pending')
        return {'FINISHED'}


def write_report(root,result):
    name=root.get('ate_export_report') or root.name+' Native Export Report'
    text=bpy.data.texts.get(name) or bpy.data.texts.new(name)
    text.clear()
    text.write(json.dumps(result,indent=2))
    root['ate_export_report']=text.name


CLASSES=(ATE_OT_native_import_worker,ATE_OT_native_import,ATE_OT_native_duplicate,ATE_OT_native_race_placement,ATE_OT_native_export)

def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.Scene.ate_native_view=EnumProperty(name='Preview variant',items=view_items,update=select_view)

def unregister():
    global _VIEW_ITEMS,_VIEW_KEYS
    del bpy.types.Scene.ate_native_view
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
    _VIEW_ITEMS=[];_VIEW_KEYS=None
