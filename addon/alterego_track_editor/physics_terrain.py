"""Bounded JPAK/VCQTC codecs from the owned AlterEgo format contracts.

Native 0x20004 geometry/search bytes are immutable. Surface palette/slot edits
preserve acceleration data. New geometry uses explicit legacy 0x20002 only.
"""
from dataclasses import dataclass
import math,struct
from bisect import bisect_left

KNOWN_CODES=('DEFA','GRS+','HDG+','RMBL','SCON','CON+','METL','SDT+','PDT+','DDT+','ASTR')
MAX_TRIANGLES=1_000_000


def u32(data,p):
    if p<0 or p+4>len(data):raise ValueError('Truncated physics field')
    return struct.unpack_from('<I',data,p)[0]


def point(data,p):
    if p<0 or p+12>len(data):raise ValueError('Truncated physics point')
    values=struct.unpack_from('<3f',data,p)
    if not all(map(math.isfinite,values)):raise ValueError('Non-finite physics position/bounds')
    return values


@dataclass
class Cell:
    index:int
    name:str
    offset:int
    data:memoryview
    version:int
    bounds:tuple
    triangles:int
    vertices:int
    node:int
    triangle:int
    refs:int

    @property
    def palette(self):return [code_label(bytes(self.data[80+i*4:84+i*4])) for i in range(8)]

    def positions(self):return [point(self.data,144+i*16) for i in range(self.vertices)]

    def faces(self):
        for i in range(self.triangles):
            p=self.triangle+i*4;flags,a,b,c=self.data[p:p+4];a=((flags&3)<<8)|a
            yield (a,a+b,a+c,(flags>>2)&7,flags>>5)

    def codes(self):
        palette=self.palette
        return [palette[face[3]] for face in self.faces()]


