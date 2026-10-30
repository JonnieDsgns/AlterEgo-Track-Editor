"""Independent decoder following the documented modern EGO declarations.

Coordinates stay native Y-up. No proprietary code or shader implementation.
"""
import array
from dataclasses import dataclass, field
import json
import math
import struct
import sys


def u32(data, p):
    if p < 0 or p+4 > len(data):
        raise ValueError('Truncated descriptor')
    return struct.unpack_from('<I', data, p)[0]


def region(data, p, size):
    if p < 0 or size < 0 or p+size > len(data):
        raise ValueError('Descriptor region out of bounds')
    return memoryview(data)[p:p+size]


def cstring(data, p, end=None):
    end = len(data) if end is None else end
    if not 0 <= p < end <= len(data):
        raise ValueError('String offset out of bounds')
    stop = data.find(b'\0', p, end)
    if stop < 0:
        raise ValueError('Unterminated string')
    return data[p:stop].decode('utf-8')


def pool(data, start, end, count):
    region(data, start, end-start)
    result = []
    while start < end:
        value = cstring(data, start, end)
        result.append(value)
        start += len(value.encode('utf-8'))+1
    if len(result) != count:
        raise ValueError('URI pool count mismatch')
    return result


def packed(kind, values):
    result = array.array(kind, values)
    if sys.byteorder != 'little':
        result.byteswap()
    return result.tobytes()


