"""Metadata-first archive catalogue and byte-budgeted, single-flight fragment cache."""
from collections import OrderedDict
from pathlib import Path
import threading
from .formats.erp import Erp


class IndexedArchive(Erp):
    def __init__(self,path):
        super().__init__(path)
        self._resource_ids = {id(r) for r in self.resources}
        self._names = {}
        for resource in self.resources:
            if resource.name in self._names:
                raise ValueError('Duplicate URI inside archive: '+resource.name)
            self._names[resource.name] = resource

    def _resource(self, resource):
        if isinstance(resource,str):
            try:
                return self._names[resource]
            except KeyError:
                raise ValueError('Missing resource: '+resource) from None
        if id(resource) not in self._resource_ids:
            raise ValueError('Resource belongs to another archive')
        return resource


class Catalog:
    def __init__(self, budget=64*1024*1024):
        self.archives = []
        self.by_uri = {}
        self.cache = OrderedDict()
        self.used = 0
        self.budget = budget
        self.lock = threading.RLock()
        self.reads = self.hits = 0
        self.warnings = []
        self.fragments = {}
        self.asset_roots = []

    def mount(self, path):
        path = Path(path).resolve()
        if any(a.path == path for a in self.archives):
            return
        archive = IndexedArchive(path)
        # First mounted wins: selected variant, WEP common, track common.
        for resource in archive.resources:
            self.by_uri.setdefault(resource.name, (archive, resource))
        self.archives.append(archive)

    def get(self, uri):
        try:
            return self.by_uri[uri]
        except KeyError:
            raise ValueError('Missing resource: ' + uri) from None

    def read(self, uri, fragment=0):
        # Serial decompression avoids duplicate loads, unbounded in-flight allocations
        # and sharing a codec between threads. Metadata has no decompressed payloads.
        with self.lock:
            if (uri,fragment) in self.fragments:
                file,identity=self.fragments[uri,fragment]
                stat=file.stat()
                if (stat.st_size,stat.st_mtime_ns)!=identity:raise ValueError('Addon fragment changed; reopen')
                if stat.st_size>64*1024*1024:raise ValueError('Addon fragment exceeds decode budget')
                return file.read_bytes()
            archive, resource = self.get(uri)
            archive._unchanged_source()
            if fragment < 0 or fragment >= len(resource.fragments):
                raise ValueError('Invalid fragment index')
            info = resource.fragments[fragment]
            if max(info.size,info.packed)>64*1024*1024:
                raise ValueError('Fragment exceeds 64 MiB decode budget')
            key = (str(archive.path), uri, fragment)
            if key in self.cache:
                self.hits += 1
                self.cache.move_to_end(key)
                return self.cache[key]
            data = archive.fragment_data(resource, fragment)
            self.reads += 1
            while self.cache and self.used + len(data) > self.budget:
                _, old = self.cache.popitem(last=False)
                self.used -= len(old)
            if len(data) <= self.budget:
                self.cache[key] = data
                self.used += len(data)
            return data

    def stats(self):
        return dict(archives=len(self.archives), resources=len(self.by_uri),
                    cachedBytes=self.used, cacheBudget=self.budget, reads=self.reads, hits=self.hits)


def safe_output(path, sources=()):
    path = Path(path).expanduser().resolve()
    if path in {Path(p).resolve() for p in sources}:
        raise ValueError('Choose a new export file')
    for parent in (path.parent, *path.parents):
        if (parent / 'F1_25.exe').exists():
            raise ValueError('Choose an export folder outside the game installation')
    if path.exists():
        raise ValueError('Export already exists; choose a new filename')
    if path.suffix.lower() != '.glb':
        raise ValueError('Export filename must end in .glb')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
