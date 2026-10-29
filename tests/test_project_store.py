import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

path=Path(__file__).resolve().parents[1]/'addon/alterego_track_editor/project_store.py'
spec=importlib.util.spec_from_file_location('project_store',path)
store=importlib.util.module_from_spec(spec);spec.loader.exec_module(store)

class ProjectTests(unittest.TestCase):
    def test_source_change_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'source';p.write_bytes(b'first')
            record=store.fingerprint(p)
            self.assertEqual(store.check_sources([record]),[])
            p.write_bytes(b'other')
            self.assertEqual(store.check_sources([record])[0]['status'],'CHANGED')
            p.unlink()
            self.assertEqual(store.check_sources([record])[0]['status'],'MISSING_OR_UNREADABLE')

    def test_manifest_updates_only_same_owner(self):
        with tempfile.TemporaryDirectory() as d:
            p=store.create_manifest(d,'id','example',[])
            store.create_manifest(d,'id','renamed',[])
            before=p.read_bytes()
            self.assertEqual(json.loads(before)['track_code'],'renamed')
            with self.assertRaises(ValueError):store.create_manifest(d,'other','different',[])
            self.assertEqual(p.read_bytes(),before)
            self.assertEqual(list(Path(d).glob('.project-*')),[])

    def test_invalid_codes_and_game_folder(self):
        for code in ('../track','', 'with space','UPPER','_track'):
            with self.assertRaises(ValueError):store.validate_code(code)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'F1_25.exe').touch()
            with self.assertRaises(ValueError):store.create_manifest(root/'nested','id','example',[])
            self.assertFalse((root/'nested').exists())

if __name__=='__main__':unittest.main()
