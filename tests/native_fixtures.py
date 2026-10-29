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
