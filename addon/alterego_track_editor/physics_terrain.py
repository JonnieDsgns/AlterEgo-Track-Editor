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


# Legacy layout limits of game-tested community builds (Istanbul ports on Spa/Sepang bases):
# XZ chunks <=1000 triangles, <=1023 vertices, <=8 codes; per-cell quadtree with an internal
# root, leaves of <=24 references and depth <=6; edge bits 7; unused palette slots padded with
# codes the base track already uses; header word 0x14 = name-table offset as in stock files.
CHUNK_TRIANGLES,CHUNK_VERTICES,LEAF_REFERENCES,LEAF_DEPTH,LEAF_MARGIN=1000,1023,24,6,0.25
DEFAULT_WORD=0xff808080


class _Oversized(Exception):
    pass


def triangle_soup(cells):
    """Native triangles of the given cells in physics-local space: (A,B,C,code,(wordA,wordB,wordC))."""
    for cell in cells:
        positions=cell.positions();palette=cell.palette
        words=[struct.unpack_from('<I',cell.data,144+i*16+12)[0] for i in range(cell.vertices)]
        for a,b,c,slot,_ in cell.faces():
            yield positions[a],positions[b],positions[c],palette[slot],(words[a],words[b],words[c])


def code_words(parsed):
    """Most common vertex word per native code, used for authored triangles of that code."""
    counts={}
    for cell in parsed.cells:
        palette=cell.palette
        for a,b,c,slot,_ in cell.faces():
            for v in (a,b,c):
                word=struct.unpack_from('<I',cell.data,144+v*16+12)[0];bucket=counts.setdefault(palette[slot],{})
                bucket[word]=bucket.get(word,0)+1
    return {code:max(bucket,key=lambda w:(bucket[w],-w)) for code,bucket in counts.items()}


def build_legacy(faces,codes=None,words=None):
    """faces: (A,B,C,code[,(three vertex words)]) in physics-local axes. Never emits 0x20004.

    codes: allowed physical codes (the base track's own codes for a track rebuild; defaults to
    the conservative authoring set). words: default vertex word per code.
    """
    allowed=list(dict.fromkeys(codes or KNOWN_CODES));allowed_set=set(allowed);words=words or {};triangles=[]
    for face in faces:
        a,b,c,code=face[:4]
        if len(triangles)>=MAX_TRIANGLES:raise ValueError('Collision triangle budget exceeded')
        if code not in allowed_set:raise ValueError(f'Physics code {code} is not used by the base track collision')
        if any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in (a,b,c)):raise ValueError('Non-finite collision geometry')
        a,b,c=[tuple(f32(v) for v in p) for p in (a,b,c)]
        u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        if sum(x*x for x in cross)<1e-14:raise ValueError('Collision triangle collapses at native precision')
        vertex_words=tuple(face[4]) if len(face)>4 else (words.get(code,DEFAULT_WORD),)*3
        triangles.append((a,b,c,code,vertex_words))
    if not triangles:raise ValueError('No collision triangles')
    xs=[p[0] for t in triangles for p in t[:3]];zs=[p[2] for t in triangles for p in t[:3]]
    size=max(max(xs)-min(xs),max(zs)-min(zs),1.0)
    cells=[]
    _chunk(triangles,list(range(len(triangles))),(min(xs),min(zs),size),[],allowed,cells,0)
    if len(cells)>100000:raise ValueError('Collision cell budget exceeded')
    names_offset=32+32*len(cells)
    out=bytearray(names_offset);out[:4]=b'JPAK';struct.pack_into('<II',out,8,len(cells),16);struct.pack_into('<I',out,0x14,names_offset)
    names=[]
    for name,_ in cells:names.append(len(out));out.extend(name.encode()+b'\0')
    for i,(_,raw) in enumerate(cells):
        out.extend(b'\0'*(-len(out)%16));offset=len(out);out.extend(raw)
        struct.pack_into('<4I',out,32+32*i,names[i],len(raw),offset,len(raw))
    result=bytes(out);check=PhysicsTerrain(result,0x20002)
    expected=sorted((t[:4] for t in triangles));actual=[]
    for cell in check.cells:
        positions=cell.positions();palette=cell.palette
        for a,b,c,slot,_ in cell.faces():
            # Cells start each triangle at its lowest vertex index; compare up to rotation.
            tri=[positions[a],positions[b],positions[c]];k=tri.index(min(tri));actual.append((*tri[k:],*tri[:k],palette[slot]))
    canonical=lambda t:(lambda tri,k:(*tri[k:],*tri[:k],t[3]))(list(t[:3]),list(t[:3]).index(min(t[:3])))
    if sorted(actual)!=sorted(canonical(t) for t in expected):raise ValueError('Legacy collision geometry readback failed')
    return result


def _chunk(triangles,ids,rect,path,allowed,cells,depth):
    codes={triangles[i][3] for i in ids}
    if len(ids)<=CHUNK_TRIANGLES and len(codes)<=8:
        try:
            cells.append(('qt'+''.join('_'+p for p in path)+'.vcqtc',_legacy_cell([triangles[i] for i in ids],allowed)));return
        except _Oversized:
            pass
    if depth>=24:raise ValueError('Collision is too dense to partition into legacy chunks')
    x,z,size=rect;half=size/2;quadrants={}
    for i in ids:
        a,b,c=triangles[i][:3]
        cx=(a[0]+b[0]+c[0])/3;cz=(a[2]+b[2]+c[2])/3
        quadrants.setdefault((int(cx>=x+half),int(cz>=z+half)),[]).append(i)
    if len(quadrants)==1 and depth>=12:
        # Coincident centroids: split deterministically by input order instead of space.
        middle=len(ids)//2;quadrants={(0,0):ids[:middle],(1,1):ids[middle:]}
    for (hx,hz),members in sorted(quadrants.items()):
        _chunk(triangles,members,(x+hx*half,z+hz*half,half),path+[f'{hx}{hz}'],allowed,cells,depth+1)


