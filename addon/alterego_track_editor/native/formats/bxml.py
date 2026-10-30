"""Lossless EGO binary XML (``\\x01BXML``) records for route and spline resources.

Each record is i16 length (payload bytes + 4), u8 type, u8 pad, i16 count, then
payload. Type 0 opens an element (name, attribute pairs), 5 closes it, 1 is text;
any other record (for example the type-6 document trailer) is kept as opaque bytes.
Strings keep their raw bytes; the tree re-encodes byte-identically or is refused.
"""
import struct

MAGIC = b'BXML'


class FormatError(ValueError):
    pass


class Element:
    __slots__ = ('name', 'attrs', 'children', 'head', 'close')

    def __init__(self, name, attrs=None, children=None, head=(0, 0), close=None):
        self.name = name          # bytes
        self.attrs = attrs or []  # [[key bytes, value bytes]]
        self.children = children or []
        self.head = head          # (type pad byte, unused) retained from the open record
        self.close = close        # raw close record bytes

    def get(self, key, default=None):
        key = key.encode() if isinstance(key, str) else key
        return next((v.decode('utf-8') for k, v in self.attrs if k == key), default)

    def set(self, key, value):
        key = key.encode() if isinstance(key, str) else key
        for pair in self.attrs:
            if pair[0] == key:
                pair[1] = value.encode('utf-8')
                return
        raise FormatError('Missing attribute: %r' % key)

    @property
    def tag(self):
        return self.name.decode('utf-8')

    def elements(self, name=None):
        return [c for c in self.children if isinstance(c, Element) and (name is None or c.tag == name)]


class Opaque:
    __slots__ = ('raw',)

    def __init__(self, raw):
        self.raw = bytes(raw)


class Document:
    def __init__(self, data):
        data = bytes(data)
        if len(data) < 5 or data[1:5] != MAGIC:
            raise FormatError('Expected a BXML resource')
        self.order = data[0]
        if self.order == 0:
            raise FormatError('Big-endian BXML is not supported')
        self.data = data
        self.prefix = data[:5]
        pos, stack, self.roots, self.trailer = 5, [], [], []
        while pos < len(data):
            if pos + 6 > len(data):
                raise FormatError('Truncated BXML record')
            length, kind, pad, count = struct.unpack_from('<hBBh', data, pos)
            end = pos + 2 + length
            if length < 4 or end > len(data):
                raise FormatError('Invalid BXML record length')
            payload = data[pos + 6:end]
            if kind == 0:
                parts = payload.split(b'\0')
                if parts[-1] != b'' or len(parts) != 2 + 2 * count or count < 0:
                    raise FormatError('Element strings do not match the attribute count')
                node = Element(parts[0], [[parts[1 + 2 * i], parts[2 + 2 * i]] for i in range(count)], head=(pad, count))
                (stack[-1].children if stack else self.roots).append(node)
                stack.append(node)
            elif kind == 5 and stack:
                stack.pop().close = data[pos:end]
            elif kind == 1 and stack:
                stack[-1].children.append(Opaque(data[pos:end]))
            elif stack:
                stack[-1].children.append(Opaque(data[pos:end]))
            else:
                self.trailer.append(Opaque(data[pos:end]))
            pos = end
        if stack:
            raise FormatError('Unclosed BXML element: '+stack[-1].tag)
        if len(self.roots) != 1:
            raise FormatError('Expected one BXML root element')
        self.root = self.roots[0]
        if self.to_bytes() != data:
            raise FormatError('BXML record layout does not re-encode identically')

    def to_bytes(self):
        out = bytearray(self.prefix)

        def emit(node):
            if isinstance(node, Opaque):
                out.extend(node.raw)
                return
            payload = node.name + b'\0' + b''.join(k + b'\0' + v + b'\0' for k, v in node.attrs)
            if any(b'\0' in s for pair in node.attrs for s in pair) or b'\0' in node.name:
                raise FormatError('BXML strings cannot contain NUL')
            if len(payload) + 4 > 0x7fff:
                raise FormatError('BXML element exceeds record size')
            out.extend(struct.pack('<hBBh', len(payload) + 4, 0, node.head[0], len(node.attrs)) + payload)
            for child in node.children:
                emit(child)
            out.extend(node.close)

        emit(self.root)
        for node in self.trailer:
            out.extend(node.raw)
        return bytes(out)


def floats(text, count=3):
    values = [float(v) for v in text.replace(',', ' ').split()]
    if len(values) != count:
        raise FormatError('Expected %d numbers: %r' % (count, text))
    return values
