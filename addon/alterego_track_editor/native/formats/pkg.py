"""Lossless, copy-on-write !pkg scalar editor; no guessed engine layouts.

Layout derived from SwoftyLauncher/tools/pkg.py at 97d4488. Existing chunks
and unknown bytes are retained. Edited values get private pool entries, so
interned values shared by other objects are never changed accidentally.
"""
import math
import struct
from dataclasses import dataclass


class FormatError(ValueError):
    pass


FORMATS = {'bool': '?', 'ui08': 'B', 'ui16': 'H', 'ui32': 'I',
           'si32': 'i', 'ui64': 'Q', 'si64': 'q', 'fp32': 'f',
           'vec3': '4f', 'vec4': '4f', 'quat': '4f', 'mat4': '16f',
           'bbox': '8f'}
ALIGN = {'ui64': 8, 'si64': 8, 'vec3': 16, 'vec4': 16, 'quat': 16,
         'woid': 16, 'shnm': 16, 'mat4': 16, 'bbox': 32}


@dataclass
class Scalar:
    type: str
    value: object
    slot: int
    pool: int
    index: int
    raw: bytes


class Document:
    def __init__(self, data):
        self.data = bytes(data)
        self.pools = []
        self.leaves = {}
        self.edits = {}
        if self.data[:4] != b'!pkg':
            raise FormatError('Expected a !pkg layer; this resource is not editable')
        self.root_offset, self.vca_offset = (x & 0xffffff for x in self.unpack('II', 8))
        if self.take(self.vca_offset, 4) != b'!vca':
            raise FormatError('Missing value pool table')
        count = self.unpack('I', self.vca_offset + 4)[0]
        if count > len(data) // 4:
            raise FormatError('Invalid value pool count')
        for i in range(count):
            off = self.unpack('I', self.vca_offset + 8 + i * 4)[0] & 0xffffff
            tag = self.take(off, 4)
            if tag == b'!sbi':
                size = self.unpack('I', off + 4)[0]
                self.pools.append(('stri', 0, self.take(off + 8, size)))
            elif tag == b'!vbi':
                typ = self.take(off + 4, 4).decode('ascii')
                cnt, stride = self.unpack('II', off + 8)
                if not stride or cnt * stride > len(data):
                    raise FormatError('Invalid pool size')
                self.pools.append((typ, stride, self.take(off + 16, cnt * stride)))
            else:
                raise FormatError('Unsupported pool tag')
        self.root = self.node(self.root_offset, (), set())

    def take(self, off, size):
        if off < 0 or size < 0 or off + size > len(self.data):
            raise FormatError('Out-of-bounds !pkg data')
        return self.data[off:off + size]

    def unpack(self, fmt, off):
        return struct.unpack('<' + fmt, self.take(off, struct.calcsize('<' + fmt)))

    def scalar(self, ref, slot):
        p, idx = ref >> 24, ref & 0xffffff
        if p >= len(self.pools):
            raise FormatError('Unknown pool reference')
        typ, stride, data = self.pools[p]
        if typ == 'stri':
            if idx >= len(data):
                raise FormatError('Invalid string reference')
            size = data[idx]
            raw = data[idx:idx + size + 2]
            if len(raw) != size + 2 or raw[-1] != 0:
                raise FormatError('Invalid string length')
            value = raw[1:-1].decode('utf-8', 'strict')
        else:
            raw = data[idx * stride:(idx + 1) * stride]
            if len(raw) != stride:
                raise FormatError('Invalid scalar reference')
            fmt = FORMATS.get(typ)
            if typ == 'shnm':
                value = raw.rstrip(b'\0').decode('utf-8', 'strict')
            elif fmt and struct.calcsize('<' + fmt) == stride:
                values = struct.unpack('<' + fmt, raw)
                value = values[0] if len(values) == 1 else list(values)
            else:
                value = raw.hex()
        return Scalar(typ, value, slot, p, idx, raw)

    def reference(self, slot, path, stack):
        ref = self.unpack('I', slot)[0]
        if ref >> 24 == 0x80:
            return self.node(ref & 0xffffff, path, stack)
        val = self.scalar(ref, slot)
        self.leaves[path] = val
        return val

    def node(self, off, path, stack):
        if off in stack or len(stack) > 100:
            raise FormatError('Cyclic or too deeply nested !pkg')
        stack = stack | {off}
        tag = self.take(off, 4)
        if tag == b'!idi':
            header = self.unpack('I', off + 4)[0]
            count, version = header & 0xffffff, header >> 24
            if version not in (0, 1):
                raise FormatError('Unsupported dictionary version')
            stride = 12 if version == 1 else 8
            self.take(off + 8, count * stride)
            result = {}
            for i in range(count):
                slot = off + 8 + i * stride
                key = self.scalar(self.unpack('I', slot)[0], slot).value
                if not isinstance(key, str) or key in result:
                    raise FormatError('Duplicate or non-string dictionary key')
                result[key] = self.reference(slot + 4, path + (key,), stack)
            return result
        if tag in (b'!ili', b'!vca'):
            count = self.unpack('I', off + 4)[0]
            self.take(off + 8, count * 4)
            return [self.reference(off + 8 + i * 4, path + (i,), stack) for i in range(count)]
        if tag == b'!iar':
            return {'opaque_iar': self.take(off + 4, 8).hex()}
        raise FormatError('Unknown !pkg chunk %r' % tag)

    def set(self, path, value):
        path = tuple(path)
        leaf = self.leaves[path]
        self.encode(leaf, value)  # validate before mutating
        if value == leaf.value:
            self.edits.pop(path, None)
        else:
            self.edits[path] = value

    @staticmethod
    def encode(leaf, value):
        if leaf.type == 'shnm':
            raw = value.encode('utf-8')
            if len(raw) > len(leaf.raw) or b'\0' in raw:
                raise FormatError('Short name exceeds %d bytes or contains NUL' % len(leaf.raw))
            return raw.ljust(len(leaf.raw), b'\0')
        if leaf.type == 'stri':
            raw = value.encode('utf-8')
            if len(raw) > 255 or b'\0' in raw:
                raise FormatError('String must fit 255 UTF-8 bytes without NUL')
            return bytes([len(raw)]) + raw + b'\0'
        if leaf.type not in FORMATS:
            raise FormatError('Opaque field is preserved and cannot be edited')
        values = value if isinstance(value, (list, tuple)) else [value]
        if any(isinstance(x, float) and not math.isfinite(x) for x in values):
            raise FormatError('Non-finite values are not supported')
        raw = struct.pack('<' + FORMATS[leaf.type], *values)
        if len(raw) != len(leaf.raw):
            raise FormatError('Unsupported scalar stride')
        return raw

    def to_bytes(self):
        if not self.edits:
            return self.data
        out = bytearray(self.data)
        changed = {}
        for path, value in self.edits.items():
            leaf = self.leaves[path]
            pool = changed.setdefault(leaf.pool, bytearray(self.pools[leaf.pool][2]))
            stride = self.pools[leaf.pool][1]
            idx = len(pool) // stride if stride else len(pool)
            if idx > 0xffffff:
                raise FormatError('Pool reference exceeds 24-bit limit')
            pool += self.encode(leaf, value)
            ref = (leaf.pool << 24) | idx
            current = struct.unpack_from('<I', out, leaf.slot)[0]
            original = struct.unpack_from('<I', self.data, leaf.slot)[0]
            if current != original and current != ref:
                raise FormatError('Aliased dictionary has conflicting edits')
            struct.pack_into('<I', out, leaf.slot, ref)
        for i, pool in changed.items():
            typ, stride, _ = self.pools[i]
            alignment = ALIGN.get(typ, 4)
            out.extend(b'\0' * (-len(out) % alignment))
            off = len(out)
            if off > 0xffffff:
                raise FormatError('Package exceeds 24-bit address limit')
            if typ == 'stri':
                out += b'!sbi' + struct.pack('<I', len(pool)) + pool
            else:
                out += b'!vbi' + typ.encode('ascii') + struct.pack('<II', len(pool) // stride, stride) + pool
            struct.pack_into('<I', out, self.vca_offset + 8 + i * 4, 0x80000000 | off)
        out.extend(b'\0' * (-len(out) % 4))
        result = bytes(out)
        check = Document(result)
        for path, leaf in self.leaves.items():
            expected = self.encode(leaf, self.edits[path]) if path in self.edits else leaf.raw
            if check.leaves[path].raw != expected:
                raise FormatError('Round-trip validation failed at %r' % (path,))
        return result


def plain(node):
    if isinstance(node, Scalar):
        return node.value
    if isinstance(node, dict):
        return {k: plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [plain(v) for v in node]
    return node
