"""Precomputed visibility: PVSObjIDRes object lists and PVSVisRes (PVSD v5) cell bitsets.

Independent implementation of the layout described by the GPL-3.0 F1MapEditor toolkit
(github.com/sticktor/F1MapEditor, ego/pvs.py at 0c244b5), checked here against stock
F1 25 files: every cell must decode to exact bitset lengths and unchanged files must
re-encode byte-identically. Measured on stock tracks (docs/research/visibility-lighting.md):
bit index = object id (bit 0 unused; the F1MapEditor note assumed id-1), the bitset holds
roundup32(objects+1)+1024 bits, and sphere index = object id, with trailing ids (crowd
zones) carrying no sphere.
"""
import struct

HEADER = 72
EXTRA = 40
CELL = 32
STREAMS = 5


class FormatError(ValueError):
    pass


def read_objects(data):
    """[(name, id, value, field size)] from a PVSObjIDRes resource."""
    count = struct.unpack_from('<I', data, 0)[0]
    pos, rows = 4, []
    for _ in range(count):
        if pos + 8 > len(data):
            raise FormatError('Truncated PVS object list')
        size, length = struct.unpack_from('<II', data, pos)
        if length > size or pos + 16 + size > len(data):
            raise FormatError('Invalid PVS object entry')
        name = data[pos + 8:pos + 8 + length].decode('utf-8')
        oid, value = struct.unpack_from('<II', data, pos + 8 + size)
        rows.append((name, oid, value, size))
        pos += 16 + size
    if pos != len(data):
        raise FormatError('Unexplained bytes after PVS object list')
    return rows


def write_objects(rows):
    out = bytearray(struct.pack('<I', len(rows)))
    for name, oid, value, size in rows:
        raw = name.encode('utf-8')
        size = size or ((len(raw) + 1 + 3) & ~3)
        if len(raw) >= size:
            raise FormatError('PVS object name does not fit its field')
        out += struct.pack('<II', size, len(raw)) + raw.ljust(size, b'\0') + struct.pack('<II', oid, value)
    return bytes(out)


def decode_stream(data, absolute, length):
    """Control byte c: (c >> k) zero bytes, then (c & mask) literal bytes; c == 0 ends the stream."""
    shift, mask = (3, 7) if absolute else (2, 3)
    out, pos = bytearray(), 0
    while True:
        if pos >= len(data):
            raise FormatError('Unterminated PVS stream')
        control = data[pos]
        pos += 1
        if control == 0:
            break
        out += bytes(control >> shift)
        count = control & mask
        if pos + count > len(data):
            raise FormatError('Truncated PVS literal run')
        out += data[pos:pos + count]
        pos += count
    if pos != len(data) or len(out) != length:
        raise FormatError('PVS stream does not decode to its bitset length')
    return bytes(out)


def encode_stream(raw, absolute):
    shift, mask = (3, 7) if absolute else (2, 3)
    most = 255 >> shift
    out, pos = bytearray(), 0
    while pos < len(raw):
        zeros = 0
        while pos < len(raw) and raw[pos] == 0 and zeros < most:
            zeros += 1
            pos += 1
        literal = raw[pos:pos + mask]
        cut = literal.find(b'\0')
        literal = literal if cut < 0 else literal[:cut]
        if not zeros and not literal:
            continue
        out.append((zeros << shift) | len(literal))
        out += literal
        pos += len(literal)
    out.append(0)
    return bytes(out)


