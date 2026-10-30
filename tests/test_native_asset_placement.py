from pathlib import Path
import json,tempfile,unittest,zipfile
from test_asset_dependencies import fixture
from test_static_family import inputs
from native_fixtures import make_track,erp,pkg,canonical_pkg,IDENTITY
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.static_asset import build_asset
from alterego_track_editor.native.geometry import mesh
from alterego_track_editor.native.storage import Catalog
from alterego_track_editor.native.formats.pkg_tree import Tree,patch_edits


def moved(x):
    m=IDENTITY[:];m[12]=x;return m


def canonical_source(root):
    """Stock-layout layer placing the authored-family fixture as an ordinary static prop."""
    catalog,family,binding,mip=fixture(root);folder=catalog.archives[0].path.parent
    archive=make_track(folder);prefix='eaid://environment_package/tracks/input/wep/';layer=prefix+'objects.layer'
    board={'name':'objects$board_a','template':'RenderModel','uniqueid':('woid',bytes([1])*16),
        'overrides':{'Model':{'model':family+'?context=render','mat binding':binding},
            'Render':{'cast shadows':('bool',0)},'WorldObject':{'transform':('mat4',IDENTITY)}}}
    archive.write_bytes(erp([(prefix+'input_common.wep','World',[pkg({'layers':[layer]})]),
        (layer,'WOInstances',[canonical_pkg({'instances':[board],'layer':'objects'})]),
        ('eaid://fixture/opaque','Opaque',[b'PRESERVE EXACTLY'])]))
    return folder,family,binding


def asset(doc,family,binding,name='new_board',source=None):
    target='eaid://environment_package/tracks/input/objects/'+name+'.idf'
    resources,report=build_asset(doc.catalog,family,target,source or inputs(),binding)
    return {'name':name,'family':report['family'],'binding':report['binding'],'resources':resources}


