"""Synthetic native resources; no game assets are embedded."""
import hashlib
from pathlib import Path
import struct

IDENTITY=[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]


def pkg(value):
    data=bytearray(b'!pkgTEST'+b'\0'*8);strings=bytearray();matrices=bytearray()
    def string(s):
        raw=s.encode();i=len(strings);strings.extend(bytes([len(raw)])+raw+b'\0');return i
    def emit(value):
        if isinstance(value,str):return string(value)
        if isinstance(value,tuple) and value[0]=='mat4':
            i=len(matrices)//64;matrices.extend(struct.pack('<16f',*value[1]));return (1<<24)|i
        if isinstance(value,dict):
            off=len(data);data.extend(b'!idi'+struct.pack('<I',len(value))+b'\0'*(8*len(value)))
            for i,(k,v) in enumerate(value.items()):
                key=string(k);ref=emit(v);struct.pack_into('<II',data,off+8+8*i,key,ref)
            return 0x80000000|off
        if isinstance(value,list):
            off=len(data);data.extend(b'!ili'+struct.pack('<I',len(value))+b'\0'*(4*len(value)))
            for i,v in enumerate(value):struct.pack_into('<I',data,off+8+4*i,emit(v))
            return 0x80000000|off
        raise TypeError(value)
    root=emit(value);vca=len(data);data.extend(b'!vca'+struct.pack('<I',2)+b'\0'*8)
    for i,(typ,stride,raw) in enumerate([('stri',0,strings),('mat4',64,matrices)]):
        data.extend(b'\0'*(-len(data)%16));off=len(data)
        struct.pack_into('<I',data,vca+8+4*i,0x80000000|off)
        data.extend(b'!sbi'+struct.pack('<I',len(raw))+raw if typ=='stri' else b'!vbi'+typ.encode()+struct.pack('<II',len(raw)//stride,stride)+raw)
    struct.pack_into('<II',data,8,root,0x80000000|vca)
    return bytes(data)+b'OPAQUE TAIL'


def erp(resources):
    entries=bytearray();payload=bytearray()
    for name,kind,fragments in resources:
        rawname=name.encode()+b'\0'
        entry=bytearray(struct.pack('<H',len(rawname))+rawname+kind.encode().ljust(16,b'\0')+b'ABCD'+bytes([len(fragments)]))
        for i,raw in enumerate(fragments):
            entry.extend(('f'+str(i)).encode().ljust(4,b'\0')+struct.pack('<QQIBQ',len(payload),len(raw),0,0x91,len(raw)));payload.extend(raw)
        entry.extend(hashlib.md5(b''.join(fragments)).digest())
        entries.extend(struct.pack('<I',len(entry))+entry)
    info=struct.pack('<II',len(resources),sum(len(r[2]) for r in resources))+entries
    header=bytearray(b'ERPK'+struct.pack('<I',3)+b'\0'*40);struct.pack_into('<QQQ',header,16,48,len(info),48+len(info))
    return bytes(header+info+payload)


def make_track(folder):
    folder=Path(folder);(folder/'wep').mkdir(parents=True)
    prefix='eaid://environment_package/tracks/'+folder.name+'/wep/'
    layer=prefix+'objects.layer'
    world=pkg({'layers':[layer]})
    matrix=IDENTITY[:];matrix[12]=10
    payload=pkg({'instances':[{'name':'Facility','template':'ExampleFacility','uniqueid':'fixture-id',
        'overrides':{'WorldObject':{'transform':('mat4',matrix)}}}]})
    archive=erp([(prefix+folder.name+'_common.wep','World',[world]),(layer,'WOInstances',[payload]),
                 ('eaid://fixture/opaque','UnknownType',[b'untouched'])])
    path=folder/'wep'/(folder.name+'_common.erp');path.write_bytes(archive)
    return path


def fnv(raw):
    h=0x811C9DC5
    for c in raw:h=((h^c)*0x01000193)&0xFFFFFFFF
    return h


def canonical_pkg(value,name=b'INST'):
    """Independent stock-style encoder: breadth-first chunks, FNV-ordered version-1 dictionaries."""
    order=['stri','woid','mat4','ui32','si32','bool'];strides={'woid':16,'mat4':64,'ui32':4,'si32':4,'bool':1}
    pools={t:bytearray() for t in order};seen={t:{} for t in order}
    def scalar(typ,raw):
        if raw not in seen[typ]:
            if typ=='stri':seen[typ][raw]=len(pools[typ]);pools[typ].extend(bytes([len(raw)])+raw+b'\0')
            else:seen[typ][raw]=len(pools[typ])//strides[typ];pools[typ].extend(raw)
        return (order.index(typ)<<24)|seen[typ][raw]
    def leaf(v):
        if isinstance(v,str):return scalar('stri',v.encode())
        typ,x=v
        raw={'woid':lambda:bytes(x),'mat4':lambda:struct.pack('<16f',*x),'ui32':lambda:struct.pack('<I',x),'si32':lambda:struct.pack('<i',x),'bool':lambda:bytes([x])}[typ]()
        return scalar(typ,raw)
    data=bytearray(b'!pkg'+name+b'\0'*8);queue=[(None,value)];cursor=0
    while cursor<len(queue):
        slot,node=queue[cursor];cursor+=1;off=len(data)
        if slot is not None:struct.pack_into('<I',data,slot,0x80000000|off)
        else:root=off
        if isinstance(node,dict):
            items=sorted(node.items(),key=lambda kv:fnv(kv[0].encode()))
            data.extend(b'!idi'+struct.pack('<I',len(items)|1<<24)+b'\0'*(12*len(items)))
            for i,(k,v) in enumerate(items):
                p=off+8+12*i;struct.pack_into('<I',data,p,scalar('stri',k.encode()));struct.pack_into('<I',data,p+8,fnv(k.encode()))
                if isinstance(v,(dict,list)):queue.append((p+4,v))
                else:struct.pack_into('<I',data,p+4,leaf(v))
        else:
            data.extend(b'!ili'+struct.pack('<I',len(node))+b'\0'*(4*len(node)))
            for i,v in enumerate(node):
                if isinstance(v,(dict,list)):queue.append((off+8+4*i,v))
                else:struct.pack_into('<I',data,off+8+4*i,leaf(v))
    data.extend(b'\0'*(-len(data)%4));vca=len(data)
    data.extend(b'!vca'+struct.pack('<I',len(order))+b'\0'*(4*len(order)))
    for i,typ in enumerate(order):
        data.extend(b'\0'*(-len(data)%{'woid':16,'mat4':16}.get(typ,4)));struct.pack_into('<I',data,vca+8+4*i,0x80000000|len(data))
        raw=pools[typ]
        data.extend(b'!sbi'+struct.pack('<I',len(raw))+raw if typ=='stri' else b'!vbi'+typ.encode()+struct.pack('<II',len(raw)//strides[typ],strides[typ])+raw)
    data.extend(b'\0'*(-len(data)%4));struct.pack_into('<II',data,8,0x80000000|root,0x80000000|vca)
    return bytes(data)


def render_nodes():
    """Two-node identity render hierarchy accepted by the native placement reader."""
    data=bytearray(struct.pack('<HH',2,0)+b'\0'*8+b'\0'*240)
    for i in range(2):
        p=12+120*i;struct.pack_into('<i',data,p+4,-1 if i==0 else 0)
        struct.pack_into('<10f',data,p+8,0,0,0,0,0,0,1,1,1,1);struct.pack_into('<I',data,p+112,1)
    return bytes(data)


def prop(name,uid,family,x,extra=None):
    matrix=IDENTITY[:];matrix[12]=x
    overrides={'Model':{'model':family+'?context=render','mat binding':family+'?mat'},
        'Render':{'cast shadows':('bool',0),'lightmap_size':('ui32',64)},'WorldObject':{'transform':('mat4',matrix)}}
    overrides.update(extra or {})
    return {'name':name,'template':'RenderModel','uniqueid':('woid',bytes([uid])*16),'overrides':overrides}


def make_canonical_track(folder,mirror=False):
    """Stock-layout layer with two static props and one functional grid placement."""
    folder=Path(folder);(folder/'wep').mkdir(parents=True)
    prefix='eaid://environment_package/tracks/'+folder.name+'/wep/';layer=prefix+'objects.layer'
    barrier,board='eaid://fixture/barrier','eaid://fixture/board'
    grid={'name':'objects$GridSlot1','template':'GridSlot','uniqueid':('woid',bytes([9])*16),
        'overrides':{'VehPlacement':{'Id':('ui32',1)},'WorldObject':{'transform':('mat4',IDENTITY)}}}
    payload=canonical_pkg({'instances':[prop('objects$barrier_a',1,barrier,5),prop('objects$board_a',2,board,7),grid],'layer':'objects'})
    resources=[(prefix+folder.name+'_common.wep','World',[pkg({'layers':[layer]})]),(layer,'WOInstances',[payload]),
        (barrier+'?render','ModelProxyRes',[render_nodes()]),(board+'?render','ModelProxyRes',[render_nodes()]),
        ('eaid://fixture/opaque','UnknownType',[b'untouched'])]
    path=folder/'wep'/(folder.name+'_common.erp');path.write_bytes(erp(resources))
    if mirror:(folder/'wep'/'mirror.erp').write_bytes(path.read_bytes())
    return path,payload


def make_reference_track(folder):
    """Canonical layer whose barrier is listed in a PVS object table and whose board is a lightmap bake source."""
    folder=Path(folder);(folder/'wep').mkdir(parents=True)
    prefix='eaid://environment_package/tracks/'+folder.name+'/wep/';layer=prefix+'objects.layer'
    family='eaid://fixture/barrier'
    barrier=prop('objects$barrier_a',1,family,5);board=prop('objects$board_a',2,family,7);spare=prop('objects$spare_a',3,family,9)
    barrier['overrides']['Render']['lightmap_bake_source']='objects$board_a'
    table=struct.pack('<III',2,40,len('objects$barrier_a'))+b'objects$barrier_a\0'+b'\0'*8
    resources=[(prefix+folder.name+'_common.wep','World',[pkg({'layers':[layer]})]),
        (layer,'WOInstances',[canonical_pkg({'instances':[barrier,board,spare],'layer':'objects'})]),
        (family+'?render','ModelProxyRes',[render_nodes()]),(prefix+folder.name+'_f1.header.pvsbin','PVSObjIDRes',[table])]
    path=folder/'wep'/(folder.name+'_common.erp');path.write_bytes(erp(resources))
    return path


def make_race_track(folder):
    """Stock-like vehicle layers: base in common, extra numbers in one variant, and a variant without vehicles."""
    folder=Path(folder);(folder/'wep').mkdir(parents=True)
    prefix='eaid://environment_package/tracks/'+folder.name+'/wep/';base=prefix+'vehicles.layer';extra=prefix+'vehicles_myteam.layer'
    def placement(name,group,n,x):
        m=IDENTITY[:];m[12]=x;vp={'Group':group}
        if n>1:vp['Id']=('ui32',n)  # Stock entry 1 omits Id.
        return {'name':name,'template':'VehiclePlacement','uniqueid':('woid',hashlib.md5(name.encode()).digest()),
            'overrides':{'VehPlacement':vp,'WorldObject':{'transform':('mat4',m)}}}
    def garage(n,x):
        m=IDENTITY[:];m[12]=x;uid=lambda k:('woid',hashlib.md5(f'base$PitGarage{k}'.encode()).digest())
        return {'name':f'base$F1Garage{n}','template':'F1Garage','uniqueid':('woid',hashlib.md5(f'base$F1Garage{n}'.encode()).digest()),
            'overrides':{'F1Garage':{'id':('si32',n),'left car placement':uid(2*n-1),'right car placement':uid(2*n)},'WorldObject':{'transform':('mat4',m)}}}
    items=[placement('base$GridSlot1','GridWheelMarker',1,0),placement('base$GridSlot2','GridWheelMarker',2,8)]
    items+=[placement(f'base$PitGarage{n}','Garage',n,100+n*5) for n in range(1,5)]+[garage(n,100+n*10) for n in (1,2)]
    items+=[placement(f'base$PitBox{n}','Pit',n,200+n*10) for n in (1,2)]
    resources=[(prefix+folder.name+'_common.wep','World',[pkg({'layers':[base]})]),
        (prefix+folder.name+'_f1_myteam.wep','World',[pkg({'layers':[extra]})]),
        (prefix+folder.name+'_f1.wep','World',[pkg({'layers':[prefix+'scenery.layer']})]),
        (prefix+'scenery.layer','WOInstances',[canonical_pkg({'instances':[],'layer':'scenery'})]),
        (base,'WOInstances',[canonical_pkg({'instances':items,'layer':'vehicles'})]),
        (extra,'WOInstances',[canonical_pkg({'instances':[placement('myteam$GridSlot3','GridWheelMarker',3,16)],'layer':'vehicles_myteam'})])]
    path=folder/'wep'/(folder.name+'_common.erp');path.write_bytes(erp(resources))
    return path
