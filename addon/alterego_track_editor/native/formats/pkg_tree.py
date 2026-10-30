"""Canonical !pkg tree for structural world-layer edits.

Layout follows SwoftyLauncher tools/pkg.py at 97d4488 (AGPL-3.0-or-later):
breadth-first chunks, FNV-1a ordered version-1 dictionaries, retained pool
references and first-match interning of new values. Structural edits are only
allowed when the unchanged input re-serializes byte-identically; anything else
(shared chunks, trailing bytes, other chunk orders) is refused, never guessed.
patch_edits() replays the launcher's clone-entry/set-value addon edits
(packages/core/src/pkgedit.rs) so exported operations can be checked offline.
"""
import copy
import math
import struct
from .pkg import FormatError

ALIGN = {'stri': 4, 'bool': 4, 'ui08': 4, 'ui16': 4, 'ui32': 4, 'si32': 4, 'fp32': 4, 'rgba': 4,
         'ui64': 8, 'si64': 8, 'vec3': 16, 'vec4': 16, 'quat': 16, 'woid': 16, 'shnm': 16,
         'bbox': 32, 'mat4': 16}
PACK = {'bool': '?', 'ui08': 'B', 'ui16': 'H', 'ui32': 'I', 'si32': 'i', 'ui64': 'Q',
        'si64': 'q', 'fp32': 'f', 'mat4': '16f', 'bbox': '8f'}


def fnv1a32(raw):
    h = 0x811C9DC5
    for c in raw:
        h = ((h ^ c) * 0x01000193) & 0xFFFFFFFF
    return h


class Value:
    __slots__ = ('type', 'raw', 'ref')

    def __init__(self, type, raw, ref=None):
        self.type, self.raw, self.ref = type, bytes(raw), ref

    @property
    def text(self):
        return self.raw.decode('utf-8', 'strict') if self.type == 'stri' else None


class Dict:
    __slots__ = ('version', 'items')

    def __init__(self, version, items):
        self.version, self.items = version, items

    def get(self, key):
        return next((node for k, node in self.items if k.text == key), None)

    def put(self, key, node):
        for i, (k, _) in enumerate(self.items):
            if k.text == key:
                self.items[i] = (k, node)
                return
        raise FormatError('Missing dictionary key: ' + key)


class List:
    __slots__ = ('tag', 'items')

    def __init__(self, tag, items):
        self.tag, self.items = tag, items


class Opaque:
    __slots__ = ('raw',)

    def __init__(self, raw):
        self.raw = bytes(raw)


