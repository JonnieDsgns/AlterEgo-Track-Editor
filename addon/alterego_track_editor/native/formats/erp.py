"""Bounded, lazy ERPK reader and copy-preserving workspace exporter.

Layout follows SwoftyLauncher's packages/formats/src/erp.rs. No game process
is accessed. Unknown compression methods are retained but never reinterpreted.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from dataclasses import dataclass, field

ZSTD = 0x11
STORED = 0x91
MAX_FRAGMENT_SIZE = 512 * 1024 * 1024


class ErpError(ValueError):
    pass


class ZstdCodec:
    """Uses Python 3.14's codec or an existing native libzstd installation."""
    def __init__(self, library=None):
        self.python = None
        if library is None:
            try:
                from compression import zstd
                self.python = zstd
                return
            except ImportError:
                pass
        candidates = [library or os.environ.get("F1_CAMERA_ZSTD_LIBRARY")]
        candidates += [ctypes.util.find_library("zstd")]
        folder = Path(sys.executable).parent
        candidates += [str(folder / name) for name in ("libzstd.dll", "zstd.dll")]
        if os.name == "nt":
            candidates += [str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) /
                               "Git/mingw64/bin/libzstd.dll")]
        self.native = None
        for candidate in filter(None, candidates):
            try:
                lib = ctypes.CDLL(candidate)
                lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
                lib.ZSTD_isError.restype = ctypes.c_uint
                lib.ZSTD_getErrorName.argtypes = [ctypes.c_size_t]
                lib.ZSTD_getErrorName.restype = ctypes.c_char_p
                lib.ZSTD_compressBound.argtypes = [ctypes.c_size_t]
                lib.ZSTD_compressBound.restype = ctypes.c_size_t
                lib.ZSTD_compress.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
                lib.ZSTD_compress.restype = ctypes.c_size_t
                lib.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                              ctypes.c_void_p, ctypes.c_size_t]
                lib.ZSTD_decompress.restype = ctypes.c_size_t
                self.native = lib
                return
            except (OSError, AttributeError):
                continue
        raise ErpError("Zstandard codec unavailable. Set F1_CAMERA_ZSTD_LIBRARY to an existing libzstd library.")

    def _check(self, result):
        if self.native.ZSTD_isError(result):
            raise ErpError("Zstandard: " + self.native.ZSTD_getErrorName(result).decode("utf-8", "replace"))
        return result

    def decompress(self, data, size):
        if not 0 <= size <= MAX_FRAGMENT_SIZE:
            raise ErpError("Fragment exceeds decompression size limit")
        if self.python:
            decoder = self.python.ZstdDecompressor()
            result = decoder.decompress(data, max_length=size + 1)
            if not decoder.eof or len(result) != size or decoder.unused_data:
                raise ErpError("Invalid Zstandard frame or decoded size mismatch")
            return result
        output = ctypes.create_string_buffer(max(size, 1))
        actual = self._check(self.native.ZSTD_decompress(output, size, data, len(data)))
        if actual != size:
            raise ErpError("Decoded fragment size mismatch")
        return output.raw[:actual]

    def compress(self, data):
        if self.python:
            return self.python.compress(data, level=19)
        capacity = self.native.ZSTD_compressBound(len(data))
        output = ctypes.create_string_buffer(capacity)
        actual = self._check(self.native.ZSTD_compress(output, capacity, data, len(data), 19))
        return output.raw[:actual]


@dataclass
class Fragment:
    name: bytes
    offset: int
    size: int
    flags: int
    compression: int
    packed: int
    replacement: bytes | None = field(default=None, repr=False)


@dataclass
class Resource:
    name: str
    kind: bytes
    unknown: bytes
    fragments: list[Fragment]
    hash: bytes

    @property
    def type_name(self):
        return self.kind.rstrip(b"\0").decode("ascii", "replace")

    @property
    def frags(self):
        return self.fragments