def bit_count(objects):
    """Bitset size observed in every stock PVSVisRes for an object list of this length."""
    return ((objects + 1 + 31) // 32) * 32 + 1024


def xor(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


class Visibility:
    def __init__(self, data):
        data = bytes(data)
        if data[:4] != b'PVSD' or struct.unpack_from('<I', data, 4)[0] != 5:
            raise FormatError('Expected PVSD version 5 visibility data')
        self.header = bytearray(data[:HEADER])
        if struct.unpack_from('<I', data, 20)[0] != len(data) - HEADER:
            raise FormatError('PVS size field does not match')
        a, b = struct.unpack_from('<II', data, 52)
        c, appendix = struct.unpack_from('<HH', data, 60)
        size = struct.unpack_from('<I', data, 64)[0]
        self.objects = struct.unpack_from('<I', data, 16)[0]
        self.bits = struct.unpack_from('<I', data, 36)[0]
        self.extra = data[HEADER:HEADER + EXTRA]
        table = HEADER + EXTRA
        count = a + b + c
        base = table + count * CELL
        self.cells = []
        for k in range(count):
            w0, w1, x, y, z, w, *bounds = struct.unpack_from('<IIhhhH4H', data, table + k * CELL)
            self.cells.append({'w0': w0, 'w1': w1, 'xyz': (x, y, z), 'w': w, 'bounds': bounds,
                               'rest': data[table + k * CELL + 24:table + (k + 1) * CELL]})
        for k, cell in enumerate(self.cells):
            start = cell['w0'] & 0x7FFFFFF
            end = (self.cells[k + 1]['w0'] & 0x7FFFFFF) if k + 1 < count else size
            if not 0 <= start <= end <= size:
                raise FormatError('Invalid PVS cell data range')
            cell['raw'] = data[base + start:base + end]
            cell['ref'] = (cell['w1'] << 5) | (cell['w0'] >> 27)
            if cell['ref'] >= count:
                raise FormatError('PVS cell references a missing cell')
        pos = base + size
        self.appendix = data[pos:pos + appendix]
        pos += appendix
        self.points = data[pos:pos + 16 * c]
        pos += 16 * c
        self.spheres = data[pos:pos + 16 * self.objects]
        if pos + 16 * self.objects != len(data):
            raise FormatError('Unexplained bytes after PVS cells')
        self.data = data
        self._sets = {}

    @property
    def set_bytes(self):
        return (self.bits + 7) // 8

    def streams(self, k):
        cell = self.cells[k]
        cuts = [0] + list(cell['bounds']) + [len(cell['raw'])]
        if cuts != sorted(cuts):
            raise FormatError('Invalid PVS stream boundaries')
        return [cell['raw'][cuts[j]:cuts[j + 1]] for j in range(STREAMS)]

    def sets(self, k, _depth=0):
        """Five complete bitsets of cell k (reference deltas resolved)."""
        if k in self._sets:
            return self._sets[k]
        if _depth > len(self.cells):
            raise FormatError('Cyclic PVS cell references')
        ref = self.cells[k]['ref']
        decoded = [decode_stream(s, ref == 0, self.set_bytes) for s in self.streams(k)]
        if ref:
            decoded = [xor(d, b) for d, b in zip(decoded, self.sets(ref, _depth + 1))]
        self._sets[k] = decoded
        return decoded

    def sphere(self, oid):
        return struct.unpack_from('<4f', self.spheres, 16 * (oid - 1))

    def with_objects(self, listed, sources):
        """New visibility bytes for objects appended to a contiguous list of `listed` ids.

        sources: source object id per new object (new ids listed+1...). Each new object copies
        its source's bit in every cell and stream; like stock trailing objects it gets no sphere.
        Cells keep their reference structure and are re-encoded.
        """
        if not sources:
            return self.data
        if self.bits != bit_count(listed):
            raise FormatError('PVS bitset size does not follow the stock rule for this object list')
        new_bits = bit_count(listed + len(sources))
        new_bytes = (new_bits + 7) // 8
        full = []
        for k in range(len(self.cells)):
            sets = []
            for bitset in self.sets(k):
                grown = bytearray(bitset) + bytes(new_bytes - len(bitset))
                for n, source in enumerate(sources):
                    if not 1 <= source <= listed:
                        raise FormatError('PVS source object is outside the object list')
                    if bitset[source >> 3] >> (source & 7) & 1:
                        target = listed + 1 + n
                        grown[target >> 3] |= 1 << (target & 7)
                sets.append(bytes(grown))
            full.append(sets)
        packed, table, offset = [], bytearray(), 0
        for k, cell in enumerate(self.cells):
            ref = cell['ref']
            sets = full[k] if not ref else [xor(a, b) for a, b in zip(full[k], full[ref])]
            streams = [encode_stream(s, ref == 0) for s in sets]
            cuts, pos = [], 0
            for s in streams[:-1]:
                pos += len(s)
                cuts.append(pos)
            if max(cuts) > 0xFFFF or offset > 0x7FFFFFF:
                raise FormatError('PVS cell data exceeds the table field ranges')
            w0 = (cell['w0'] & 0xF8000000) | offset
            table += struct.pack('<IIhhhH4H', w0, cell['w1'], *cell['xyz'], cell['w'], *cuts) + cell['rest']
            raw = b''.join(streams)
            packed.append(raw)
            offset += len(raw)
        body = b''.join(packed)
        header = bytearray(self.header)
        struct.pack_into('<I', header, 36, new_bits)
        struct.pack_into('<I', header, 64, len(body))
        rest = self.extra + bytes(table) + body + self.appendix + self.points + self.spheres
        struct.pack_into('<I', header, 20, len(rest))
        result = bytes(header) + rest
        check = Visibility(result)
        for k in range(len(self.cells)):
            if check.sets(k) != full[k]:
                raise FormatError('PVS readback failed for cell %d' % k)
        return result
