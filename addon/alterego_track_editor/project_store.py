"""Portable project manifest and explicit source identity checks (no Blender API)."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
import re

SCHEMA = 'AlterEgo.TrackProject.v1'


def validate_code(code):
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', code):
        raise ValueError('Track code must start with a letter and use lowercase letters, numbers or underscores')
    return code


def fingerprint(path):
    path = Path(path).resolve(strict=True)
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Source changed while recording it')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest.hexdigest()}


def check_sources(records):
    findings = []
    for record in records:
        try:
            actual = fingerprint(record['path'])
            if (actual['sha256'], actual['bytes']) != (record['sha256'], record['bytes']):
                findings.append({'path': record['path'], 'status': 'CHANGED'})
        except (OSError, ValueError):
            findings.append({'path': record['path'], 'status': 'MISSING_OR_UNREADABLE'})
    return findings


def create_manifest(directory, identity, code, sources):
    validate_code(code)
    destination = Path(directory).expanduser().resolve()
    # Prevent companion writes to any recognized game installation ancestor.
    if any((p / 'F1_25.exe').is_file() for p in (destination, *destination.parents)):
        raise ValueError('Choose a project folder outside the game installation')
    destination.mkdir(parents=True, exist_ok=True)
    file = destination / 'project.json'
    value = {'schema': SCHEMA, 'project_id': identity, 'track_code': code, 'sources': sources}
    if file.exists():
        existing = json.loads(file.read_text(encoding='utf-8'))
        if existing.get('project_id') != identity or existing.get('schema') != SCHEMA:
            raise ValueError('Companion folder belongs to another project')
        if existing == value:
            return file
        handle, temporary = tempfile.mkstemp(prefix='.project-', suffix='.json', dir=destination)
        try:
            with os.fdopen(handle, 'w', encoding='utf-8') as stream:
                json.dump(value, stream, indent=2)
            os.replace(temporary, file)
        finally:
            if Path(temporary).exists():
                Path(temporary).unlink()
    else:
        with file.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)
    return file
