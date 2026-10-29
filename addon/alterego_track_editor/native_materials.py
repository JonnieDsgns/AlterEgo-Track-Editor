"""Blender preview bridge for native shader bindings; source identity is retained."""
import hashlib
import json
from pathlib import Path
import tempfile
import bpy
from .native.materials import Materials


def signature(mat):
    rows=[list(mat.diffuse_color),mat.use_nodes]
    if mat.use_nodes:
        for node in mat.node_tree.nodes:
            values=[]
            for socket in node.inputs:
                if hasattr(socket,'default_value'):
                    value=socket.default_value
                    try:value=list(value)
                    except TypeError:pass
                    values.append((socket.identifier,value))
            rows.append((node.name,node.type,values,(node.image.name,None if node.image.packed_file else node.image.filepath) if node.type=='TEX_IMAGE' and node.image else None))
        rows.extend((link.from_node.name,link.from_socket.identifier,link.to_node.name,link.to_socket.identifier) for link in mat.node_tree.links)
    return hashlib.sha256(json.dumps(rows,default=str,sort_keys=True).encode()).hexdigest()


class PreviewMaterials:
    def __init__(self,catalog):
        self.native=Materials(catalog)
        self.materials={}
        self.images={}
        self.warnings=[]

    def image(self,key):
        if not key:return None
        if key not in self.images:
            payload=self.native.png(key)
            with tempfile.TemporaryDirectory(prefix='ate-image-') as temporary:
                file=Path(temporary)/'preview.png';file.write_bytes(payload)
                image=bpy.data.images.load(str(file),check_existing=False)
                image.name='F1 '+key[:18]
                image.pack()
                image.filepath='//textures/'+key+'.png'
                image['ate_original_packed_hash']=hashlib.sha256(image.packed_file.data).hexdigest()
            self.images[key]=image
        return self.images[key]

    def resolve(self,binding,slot,direct=None,appearance=None):
        appearance=appearance or self.native.resolve(binding,slot,direct)
        identity=appearance['id']
        if identity in self.materials:return self.materials[identity]
        mat=bpy.data.materials.new(appearance.get('name',slot or 'Native material'))
        mat.use_nodes=True
        mat['ate_native_material']=identity
        mat['ate_native_shader']=appearance.get('shader','Unresolved')
        mat['ate_native_source_values']=json.dumps(appearance.get('sourceValues',{}))
        mat['ate_preview_only']=True
        tree=mat.node_tree
        bsdf=next(n for n in tree.nodes if n.type=='BSDF_PRINCIPLED')
        factor=appearance.get('factor',[1,1,1,1])
        mat.diffuse_color=factor
        bsdf.inputs['Base Color'].default_value=factor
        bsdf.inputs['Roughness'].default_value=appearance.get('roughness',.9)
        bsdf.inputs['Metallic'].default_value=appearance.get('metallic',0)
        if appearance.get('alphaMode')!='OPAQUE':
            mat.surface_render_method='DITHERED'
        for role,socket,uvkey,transformkey in [('base','Base Color','uvset','uvTransform'),('normal','Normal','normalUV','normalTransform')]:
            key=appearance.get(role)
            if not key:continue
            try:
                image=self.image(key)
                if role=='normal':image.colorspace_settings.name='Non-Color'
                texture=tree.nodes.new('ShaderNodeTexImage');texture.image=image
                uv=tree.nodes.new('ShaderNodeUVMap');uv.uv_map='UV'+str(appearance.get(uvkey,0))
                mapping=tree.nodes.new('ShaderNodeMapping')
                scale=appearance.get(transformkey,[1,1,0,0])
                mapping.inputs['Scale'].default_value=(scale[0],scale[1],1)
                mapping.inputs['Location'].default_value=(scale[2],scale[3],0)
                tree.links.new(uv.outputs['UV'],mapping.inputs['Vector'])
                tree.links.new(mapping.outputs['Vector'],texture.inputs['Vector'])
                if role=='normal':
                    normal=tree.nodes.new('ShaderNodeNormalMap');tree.links.new(texture.outputs['Color'],normal.inputs['Color'])
                    tree.links.new(normal.outputs['Normal'],bsdf.inputs['Normal'])
                else:
                    tint=tree.nodes.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1
                    tint.inputs[2].default_value=factor
                    tree.links.new(texture.outputs['Color'],tint.inputs[1]);tree.links.new(tint.outputs[0],bsdf.inputs['Base Color'])
                    if appearance.get('alphaMode')!='OPAQUE':tree.links.new(texture.outputs['Alpha'],bsdf.inputs['Alpha'])
            except Exception as exc:
                self.warnings.append({'material':identity,'texture':key,'reason':str(exc)})
        mat['ate_preview_signature']=signature(mat)
        self.materials[identity]=mat
        return mat

    def assign(self,obj,geometry,binding):
        groups=geometry.groups or [{'first':0,'count':len(geometry.indices)//4,'slot':'Default'}]
        while len(obj.data.materials)<len(groups):obj.data.materials.append(None)
        first_layout=not obj.data.get('ate_material_layout_ready')
        for index,group in enumerate(groups):
            material=self.resolve(binding,group.get('slot',''),group.get('material'),group.get('appearance'))
            obj.material_slots[index].link='OBJECT';obj.material_slots[index].material=material
            if first_layout:
                for face in range(group['first']//3,(group['first']+group['count'])//3):
                    if face<len(obj.data.polygons):obj.data.polygons[face].material_index=index
        if first_layout:
            obj.data['ate_original_geometry']=__import__(__package__+'.native_ui',fromlist=['mesh_signature']).mesh_signature(obj.data)
            obj.data['ate_material_layout_ready']=True
        obj['ate_imported_materials']=json.dumps([m.material.get('ate_native_material') if m.material else None for m in obj.material_slots])