def _safe_output(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output:
        raise ErpError("Export must use a separate output file")
    # A game root is identified by its executable, including ancestors of the
    # destination. This protects renamed/moved installs without a hardcoded path.
    for folder in (output.parent, *output.parent.parents):
        if (folder / "F1_25.exe").exists():
            raise ErpError("Export into the F1 installation is prohibited; choose a workspace folder")
    return output


class Erp:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self._identity = self.path.stat()
        self._codec = None
        self.resources = []
        with self.path.open("rb") as stream:
            self.header = stream.read(0x30)
            if len(self.header) != 0x30 or self.header[:4] != b"ERPK":
                raise ErpError("Not an ERPK archive")
            self.version = struct.unpack_from("<I", self.header, 4)[0]
            if self.version not in (2, 3, 4):
                raise ErpError(f"Unsupported ERP version {self.version}")
            info_offset, info_size, self.data_offset = struct.unpack_from("<QQQ", self.header, 0x10)
            if info_offset != 0x30 or self.data_offset != info_offset + info_size:
                raise ErpError("Unsupported ERP index layout")
            if info_size < 8 or self.data_offset > self._identity.st_size or info_size > 64 * 1024 * 1024:
                raise ErpError("Invalid ERP index bounds")
            index = stream.read(info_size)
        cursor = 0

        def take(count):
            nonlocal cursor
            if count < 0 or cursor + count > len(index):
                raise ErpError("Truncated ERP index")
            result = index[cursor:cursor + count]
            cursor += count
            return result

        count, declared_fragments = struct.unpack("<II", take(8))
        if count > info_size // 40:
            raise ErpError("Invalid ERP resource count")
        total_fragments = 0
        for _ in range(count):
            length = struct.unpack("<I", take(4))[0]
            end = cursor + length
            name_length = struct.unpack("<H", take(2))[0]
            name_bytes = take(name_length)
            if not name_bytes or name_bytes[-1:] != b"\0" or b"\0" in name_bytes[:-1]:
                raise ErpError("Invalid ERP resource name")
            try:
                name = name_bytes[:-1].decode("utf-8")
            except UnicodeDecodeError as error:
                raise ErpError("Invalid UTF-8 resource name") from error
            kind = take(16)
            unknown = take(6 if self.version >= 4 else 4)
            fragments = []
            for _ in range(take(1)[0]):
                fname = take(4)
                offset, size, flags = struct.unpack("<QQI", take(20))
                compression = take(1)[0]
                packed = struct.unpack("<Q", take(8))[0]
                if offset + packed > self._identity.st_size - self.data_offset:
                    raise ErpError("ERP fragment lies outside archive")
                fragments.append(Fragment(fname, offset, size, flags, compression, packed))
            resource_hash = take(16)
            if cursor != end:
                raise ErpError("ERP entry length mismatch")
            self.resources.append(Resource(name, kind, unknown, fragments, resource_hash))
            total_fragments += len(fragments)
        if cursor != len(index) or total_fragments != declared_fragments:
            raise ErpError("ERP index count or length mismatch")

    @property
    def res(self):
        return self.resources

    def _unchanged_source(self):
        stat = self.path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (self._identity.st_size, self._identity.st_mtime_ns):
            raise ErpError("Source archive changed; reopen it before exporting")

    def find(self, name):
        matches = [r for r in self.resources if r.name == name]
        if len(matches) != 1:
            raise ErpError(f"Resource {name!r} has {len(matches)} matches")
        return matches[0]

    def _resource(self, resource):
        if isinstance(resource, str):
            return self.find(resource)
        if not any(r is resource for r in self.resources):
            raise ErpError("Resource belongs to another archive")
        return resource

    def raw_fragment(self, resource, index):
        self._unchanged_source()
        fragment = self._fragment(resource, index)
        if fragment.packed > MAX_FRAGMENT_SIZE:
            raise ErpError("Packed fragment exceeds read size limit")
        with self.path.open("rb") as stream:
            stream.seek(self.data_offset + fragment.offset)
            data = stream.read(fragment.packed)
        if len(data) != fragment.packed:
            raise ErpError("Truncated ERP payload")
        return data

    def _zstd(self):
        if self._codec is None:
            self._codec = ZstdCodec()
        return self._codec

    def _fragment(self, resource, index):
        resource = self._resource(resource)
        if not isinstance(index, int) or not 0 <= index < len(resource.fragments):
            raise ErpError("Fragment index is outside resource")
        return resource.fragments[index]

    def fragment_data(self, resource, index):
        fragment = self._fragment(resource, index)
        if fragment.replacement is not None:
            return fragment.replacement
        if fragment.size > MAX_FRAGMENT_SIZE:
            raise ErpError("Fragment exceeds size limit")
        raw = self.raw_fragment(resource, index)
        if fragment.compression == ZSTD:
            return self._zstd().decompress(raw, fragment.size)
        if fragment.compression != STORED:
            raise ErpError(f"Unsupported compression code 0x{fragment.compression:02x}")
        if len(raw) != fragment.size:
            raise ErpError("Stored fragment size mismatch")
        return raw

    def replace_fragment(self, resource, index, data):
        fragment = self._fragment(resource, index)
        if fragment.compression not in (ZSTD, STORED):
            raise ErpError("Cannot edit unknown compression type")
        if len(data) > MAX_FRAGMENT_SIZE:
            raise ErpError("Replacement exceeds size limit")
        if bytes(data) != self.fragment_data(resource, index):
            fragment.replacement = bytes(data)

    def write(self, output):
        output = _safe_output(self.path, output)
        self._unchanged_source()
        if not output.parent.is_dir():
            raise ErpError("Output directory does not exist")
        changed = any(f.replacement is not None for r in self.resources for f in r.fragments)
        descriptor, temporary = tempfile.mkstemp(prefix=".f1-camera-", suffix=".tmp", dir=output.parent)
        try:
            with os.fdopen(descriptor, "wb") as target, self.path.open("rb") as source:
                if not changed:
                    shutil.copyfileobj(source, target, 1024 * 1024)
                else:
                    entries, payloads, offset = bytearray(), [], 0
                    for resource in self.resources:
                        entry = bytearray()
                        name = resource.name.encode("utf-8") + b"\0"
                        entry += struct.pack("<H", len(name)) + name + resource.kind + resource.unknown
                        entry += bytes([len(resource.fragments)])
                        edited = any(f.replacement is not None for f in resource.fragments)
                        digest = hashlib.md5() if edited else None
                        for index, fragment in enumerate(resource.fragments):
                            if edited:
                                digest.update(self.fragment_data(resource, index))
                            data = fragment.replacement
                            raw = self._zstd().compress(data) if data is not None and fragment.compression == ZSTD else data
                            size, packed = (len(data), len(raw)) if data is not None else (fragment.size, fragment.packed)
                            entry += fragment.name + struct.pack("<QQIBQ", offset, size, fragment.flags, fragment.compression, packed)
                            payloads.append((raw, fragment))
                            offset += packed
                        entry += digest.digest() if edited else resource.hash
                        entries += struct.pack("<I", len(entry)) + entry
                    info = struct.pack("<II", len(self.resources), len(payloads)) + entries
                    header = bytearray(self.header)
                    struct.pack_into("<QQQ", header, 0x10, 0x30, len(info), 0x30 + len(info))
                    target.write(header)
                    target.write(info)
                    for raw, fragment in payloads:
                        if raw is not None:
                            target.write(raw)
                        else:
                            source.seek(self.data_offset + fragment.offset)
                            remaining = fragment.packed
                            while remaining:
                                block = source.read(min(remaining, 1024 * 1024))
                                if not block:
                                    raise ErpError("Source archive truncated while exporting")
                                target.write(block)
                                remaining -= len(block)
                target.flush()
                os.fsync(target.fileno())
            self._unchanged_source()
            os.replace(temporary, output)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return output

    frag_data = fragment_data
    set_frag = replace_fragment
    to_file = write