class NativeAssetPlacementTests(unittest.TestCase):
    def test_full_export_embeds_family_and_places_new_instance(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder,family,binding=canonical_source(root);doc=TrackDocument(folder)
            board=doc.records[0];self.assertIsNone(board['clone_reason'])
            placed=asset(doc,family,binding)
            replacements=doc.apply({},[{'id':'a1'*16,'source':board['id'],'world':moved(30),'asset':placed},
                                       {'id':'b2'*16,'source':board['id'],'world':moved(40)}])
            result=doc.write_updated(root/'out'/'input',replacements)
            self.assertEqual([i['asset'] for i in result['inserted_placements']],[placed['family'],None])
            check=TrackDocument(root/'out'/'input');names={r['name']:r for r in check.records}
            new=names['objects$new_board_ate_'+'a1'*6];copy=names['objects$board_a_ate_'+'b2'*6]
            self.assertEqual(new['model'],placed['family']+'?context=render');self.assertEqual(new['binding'],placed['binding'])
            self.assertIsNone(new['render_error']);self.assertEqual(new['world'][12],30.)
            self.assertEqual(copy['model'],board['model']);self.assertEqual(names['objects$board_a']['model'],board['model'])
            self.assertEqual(mesh(check.catalog,placed['family']+'?lod=1&mesh').triangles,4)
            self.assertEqual(check.catalog.read('eaid://fixture/opaque'),b'PRESERVE EXACTLY')
            # Families are embedded only in the archive holding the edited layer.
            common=check.catalog.get(new['layer'])[0].path
            self.assertEqual(check.catalog.get(placed['family']+'?model')[0].path,common)
            self.assertFalse(any(r.name.startswith(placed['family']) for a in check.catalog.archives if a.path!=common for r in a.resources))
            check.close();doc.close()

    def test_update_addon_ships_asset_archive_and_composable_edits(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder,family,binding=canonical_source(root);doc=TrackDocument(folder);board=doc.records[0]
            placed=asset(doc,family,binding)
            replacements=doc.apply({},[{'id':'c3'*16,'source':board['id'],'world':moved(5),'asset':placed}])
            uri=board['layer'];edits=doc.layer_edits[uri]
            self.assertEqual(edits[0]['set']['overrides.Model.model'],placed['family']+'?context=render')
            self.assertEqual(edits[0]['set']['overrides.Model.mat binding'],placed['binding'])
            self.assertEqual(patch_edits(Tree(doc.layers[uri]['doc'].data),edits).to_bytes(),replacements[uri])
            for fmt in ('patch-pkg','replace'):
                target=root/f'{fmt}.swoftyaddon';doc.write_patch(target,replacements,fmt)
                with zipfile.ZipFile(target) as z:
                    ops=json.loads(z.read('operations/erp.json'))['ops'];provenance=json.loads(z.read('provenance.json'))
                    (root/f'{fmt}.erp').write_bytes(z.read('assets/new-assets.erp'))
                copies=[o for o in ops if o['op']=='copy-resource']
                self.assertEqual(sorted(o['resource'] for o in copies),sorted(n for n,_,_ in placed['resources']))
                self.assertTrue(all(o['source']=='assets/new-assets.erp' and o['erp'].endswith('wep/input_common.erp') for o in copies))
                self.assertEqual(ops[-1]['op'],'patch-pkg' if fmt=='patch-pkg' else 'replace-resource')
                self.assertEqual(provenance['new_asset_resources'],sorted(n for n,_,_ in placed['resources']))
                shipped=Catalog();shipped.mount(root/f'{fmt}.erp')
                for name,_,fragments in placed['resources']:
                    for i,raw in enumerate(fragments):self.assertEqual(shipped.read(name,i),raw)
            doc.close()

    def test_asset_conflicts_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder,family,binding=canonical_source(root);doc=TrackDocument(folder);board=doc.records[0]
            first=asset(doc,family,binding);changed=inputs();changed[0][0].positions=[(x+1,y,z) for x,y,z in changed[0][0].positions]
            second=asset(doc,family,binding,source=changed)
            with self.assertRaisesRegex(ValueError,'disagree'):
                doc.apply({},[{'id':'d4'*16,'source':board['id'],'world':moved(1),'asset':first},
                              {'id':'e5'*16,'source':board['id'],'world':moved(2),'asset':second}])
            existing=dict(first,resources=first['resources']+[(family+'?model',first['resources'][0][1],[b'x'])])
            with self.assertRaisesRegex(ValueError,'already exists'):
                doc.apply({},[{'id':'f6'*16,'source':board['id'],'world':moved(1),'asset':existing}])
            incomplete=dict(first,resources=[r for r in first['resources'] if not r[0].endswith('?render')])
            with self.assertRaisesRegex(ValueError,'Incomplete'):
                doc.apply({},[{'id':'a7'*16,'source':board['id'],'world':moved(1),'asset':incomplete}])
            doc.close()


if __name__=='__main__':unittest.main()


class NativeAssetReplacementTests(unittest.TestCase):
    def test_existing_prop_uses_edited_asset_in_both_formats(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder,family,binding=canonical_source(root);doc=TrackDocument(folder);board=doc.records[0]
            placed=asset(doc,family,binding)
            replacements=doc.apply({board['id']:moved(3)},retargets={board['id']:placed})
            uri=board['layer'];edits=doc.layer_edits[uri]
            self.assertEqual([e['op'] for e in edits],['set-value']*3)
            self.assertEqual(patch_edits(Tree(doc.layers[uri]['doc'].data),edits).to_bytes(),replacements[uri])
            doc.write_patch(root/'update.zip',replacements,'patch-pkg')
            with zipfile.ZipFile(root/'update.zip') as z:ops=json.loads(z.read('operations/erp.json'))['ops']
            self.assertEqual(sum(o['op']=='copy-resource' for o in ops),len(placed['resources']))
            doc.write_updated(root/'out'/'input',replacements)
            check=TrackDocument(root/'out'/'input');r=check.records[0]
            self.assertEqual((r['name'],r['model'],r['binding'],r['world'][12]),(board['name'],placed['family']+'?context=render',placed['binding'],3.))
            self.assertEqual(mesh(check.catalog,placed['family']+'?lod=1&mesh').triangles,4)
            check.close();doc.close()
