"""Read-only real PVS checks: strict decode of every cell, object list round trip, bit semantics, test append.

Arguments: tracks folder, output JSON. Private summary only.
"""
from pathlib import Path
import json,math,random,struct,sys,time,types

repo=Path(__file__).resolve().parents[1]
package=types.ModuleType('alterego_track_editor');package.__path__=[str(repo/'addon/alterego_track_editor')];sys.modules['alterego_track_editor']=package
from alterego_track_editor.native.storage import Catalog
from alterego_track_editor.native.formats.pvs import Visibility,read_objects,write_objects

base,output=map(Path,sys.argv[1:3]);only=set(sys.argv[3].split(',')) if len(sys.argv)>3 else None;quick=len(sys.argv)>4;results=[];random.seed(7)
for folder in sorted(p for p in base.iterdir() if (p/'wep').is_dir() and (only is None or p.name in only)):
    catalog=Catalog()
    for archive in sorted((folder/'wep').glob('*.erp')):catalog.mount(archive)
    for uri,(_,resource) in sorted(catalog.by_uri.items()):
        if resource.type_name!='PVSVisRes':continue
        start=time.perf_counter();vis=Visibility(catalog.read(uri))
        header=uri.replace('.volumedata.pvsbin','.header.pvsbin');objects=read_objects(catalog.read(header))
        assert write_objects(objects)==catalog.read(header)
        cells=[vis.sets(k) for k in range(len(vis.cells))]  # strict: every stream decodes to the exact length
        # Bit semantics: is object i's bit set more often in cells near its bounding sphere than in random cells?
        near_hits=near_total=far_hits=far_total=0
        positions=[c['xyz'] for c in vis.cells]
        for oid in random.sample(range(1,vis.objects),0 if quick else min(300,vis.objects-1)):
            x,y,z,r=vis.sphere(oid);bit=oid
            if not all(map(math.isfinite,(x,y,z,r))):continue
            for k,(cx,cz,_) in enumerate(positions):
                d=math.hypot(cx-x,cz-z);visible=any(s[bit>>3]>>(bit&7)&1 for s in cells[k])
                if d<=max(r,10)+20:near_hits+=visible;near_total+=1
                elif d>1500:far_hits+=visible;far_total+=1
        from alterego_track_editor.native.formats.pvs import bit_count
        source=next(oid for oid in range(1,len(objects)+1) if any(s[oid>>3]>>(oid&7)&1 for c in cells for s in c))
        grown=vis.with_objects(len(objects),[source]);check=Visibility(grown);new=len(objects)+1
        def masked(b):
            b=bytearray(b);b[new>>3]&=~(1<<(new&7))&255;return bytes(b)  # the new id lies in the stock spare bits
        same=all(masked(check.sets(k)[j][:vis.set_bytes])==cells[k][j] for k in range(len(cells)) for j in range(5))
        copied=all((check.sets(k)[j][new>>3]>>(new&7)&1)==(cells[k][j][source>>3]>>(source&7)&1) for k in range(len(cells)) for j in range(5))
        results.append({'track':folder.name,'resource':uri.rsplit('/',1)[-1],'objects':vis.objects,'bits':vis.bits,'object_list':len(objects),
            'cells':len(vis.cells),'reference_cells':sum(1 for c in vis.cells if c['ref']),'bytes':len(vis.data),
            'near_visible':round(near_hits/max(near_total,1),3),'near_samples':near_total,'far_visible':round(far_hits/max(far_total,1),3),
            'far_samples':far_total,'bit_rule':vis.bits==bit_count(len(objects)),'append_readback':True,'old_bits_unchanged':same,'source_bits_copied':copied,'grown_bytes':len(grown),'seconds':round(time.perf_counter()-start,1)})
        print(json.dumps(results[-1]),flush=True)
output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(results,indent=2))
