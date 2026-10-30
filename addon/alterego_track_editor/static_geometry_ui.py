"""Blender evaluated-mesh adapter for the isolated static geometry compiler."""
import json
import math
import hashlib
import re
import uuid
from pathlib import Path
import bpy
from bpy.props import StringProperty,IntProperty,BoolProperty
from types import SimpleNamespace
from mathutils import Vector
from . import jobs,marker_ui,project_store
from .native_project import TrackDocument
from .native_ui import AXES
from .static_geometry import StaticInput,StaticFamily,write_family_test


def source_identity(obj):
    return obj.get('ate_geometry_source_id') or obj.get('ate_native_id')


def geometry_group(root,obj):
    if not obj or not obj.get('ate_geometry_source_id'):return None
    return next((c for c in root.children if c.get('ate_geometry_source_id')==source_identity(obj) and any(o==obj for o in c.objects)),None)


def show_lod(context,group,level):
    target=next((o for o in group.objects if o.ate_geometry_lod==level),None)
    if target is None:raise ValueError('Requested LOD is missing')
    for item in list(context.selected_objects):item.select_set(False)
    for item in group.objects:item.hide_set(item!=target)
    target.select_set(True);context.view_layer.objects.active=target


class ATE_OT_preview_geometry_lod(bpy.types.Operator):
    bl_idname='alterego_track.preview_geometry_lod'
    bl_label='Preview Geometry LOD'
    level:IntProperty(default=0,min=0,max=127)
    def execute(self,context):
        root=marker_ui.project(context);group=geometry_group(root,context.active_object) if root else None
        if group is None:return {'CANCELLED'}
        show_lod(context,group,self.level)
        return {'FINISHED'}