class Tree:
    def __init__(self, data):
        data = bytes(data)
        if data[:4] != b'!pkg' or len(data) < 16:
            raise FormatError('Expected a !pkg resource')
        self.name = data[4:8]
        self.data = data
        root_word, vca_word = struct.unpack_from('<II', data, 8)
        vca = vca_word & 0xffffff
        if data[vca:vca + 4] != b'!vca':
            raise FormatError('Missing value pool table')
        count = self._u32(vca + 4)
        if count > len(data) // 4:
            raise FormatError('Invalid value pool count')
        self.pools = []
        for i in range(count):
            off = self._u32(vca + 8 + 4 * i) & 0xffffff
            tag = self._take(off, 4)
            if tag == b'!sbi':
                self.pools.append(['stri', 0, self._take(off + 8, self._u32(off + 4)), None])
            elif tag == b'!vbi':
                typ = self._take(off + 4, 4).decode('ascii')
                n, stride = struct.unpack_from('<II', data, off + 8)
                if not stride or n * stride > len(data):
                    raise FormatError('Invalid pool size')
                self.pools.append([typ, stride, self._take(off + 16, n * stride), None])
            else:
                raise FormatError('Unsupported pool tag')
        self._seen = set()
        self.root = self._chunk(root_word & 0xffffff, 0)
        del self._seen
        self.canonical = self.to_bytes() == data

    def _take(self, off, size):
        if off < 0 or size < 0 or off + size > len(self.data):
            raise FormatError('Out-of-bounds !pkg data')
        return self.data[off:off + size]

    def _u32(self, off):
        return struct.unpack('<I', self._take(off, 4))[0]

    def _value(self, ref):
        pool, index = ref >> 24, ref & 0xffffff
        if pool >= len(self.pools):
            raise FormatError('Unknown pool reference')
        typ, stride, raw, _ = self.pools[pool]
        if typ == 'stri':
            if index >= len(raw) or index + raw[index] + 2 > len(raw) or raw[index + raw[index] + 1] != 0:
                raise FormatError('Invalid string reference')
            return Value(typ, raw[index + 1:index + 1 + raw[index]], (pool, index))
        if (index + 1) * stride > len(raw):
            raise FormatError('Invalid scalar reference')
        return Value(typ, raw[index * stride:(index + 1) * stride], (pool, index))

    def _ref(self, ref, depth):
        return self._chunk(ref & 0xffffff, depth + 1) if ref >> 24 == 0x80 else self._value(ref)

    def _chunk(self, off, depth):
        if off in self._seen or depth > 100:
            raise FormatError('Shared, cyclic or too deeply nested !pkg chunks are not editable')
        self._seen.add(off)
        tag = self._take(off, 4)
        if tag == b'!idi':
            header = self._u32(off + 4)
            n, version = header & 0xffffff, header >> 24
            if version not in (0, 1):
                raise FormatError('Unsupported dictionary version')
            stride = 12 if version == 1 else 8
            self._take(off + 8, n * stride)
            items = []
            for i in range(n):
                key_ref, value_ref = struct.unpack_from('<II', self.data, off + 8 + i * stride)
                key = self._value(key_ref)
                if key.type != 'stri':
                    raise FormatError('Non-string dictionary key')
                items.append((key, self._ref(value_ref, depth)))
            return Dict(version, items)
        if tag in (b'!ili', b'!vca'):
            n = self._u32(off + 4)
            self._take(off + 8, n * 4)
            return List(tag, [self._ref(self._u32(off + 8 + 4 * i), depth) for i in range(n)])
        if tag == b'!iar':
            return Opaque(self._take(off + 4, 8))
        raise FormatError('Unknown !pkg chunk %r' % tag)

    def _intern(self, value, pools):
        # Retained references stay exact; new values reuse the first equal entry, as Swofty does.
        if value.ref is not None:
            return (value.ref[0] << 24) | value.ref[1]
        pool = next((i for i, p in enumerate(pools) if p[0] == value.type), None)
        if pool is None:
            raise FormatError('Layer has no %s value pool; new pools are not created' % value.type)
        typ, stride, raw, index = pools[pool]
        if index is None:
            index = {}
            if typ == 'stri':
                o = 0
                while o < len(raw):
                    index.setdefault(bytes(raw[o + 1:o + 1 + raw[o]]), o)
                    o += raw[o] + 2
            else:
                for i in range(len(raw) // stride):
                    index.setdefault(bytes(raw[i * stride:(i + 1) * stride]), i)
            pools[pool][3] = index
        if value.raw not in index:
            if typ == 'stri':
                if len(value.raw) > 255:
                    raise FormatError('String exceeds 255 bytes')
                index[value.raw] = len(raw)
                raw += bytes([len(value.raw)]) + value.raw + b'\0'
            else:
                if len(value.raw) != stride:
                    raise FormatError('Unsupported scalar stride')
                index[value.raw] = len(raw) // stride
                raw += value.raw
        position = index[value.raw]
        if position > 0xffffff:
            raise FormatError('Pool reference exceeds 24-bit limit')
        return (pool << 24) | position

    def to_bytes(self):
        pools = [[typ, stride, bytearray(raw), None] for typ, stride, raw, _ in self.pools]
        out = bytearray(b'!pkg' + self.name + b'\0' * 8)
        queue = []

        def emit(node):
            start = len(out)
            if isinstance(node, Dict):
                stride = 12 if node.version == 1 else 8
                items = sorted(node.items, key=lambda kv: fnv1a32(kv[0].raw)) if node.version == 1 else node.items
                out.extend(b'!idi' + struct.pack('<I', len(items) | (node.version << 24)))
                table = len(out)
                out.extend(b'\0' * (stride * len(items)))
                for i, (key, child) in enumerate(items):
                    slot = table + stride * i
                    struct.pack_into('<I', out, slot, self._intern(key, pools))
                    if node.version == 1:
                        struct.pack_into('<I', out, slot + 8, fnv1a32(key.raw))
                    if isinstance(child, Value):
                        struct.pack_into('<I', out, slot + 4, self._intern(child, pools))
                    else:
                        queue.append((slot + 4, child))
            elif isinstance(node, List):
                out.extend(node.tag + struct.pack('<I', len(node.items)))
                table = len(out)
                out.extend(b'\0' * (4 * len(node.items)))
                for i, child in enumerate(node.items):
                    if isinstance(child, Value):
                        struct.pack_into('<I', out, table + 4 * i, self._intern(child, pools))
                    else:
                        queue.append((table + 4 * i, child))
            else:
                out.extend(b'!iar' + node.raw)
            return start

        root = emit(self.root)
        cursor = 0
        while cursor < len(queue):
            slot, node = queue[cursor]
            cursor += 1
            struct.pack_into('<I', out, slot, 0x80000000 | emit(node))
        out.extend(b'\0' * (-len(out) % 4))
        vca = len(out)
        out.extend(b'!vca' + struct.pack('<I', len(pools)))
        table = len(out)
        out.extend(b'\0' * (4 * len(pools)))
        for i, (typ, stride, raw, _) in enumerate(pools):
            out.extend(b'\0' * (-len(out) % ALIGN.get(typ, 4)))
            struct.pack_into('<I', out, table + 4 * i, 0x80000000 | len(out))
            if typ == 'stri':
                out.extend(b'!sbi' + struct.pack('<I', len(raw)) + raw)
            else:
                out.extend(b'!vbi' + typ.encode('ascii') + struct.pack('<II', len(raw) // stride, stride) + raw)
        out.extend(b'\0' * (-len(out) % 4))
        if len(out) > 0xffffff:
            raise FormatError('Package exceeds 24-bit address limit')
        struct.pack_into('<II', out, 8, 0x80000000 | root, 0x80000000 | vca)
        return bytes(out)

    def node(self, path):
        node = self.root
        for step in path:
            node = child(node, step)
            if node is None:
                raise FormatError('Missing !pkg path %r' % (path,))
        return node

    def set_value(self, path, value):
        parent = self.node(path[:-1])
        old = child(parent, path[-1])
        if not isinstance(old, Value):
            raise FormatError('Not a value: %r' % (path,))
        replace(parent, path[-1], Value(old.type, encode(old, value)))

    def clone_entry(self, path, index, values):
        container = self.node(path)
        if not isinstance(container, List) or not 0 <= index < len(container.items):
            raise FormatError('Clone source is not an array entry')
        entry = copy.deepcopy(container.items[index])
        for relative, value in values.items():
            parent = node_at(entry, relative[:-1])
            old = child(parent, relative[-1])
            if not isinstance(old, Value):
                raise FormatError('Cloned field is not a value: %r' % (relative,))
            replace(parent, relative[-1], Value(old.type, encode(old, value)))
        container.items.append(entry)
        return len(container.items) - 1


def child(node, step):
    if isinstance(node, Dict) and isinstance(step, str):
        return node.get(step)
    if isinstance(node, List) and isinstance(step, int):
        return node.items[step] if 0 <= step < len(node.items) else None
    return None


def node_at(node, path):
    for step in path:
        node = child(node, step)
        if node is None:
            raise FormatError('Missing !pkg path %r' % (path,))
    return node


def replace(parent, step, node):
    if isinstance(parent, Dict):
        parent.put(step, node)
    else:
        parent.items[step] = node


def encode(old, value):
    """Encode value with the existing field's native type and width; no type changes."""
    typ = old.type
    if typ == 'stri':
        raw = value.encode('utf-8') if isinstance(value, str) else None
        if raw is None or len(raw) > 255 or b'\0' in raw:
            raise FormatError('String must fit 255 UTF-8 bytes without NUL')
        return raw
    if typ in ('woid', 'rgba'):
        try:
            raw = bytes.fromhex(value.lstrip('#')) if isinstance(value, str) else bytes(value)
        except (TypeError, ValueError):
            raise FormatError('%s value must be hexadecimal' % typ) from None
        if len(raw) != len(old.raw):
            raise FormatError('%s value must have %d bytes' % (typ, len(old.raw)))
        return raw
    if typ == 'shnm':
        raw = value.encode('utf-8')
        if len(raw) > len(old.raw) or b'\0' in raw:
            raise FormatError('Short name exceeds field width')
        return raw.ljust(len(old.raw), b'\0')
    if typ in ('vec3', 'vec4', 'quat'):
        values = [float(x) for x in value]
        if len(values) not in (3, 4):
            raise FormatError('Vector value needs 3 or 4 numbers')
        fmt, values = '4f', values + [0.0] * (4 - len(values))
    elif typ in PACK:
        fmt = PACK[typ]
        values = list(value) if isinstance(value, (list, tuple)) else [value]
    else:
        raise FormatError('Opaque %s field cannot be edited' % typ)
    if any(isinstance(x, float) and not math.isfinite(x) for x in values):
        raise FormatError('Non-finite values are not supported')
    try:
        raw = struct.pack('<' + fmt, *values)
    except struct.error as exc:
        raise FormatError(str(exc)) from None
    if len(raw) != len(old.raw):
        raise FormatError('Unsupported scalar stride')
    return raw


def float32(values):
    """JSON numbers that round-trip exactly to the stored float32 values."""
    return [struct.unpack('<f', struct.pack('<f', float(v)))[0] for v in values]


def selector(path):
    """Parse launcher selector paths: keys, [index] and [field=value] steps."""
    steps, rest = [], path.strip()
    while rest:
        if rest.startswith('['):
            end = rest.find(']')
            if end < 0:
                raise FormatError(path + ': unclosed [')
            inner = rest[1:end]
            if '=' in inner:
                key, value = inner.split('=', 1)
                steps.append(('match', key.strip(), value))
            else:
                try:
                    steps.append(('index', int(inner.strip())))
                except ValueError:
                    raise FormatError(path + ': bad selector') from None
            rest = rest[end + 1:]
        else:
            end = min([i for i in (rest.find('.'), rest.find('[')) if i >= 0] or [len(rest)])
            if end:
                steps.append(('key', rest[:end]))
            rest = rest[end:]
        if rest.startswith('.'):
            rest = rest[1:]
    return steps


def text(node):
    if not isinstance(node, Value):
        return None
    if node.type == 'stri':
        return node.text
    if node.type in ('ui32', 'si32', 'ui16', 'ui08'):
        number = struct.unpack('<' + PACK[node.type], node.raw)[0]
        return str(number)
    return None


def _position(items, step):
    if step[0] == 'index':
        return step[1] if 0 <= step[1] < len(items) else None
    if step[0] == 'match':
        return next((i for i, n in enumerate(items) if isinstance(n, Dict) and text(n.get(step[1])) == step[2]), None)
    return None


def _walk(node, steps, path):
    for step in steps:
        if isinstance(node, Dict) and step[0] == 'key':
            node = node.get(step[1])
        elif isinstance(node, List) and step[0] != 'key':
            i = _position(node.items, step)
            node = None if i is None else node.items[i]
        else:
            node = None
        if node is None:
            raise FormatError(path + ': no ' + repr(step))
    return node


def _set(node, path, value):
    steps = selector(path)
    if not steps:
        raise FormatError('Empty value path')
    parent = _walk(node, steps[:-1], path)
    last = steps[-1]
    if isinstance(parent, Dict) and last[0] == 'key':
        old, key = parent.get(last[1]), last[1]
    elif isinstance(parent, List) and last[0] != 'key':
        key = _position(parent.items, last)
        old = None if key is None else parent.items[key]
    else:
        old = None
    if not isinstance(old, Value):
        raise FormatError(path + ' is not a value')
    replace(parent, key, Value(old.type, encode(old, value)))


def patch_edits(tree, edits):
    """Apply launcher clone-entry/set-value edits to a Tree, mirroring pkgedit.rs."""
    for edit in edits:
        op = edit.get('op')
        if op == 'set-value':
            _set(tree.root, edit['path'], edit['value'])
        elif op == 'clone-entry':
            if edit.get('from'):
                raise FormatError('Cross-resource clone-entry is not replayed offline')
            src = selector(edit['src'])
            if len(src) != 1 or src[0][0] != 'match':
                raise FormatError('Only [field=value] array clone selectors are supported')
            container = _walk(tree.root, selector(edit['at']), edit['at'])
            if not isinstance(container, List):
                raise FormatError(edit['at'] + ' is not an array')
            key, name = src[0][1], edit['as']
            i = _position(container.items, src[0])
            if i is None:
                raise FormatError(edit['at'] + ': no entry ' + edit['src'])
            if _position(container.items, ('match', key, name)) is not None:
                raise FormatError('An entry with %s=%s already exists' % (key, name))
            entry = copy.deepcopy(container.items[i])
            _set(entry, key, name)
            for path in sorted(edit.get('set', {})):
                _set(entry, path, edit['set'][path])
            container.items.append(entry)
        else:
            raise FormatError('Unsupported patch-pkg edit: %s' % op)
    return tree
