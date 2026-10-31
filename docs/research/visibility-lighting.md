# Visibility and baked lighting for new placements - preview 0.3.3

31 October 2026. Static, measured format work; in-game effect not verified.

## What changed

New placements (Duplicate as New Placement, Place Edited Asset and Add Next Race Placement) previously had no precomputed-visibility (PVS) or baked-lighting entries. Export Updated Native Track now, by default (option *Visibility and lighting for new placements*):

- appends each new placement whose source is listed in a track's `PVSObjIDRes` object list with the next object id, and gives it its source object's visibility bit in every cell and in all five per-cell bitsets of the matching `PVSVisRes`;
- appends a `LightMapLocRes` record that shares its source's lightmap atlas rectangle, in every lightmap-location resource of the track (`bake/<track>_ao.bake.erp`, and `_radiance` where present).

These resources are binary, so Swofty update addons replace them whole (`replace-resource`, not composable). Native track folders now mount `bake/` archives.

## Formats (independent implementation; layout first described by the GPL-3.0 F1MapEditor toolkit)

- `PVSObjIDRes` (`<track>_f1.header.pvsbin`): u32 count; per object u32 field size ((len+1+3)&~3), u32 name length, padded name, u32 id, u32 value (always 1). Ids are 1..n.
- `PVSVisRes` (`<track>_f1.volumedata.pvsbin`): 72-byte `PVSD` v5 header (u32 +16 sphere count, +20 size after header, +36 bitset bits, +52/+56 cell group counts, u16 +60/+62, u32 +64 cell data size), 40 extra bytes, 32-byte cell table (offset and reference-cell index in two words, i16 position, four stream boundaries, 8 bytes), cell data, appendix, points, 16-byte spheres. Each cell holds five run-length-coded bitsets; reference cells store an XOR delta.
- `LightMapLocRes`: u32 count + 32-byte records `<16s I f f f>` (uniqueid, atlas layer, size fraction of 4096, u, v).

## Evidence (stock F1 25, read-only)

- All 28 installed tracks (PVS data exists for the F1 world only): every bitset of every cell decodes to the exact bitset length, object lists rewrite byte-identically, the bitset-size rule below holds, and appending one object reads back with its source's bits copied in every cell (7,220–38,257 cells per track). Unchanged old bits were confirmed on 12 tracks after fixing a test that ignored the new bit sitting in the stock spare range.
- **Bit index = object id** (not id-1 as the F1MapEditor note assumed): for objects whose neighbouring ids lie more than 300 m away, the object's own bit is set in 95–100 % of cells within 20 m of it, against 16–37 % for the neighbouring bits (Monaco, Bahrain, Spa, Austria; 120 objects each).
- Bitset size = list count + 1 rounded up to 32, plus 1,024 spare bits, on every track. Sphere index = object id (centre within radius for 97–99 % of placed objects); trailing list entries (crowd zones) have no sphere, so new ids are added the same way, without a sphere.
- `LightMapLocRes`: Monaco 6,677 records; layer 0 = terrain; size x 4096 = `Render.lightmap_size` for 4,201 of 4,202 instances with that field; rectangles are shared in stock data (one by 622 instances).
- Real derivation: Monaco one PVS-listed duplicate -> object list +1, 7,220 cells re-encoded and read back, both lightmap resources +1 (14.6 s); Spa 24,342 cells (132.9 s, pure Python).

## Limits

Whether the game uses the copied bits as intended, and how it treats a listed object without a sphere, is untested in-game. Moved placements keep their original visibility and lighting; deleted placements leave unused entries. The copied lightmap rectangle holds lighting baked for the source's position, so shading can differ. Large tracks take minutes to export when visibility data is rewritten.