def load_lods(context,root,obj,document):
    identity=source_identity(obj);record=document.by_id.get(identity)
    if record is None or record['render_error'] or not record['model'].endswith('?context=render'):
        raise ValueError('Select an imported native static model with resolved placement')
    existing=[c for c in root.children if c.get('ate_geometry_source_id')==identity]
    if existing:
        return existing[0],False
    family=StaticFamily(document.catalog,record['model'][:-len('?context=render')])
    from .native_materials import PreviewMaterials
    from .importer import ImportTransaction
    from .native_ui import matrix
    transaction=ImportTransaction()
    try:
        group=bpy.data.collections.new(obj.name+' Geometry LODs');root.children.link(group)
        group['ate_geometry_source_id']=identity;group['ate_geometry_family']=family.family
        previews=PreviewMaterials(document.catalog)
        for level,template in family.templates.items():
            parts=template.source_inputs();positions=[];faces=[];face_slots=[];uvs=[[],[],[],[]];colours=[];normals=[]
            for index,part in enumerate(parts):
                offset=len(positions)
                positions.extend(tuple(AXES.to_3x3()@Vector(p)) for p in part.positions)
                faces.extend(tuple(offset+j for j in part.indices[i:i+3]) for i in range(0,len(part.indices),3))
                face_slots.extend([index]*(len(part.indices)//3))
                for channel in range(4):
                    stream=part.attributes.get((5,channel//2))
                    uvs[channel].extend([row[(channel%2)*2:(channel%2)*2+2] for row in stream] if stream else [(0.,0.)]*len(part.positions))
                colours.extend(part.attributes.get((6,0),[(255,255,255,255)]*len(part.positions)))
                normals.extend(tuple(AXES.to_3x3()@Vector(n)) for n in part.attributes.get((2,0),[(0.,0.,0.)]*len(part.positions)))
            data=bpy.data.meshes.new(obj.name+f' LOD {level}');data.from_pydata(positions,[],faces)
            if data.validate(clean_customdata=False):raise ValueError('Native LOD geometry requires repair; import stopped')
            for polygon,slot in zip(data.polygons,face_slots):polygon.material_index=slot;polygon.use_smooth=True
            for channel in range(4):
                layer=data.uv_layers.new(name='UV'+str(channel))
                for loop in data.loops:layer.data[loop.index].uv=uvs[channel][loop.vertex_index]
            colour=data.color_attributes.new(name='NativeColour',type='FLOAT_COLOR',domain='POINT')
            data.color_attributes.active_color=colour
            for dest,value in zip(colour.data,colours):dest.color=tuple(v/255 for v in value)
            if all(all(math.isfinite(v) for v in n) and sum(v*v for v in n)>1e-10 for n in normals):
                data.normals_split_custom_set([normals[l.vertex_index] for l in data.loops])
            item=bpy.data.objects.new(obj.name+f' LOD {level}',data);group.objects.link(item)
            item.matrix_world=AXES@matrix(record['world'])@matrix(record['render'])@AXES.inverted()
            item['tw_project_id']=root['tw_project_id'];item['ate_geometry_source_id']=identity
            item['ate_reference_only']=True;item.ate_geometry_lod=level;item.hide_render=True
            for slot in template.slots:data.materials.append(previews.resolve(record['binding'],slot))
        return group,True
    except BaseException:
        transaction.rollback();raise


class ATE_OT_load_geometry_lods(bpy.types.Operator):
    bl_idname='alterego_track.load_geometry_lods'
    bl_label='Load Geometry LODs'
    bl_description='Load actual native detail levels into a separate editing collection; existing edits are reused'
    bl_options={'REGISTER','UNDO'}

    @classmethod
    def poll(cls,context):return ATE_OT_static_geometry_test.poll(context)

    def execute(self,context):
        root=marker_ui.project(context);document=None
        try:
            if project_store.check_sources(json.loads(root['ate_sources'])):raise ValueError('Source changed; reimport first')
            document=TrackDocument(root['ate_native_source'],root.get('ate_native_base') or None)
            group,created=load_lods(context,root,context.active_object,document)
            show_lod(context,group,min(o.ate_geometry_lod for o in group.objects))
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        finally:
            if document:document.close()
        self.report({'INFO'},f"{'Loaded' if created else 'Reused'} {len(group.objects)} geometry LODs; original placements retained")
        return {'FINISHED'}


def evaluated_input(context,obj,template,material_index=0):
    if obj.type!='MESH' or obj.data.shape_keys or obj.animation_data:
        raise ValueError('Select an unanimated static mesh without shape keys')
    obj.update_from_editmode()
    obj.data.update()
    obj.update_tag(refresh={'DATA'})
    context.view_layer.update()
    evaluated=obj.evaluated_get(context.evaluated_depsgraph_get())
    data=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=context.evaluated_depsgraph_get())
    try:
        data.calc_loop_triangles()
        if not data.loop_triangles:raise ValueError('The selected mesh has no triangles')
        triangles=[t for t in data.loop_triangles if t.material_index==material_index]
        if not triangles:raise ValueError(f'Native material slot {material_index+1} has no authored triangles')
        keys=set(template.streams)-{(1,0)}
        required_uv=4 if (5,1) in keys else 2 if (5,0) in keys else 1 if (3,0) in keys else 0
        if len(data.uv_layers)<required_uv:
            raise ValueError(f'This template needs {required_uv} explicit UV layers (two per native UV stream)')
        if (3,0) in keys:data.calc_tangents(uvmap=data.uv_layers[0].name)
        colour=data.color_attributes.active_color
        if (6,0) in keys and (colour is None or colour.domain not in ('CORNER','POINT')):
            raise ValueError('This template needs an active vertex colour layer')
        axes=AXES.inverted().to_3x3()
        positions=[];indices=[];attributes={k:[] for k in keys};lookup={}
        for triangle in triangles:
            for corner in triangle.loops:
                loop=data.loops[corner]
                p=tuple(axes@data.vertices[loop.vertex_index].co)
                values={}
                for key in keys:
                    if key==(2,0):values[key]=tuple((axes@data.corner_normals[corner].vector).normalized())
                    elif key==(3,0):values[key]=(*tuple((axes@loop.tangent).normalized()),loop.bitangent_sign)
                    elif key[0]==5:
                        layer=key[1]*2
                        values[key]=(*data.uv_layers[layer].data[corner].uv,*data.uv_layers[layer+1].data[corner].uv)
                    elif key==(6,0):
                        index=corner if colour.domain=='CORNER' else loop.vertex_index
                        rgba=colour.data[index].color
                        if any(not math.isfinite(v) or not 0<=v<=1 for v in rgba):
                            raise ValueError('Native byte vertex colours require values from zero to one')
                        values[key]=tuple(round(v*255) for v in rgba)
                identity=(p,tuple((k,values[k]) for k in sorted(keys)))
                if identity not in lookup:
                    lookup[identity]=len(positions);positions.append(p)
                    for key in keys:attributes[key].append(values[key])
                indices.append(lookup[identity])
        return StaticInput(positions,indices,attributes)
    finally:evaluated.to_mesh_clear()


def evaluated_parts(context,obj,template):
    # Reject extra material slots with faces rather than silently omitting them.
    obj.update_from_editmode();obj.data.update();obj.update_tag(refresh={'DATA'});context.view_layer.update()
    evaluated=obj.evaluated_get(context.evaluated_depsgraph_get())
    data=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=context.evaluated_depsgraph_get())
    try:
        if any(p.material_index>=len(template.parts) for p in data.polygons):
            raise ValueError('Authored faces use a material slot outside the native template')
    finally:evaluated.to_mesh_clear()
    return [evaluated_input(context,obj,SimpleNamespace(streams=streams),i) for i,streams in enumerate(template.parts)]


def family_sources(context,root,document,record,templates,selected):
    """Evaluated authored inputs per LOD, with native material bindings checked against the source."""
    sources={}
    from .native_materials import signature
    from .native.materials import Materials
    materials=Materials(document.catalog)
    for item in selected:
        if not any(o==item for o in root.all_objects):raise ValueError('LOD object belongs to another project')
        level=item.ate_geometry_lod
        if level not in templates.templates:raise ValueError(f'LOD {level} is outside this native family')
        if level in sources:raise ValueError(f'Multiple selected objects claim LOD {level}')
        expected=[materials.resolve(record['binding'],slot)['id'] for slot in templates.templates[level].slots]
        actual=[m.material.get('ate_native_material') if m.material else None for m in item.material_slots]
        if actual[:len(expected)]!=expected:
            raise ValueError(f'LOD {level} material slots must match its original native bindings')
        if any(m.material and signature(m.material)!=m.material.get('ate_preview_signature') for m in item.material_slots):
            raise ValueError('Edited materials need the native material writer')
        for slot in item.material_slots:
            if not slot.material or not slot.material.use_nodes:continue
            for node in slot.material.node_tree.nodes:
                image=node.image if node.type=='TEX_IMAGE' else None
                if image and (image.is_dirty or (image.packed_file and hashlib.sha256(image.packed_file.data).hexdigest()!=image.get('ate_original_packed_hash'))):
                    raise ValueError('Edited textures need the native texture writer')
        sources[level]=evaluated_parts(context,item,templates.templates[level])
    return sources


ASSET_NAME=re.compile('[a-z0-9_]{1,64}')


def compile_placed_assets(context,root,document,insertions):
    """Compile each (LOD group, asset name) once and attach it to the insertions that place it."""
    from .static_asset import choose_identity,build_asset
    compiled,names={},{}
    for spec in insertions:
        key=spec.pop('asset_key',None)
        if key is None:continue
        source,name=key
        if names.setdefault(name,source)!=source:raise ValueError('Asset name '+name+' is used for two different geometry groups')
        if key not in compiled:
            record=document.by_id.get(source)
            group=next((c for c in root.children if c.get('ate_geometry_source_id')==source),None)
            if record is None or group is None or not group.objects:raise ValueError('Placed asset '+name+' has no loaded geometry LODs')
            family=record['model'][:-len('?context=render')]
            templates=StaticFamily(document.catalog,family)
            missing=set(templates.templates)-{o.ate_geometry_lod for o in group.objects}
            if missing:raise ValueError(f'Placed asset {name} is missing LODs {sorted(missing)}')
            sources=family_sources(context,root,document,record,templates,list(group.objects))
            target=choose_identity(document.catalog,family,'eaid://environment_package/tracks/'+root['ate_track_code']+'/objects/'+name+'.idf')
            resources,report=build_asset(document.catalog,family,target,sources,record['binding'])
            compiled[key]={'name':name,'family':report['family'],'binding':report['binding'],'resources':resources}
        spec['asset']=compiled[key]
    return compiled


class ATE_OT_place_edited_asset(bpy.types.Operator):
    bl_idname='alterego_track.place_edited_asset'
    bl_label='Place Edited Asset'
    bl_description='Add a new native placement of this edited LOD family at the 3D cursor; the original object is unchanged. Visual only, no collision'
    bl_options={'REGISTER','UNDO'}
    asset_name:StringProperty(name='Asset name',default='custom_asset')

    @classmethod
    def poll(cls,context):
        root=marker_ui.ui_project(context)
        return root is not None and context.mode=='OBJECT' and geometry_group(root,context.active_object) is not None and not jobs.busy(context)

    def invoke(self,context,event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self,context):
        root=marker_ui.project(context);group=geometry_group(root,context.active_object)
        if not ASSET_NAME.fullmatch(self.asset_name):
            self.report({'ERROR'},'Use lowercase letters, digits and underscores for the asset name');return {'CANCELLED'}
        identity=group['ate_geometry_source_id']
        source=next((o for o in root.all_objects if o.get('ate_native_id')==identity),None)
        if source is None or not source.get('ate_native_cloneable',True):
            self.report({'ERROR'},'Only static props (RenderModel placements) can be placed as new assets');return {'CANCELLED'}
        lowest=min(group.objects,key=lambda o:o.ate_geometry_lod)
        placed=bpy.data.objects.new(self.asset_name+' placement',lowest.data)  # Shares the editable LOD mesh.
        for collection in source.users_collection:collection.objects.link(placed)
        pose=source.matrix_world.copy();pose.translation=context.scene.cursor.location
        placed.matrix_world=pose
        for key in ('ate_imported_roles','ate_native_render','ate_native_template'):
            if key in source:placed[key]=source[key]
        placed['tw_project_id']=root['tw_project_id']
        placed['ate_native_clone_of']=identity;placed['ate_native_insert_id']=uuid.uuid4().hex
        placed['tw_asset_id']=placed['ate_native_insert_id']
        placed['ate_asset_source']=identity;placed['ate_asset_name']=self.asset_name
        for item in context.selected_objects:item.select_set(False)
        placed.select_set(True);context.view_layer.objects.active=placed
        self.report({'INFO'},'Placed new asset; it is compiled from all LODs at export. Visual only: no collision')
        return {'FINISHED'}


class ATE_OT_use_edited_asset(bpy.types.Operator):
    bl_idname='alterego_track.use_edited_asset'
    bl_label='Use Edited Asset for Selected'
    bl_description='Point the selected existing static props at the active edited LOD family; placements are kept'
    bl_options={'REGISTER','UNDO'}
    asset_name:StringProperty(name='Asset name',default='custom_asset')

    @classmethod
    def poll(cls,context):return ATE_OT_place_edited_asset.poll(context)

    def invoke(self,context,event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self,context):
        root=marker_ui.project(context);group=geometry_group(root,context.active_object)
        if not ASSET_NAME.fullmatch(self.asset_name):
            self.report({'ERROR'},'Use lowercase letters, digits and underscores for the asset name');return {'CANCELLED'}
        targets=[o for o in context.selected_objects if o.get('ate_native_id') and o.get('tw_project_id')==root['tw_project_id']]
        if not targets or any(not o.get('ate_native_cloneable',True) for o in targets):
            self.report({'ERROR'},'Select imported static props, then make an edited LOD active');return {'CANCELLED'}
        lowest=min(group.objects,key=lambda o:o.ate_geometry_lod)
        for obj in targets:
            if not obj.get('ate_asset_source'):obj['ate_original_mesh']=obj.data.name if obj.data else ''
            obj.data=lowest.data  # Viewport shows the edited family; export compiles every LOD.
            obj['ate_asset_source']=group['ate_geometry_source_id'];obj['ate_asset_name']=self.asset_name
        self.report({'INFO'},f'{len(targets)} placements will use asset {self.asset_name} at export; collision unchanged')
        return {'FINISHED'}


class ATE_OT_restore_original_model(bpy.types.Operator):
    bl_idname='alterego_track.restore_original_model'
    bl_label='Restore Original Model'
    bl_description='Undo Use Edited Asset for the selected existing placements'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        restored=0
        for obj in context.selected_objects:
            if not obj.get('ate_native_id') or not obj.get('ate_asset_source'):continue
            original=bpy.data.meshes.get(obj.get('ate_original_mesh',''))
            if original is None:
                self.report({'ERROR'},'Original preview mesh is missing for '+obj.name);return {'CANCELLED'}
            obj.data=original
            for key in ('ate_asset_source','ate_asset_name','ate_original_mesh'):del obj[key]
            restored+=1
        self.report({'INFO'},f'Restored {restored} original models')
        return {'FINISHED'}


def native_copy_changed(self,context):
    if self.native_copy:self.bundle_dependencies=False


class ATE_OT_static_geometry_test(bpy.types.Operator):
    bl_idname='alterego_track.export_static_geometry_test'
    bl_label='Export Selected Geometry Test'
    bl_description='Write a complete evaluated geometry LOD family into a separate native ERP test copy; no placement, collision or material edits'
    filepath:StringProperty(subtype='FILE_PATH')
    filter_glob:StringProperty(default='*.erp',options={'HIDDEN'})
    independent:BoolProperty(name='Create independent asset',default=False)
    asset_name:StringProperty(name='Asset name',default='custom_asset')
    bundle_dependencies:BoolProperty(name='Bundle materials and textures',description='Copy native materials, texture views/surfaces and external mip files; shared native shaders remain external',default=False)
    native_copy:BoolProperty(name='Write a native track copy',description='Replace this existing model reference in a separate stock-track folder; collision is retained, not rebuilt',default=False,update=native_copy_changed)

    def draw(self,context):
        self.layout.prop(self,'independent')
        if self.independent:
            self.layout.prop(self,'asset_name')
            self.layout.prop(self,'native_copy')
            row=self.layout.row();row.enabled=not self.native_copy;row.prop(self,'bundle_dependencies')
            self.layout.label(text='The filename stem becomes a new output folder.')
            self.layout.label(text='Shared native shaders remain external.')
            self.layout.label(text='Collision is retained, not rebuilt.' if self.native_copy else 'No track placement or collision generated.')

    @classmethod
    def poll(cls,context):
        root=marker_ui.ui_project(context);obj=context.active_object
        return root is not None and bool(root.get('ate_native_source')) and obj is not None and bool(source_identity(obj)) and obj.type=='MESH' and not jobs.busy(context)

    def invoke(self,context,event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self,context):
        root=marker_ui.project(context);obj=context.active_object;document=None
        try:
            if project_store.check_sources(json.loads(root['ate_sources'])):
                raise ValueError('Source files changed or are missing; reimport before exporting')
            document=TrackDocument(root['ate_native_source'],root.get('ate_native_base') or None)
            record=document.by_id.get(source_identity(obj))
            if record is None or record['render_error'] or not record['model'].endswith('?context=render'):
                raise ValueError('Select an imported native static model with resolved render placement')
            if not any(o==obj for o in root.all_objects):raise ValueError('Selected mesh belongs to another project')
            family=record['model'][:-len('?context=render')]
            templates=StaticFamily(document.catalog,family)
            group=geometry_group(root,obj)
            selected=list(group.objects) if group else [o for o in context.selected_objects if source_identity(o)==source_identity(obj)]
            if obj not in selected:selected.append(obj)
            sources=family_sources(context,root,document,record,templates,selected)
            if self.independent:
                from .static_asset import write_asset,choose_identity,build_asset
                if not ASSET_NAME.fullmatch(self.asset_name):raise ValueError('Use lowercase letters, digits and underscores for the asset name')
                target='eaid://environment_package/tracks/'+root['ate_track_code']+'/objects/'+self.asset_name+'.idf'
                target=choose_identity(document.catalog,family,target)
                if self.native_copy:
                    if self.bundle_dependencies:raise ValueError('Track-copy mode currently retains original material/texture dependencies; bundle separately')
                    resources,asset=build_asset(document.catalog,family,target,sources,record['binding'])
                    result=document.write_asset_update(record['id'],target,asset['binding'],resources,Path(bpy.path.abspath(self.filepath)).with_suffix(''))
                    report={**asset,**result}
                else:
                    report=write_asset(document.catalog,family,target,sources,record['binding'],Path(bpy.path.abspath(self.filepath)).with_suffix(''),self.bundle_dependencies)
            else:
                report=write_family_test(document.catalog,family,sources,bpy.path.abspath(self.filepath))
            root['ate_last_geometry_test']=json.dumps(report)
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        finally:
            if document:document.close()
        self.report({'INFO'},f"Exported {report['lods']} geometry LODs; no collision or complete track package")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(ATE_OT_preview_geometry_lod)
    bpy.utils.register_class(ATE_OT_load_geometry_lods)
    bpy.utils.register_class(ATE_OT_static_geometry_test)
    bpy.utils.register_class(ATE_OT_place_edited_asset)
    bpy.utils.register_class(ATE_OT_use_edited_asset)
    bpy.utils.register_class(ATE_OT_restore_original_model)
    bpy.types.Object.ate_geometry_lod=IntProperty(name='Geometry LOD',description='Explicit native detail level for selected geometry test objects; select a complete family to export',default=0,min=0,max=127)
def unregister():
    del bpy.types.Object.ate_geometry_lod
    bpy.utils.unregister_class(ATE_OT_restore_original_model)
    bpy.utils.unregister_class(ATE_OT_use_edited_asset)
    bpy.utils.unregister_class(ATE_OT_place_edited_asset)
    bpy.utils.unregister_class(ATE_OT_static_geometry_test)
    bpy.utils.unregister_class(ATE_OT_load_geometry_lods)
    bpy.utils.unregister_class(ATE_OT_preview_geometry_lod)
