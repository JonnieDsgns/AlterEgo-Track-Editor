"""Audit a user-supplied Track Workshop release without loading Blender/native code.

Writes private inventory and a Python/test-only snapshot under build/.
No upstream tree is modified and no packaged executable is extracted or run.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def audit(archive, source, output):
    output.mkdir(parents=True, exist_ok=True)
    files, tests = [], []
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            name = PurePosixPath(item.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in item.filename:
                raise ValueError('Unsafe release member')
            if item.is_dir():
                continue
            raw = z.read(item)
            relative = Path(*name.parts[1:])
            row = {'path': str(relative).replace('\\', '/'), 'bytes': len(raw),
                   'sha256': hashlib.sha256(raw).hexdigest()}
            candidate = source / relative
            row['source_match'] = candidate.is_file() and hashlib.sha256(candidate.read_bytes()).hexdigest() == row['sha256']
            if name.suffix == '.py':
                tree = ast.parse(raw.decode('utf-8-sig'))
                row['imports'] = sorted(set(n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)) |
                                        {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names})
                row['symbols'] = [n.name for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
                row['test_methods'] = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
                if row['test_methods']:
                    tests.append({'path': row['path'], 'methods': row['test_methods']})
            # Restrict extraction to authored Python, test and JSON text files.
            if name.suffix in ('.py', '.json') and 'backend' not in name.parts and 'runtime' not in name.parts:
                target = output / 'baseline-python' / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and target.read_bytes() != raw:
                    raise ValueError('Existing snapshot differs: ' + str(relative))
                target.write_bytes(raw)
            files.append(row)
    result = {'release_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'files': files, 'tests': tests, 'test_methods': sum(len(t['methods']) for t in tests),
              'scope': 'Static inventory; binary members hashed only, never executed or extracted.'}
    (output / 'baseline-inventory.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('Release files:', len(files), 'test methods:', result['test_methods'])
    print('Source differences:', ', '.join(x['path'] for x in files if not x['source_match'] and x['path'].endswith('.py')))
    print('Test files:', ', '.join(t['path'] for t in tests))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1]/'build'/'audit')
    a = p.parse_args()
    audit(a.archive, a.source, a.output)