class PhysicsTerrain:
    def __init__(self,data,expected_version=None):
        if len(data)>128*1024**2 or len(data)<32 or data[:4]!=b'JPAK':raise ValueError('Expected bounded physics JPAK')
        self.data=bytes(data);count,alignment=u32(data,8),u32(data,12)
        if not 0<count<=100000 or alignment!=16 or 32+count*32>len(data):raise ValueError('Invalid physics container table')
        self.cells=[];names=set();ranges=[];versions=set();total=0
        for i in range(count):
            p=32+i*32;name,size,offset,packed=struct.unpack_from('<4I',data,p)
            if size!=packed or size<144 or offset%16 or offset<32+count*32 or offset+size>len(data) or not 32+count*32<=name<len(data):
                raise ValueError('Invalid physics cell range')
            end=data.find(b'\0',name,min(name+2048,len(data)))
            if end<0:raise ValueError('Unterminated physics cell name')
            label=data[name:end].decode('utf-8')
            if not label.endswith('.vcqtc') or label in names:raise ValueError('Invalid/duplicate physics cell name')
            names.add(label);raw=memoryview(self.data)[offset:offset+size];version=u32(raw,0)
            if version not in (0x20002,0x20004) or (expected_version is not None and version!=expected_version):
                raise ValueError('Unsupported or mismatched physics version')
            versions.add(version)
            bounds=point(raw,4)+point(raw,16)
            if any(bounds[k]>bounds[k+3] for k in range(3)):raise ValueError('Invalid physics bounds')
            triangles,vertices,materials=[u32(raw,k) for k in (28,32,36)]
            vo,node,tri,refs=[u32(raw,k) for k in (40,48,56,64)]
            total+=triangles
            expected=tri+triangles*4
            if version==0x20004:expected=(expected+15)&~15
            if not triangles or not vertices or total>MAX_TRIANGLES or materials!=8 or vo!=144 or node!=144+vertices*16 or tri<node or (tri-node)%2 or refs!=expected or refs>size:
                raise ValueError('Invalid physics cell layout/budget')
            cell=Cell(i,label,offset,raw,version,bounds,triangles,vertices,node,tri,refs)
            for j in range(vertices):
                v=point(raw,144+j*16)
                if any(v[k]<bounds[k]-.001 or v[k]>bounds[k+3]+.001 for k in range(3)):raise ValueError('Physics vertex outside bounds')
            palette=cell.palette
            for a,b,c,slot,_ in cell.faces():
                if max(a,b,c)>=vertices:raise ValueError('Physics triangle index outside cell')
            self._leaves(cell)
            self.cells.append(cell);ranges.append((offset,offset+size,name,end+1))
        if len(versions)!=1:raise ValueError('Mixed physics versions require explicit handling')
        self.version=versions.pop()
        ordered=sorted(ranges)
        if any(a[1]>b[0] for a,b in zip(ordered,ordered[1:])):raise ValueError('Overlapping physics cells')
        starts=[r[0] for r in ordered]
        for _,_,start,end in ranges:
            j=bisect_left(starts,end)-1
            if j>=0 and ordered[j][1]>start:raise ValueError('Cell name overlaps physics payload')

    @staticmethod
    def _leaves(cell):
        raw=cell.data;stack=[0];visited=set();covered=bytearray(cell.triangles);ranges=[]
        while stack:
            index=stack.pop()
            if index<0 or index>=(cell.triangle-cell.node)//2 or index in visited:raise ValueError('Invalid/cyclic physics search tree')
            visited.add(index);word=struct.unpack_from('>H',raw,cell.node+2*index)[0]
            if word<0x8000:stack.extend(reversed(range(word,word+4)));continue
            if word==0xffff:continue
            start=(word&0x7fff)*(4 if cell.version==0x20004 else 1);p=cell.refs+start
            if cell.version==0x20002:
                if p+3>len(raw):raise ValueError('Legacy leaf outside references')
                triangle=struct.unpack_from('>H',raw,p)[0];p+=2
                while True:
                    if triangle>=cell.triangles:raise ValueError('Legacy leaf triangle outside cell')
                    covered[triangle]=1
                    if p>=len(raw):raise ValueError('Unterminated legacy physics leaf')
                    delta=raw[p];p+=1
                    if delta==255:break
                    triangle+=delta
                end=p-cell.refs
            else:
                if p+6>len(raw):raise ValueError('Native leaf outside references')
                count,aux=raw[p+4],raw[p+5]
                records=(p+6+count*2+3)&~3;end=records+count*4
                if not count or aux>count or end>len(raw):raise ValueError('Invalid native leaf layout')
                if count%2==0 and struct.unpack_from('<H',raw,p+6+count*2)[0]!=0xffff:raise ValueError('Invalid native leaf alignment')
                for j in range(count):
                    triangle=struct.unpack_from('<H',raw,p+6+j*2)[0]
                    if triangle>=cell.triangles:raise ValueError('Native leaf triangle outside cell')
                    covered[triangle]=1
                end-=cell.refs
            ranges.append((start,end))
        ordered=sorted(ranges)
        if not all(covered) or not ranges or any(a[1]>b[0] for a,b in zip(ordered,ordered[1:])):
            raise ValueError('Incomplete/overlapping physics search coverage')
        if cell.version==0x20002 and (ordered[0][0]!=0 or ordered[-1][1]!=len(raw)-cell.refs or any(a[1]!=b[0] for a,b in zip(ordered,ordered[1:]))):
            raise ValueError('Unexplained legacy reference bytes')

    def edit_codes(self,changes):
        if not changes:return self.data
        if any(type(i) is not int or not 0<=i<len(self.cells) for i in changes):raise ValueError('Invalid physics cell identity')
        observed={code for c in self.cells for code in c.codes()};out=bytearray(self.data)
        for index,codes in changes.items():
            cell=self.cells[index];palette=cell.palette;faces=list(cell.faces())
            if len(codes)!=cell.triangles or any(c not in observed|set(KNOWN_CODES) for c in codes):
                raise ValueError('Invalid/unrecognized physics code assignment')
            if len(set(codes))>8:raise ValueError('A native cell supports at most eight physical codes')
            slots=[None]*len(codes);reserved=set();mapping={}
            for i,(code,face) in enumerate(zip(codes,faces)):
                if code==palette[face[3]]:slots[i]=face[3];reserved.add(face[3])
            for code in sorted(set(codes)):
                if code in palette:
                    mapping[code]=next((j for j in sorted(reserved) if palette[j]==code),palette.index(code))
                    reserved.add(mapping[code])
            needed=len(set(codes)-set(mapping))
            for slot in sorted(reserved-set(mapping.values()),reverse=True):
                if 8-len(reserved)>=needed:break
                canonical=mapping[palette[slot]]
                slots=[canonical if j==slot else j for j in slots];reserved.remove(slot)
            for code in sorted(set(codes)-set(mapping)):
                slot=next(j for j in range(8) if j not in reserved);mapping[code]=slot;reserved.add(slot);palette[slot]=code
            for j,code in enumerate(palette):out[cell.offset+80+j*4:cell.offset+84+j*4]=code_bytes(code)
            for i,code in enumerate(codes):
                slot=slots[i] if slots[i] is not None else mapping[code];p=cell.offset+cell.triangle+i*4
                out[p]=(out[p]&0xe3)|(slot<<2)
        result=bytes(out);PhysicsTerrain(result,self.version)
        return result


