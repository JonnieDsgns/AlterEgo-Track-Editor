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
    resources=[(prefix+folder.name+'_common.wep','World',[pkg({'layers':[layer]})]),
        (layer,'WOInstances',[canonical_pkg({'instances':[barrier,board,spare],'layer':'objects'})]),
        (family+'?render','ModelProxyRes',[render_nodes()]),
        (prefix+folder.name+'_f1.header.pvsbin','PVSObjIDRes',[pvs_objects(['objects$barrier_a'])]),
        (prefix+folder.name+'_f1.volumedata.pvsbin','PVSVisRes',[pvs_cells(1,[[1],[1],[],[1],[]],[[],[],[],[],[]])]),
        ('eaid://ego_package/lightmap_locations','LightMapLocRes',[struct.pack('<I16sIfff',1,bytes([1])*16,2,64/4096,0.25,0.5)])]
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


def bxml(tree):
    """Independent fixture encoder: (name, [(key, value)], [children]) -> stock-style BXML bytes."""
    out=bytearray(b'\x01BXML')
    def emit(node):
        name,attrs,children=node
        payload=name.encode()+b'\0'+b''.join(k.encode()+b'\0'+v.encode()+b'\0' for k,v in attrs)
        out.extend(struct.pack('<hBBh',len(payload)+4,0,0,len(attrs))+payload)
        for child in children:emit(child)
        out.extend(b'\x04\x00\x05\x00\x00\x00')
    emit(tree);out.extend(b'\x04\x00\x06\x00\x00\x00'*2)
    return bytes(out)


def make_route_track(folder):
    """Square 400 m main loop, open pit spline, AI gates and gameplay/audio markup."""
    folder=Path(folder);(folder/'wep').mkdir(parents=True)
    code=folder.name;prefix='eaid://environment_package/tracks/'+code+'/';layer=prefix+'wep/objects.layer'
    corners=[(0,0,0),(100,0,0),(100,0,100),(0,0,100)];main=[]
    for (ax,ay,az),(bx,by,bz) in zip(corners,corners[1:]+corners[:1]):
        main+=[(ax+(bx-ax)*i/10,0,az+(bz-az)*i/10) for i in range(10)]
    knot=lambda p:('Knot',[('position','%g, %g, %g'%p)],[])
    trackspace=bxml(('rootnode',[],[('TrackSpaceSpline',[('name','maintrack')],[knot(p) for p in main]),
        ('TrackSpaceSpline',[('name','pit_1')],[knot((x,0,-10)) for x in range(0,101,10)])]))
    ts=bxml(('Trackspace',[('Version','ts_data_v3.002')],[('VolumeList',[('name','trackspace_0'),('type','main'),('numVolumes','0'),('closed','True')],[]),
        ('VolumeList',[('name','trackspace_1'),('type','pit'),('numVolumes','0'),('closed','False')],[])]))
    def markup(name,spline,start,end,types,props=()):
        return ('MarkupElement',[('Name',name),('Start',start),('End',end),('SplineName',spline)],[('Attributes',[],
            [('Attribute',[('Type',t)],[('Properties',[],[('Property',[('Type',k),('Value',v)],[]) for k,v in props])]) for t in types])])
    tm=bxml(('TrackspaceMarkup',[('Version','ts_data_v3.002')],[('MarkupList',[],[markup('sector1','maintrack','0','0.3',['sector_1']),
        markup('sector2','maintrack','0.3','0.7',['sector_2']),markup('sector3','maintrack','0.7','1',['sector_3']),
        markup('drs_activation_1','maintrack','0.9','0.1',['drs_act'],[('ID','1')]),markup('pit_limiter_on','pit_1','0.1','0.9',['pit_lim_on']),
        markup('audio_tunnel','maintrack','0.4','0.5',['aud_env_zone'],[('zone_name','reverb_tunnel')])])]))
    def gate(i,p):
        waypoints=[('waypoint',[('id',str(n)),('type',t),('length',v)],[]) for n,(t,v) in enumerate([('racing_line','0.5'),('left_track_limit','-5'),('right_track_limit','5')])]
        return ('gate',[('id',str(i)),('name','ai_gate_track_%03d'%i)],[('position',[('x','%g'%p[0]),('y','0'),('z','%g'%p[2])],[]),
            ('normal',[('x','0'),('y','0'),('z','1')],[]),('waypoints',[('num_waypoints','3')],waypoints)])
    count=10
    ai=bxml(('track',[('name','default')],[('gates',[('num_gates',str(count))],[gate(i,p) for i,p in enumerate(main[:count])]),
        ('links',[('num_links',str(count-1))],[('link',[('id',str(i)),('from_gate',str(i)),('to_gate',str(i+1))],[]) for i in range(count-1)]),
        ('routes',[('num_routes','1')],[('route',[('id','0'),('type','track'),('from_link','0'),('to_link',str(count-2)),('from_route','track'),('to_route','track')],[])])]))
    resources=[(prefix+'wep/'+code+'_common.wep','World',[pkg({'layers':[layer]})]),(layer,'WOInstances',[canonical_pkg({'instances':[],'layer':'objects'})]),
        (prefix+'ai/'+code+'_ai_track.trackspacespline','TrackSpace',[trackspace]),(prefix+'track_space_data/'+code+'_common.trackspacedata','TS',[ts]),
        (prefix+'track_space_data/'+code+'_common.trackmarkup','TM',[tm]),(prefix+'ai/'+code+'_ai_track.aispline','AISplineData',[ai,b'TSMD'+b'\0'*116])]
    path=folder/'wep'/(code+'_common.erp');path.write_bytes(erp(resources))
    return path,tm


def pvs_objects(names):
    """Stock PVSObjIDRes layout: count, then field size, length, padded name, id, value 1."""
    out=bytearray(struct.pack('<I',len(names)))
    for i,name in enumerate(names):
        raw=name.encode();size=(len(raw)+1+3)&~3
        out+=struct.pack('<II',size,len(raw))+raw.ljust(size,b'\0')+struct.pack('<II',i+1,1)
    return bytes(out)


def pvs_cells(objects,*cell_bits):
    """PVSD v5 with absolute cells; each cell lists set bit numbers per stream (one-byte runs)."""
    bits=((objects+1+31)//32)*32+1024;size=(bits+7)//8;table=bytearray();body=bytearray()
    for n,streams in enumerate(cell_bits):
        raws=[]
        for setbits in streams:
            data=bytearray(size)
            for b in setbits:data[b>>3]|=1<<(b&7)
            raws.append(b''.join(bytes([1<<3]) if v==0 else bytes([1,v]) for v in data)+b'\0')
        cuts=[];pos=0
        for r in raws[:-1]:pos+=len(r);cuts.append(pos)
        table+=struct.pack('<IIhhhH4H',len(body),0,n*4,n*4,0,0,*cuts)+bytes(8);body+=b''.join(raws)
    spheres=b''.join(struct.pack('<4f',0,0,0,1) for _ in range(objects+1))
    header=bytearray(72);header[:4]=b'PVSD';struct.pack_into('<I',header,4,5);struct.pack_into('<I',header,16,objects+1)
    struct.pack_into('<I',header,36,bits);struct.pack_into('<II',header,52,len(cell_bits),0);struct.pack_into('<HH',header,60,0,0)
    struct.pack_into('<I',header,64,len(body));rest=bytes(40)+bytes(table)+bytes(body)+spheres
    struct.pack_into('<I',header,20,len(rest))
    return bytes(header)+rest
