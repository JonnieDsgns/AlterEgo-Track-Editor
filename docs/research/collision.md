# Collision editing and construction - preview0.2.5

30 October 2026. Internal asset-authoring milestone, not full V1/game acceptance.

## Native collision surface editing

The Collision sidebar panel can load native collision near the 3D cursor, with a radius and preview-cell limit. Zero radius includes all cells within that limit. Repeated loading reuses edits and can add other regions. Only the current region is shown; previously loaded edits are retained. Each native four-byte palette identifier is displayed as a physics material. Unknown/nonprintable entries are preserved as opaque HEX tokens, not interpreted as a default surface. No appearance-to-physics or code-to-driving-class mapping is inferred.

Choose a native physics code and Assign Physics Code. In Edit mode it affects selected faces of selected collision meshes; Object mode affects selected cells. Export Collision Surface Update writes a separate native track folder or supported updated addon archive. Native geometry, world poses, vertex words, edge flags, bounds, search nodes, modern six-byte leaf headers, alignment bytes and per-triangle search records remain unchanged. Missing/deleted/duplicated previews, modifiers, geometry/movement edits, stale sources and conflicting assignments to shared cells are rejected. A cell may use at most eight physics codes.

The export updates the selected shared physics resource. Every original layer/variant that references it receives those code edits. Matching edits from its other loaded bindings are merged; conflicts abort. Other resources' edits and other Blender authoring workflows are not merged into this specialized export. The normal visual-material/surface controls do not assign these native physics codes automatically. Physical response remains game-unverified.

## Authored geometry: explicit legacy test only

For authored Blender meshes, enable Collision and choose an explicit native code. Export Legacy Collision Test evaluates selected static meshes and modifiers in world coordinates, preserves mirrored-transform winding and writes JPAK/VCQTC version0x20002. Fresh bounded spatial cells and complete single-root leaves are generated; donor acceleration bytes are not reused. Input geometry is checked after Float32 quantization for degeneracy, range and finite bounds. The code list is a conservative authoring set from the existing compiler, not a complete global material whitelist.

This is an older collision format. It is not a verified F1 25 version0x20004 replacement, is not mounted by the tool, and is not an installable/game-ready track package. No automatic format substitution occurs. Modern native geometry creation remains blocked by unresolved leaf header/record semantics. The visual terrain writer is a separate unfinished task.

## Evidence

66Python tests pass (29project+37baseline). New tests cover independent synthetic modern layouts, no-op identity, palette changes with preservation of every other byte, duplicate palette slots, opaque tokens, edge/index flags, complete tree coverage, malformed references, Float32 collapse, legacy spatial/palette limits and explicit version rejection.

Headless Blender4.5.0Beta/5.0.1 checks cover selected-face editing, preview reuse, separate native export/readback, shared-preview conflict rejection, source preservation, moved-geometry rejection, save/reopen and legacy generation with mirrored parent/world axes. Stable4.5 and full interactive verification remain unperformed.

Real source checks pass on Monaco, Spa-Francorchamps, Austria, Bahrain, Miami and Las Vegas:3391cells/1134357triangles total. Each supports exact no-op and surface edit readback with every non-palette/non-slot byte retained. Bahrain includes15used zero-valued palette entries; these remain opaque HEX_00000000 tokens. A bounded Blender5.0.1 Monaco check loaded2of150cells/659faces and exported code edits without source changes. This was not a full-track or game-loading test.

An independent managed reader harness linked to the unchanged owned C# format sources accepted the authored legacy files (including140triangles/18cells) and the edited synthetic modern payload. No original backend/application or game was launched. No installation writes or game-derived fixtures are published. Source hashes are recorded in static-writer-source.json.

## Format boundary

Native0x20004 cell/reference structures are parsed and preserved. Height bounds have some previous source evidence, but the second leaf word, auxiliary fields and complete generation rules are not fully established here. They are not guessed. New geometry generation is therefore limited to explicitly labelled legacy tests, while native editing is restricted to palette/code slots.

