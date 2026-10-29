import importlib
from pathlib import Path
import sys
import tempfile
import types
import json
import zipfile
import unittest
from native_fixtures import make_track

root=Path(__file__).resolve().parents[1]/'addon/alterego_track_editor'
package=types.ModuleType('native_test_editor');package.__path__=[str(root)];sys.modules[package.__name__]=package
native=importlib.import_module(package.__name__+'.native_project')
variants=importlib.import_module(package.__name__+'.variants')


class NativeProjectTests(unittest.TestCase):
    def test_noop_and_updated_layer_preserve_opaque(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'track';path=make_track(folder);original=path.read_bytes()
            doc=native.TrackDocument(folder)
            self.assertEqual(len(doc.records),1)
            self.assertTrue(doc.records[0]['editable'])
            doc.write_updated(Path(d)/'noop',{})
            self.assertEqual((Path(d)/'noop/wep/track_common.erp').read_bytes(),original)
            r=doc.records[0];pose=r['world'][:];pose[13]=30
            replacements=doc.apply({r['id']:pose})
            doc.write_updated(Path(d)/'updated',replacements)
            changed=native.TrackDocument(Path(d)/'updated')
            self.assertEqual(changed.records[0]['world'][13],30)
            self.assertEqual(changed.catalog.read('eaid://fixture/opaque'),b'untouched')
            self.assertEqual(path.read_bytes(),original)

    def test_patch_targets_and_mirrored_archives(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder=root/'track';source=make_track(folder)
            mirror=folder/'wep/mirror.erp';mirror.write_bytes(source.read_bytes())
            doc=native.TrackDocument(folder);r=doc.records[0];pose=r['world'][:];pose[12]=20
            replacements=doc.apply({r['id']:pose})
            patch=root/'update.swoftyaddon';self.assertEqual(doc.write_patch(patch,replacements),2)
            with zipfile.ZipFile(patch) as z:
                ops=json.loads(z.read('operations/erp.json'))['ops']
                self.assertEqual({o['erp'] for o in ops},{'2025_asset_groups/environment_package/tracks/track/wep/track_common.erp','2025_asset_groups/environment_package/tracks/track/wep/mirror.erp'})
            with self.assertRaises(ValueError):doc.write_patch(patch,replacements)

    def test_conflicting_mirror_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'track';source=make_track(folder)
            original=native.TrackDocument(folder);r=original.records[0];pose=r['world'][:];pose[12]=99
            replacements=original.apply({r['id']:pose})
            original.write_updated(Path(d)/'changed',replacements)
            (folder/'wep/conflict.erp').write_bytes((Path(d)/'changed/wep/track_common.erp').read_bytes())
            doc=native.TrackDocument(folder);r=doc.records[0];pose=r['world'][:];pose[13]=2
            with self.assertRaisesRegex(ValueError,'Conflicting copies'):
                doc.write_patch(Path(d)/'invalid.zip',doc.apply({r['id']:pose}))
            self.assertFalse((Path(d)/'invalid.zip').exists())

    def test_raw_package_and_addon_preserve_unrelated_payloads(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder=root/'track';erp=make_track(folder)
            manifest={'track_code':'track','erp':'track.erp','activation':{'copy_from_track':'melbourne'}}
            for addon in (False,True):
                source=root/('addon.swoftyaddon' if addon else 'package.zip')
                prefix='track/' if addon else ''
                with zipfile.ZipFile(source,'w') as z:
                    z.writestr(prefix+'manifest.json',json.dumps(manifest))
                    z.writestr(prefix+'track.erp',erp.read_bytes())
                    z.writestr('credits.txt','preserve me')
                    if addon:
                        z.writestr('swofty.json',json.dumps({'name':'Fixture','operations':{'assets':['assets.json'],'native':['never.dll']}}))
                        z.writestr('assets.json',json.dumps({'ops':[{'op':'track.add','source':'track'}]}))
                        z.writestr('never.dll',b'NOT EXECUTABLE')
                original=source.read_bytes()
                doc=native.TrackDocument(source)
                self.assertEqual(len(doc.records),1)
                r=doc.records[0];matrix=r['world'][:];matrix[14]=9
                result=root/('updated-addon.zip' if addon else 'updated-package.zip')
                doc.write_updated(result,doc.apply({r['id']:matrix}));doc.close()
                with zipfile.ZipFile(result) as z:
                    self.assertEqual(z.read('credits.txt'),b'preserve me')
                    if addon:self.assertEqual(z.read('never.dll'),b'NOT EXECUTABLE')
                reopened=native.TrackDocument(result)
                self.assertEqual(reopened.records[0]['world'][14],9)
                reopened.close()
                self.assertEqual(source.read_bytes(),original)

    def test_source_tree_and_existing_output_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'track';make_track(folder);doc=native.TrackDocument(folder)
            for output in (folder,folder/'export',Path(d)):
                with self.assertRaises(ValueError):doc.write_updated(output,{})

    def test_variant_keys_do_not_alias_story_to_f1(self):
        self.assertEqual(variants.role('classic')[0],'CLASSIC')
        self.assertNotEqual(variants.role('f1_story'),variants.role('f1'))
        self.assertIn('classic',variants.inventory(['f1'])['missing'])

if __name__=='__main__':unittest.main()
