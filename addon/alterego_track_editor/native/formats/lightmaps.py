"""LightMapLocRes: baked-lighting atlas rectangles keyed by instance uniqueid.

Layout (stock bake/<track>_*.bake.erp, checked on Monaco/Spa): u32 count, then 32-byte
records <16s I f f f> = uniqueid, atlas layer (0 = terrain), size as a fraction of the
4096 atlas edge (x 4096 = Render.lightmap_size), u, v. Stock files share rectangles
between instances (Monaco: one rectangle used by 622), which new placements reuse.
"""
import struct

RECORD = struct.Struct('<16sIfff')


class FormatError(ValueError):
    pass


def read(data):
    count = struct.unpack_from('<I', data, 0)[0] if len(data) >= 4 else -1
    if count < 0 or 4 + RECORD.size * count != len(data):
        raise FormatError('Unexpected LightMapLocRes size')
    return [RECORD.unpack_from(data, 4 + RECORD.size * i) for i in range(count)]


def write(records):
    return struct.pack('<I', len(records)) + b''.join(RECORD.pack(*r) for r in records)


def share(data, pairs):
    """Append records giving each new uniqueid its source's rectangle.

    pairs: [(source uniqueid bytes, new uniqueid bytes)]. Sources without a record are skipped.
    Returns (new bytes, number of added records).
    """
    records = read(data)
    by_uid = {r[0]: r for r in records}
    added = []
    for source, new in pairs:
        if new in by_uid:
            raise FormatError('New placement already has a lightmap record')
        if source in by_uid:
            record = (new, *by_uid[source][1:])
            by_uid[new] = record
            added.append(record)
    if not added:
        return data, 0
    result = write(records + added)
    if read(result)[:len(records)] != records:
        raise FormatError('Lightmap readback failed')
    return result, len(added)
