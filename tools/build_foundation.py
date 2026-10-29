"""Build the source-only internal Blender foundation ZIP; excludes tests and local assets."""
from pathlib import Path
import hashlib
import json
import zipfile

root=Path(__file__).resolve().parents[1]
addon=root/'addon/alterego_track_editor'
destination=root/'dist/AlterEgo-Track-Editor-0.2.2-preview.zip'
destination.parent.mkdir(exist_ok=True)
files=sorted(p for p in addon.rglob('*') if p.is_file() and not any(x in ('tests','__pycache__') for x in p.relative_to(addon).parts) and p.suffix in ('.py','.md','.txt'))
with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p,'alterego_track_editor/'+p.relative_to(addon).as_posix())
with zipfile.ZipFile(destination) as z:
    assert z.testzip() is None
    assert all(Path(n).suffix in ('.py','.md','.txt') for n in z.namelist())
print(json.dumps({'path':str(destination),'files':len(files),'bytes':destination.stat().st_size,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}))