@dataclass
class Geometry:
    positions: bytes
    normals: bytes
    indices: bytes
    bounds: list
    triangles: int
    warnings: list
    uvs: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    colours: bytes = b''

    def binary(self, variants=None):
        meta=json.dumps(dict(groups=self.groups or [dict(first=0,count=len(self.indices)//4,slot='Default')],variants=variants or {}),separators=(',',':'),allow_nan=False).encode()
        meta+=b' '*((-len(meta))%4)
        count=len(self.positions)//12
        uv=[self.uvs[i] if i<len(self.uvs) else b'\0'*(count*8) for i in range(3)]
        return struct.pack('<4sIII', b'TVG2', count,len(self.indices)//4,len(meta))+meta+self.positions+self.normals+b''.join(uv)+self.indices


def buffer(catalog, uri):
    header = catalog.read(uri, 0)
    if len(header) != 16:
        raise ValueError('Buffer header must be 16 bytes')
    _, stride, count, fmt = struct.unpack('<4I', header)
    data = catalog.read(uri, 1)
    if not stride or len(data) != stride*count:
        raise ValueError('Buffer length mismatch')
    return stride, count, fmt, data


def triangles(catalog, position_uri, index_uri, first, count, base, normal_uri=None, attributes=None):
    stride, vertices, fmt, pos = buffer(catalog, position_uri)
    if stride != 12 or fmt != 39:
        raise ValueError('Unsupported POSITION format/stride')
    width, icount, _, ib = buffer(catalog, index_uri)
    if width not in (2, 4) or count % 3 or first+count > icount:
        raise ValueError('Invalid triangle index range')
    if count > 30_000_000:
        raise ValueError('Geometry exceeds per-resource limit')
    raw = array.array('H' if width == 2 else 'I')
    raw.frombytes(region(ib, first*width, count*width))
    if sys.byteorder != 'little':
        raw.byteswap()
    remap = {}
    ids = []
    indices = []
    for index in raw:
        source = base+index
        if source >= vertices:
            raise ValueError('Vertex index outside POSITION buffer')
        if source not in remap:
            remap[source] = len(ids)
            ids.append(source)
        indices.append(remap[source])
    positions = [struct.unpack_from('<3f', pos, i*12) for i in ids]
    if any(not all(map(math.isfinite, p)) for p in positions):
        raise ValueError('Non-finite position')
    normals = None
    if normal_uri:
        try:
            ns, nc, nf, data = buffer(catalog, normal_uri)
            if ns == 8 and nf == 35 and all(i < nc for i in ids):
                normals = [struct.unpack_from('<4e', data, i*ns)[:3] for i in ids]
                if any(not all(map(math.isfinite, n)) for n in normals):
                    normals = None
        except ValueError:
            pass
    if normals is None:
        normals = [[0., 0., 0.] for _ in ids]
        for j in range(0, len(indices), 3):
            a, b, c = (positions[i] for i in indices[j:j+3])
            x, y = [b[k]-a[k] for k in range(3)], [c[k]-a[k] for k in range(3)]
            n = [x[1]*y[2]-x[2]*y[1], x[2]*y[0]-x[0]*y[2], x[0]*y[1]-x[1]*y[0]]
            for i in indices[j:j+3]:
                for k in range(3):
                    normals[i][k] += n[k]
    normals = [[x/(math.sqrt(sum(v*v for v in n)) or 1) for x in n] for n in normals]
    if attributes is None:
        return positions, normals, indices
    uvs={}
    for channel,uri,pair,flip in attributes:
        stride,n,fmt,data=buffer(catalog,uri)
        if not all(i<n for i in ids):raise ValueError('UV index outside buffer')
        if channel==-1:
            if (stride,fmt)==(4,14):
                uvs[-1]=[tuple(v/255 for v in struct.unpack_from('<4B',data,i*4)) for i in ids]
            elif (stride,fmt)==(8,35):
                # Half-float RGBA colour (seen in nine F1 25 terrain resources); clamped for preview.
                colours=[struct.unpack_from('<4e',data,i*8) for i in ids]
                if any(not all(map(math.isfinite,c)) for c in colours):raise ValueError('Non-finite vertex colour')
                uvs[-1]=[tuple(min(max(v,0.),1.) for v in c) for c in colours]
            else:raise ValueError('Unsupported vertex colour format')
            continue
        if (stride,fmt) in ((4,29),(8,35)):
            unpack='<2e';offset=pair*4
        elif (stride,fmt)==(16,39):
            unpack='<2f';offset=pair*8
        else:raise ValueError(f'Unsupported UV format {fmt}/{stride}')
        if offset+struct.calcsize(unpack)>stride:raise ValueError('UV pair outside stride')
        coords=[struct.unpack_from(unpack,data,i*stride+offset) for i in ids]
        if any(not all(map(math.isfinite,p)) for p in coords):raise ValueError('Non-finite UV')
        uvs[channel]=[(u,1-v if flip else v) for u,v in coords]
    return positions,normals,indices,uvs


def combine(parts, warnings=None):
    pos, normals, indices = [], [], []
    uv=[[],[],[]];colours=[];has_colours=False
    for part in parts:
        p,n,ix=part[:3]
        channels=part[3] if len(part)>3 else {}
        has_colours=has_colours or -1 in channels
        colours.extend(channels.get(-1,[(1.,1.,1.,1.)]*len(p)))
        offset = len(pos)
        pos.extend(p)
        normals.extend(n)
        indices.extend(i+offset for i in ix)
        for k in range(3):uv[k].extend(channels.get(k,[(0.,0.)]*len(p)))
    if not pos or not indices:
        raise ValueError('No supported triangle geometry')
    low = [min(p[k] for p in pos) for k in range(3)]
    high = [max(p[k] for p in pos) for k in range(3)]
    return Geometry(packed('f', (v for p in pos for v in p)),
                    packed('f', (v for n in normals for v in n)),
                    packed('I', indices), low+high, len(indices)//3, warnings or [],
                    [packed('f',(v for pair in coords for v in pair)) for coords in uv],
                    colours=packed('f',(v for c in colours for v in c)) if has_colours else b'')


def mesh(catalog, uri):
    data = catalog.read(uri)
    if len(data) < 76:
        raise ValueError('Legacy or truncated mesh descriptor')
    n, v, i = struct.unpack_from('<3I', data)
    if not 0 < n <= 100000 or i != 1:
        raise ValueError('Unsupported submesh/index-buffer layout')
    region(data, 76, 88*n)
    offsets = [76+u32(data, p) for p in (20, 24, 28, 32, 40, 44)]
    vb, ib = pool(data, offsets[0], offsets[1], v), pool(data, offsets[1], offsets[2], i)
    dc = u32(data, 36)
    region(data, offsets[4], dc*20)
    region(data, offsets[5], dc*8)
    def attribute(record, semantic,channel=0):
        active = u32(data, record)
        if active > 8:
            raise ValueError('Invalid attribute count')
        for lane in range(active):
            index = u32(data, record+56+4*lane)
            if index >= dc:
                raise ValueError('Invalid declaration index')
            decl = struct.unpack_from('<5I', data, offsets[4]+20*index)
            if decl[2:4] == (semantic, channel):
                if decl[1] != 0:
                    raise ValueError('Interleaved attribute offsets unsupported')
                stream = u32(data, offsets[5]+8*index+4)
                if stream >= len(vb):
                    raise ValueError('Invalid vertex-buffer binding')
                if semantic == 1 and decl[4] != 47:
                    raise ValueError('Unsupported position declaration')
                return vb[stream]
        return None
    parts = [];groups=[];first_output=0
    for index in range(n):
        p = 76+88*index
        first, count, base = struct.unpack_from('<3I', data, p+12)
        position = attribute(p, 1)
        if not position:
            raise ValueError('Position declaration missing')
        attrs=[]
        primary=attribute(p,5,0)
        secondary=attribute(p,5,1)
        if primary:
            attrs.append((0,primary,0,False))
            stride,_,_,_=buffer(catalog,primary)
            if stride in (8,16):attrs.append((1,primary,1,False))
        if secondary:attrs.append((2,secondary,0,False))
        parts.append(triangles(catalog, position, ib[0], first, count, base, attribute(p, 2),attrs))
        slot=cstring(data,offsets[2]+u32(data,p+48),offsets[3])
        groups.append(dict(first=first_output,count=count,slot=slot));first_output+=count
    result=combine(parts)
    result.groups=groups
    return result


def terrain_info(data):
    n, m, d, v = struct.unpack_from('<4I', data)
    strings = 20+72*n+20*d+36*m+8*v
    if not n or not m or not v or strings >= len(data):
        raise ValueError('Invalid terrain header')
    p = 16+48*n
    cells = [struct.unpack_from('<4I', data, p+16*j) for j in range(n)]
    p += 16*n
    draws = [struct.unpack_from('<4I', data, p+16*j) for j in range(d)]
    p += 16*d
    mats = [u32(data, p+4*j) for j in range(d)]
    p += 4*d
    bindings = [struct.unpack_from('<8I', data, p+32*j) for j in range(m)]
    p += 32*m+4*v+8*n
    names = [cstring(data, strings+u32(data, p+4*j)) for j in range(1+v+m)]
    result = []
    for cell, (count, first, mapping, _) in enumerate(cells):
        if first+count > d or mapping+count > d:
            raise ValueError('Invalid terrain draw range')
        for j in range(count):
            material = mats[mapping+j]
            if material >= m:
                raise ValueError('Invalid terrain material')
            binding = bindings[material]
            if binding[0] >= v:
                raise ValueError('Invalid terrain position binding')
            attrs=[]
            if binding[3]<v:attrs.append((-1,names[1+binding[3]],0,False))
            for lane in (4,5):
                if binding[lane]<v:
                    for pair in range(2):
                        channel=(lane-4)*2+pair
                        if channel<3:attrs.append((channel,names[1+binding[lane]],pair,True))
            result.append((cell, j, names[1+binding[0]], names[0], draws[first+j],
                           names[1+binding[1]] if binding[1] < v else None,attrs,names[1+v+material]))
    return result
