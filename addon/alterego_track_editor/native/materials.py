"""Read-only native material bindings and bounded image resolution.

Native layouts follow the supplied AlterEgo format documentation. Shader
projection is deliberately conservative; no proprietary shader code is used.
"""
from collections import OrderedDict
import hashlib
import io
import math
from pathlib import Path
import struct
import threading
from .geometry import cstring, u32, region


def binding_table(data):
    n, _, length = struct.unpack_from('<3I',data)
    if n > 100000:
        raise ValueError('Invalid material binding count')
    labels, uris = 12+8*n, 12+length
    region(data,12,8*n)
    if not labels <= uris <= len(data):
        raise ValueError('Material binding pools out of bounds')
    result = {}
    for i in range(n):
        label, uri = struct.unpack_from('<2I',data,12+8*i)
        result[cstring(data,labels+label,uris)] = cstring(data,uris+uri)
    return result


def material_file(data):
    count = u32(data,0)
    base = 32+36*count
    region(data,0,base)
    numeric, shader, names, primary, secondary, tail = [u32(data,k) for k in (8,12,16,20,24,28)]
    if not 0 <= numeric <= shader <= names <= primary <= secondary <= tail <= len(data)-base:
        raise ValueError('Invalid material regions')
    textures, values = {}, {}
    for i in range(count):
        p=32+36*i
        name=cstring(data,base+names+u32(data,p),base+primary)
        kind,size,offset=u32(data,p+8),u32(data,p+16),u32(data,p+28)
        if kind==2:
            if not size or offset+size > secondary-primary:
                raise ValueError('Texture URI outside material pool')
            textures[name]=cstring(data,base+primary+offset,base+primary+offset+size)
        elif kind&0xffff==3 and size in (4,8,12,16):
            if offset+size>numeric:
                raise ValueError('Numeric input outside material region')
            value=list(struct.unpack_from('<'+str(size//4)+'f',data,base+offset))
            if all(map(math.isfinite,value)):
                values[name]=value
        elif kind==6 and size==4:
            if offset+size>numeric:raise ValueError('Integer input outside material region')
            values[name]=[u32(data,base+offset)]
    return dict(shader=cstring(data,base+shader,base+names),textures=textures,values=values)


def lz4_block(data, expected):
    """Bounded raw LZ4 block decoder (external EGO mip compression 3)."""
    if not 0 <= expected <= 16*1024*1024:
        raise ValueError('Mip exceeds decode budget')
    output=bytearray();p=0
    def length(n):
        nonlocal p
        if n==15:
            while True:
                if p>=len(data):raise ValueError('Truncated LZ4 length')
                b=data[p];p+=1;n+=b
                if b!=255:break
        return n
    while p<len(data):
        token=data[p];p+=1
        n=length(token>>4)
        if p+n>len(data) or len(output)+n>expected:raise ValueError('Invalid LZ4 literals')
        output.extend(data[p:p+n]);p+=n
        if p==len(data):break
        if p+2>len(data):raise ValueError('Truncated LZ4 match')
        distance=data[p]|data[p+1]<<8;p+=2
        n=length(token&15)+4
        if not distance or distance>len(output) or len(output)+n>expected:raise ValueError('Invalid LZ4 match')
        while n:
            count=min(n,distance);output.extend(output[-distance:len(output)-distance+count] if count<distance else output[-distance:]);n-=count
    if len(output)!=expected:raise ValueError('LZ4 decoded size mismatch')
    return bytes(output)


def external_mips(data):
    p=data[0]
    if p+5>len(data):raise ValueError('Truncated mip descriptor')
    path=data[1:1+p].decode('utf-8').rstrip('\0')
    modern=False
    if p+6<=len(data):
        count=u32(data,p+2)
        modern=count<=32 and len(data) in (p+6+26*count+8,p+6+26*count+9)
    start=p+(6 if modern else 5)
    count=u32(data,p+(2 if modern else 1))
    stride=26 if modern else 25
    if count>32:raise ValueError('Invalid external mip count')
    region(data,start,count*stride)
    records=[]
    for i in range(count):
        r=start+i*stride+(1 if modern else 0)
        records.append((data[r],*struct.unpack_from('<3Q',data,r+1)))
    return path,records


def decode_image(raw, width, height, native_format, normal=False):
    try:
        from PIL import Image
    except ImportError:
        from ..image_codec import decode_image as fallback
        return fallback(raw, width, height, native_format, normal)
    if not 0<width<=4096 or not 0<height<=4096 or width*height>4*1024*1024:
        raise ValueError('Texture dimensions exceed decode budget')
    kinds={52:1,54:1,55:3,57:3,62:2,63:4,65:5,69:7,70:7}
    if native_format in kinds:
        kind=kinds[native_format];size=max(1,(width+3)//4)*max(1,(height+3)//4)*(8 if kind in (1,4) else 16)
        if len(raw)<size:raise ValueError('Truncated compressed texture level')
        mode='L' if kind==4 else 'RGB' if kind==5 else 'RGBA'
        name={1:'DXT1',2:'DXT3',3:'DXT5',4:'BC4',5:'BC5',7:'BC7'}[kind]
        image=Image.frombytes(mode,(width,height),raw[:size],'bcn',(kind,name)).convert('RGBA')
    elif native_format==15:
        if len(raw)<width*height*4:raise ValueError('Truncated RGBA texture')
        image=Image.frombytes('RGBA',(width,height),raw[:width*height*4])
    else:
        raise ValueError(f'Unsupported native texture format {native_format}')
    if normal and native_format==65:
        # BC5 stores XY. Reconstruct a positive tangent-space Z for glTF.
        pixels=bytearray(image.tobytes())
        for p in range(0,len(pixels),4):
            x,y=pixels[p]/127.5-1,pixels[p+1]/127.5-1
            pixels[p+2]=round((math.sqrt(max(0,1-x*x-y*y))*.5+.5)*255)
        image=Image.frombytes('RGBA',image.size,bytes(pixels))
    return image


class Materials:
    def __init__(self,catalog):
        self.catalog=catalog
        self.materials={}
        self.bindings={}
        self.textures={}
        self.cache=OrderedDict();self.used=0;self.budget=32*1024*1024
        self.lock=threading.RLock()
        self.warnings={}
        self.failures={}
        self.source_identities={}
        self.level_size=512
        self.items={}

    def note(self,key,message):
        self.warnings.setdefault(key,str(message))

    def validate_sources(self):
        for path,identity in list(self.source_identities.items()):
            stat=Path(path).stat()
            if (stat.st_size,stat.st_mtime_ns)!=identity:
                raise ValueError('External texture source changed; reopen the scene')

    def register_texture(self,key,loader):
        self.textures.setdefault(key,loader)
        return key

    def texture_key(self,uri,normal=False):
        key=hashlib.sha256((uri+str(normal)).encode()).hexdigest()[:24]
        self.register_texture(key,lambda:self.native_texture(uri,normal))
        return key

    def png(self,key):
        with self.lock:
            self.validate_sources()
            if key in self.failures:raise ValueError(self.failures[key])
            if key in self.cache:
                self.cache.move_to_end(key);return self.cache[key]
            try:
                data=self.textures[key]()
            except Exception as exc:
                self.note(key,exc);self.failures[key]=str(exc);raise
            while self.cache and self.used+len(data)>self.budget:
                _,old=self.cache.popitem(last=False);self.used-=len(old)
            if len(data)<=self.budget:
                self.cache[key]=data;self.used+=len(data)
            return data

    def native_texture(self,uri,normal=False):
        catalog=self.catalog
        archive,resource=catalog.get(uri)
        if resource.type_name=='GfxSRVResource':
            view=catalog.read(uri);uri=cstring(view,24)
            archive,resource=catalog.get(uri)
        if resource.type_name!='GfxSurfaceRes':raise ValueError('Texture surface unresolved')
        head=catalog.read(uri)
        fmt,width,height=u32(head,8),u32(head,12),u32(head,16)
        if fmt==62:self.note(uri,'Format 62 BC2/BC3 naming unresolved in source contract; shared RGB layout supported, alpha interpreted as BC2')
        if len(head) not in (36,40) or u32(head,28)!=1:
            raise ValueError('Texture array/cube/metadata layout unsupported')
        blockbytes=8 if fmt in (52,54,63) else 16
        def levelbytes(w,h):return w*h*4 if fmt==15 else max(1,(w+3)//4)*max(1,(h+3)//4)*blockbytes
        external=None
        if len(resource.fragments)>2:
            path,records=external_mips(catalog.read(uri,2))
            fullw,fullh=width<<len(records),height<<len(records)
            for level,(compression,offset,packed,decoded) in enumerate(records):
                w,h=max(1,fullw>>level),max(1,fullh>>level)
                if max(w,h)<=self.level_size:
                    if decoded!=levelbytes(w,h) or max(packed,decoded)>16*1024*1024:
                        raise ValueError('Invalid external mip size')
                    roots=list(getattr(catalog,'asset_roots',[]))
                    mapped=None
                    normalized=path.replace('\\','/')
                    shipped=getattr(catalog,'mip_files',{})
                    basename=normalized.rsplit('/',1)[-1]
                    hashed=hashlib.md5(normalized.encode()).hexdigest()[:12]+'_'+basename
                    mapped=shipped.get(basename,shipped.get(hashed))
                    for prefix,directory in getattr(catalog,'asset_mappings',[]):
                        if normalized.startswith(prefix):
                            candidate=(directory/normalized[len(prefix):]).resolve()
                            if not candidate.is_relative_to(directory.resolve()):raise ValueError('Mip mapping escapes addon')
                            if candidate.is_file():mapped=candidate;break
                    roots.extend(p for p in (archive.path.parent,*archive.path.parents) if (p/'F1_25.exe').is_file())
                    game_root=next((p for p in roots if (p/path.replace('\\','/')).is_file()),None)
                    if game_root is None and mapped is None:
                        self.note(uri,'External mip unavailable; using embedded resident texture level')
                        break
                    file=mapped or (game_root/normalized).resolve()
                    if mapped is None and not file.is_relative_to(game_root.resolve()):raise ValueError('External mip escapes game root')
                    stat=file.stat()
                    identity=(stat.st_size,stat.st_mtime_ns)
                    if str(file) in self.source_identities and self.source_identities[str(file)]!=identity:
                        raise ValueError('External mip source changed; reopen the scene')
                    self.source_identities[str(file)]=identity
                    if offset+packed>stat.st_size:raise ValueError('External mip outside file')
                    with file.open('rb') as f:f.seek(offset);raw=f.read(packed)
                    after=file.stat()
                    if len(raw)!=packed or (after.st_size,after.st_mtime_ns)!=identity:raise ValueError('External mip changed or truncated')
                    if compression==3:raw=lz4_block(raw,decoded)
                    elif compression==4:raw=archive._zstd().decompress(raw,decoded)
                    elif compression!=0:raise ValueError(f'Unsupported mip compression {compression}')
                    if len(raw)!=decoded:raise ValueError('External mip decoded size mismatch')
                    external=(raw,w,h);break
        if external:
            raw,width,height=external
        else:
            raw=catalog.read(uri,1);offset=0
            for level in range(max(1,u32(head,24))):
                length=levelbytes(width,height)
                if max(width,height)<=self.level_size or level+1>=max(1,u32(head,24)):break
                offset+=length;width=max(1,width//2);height=max(1,height//2)
            raw=raw[offset:]
        image=decode_image(raw,width,height,fmt,normal)
        if max(image.size)>self.level_size:image.thumbnail((self.level_size,self.level_size))
        output=io.BytesIO();image.save(output,format='PNG');return output.getvalue()

    def resolve(self,binding,slot,direct=None):
        try:
            if direct:
                uri=direct
            elif binding:
                if binding not in self.bindings:
                    self.bindings[binding]=binding_table(self.catalog.read(binding))
                uri=self.bindings[binding][slot]
            else:
                raise ValueError('No material binding')
            if uri not in self.materials:
                data=material_file(self.catalog.read(uri));self.materials[uri]=self.project(uri,data)
            return self.materials[uri]
        except Exception as exc:
            key=(binding or direct or 'unbound')+' / '+slot;self.note(key,exc)
            return dict(id=key,name=slot or 'Unresolved',factor=[.55,.62,.67,1],alphaMode='OPAQUE',cutoff=.5,roughness=.9,metallic=0,base=None,normal=None,uvset=0,normalUV=0,uvTransform=[1,1,0,0],normalTransform=[1,1,0,0])

    def project(self,uri,data):
        shader=data['shader'].rsplit('/',1)[-1].removesuffix('.nefx2')
        tex,values=data['textures'],data['values']
        base=next((tex[n] for n in ('me_albedoMap','me_baseAlbedoMap','me_diffuseMap','me_baseDiffuseTex','me_basecolorMap','me_diffuseTex') if tex.get(n)),None)
        if base is None and shader in ('lights_scrolling','lights_animated'):base=tex.get('me_effectMap')
        # track_blend's diffuse sampler is a dust/detail overlay, not ground colour.
        macro_fallback=(base is None or shader=='track_blend') and bool(tex.get('me_macroMap'))
        if macro_fallback:
            base=tex['me_macroMap']
            self.note(uri,'Macro-colour terrain projection; detailed layer blending and mask channels are not reproduced')
        sponsor=shader.startswith(('sponsor_board','sponsor_painted','sponsor_detail','sponsor_screen'))
        # Terrain macro colour uses the zw pair of the primary UV stream.
        # The xy pair can be kilometre-scale repeating detail coordinates.
        uvset=1 if macro_fallback else 2 if sponsor else 0
        tint=values.get('me_diffuseTint',values.get('me_baseMapTint',[1,1,1]))[:3]
        if len(tint)!=3 or any(v<0 or v>16 for v in tint):tint=[1,1,1]
        # glTF base factors are bounded. Preserve the other colour channels
        # instead of turning an entire HDR-tinted material white.
        tint=[min(1,v) for v in tint]
        alpha=not macro_fallback and (any(n in shader for n in ('alpha','mask','foliage','spt_','vegetation','billboard','bush','fence')) or ('tree' in shader and 'bark' not in shader))
        transparent='glass' in shader or 'transparent' in shader
        cutoff=values.get('me_alphaThreshold',[.5])[0]
        if not 0<=cutoff<=1:cutoff=.5
        uv=values.get('me_uvTile',[1,1])[:2]+[values.get('me_uOffset',[0])[0],values.get('me_vOffset',[0])[0]]
        if len(uv)!=4:uv=[1,1,0,0]
        if macro_fallback:
            uv=[values.get('me_macro_uscale',[1])[0],values.get('me_macro_vscale',[1])[0],0,0]
            tint=[1,1,1]
        if 'me_baseMapUScale' in values and not macro_fallback:
            uv[:2]=[values['me_baseMapUScale'][0],values.get('me_baseMapVScale',[1])[0]]
            uv[2:]=[values.get('me_baseMapUOffset',[0])[0],values.get('me_baseMapVOffset',[0])[0]]
        normal=next((tex[n] for n in ('me_normalMap','me_baseNormalMap','me_baseNormalTex','me_normalTex') if tex.get(n)),None)
        normaluv=values.get('me_normalUVScale',[1,1])[:2]+values.get('me_normalUVOffset',[0,0])[:2]
        if len(normaluv)!=4:normaluv=[1,1,0,0]
        if shader.startswith('lt_') and 'me_normalUVScale' not in values:normaluv=uv[:]
        result=dict(id=uri,name=uri.rsplit('/',1)[-1],shader=data['shader'],factor=tint+[1],alphaMode='BLEND' if transparent else 'MASK' if alpha else 'OPAQUE',
                    cutoff=cutoff,roughness=.85,metallic=0,base=self.texture_key(base) if base else None,
                    normal=self.texture_key(normal,True) if normal else None,
                    uvset=uvset,normalUV=0,uvTransform=uv,normalTransform=normaluv,
                    sourceTextures=tex,sourceValues=values)
        if macro_fallback and (shader=='track_blend' or 'alpha' in shader):
            # These are coverage-controlled overlays. Painting the macro image
            # opaquely over the underlying road invents terrain and causes fighting.
            result.update(factor=[1,1,1,0],alphaMode='MASK',cutoff=.5,base=None,normal=None)
            self.note(uri,'Coverage-controlled terrain overlay omitted visually until native layer/mask blending is supported; geometry retained')
        if not base:self.note(uri,'No supported base-colour sampler; using material tint')
        if shader not in ('object_opaque','object_alpha','sponsor_board','terrain_single'):
            self.note(uri,f'{shader}: approximate sampler/UV projection; native blending and lighting not reproduced')
        return result