def _legacy_cell(faces,allowed):
    used=list(dict.fromkeys(f[3] for f in faces))
    palette=used+[c for c in allowed if c not in used][:8-len(used)]
    palette+=[used[0]]*(8-len(palette))
    # Spatially ordered triangles keep vertex indices close (B/C are A plus one byte).
    def morton(face):
        cx=sum(p[0] for p in face[:3])/3;cz=sum(p[2] for p in face[:3])/3
        return (round(cx,1),round(cz,1))
    faces=sorted(faces,key=morton)
    vertices=[];lookup={};encoded=[]
    for a,b,c,code,vertex_words in faces:
        index=[]
        for point,word in zip((a,b,c),vertex_words):
            key=(point,word);found=lookup.get(key)
            if found is None or len(vertices)-found>200:
                found=len(vertices);vertices.append(key);lookup[key]=found
            index.append(found)
        if max(index)-min(index)>255:
            index=[];base=len(vertices)
            for point,word in zip((a,b,c),vertex_words):vertices.append((point,word));index.append(len(vertices)-1)
        k=index.index(min(index));index=index[k:]+index[:k]
        encoded.append((index,palette.index(code)))
    if len(vertices)>CHUNK_VERTICES:raise _Oversized()
    points=[v[0] for v in vertices]
    lower=[min(f32(min(p[k] for p in points)-.001),neighbor(min(p[k] for p in points),False)) for k in range(3)]
    upper=[max(f32(max(p[k] for p in points)+.001),neighbor(max(p[k] for p in points),True)) for k in range(3)]
    if not all(map(math.isfinite,lower+upper)):raise ValueError('Collision bounds cannot be represented')
    nodes,leaves=_legacy_tree(faces,(lower[0],lower[2],upper[0],upper[2]))
    references=bytearray();words=[]
    for leaf in leaves:
        if leaf is None:words.append(0xffff);continue
        if len(references)>0x7fff:raise _Oversized()
        words.append(0x8000|len(references))
        previous=leaf[0];references.extend(struct.pack('>H',previous))
        for current in leaf[1:]:
            while current-previous>254:previous+=254;references.append(254)  # real filler triangle references
            references.append(current-previous);previous=current
        references.append(255)
    n=len(faces);node=144+len(vertices)*16;tri=node+2*len(nodes);refs=tri+n*4
    raw=bytearray(refs+len(references))
    for p,value in ((0,0x20002),(28,n),(32,len(vertices)),(36,8),(40,144),(48,node),(56,tri),(64,refs)):struct.pack_into('<I',raw,p,value)
    struct.pack_into('<6f',raw,4,*lower,*upper)
    for i,code in enumerate(palette):raw[80+i*4:84+i*4]=code_bytes(code)
    for i,(point,word) in enumerate(vertices):struct.pack_into('<3fI',raw,144+i*16,*point,word)
    for i,word in enumerate(nodes):struct.pack_into('>H',raw,node+2*i,word if word<0x8000 else words[word-0x8000])
    for i,(index,slot) in enumerate(encoded):
        a,b,c=index
        if a>1023:raise _Oversized()
        raw[tri+i*4:tri+i*4+4]=bytes([(7<<5)|(slot<<2)|(a>>8),a&255,b-a,c-a])
    raw[refs:]=references
    return bytes(raw)


def _legacy_tree(faces,rect):
    """Breadth-first quadtree: four consecutive children per internal node, child order
    low-X/high-Z, high-X/high-Z, low-X/low-Z, high-X/low-Z. Returns node words (internal
    child index, or 0x8000+leaf number) and leaf triangle lists (None = empty child)."""
    boxes=[(min(p[0] for p in f[:3])-LEAF_MARGIN,min(p[2] for p in f[:3])-LEAF_MARGIN,
            max(p[0] for p in f[:3])+LEAF_MARGIN,max(p[2] for p in f[:3])+LEAF_MARGIN) for f in faces]
    nodes=[None];leaves=[];queue=[(0,rect,list(range(len(faces))),0)];head=0
    while head<len(queue):
        slot,(x0,z0,x1,z1),members,depth=queue[head];head+=1
        if depth>0 and (len(members)<=LEAF_REFERENCES or depth>=LEAF_DEPTH):
            nodes[slot]=0x8000+len(leaves);leaves.append(sorted(members) if members else None);continue
        xm,zm=(x0+x1)/2,(z0+z1)/2;first=len(nodes);nodes[slot]=first;nodes.extend([None]*4)
        if first>0x7fff:raise _Oversized()
        for k,child in enumerate(((x0,zm,xm,z1),(xm,zm,x1,z1),(x0,z0,xm,zm),(xm,z0,x1,zm))):
            inside=[i for i in members if boxes[i][0]<=child[2] and boxes[i][2]>=child[0] and boxes[i][1]<=child[3] and boxes[i][3]>=child[1]]
            queue.append((first+k,child,inside,depth+1))
    return nodes,leaves
