"""Bounded static terrain colour baking shared by preview and GLB export."""
import hashlib
import io
import numpy as np
try:
    from PIL import Image
except ImportError:
    from ..image_codec import ImageFacade as Image


def sample(image, uv):
    h,w=image.shape[:2]
    xy=np.remainder(uv,1)*[w,h]-.5
    low=np.floor(xy).astype(np.int64);f=xy-low
    x,y=low[:,0]%w,low[:,1]%h
    a=image[y,x]*(1-f[:,0,None])+image[y,(x+1)%w]*f[:,0,None]
    b=image[(y+1)%h,x]*(1-f[:,0,None])+image[(y+1)%h,(x+1)%w]*f[:,0,None]
    return a*(1-f[:,1,None])+b*f[:,1,None]


def height_blend(previous_height, height, mask, thickness, softness):
    denominator=max(abs(thickness*softness),1e-5)
    t=np.clip((height-previous_height)*mask/denominator,0,1)
    return t*t*(3-2*t)


def surface_world_uvs(geometry, material):
    """Project explicit terrain_single WSM flags without changing source UV0/UV1."""
    if not material.get('shader','').rsplit('/',1)[-1].startswith('terrain_single'):return material
    values=material.get('sourceValues',{})
    diffuse=bool(values.get('me_diffuseWSM',[0])[0])
    normal=bool(values.get('me_normalWSM',[0])[0])
    if not (diffuse or normal):return material
    positions=np.frombuffer(geometry.positions,dtype='<f4').reshape(-1,3)
    coords=positions[:,[0,2]].copy();coords[:,1]*=-1
    geometry.uvs=list(geometry.uvs);geometry.uvs[2]=coords.astype('<f4').tobytes()
    result=dict(material)
    for enabled,flag,transform,name in ((diffuse,'uvset','uvTransform','diffuse'),(normal,'normalUV','normalTransform','normal')):
        if enabled:
            scale=values.get('me_'+name+'WSMScale',[1])[0]
            result[flag]=2;result[transform]=[scale,scale,0,1]
    return result