def code_valid(code):return isinstance(code,str) and len(code)==4 and all(32<=ord(c)<=126 for c in code)


def code_label(raw):
    return raw.decode('ascii') if all(32<=c<=126 for c in raw) else 'HEX_'+raw.hex().upper()


def code_bytes(label):
    if code_valid(label):return label.encode('ascii')
    if isinstance(label,str) and label.startswith('HEX_') and len(label)==12:
        try:return bytes.fromhex(label[4:])
        except ValueError:pass
    raise ValueError('Invalid native palette token')


def f32(x):
    try:return struct.unpack('<f',struct.pack('<f',x))[0]
    except (OverflowError,struct.error):raise ValueError('Physics value exceeds Float32')


def neighbor(x,up):
    bits=struct.unpack('<I',struct.pack('<f',x))[0]
    if x==0:bits=1 if up else 0x80000001
    elif (x>0)==up:bits+=1
    else:bits-=1
    return struct.unpack('<f',struct.pack('<I',bits))[0]


def build_legacy(faces):
    """faces: iterable of (A,B,C,explicit four-character code). Never emits 0x20004."""
    buckets={};count=0
    for a,b,c,code in faces:
        count+=1
        if count>MAX_TRIANGLES or code not in KNOWN_CODES:raise ValueError('Collision triangle budget or native code unsupported')
        if any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in (a,b,c)):raise ValueError('Non-finite collision geometry')
        a,b,c=[tuple(f32(v) for v in p) for p in (a,b,c)]
        u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        if sum(x*x for x in cross)<1e-14:raise ValueError('Collision triangle collapses at native precision')
        key=(math.floor((a[0]+b[0]+c[0])/96),math.floor((a[2]+b[2]+c[2])/96))
        if any(not -2**31<=x<2**31 for x in key):raise ValueError('Collision coordinates exceed spatial range')
        buckets.setdefault(key,[]).append((a,b,c,code))
    if not count:raise ValueError('No authored collision triangles')
    cells=[]
    for key in sorted(buckets):
        group=[];palette=[]
        for face in buckets[key]:
            if group and (len(group)==64 or (face[3] not in palette and len(palette)==8)):
                cells.append(_legacy_cell(group,palette));group=[];palette=[]
            group.append(face)
            if face[3] not in palette:palette.append(face[3])
        if group:cells.append(_legacy_cell(group,palette))
    if len(cells)>100000:raise ValueError('Collision cell budget exceeded')
    out=bytearray(32+32*len(cells));out[:4]=b'JPAK';struct.pack_into('<II',out,8,len(cells),16)
    names=[]
    for i in range(len(cells)):names.append(len(out));out.extend(f'qt_{i:06d}.vcqtc\0'.encode())
    for i,raw in enumerate(cells):
        out.extend(b'\0'*(-len(out)%16));offset=len(out);out.extend(raw)
        struct.pack_into('<4I',out,32+32*i,names[i],len(raw),offset,len(raw))
    result=bytes(out);check=PhysicsTerrain(result,0x20002)
    if sum(c.triangles for c in check.cells)!=count:raise ValueError('Legacy collision readback failed')
    return result


def _legacy_cell(faces,palette):
    n=len(faces);vertices=n*3;node=144+vertices*16;tri=node+2;refs=tri+n*4
    raw=bytearray(refs+2+n)
    for p,value in ((0,0x20002),(28,n),(32,vertices),(36,8),(40,144),(48,node),(56,tri),(64,refs)):struct.pack_into('<I',raw,p,value)
    points=[]
    for i,(a,b,c,code) in enumerate(faces):
        for j,point in enumerate((a,b,c)):struct.pack_into('<3fI',raw,144+(i*3+j)*16,*point,0xff808080);points.append(point)
        base=i*3;raw[tri+i*4:tri+i*4+4]=bytes([(7<<5)|(palette.index(code)<<2)|(base>>8),base&255,1,2])
    lower=[min(f32(min(p[k] for p in points)-.001),neighbor(min(p[k] for p in points),False)) for k in range(3)]
    upper=[max(f32(max(p[k] for p in points)+.001),neighbor(max(p[k] for p in points),True)) for k in range(3)]
    if not all(map(math.isfinite,lower+upper)):raise ValueError('Collision bounds cannot be represented')
    struct.pack_into('<6f',raw,4,*lower,*upper)
    for i in range(8):raw[80+i*4:84+i*4]=(palette[i] if i<len(palette) else 'DEFA').encode()
    struct.pack_into('>H',raw,node,0x8000)
    for i in range(1,n):raw[refs+1+i]=1
    raw[-1]=255
    return bytes(raw)