Next: modern search-record research, native collision/visual-terrain generation, broader addon targeting, new object insertion and combined full-track/race-system export. Public V1 requirements remain unchanged.

## 0.3.1: experimental whole-track legacy rebuild

**New evidence.** Two community Istanbul ports, measured read-only from locally available community packages, use legacy JPAK/VCQTC `0x20002` as the track's whole physics terrain: `IstanbulPark_v11.0` on a Sepang/bahrain24 slot (371 cells, 143,699 triangles) and the handoff build `IstanbulPark_Spa_v2.70` on Spa (371 cells, 143,485 triangles). Their handoff records user playtests with no fall-through after v0.7, and that codes the base track does not use (`ASTR`, `PDT+`, `METL` on Spa) made the game drop whole chunks until mapped to the base's own codes. Acceptance on every base track is not established. Measured layout of both files: name-table offset in header word `0x14` (also present in stock modern files, which our earlier builder left zero), quadtree-path cell names, at most 997 triangles and 659 vertices per cell, B/C vertex offsets of at most 200, an internal root in every cell, leaves at depths 1–6, edge bits 7 on every triangle, consistent vertex words per code, used palette slots as a prefix with unused slots padded only by codes the track already uses. Stock files carry an extra `qtsign.vcqtc` cell that these playable legacy files omit.

**Builder.** `build_legacy` now follows that layout: XZ quadtree chunks of at most 1,000 triangles, 1,023 vertices and 8 codes; per-cell breadth-first quadtrees with an internal root, leaves of at most 24 references or depth 6, triangle boxes widened by 0.25 m for leaf membership; deduplicated vertices with each triangle starting at its lowest index; gaps above 254 encoded with real intermediate triangle references (not a skip code). Every output is re-decoded and must contain exactly the input triangles and codes. The authored legacy test export uses the same builder.

**Workflow.** Export Updated Native Track > Rebuild collision (experimental legacy) replaces the track's single physics terrain resource with a rebuild of: all native triangles (with their own vertex words), loaded Collision previews as currently edited in Blender (geometry and codes; removing a whole loaded cell is refused), and every project mesh with Collision enabled. Allowed codes are exactly those used by the track's native collision; the code dropdown lists them once collision has been loaded. Authored collision meshes without the option are refused instead of being ignored. Update addons ship the rebuilt resource as one `replace-resource`.

**Checks.** Python: game-tested layout properties on a 7,200-triangle grid, dense stacked geometry, foreign-code and degenerate rejection, per-vertex and per-code words, modern-to-legacy round trip. Real read-only whole-track rebuilds: Monaco 48,961 triangles -> 142 cells (2.1 s), Spa 349,887 -> 1,482 (18.4 s), Bahrain 308,082 -> 796 (10.7 s), all exact on readback with at most 996 triangles and 648 vertices per cell. Headless Blender 4.5.0 Beta/5.0.1: default export leaves collision untouched, foreign code and silent authored collision refused, edited preview + authored triangle rebuilt with base vertex words, update addon, removed cell refused, source unchanged. Real Blender 5.0.1 Monaco: one cell edited plus one authored `SIGN` triangle -> 48,962 triangles in 142 cells.

**Limits.** Experimental: the whole collision is replaced by a format the stock track does not use; driving behaviour, kerbs/grip and AI on the rebuilt surface are untested in-game for any stock track. Native 0x20004 search records, the `qtsign` cell and modern-only fields are not carried over. Physics terrain only: object physics (`StaticPhysics`, `PhysicsEntity`) is unchanged.

Note (0.3.3): in modern 0x20004 cells, header words +0x2C/+0x34 are float32 Y extrema within the cell bounds (all 150 Monaco cells), as first described by the F1MapEditor toolkit. Modern generation remains unsupported.