def bake_terrain(service, geometry, material, identity, geometry_factory, size=256):
    textures=material.get('sourceTextures',{});values=material.get('sourceValues',{})
    if not any(n in material.get('shader','') for n in ('terrain_4way_blend','terrain_detritus_4x')) or 'me_layer1_albedoMap' not in textures:return material
    positions=np.frombuffer(geometry.positions,dtype='<f4').reshape(-1,3)
    indices=np.frombuffer(geometry.indices,dtype='<u4').reshape(-1,3)
    original=[np.frombuffer(data,dtype='<f4').reshape(-1,2) for data in geometry.uvs]
    xz=positions[:,[0,2]];low=xz.min(0);span=np.maximum(xz.max(0)-low,.001)
    atlas=(xz-low)/span
    # Keep all texture samples away from the repeating boundary.
    atlas=(atlas*(size-2)+1)/size
    geometry.uvs=list(geometry.uvs);geometry.uvs[2]=atlas.astype('<f4').tobytes()
    key=hashlib.sha256(('terrain-bake-v1'+identity).encode()).hexdigest()[:24]
    def loader():
        geometry=geometry_factory()
        positions=np.frombuffer(geometry.positions,dtype='<f4').reshape(-1,3)
        indices=np.frombuffer(geometry.indices,dtype='<u4').reshape(-1,3)
        original=[np.frombuffer(data,dtype='<f4').reshape(-1,2) for data in geometry.uvs]
        atlas=original[2]
        vertex_colours=np.frombuffer(geometry.colours,dtype='<f4').reshape(-1,4) if geometry.colours else np.ones((len(positions),4),dtype=np.float32)
        images={}
        def image(name):
            if name not in images:
                uri=textures.get(name)
                if not uri:raise ValueError('Missing terrain sampler '+name)
                images[name]=np.asarray(Image.open(io.BytesIO(service.png(service.texture_key(uri)))).convert('RGBA'),dtype=np.float32)/255
            return images[name]
        def scalar(name,default=1):return values.get(name,[default])[0]
        def uv_for(prefix,world,uv,macro=False):
            flag=scalar(prefix+('_wsm' if prefix!='me_macro' else '_wsm'),0)
            scale=scalar(prefix+'_wsm_scale',1)
            coord=world[:,[0,2]]*scale if flag else uv.copy()
            if flag:coord[:,1]=1-coord[:,1]
            return coord*[scalar(prefix+'_uscale'),scalar(prefix+'_vscale')]
        out=np.zeros((size,size,4),dtype=np.float32)
        for tri in indices:
            screen=atlas[tri]*size-.5
            lo=np.maximum(np.floor(screen.min(0)).astype(int)-1,0);hi=np.minimum(np.ceil(screen.max(0)).astype(int)+1,size-1)
            a,b,c=screen;ab=b-a;ac=c-a;det=ab[0]*ac[1]-ab[1]*ac[0]
            if abs(det)<1e-9:continue
            yy,xx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1];p=np.stack([xx.ravel(),yy.ravel()],axis=1)-a
            u=(p[:,0]*ac[1]-p[:,1]*ac[0])/det;v=(ab[0]*p[:,1]-ab[1]*p[:,0])/det
            inside=(u>=-.015)&(v>=-.015)&(u+v<=1.015)
            if not inside.any():continue
            weights=np.stack([1-u-v,u,v],axis=1)[inside]
            world=weights@positions[tri];uv0=weights@original[0][tri];uv1=weights@original[1][tri]
            mask=weights@vertex_colours[tri] if scalar('me_useVertColourBlend',0) else sample(image('me_blendMap'),uv_for('me_blend',world,uv1))
            macro=sample(image('me_macroMap'),uv_for('me_macro',world,uv1))[:,:3]**2.2*2 if textures.get('me_macroMap') else np.ones((len(weights),3))
            alpha_shader='alpha' in material['shader'] or 'detritus' in material['shader']
            colour=None;height=None;macro_weight=None;coverage=mask[:,3] if alpha_shader else np.ones(len(mask))
            for layer in range(1,5):
                prefix='me_layer'+str(layer)
                rgba=sample(image(prefix+'_albedoMap'),uv_for(prefix,world,uv0))
                signed=rgba[:,3]*2-1
                signed=np.where(signed>=0,np.clip(signed*scalar(prefix+'_softness_offset'),-1,1),signed)
                h=signed*scalar(prefix+'_thickness')+scalar(prefix+'_offset',0)
                rgb=rgba[:,:3]**2.2*np.maximum(values.get(prefix+'_tint',[1,1,1])[:3],0)**2.2
                weight=scalar(prefix+'_macro_weight',0)
                if colour is None:colour=rgb;height=h;macro_weight=np.full(len(h),weight)
                else:
                    blend=height_blend(height,h,mask[:,layer-2],scalar(prefix+'_thickness'),scalar(prefix+'_softness'))
                    colour=colour*(1-blend[:,None])+rgb*blend[:,None]
                    height=height*(1-blend)+h*blend;macro_weight=macro_weight*(1-blend)+weight*blend
                    if alpha_shader:coverage=coverage+(1-coverage)*blend
            colour*=1+(macro-1)*macro_weight[:,None]
            if alpha_shader and textures.get('me_alphaMap'):
                coverage*=sample(image('me_alphaMap'),uv0*[scalar('me_alpha_scale_u'),scalar('me_alpha_scale_v')])[:,0]
            result=np.column_stack([np.clip(colour,0,1)**(1/2.2),coverage])
            out[yy.ravel()[inside],xx.ravel()[inside]]=result
        # Extend edge texels to avoid dark seams at triangle and chunk boundaries.
        valid=out[:,:,3]>0
        for _ in range(2):
            for axis in (0,1):
                for shift in (-1,1):
                    neighbour=np.roll(out,shift,axis);available=np.roll(valid,shift,axis)&~valid
                    out[available]=neighbour[available];valid|=available
        png=io.BytesIO();Image.fromarray(np.uint8(np.clip(out,0,1)*255)).save(png,format='PNG');return png.getvalue()
    service.register_texture(key,loader)
    result=dict(material,id=material['id']+'#'+key,base=key,normal=None,factor=[1,1,1,1],uvset=2,uvTransform=[1,1,0,0],alphaMode='BLEND' if any(n in material['shader'] for n in ('alpha','detritus')) else 'OPAQUE')
    service.note(result['id'],'Baked static four-layer colour/height/macro blend; normal/surface blending and runtime wetness not reproduced')
    return result
