# Native placement insertion and composable layer edits - preview 0.2.6

30 October 2026. Internal asset-authoring milestone; not V1 and not game-verified.

## Workflow

Select one or more imported native static props and choose Project Settings > Duplicate as New Placement. Each duplicate is a new Blender object that shares the source mesh/material data; geometry is not copied. Move, rotate or scale it, then use Export Updated Native Track.

- Updated Native Files writes a separate full track folder or updated addon/package with the new instances appended to the source layer.
- Swofty Update Addon (stock-track sources) offers Composable Edits (default) or Whole Layers. Composable Edits writes launcher `erp.patch-pkg` operations: `set-value` for moved placements and `clone-entry` for new ones. The launcher documents that `patch-pkg` edits in one resource compose with other addons, whereas `replace-resource` conflicts. Whole Layers keeps the 0.2.5 replace-resource format and now also carries insertions.

A text block named `<project> Native Export Report` lists moved and inserted placements, their generated names/uniqueids, source and variants, and the limitations below.

## Eligibility

Only instances that look like ordinary static visual props are duplicated: template `RenderModel`, exactly the fields `name`, `overrides`, `template`, `uniqueid`, override components limited to `Model`, `Render` and `WorldObject` (Model and WorldObject required), a resolved `?context=render` model, `woid` uniqueid, string name and `mat4` transform. Functional placements (grid slots, garages, pit boxes, cameras, audio, lights, triggers, crowds, marshals, decals, physics bodies, particle effects, etc.) are refused: copying them would duplicate gameplay identities or IDs that need typed editors. Duplicates stay in the source layer and therefore in exactly the same variants/worlds. Moving a new placement into another variant is rejected.

Plain Blender copies (Shift+D, `Object.copy`) of native objects or of new placements are rejected at export with a pointer to the explicit operator, so insertion never happens implicitly. Deleting a new placement simply drops it; deleting an original native placement is still rejected.

## Native identities

The new instance copies the source entry, then sets:

- `name`: `<source name>_ate_<first 12 hex characters of the Blender insertion id>`; must be unique across every loaded layer, at most 255 bytes and free of `]` (launcher selector syntax).
- `uniqueid`: `md5("alterego-track-editor:<track code>:<layer uri>:<name>")` as a 16-byte `woid`, mirroring Swofty Custom Grid Size's namespaced MD5 convention; collisions with any existing uniqueid abort.
- `overrides.WorldObject.transform`: the authored world matrix with the source's render-local transform removed, as for existing placement edits.

The insertion id is stored on the Blender object, so save/reopen and repeated exports reproduce identical bytes. All other fields, including `Model.model`, `Model.mat binding` and every `Render` field (lightmap size/bake source, shadow and reflection flags), are copied unchanged.

## Format evidence

Read-only surveys of real stock layers found, for all 84 Monaco layers: no shared chunks, no unreachable bytes, breadth-first chunk order, version-1 dictionaries only, header name `INST`, root keys `instances` and `layer`, uniqueid type `woid` (9,456/9,456). Monaco and Spa had no duplicate instance names (36,411 instances across 175 layers). The surveyed instance shape was `name/overrides/template/uniqueid` for every instance.

SwoftyLauncher's Python serializer (`tools/pkg.py`) and the new `native/formats/pkg_tree.py` writer each reproduced all 175 Monaco/Spa layers byte-for-byte. `pkg_tree.py` additionally reproduced every layer in Austria, Bahrain, Miami and Las Vegas: 511/511 layers across six tracks. Structural edits are only permitted when the unchanged layer re-serializes identically; otherwise insertions are refused and moves keep the 0.2.5 copy-on-write editor (which preserves trailing/opaque bytes). Canonical layers now write moves through the same tree writer, matching what the launcher's `set-value` produces.

Reference hashes for the inspected launcher sources are recorded in `native-source.json`. `pkg_tree.py` is an independent implementation of that layout and of the `clone-entry`/`set-value` semantics in `packages/core/src/pkgedit.rs`; no launcher code is executed by the add-on.

## Validation performed

- Every insertion export is read back through the separate TrackView-derived `pkg.py` parser: existing instances must be unchanged apart from intended moves; each new entry must equal its source apart from name, uniqueid and transform.
- Every generated `patch-pkg` edit list is replayed offline on the original layer and must produce exactly the full-export bytes before anything is published.
- 34 project + 37 baseline Python tests pass, including an independently encoded stock-layout fixture, selector parsing, duplicate-name/invalid-value rejection, mirrors, determinism, collision of identities, functional-source refusal and non-canonical refusal.
- Headless Blender 4.5.0 Beta and 5.0.1: functional duplicate refused, shared-mesh duplicate, plain copies rejected, full export readback, two-archive composable patch, save/reopen identical layer bytes, source unchanged. Existing native, static-family, collision and library Blender checks still pass on both. The extracted 0.2.6 ZIP passes insertion/native/collision checks on 5.0.1.
- Real read-only checks (private outputs) on Monaco, Spa-Francorchamps, Bahrain, Miami and Las Vegas: one moved and one inserted barrier in the largest eligible layer; own replay exact; SwoftyLauncher's Python serializer applying the same edits produces identical bytes; real archive copy reads back with every other resource unchanged; sources unchanged. Eligible static props: Monaco 6,113/9,456, Spa 20,998/26,955, Bahrain 20,027/26,968, Miami 14,074/23,300, Las Vegas 19,904/25,547.
- Bounded real Blender 5.0.1 Monaco check: 24 static props imported, one duplicated and moved, saved/reopened, exported as composable and whole-layer update addons; the composable edits replay exactly to the whole-layer bytes (113.8 s).
- Austria's installed folder contains local backup copies (`austria_common - Kopie.erp`, `austria_common - Kopie (2).erp`) whose layers differ from `austria_common.erp`; the existing mirrored-layer conflict guard refuses edits there. This is correct behaviour for an ambiguous source, not a format failure.

The launcher's Rust `patch-pkg` build path was not executed (no Rust toolchain is installed); the Python serializer replay is the independent check. `patch-pkg` exists in launcher releases from v1.0.0, so the existing `>=1.3.0` compat field is retained.

## Limitations and open questions

- **Visual only.** No collision is generated for new placements; vehicles will pass through duplicated barriers. Track physics terrain is not rebuilt.
- **Precomputed visibility.** Monaco's F1 world has `PVSObjIDRes` data listing about 6,900 instance names. New names are absent from it. In-game culling of new placements in PVS-enabled worlds is unknown, and moved existing objects keep their old visibility data.
- **Lighting.** Copied `Render` fields include lightmap size and `lightmap_bake_source`; no lightmap bake data is generated. A scan of 9,122 non-texture Monaco resources found no resource containing the raw 16-byte uniqueids, but other identity mechanisms (names, hashes) are not ruled out.
- Changes-only Swofty export still requires stock-track sources; addon-base targeting is unresolved.
- Cross-layer/variant insertion, deletion (no launcher remove-entry edit exists), functional object creation and new-asset placement are not implemented. Independent assets (0.2.3/0.2.4) are not yet placeable as new instances.
- No game loading or gameplay was performed. The user performs game validation.

## 0.2.7: edited assets as new placements

Select an imported static prop, use Advanced Files > Load Geometry LODs, edit the companion LOD meshes, then choose Place Edited Asset and enter an asset name. A new placement appears at the 3D cursor, sharing the lowest LOD mesh so edits stay visible; the original object is unchanged. Several placements may use the same asset name; a name used for two different LOD groups is rejected.

At Export Updated Native Track, each (LOD group, asset name) is compiled once from all LODs with the existing complete-family compiler and independent-asset builder (0.2.2/0.2.3): renamed mesh/model/render/buffer resources plus a copied material binding context, with source material/shader/texture dependencies kept external. The placement clones its source entry as in 0.2.6 and additionally sets `overrides.Model.model` to the new family and `overrides.Model.mat binding` to the new context. Templates with opaque extra mesh records keep equal-length identities, so the family name may carry a deterministic hash suffix.

- Updated Native Files embeds the family only in the archive(s) holding the layer that places it.
- Swofty Update Addon ships the family in `assets/new-assets.erp` and adds `copy-resource` ops (byte-exact copy that fails if the name already exists) before the layer edit, in both Composable Edits and Whole Layers formats.
- Rejected: missing LODs, deleted LOD groups, edited materials/textures, material-slot mismatches, families colliding with existing resources and two placements whose compiled resources disagree.

Verification: 37 project + 37 baseline Python tests (new: full export with retargeted model, per-archive embedding, update addon asset archive/copy ops/replay, conflict cases). Headless Blender 4.5.0 Beta and 5.0.1: invalid names rejected, shared LOD mesh, full export with per-LOD edits read back, update addon copy-resource ops and asset archive, save/reopen produces identical layer and family bytes, missing family rejected, source unchanged. Bounded real Blender 5.0.1 Monaco check: one `armco_monaco_white_b` placement, all 3 LODs edited (100/76/24 triangles), placed as a new asset and exported in both update formats: 11 copied resources, composable edits replay exactly to the whole-layer bytes (148 s). The new asset has the same visual-only limits as other new placements: no collision, PVS or lightmap data. Not game-verified.

## 0.2.8: deleting static props and replacing their model

**Delete.** Deleting an imported native static prop in Blender now exports as removal of its layer entry (full exports and Whole Layers update addons). The launcher has no entry-removal edit, so Composable Edits refuses layers with deletions. Deletion is refused for functional/non-RenderModel placements and for props whose name or uniqueid appears in another entry's fields (for example `Render.lightmap_bake_source`). Props named in a `PVSObjIDRes` visibility table need the explicit export option *Allow deleting PVS-listed objects*. The game's handling of a missing PVS object is unknown, and most props are listed: in Monaco 5,341 static props are PVS-listed and 351 can be deleted without the opt-in; in Spa 19,496 and 843. Other placements are not renumbered or changed.

**Replace.** Select existing static props, make an edited LOD companion active and choose Use Edited Asset for Selected. Each placement keeps its identity and pose but points `Model.model`/`Model.mat binding` at the compiled family at export (composable `set-value` edits plus `copy-resource` in update addons). Restore Original Model reverts the choice. This supersedes the 0.2.4 stock-folder-only native copy path for normal track exports. Collision is unchanged.

Verification: 40 project + 37 baseline Python tests (new: deletion guards for functional, referenced and PVS-listed props; delete-plus-duplicate of one source; whole-layer-only updates; model replacement in both update formats). Headless Blender 4.5.0 Beta and 5.0.1 deletion and replacement/restore checks pass, plus every earlier native/insertion/static-family/collision/library check. Real read-only Monaco and Spa: a PVS-listed barrier removed from the largest prop layer with exact readback, and SwoftyLauncher's Python serializer produces identical bytes. Not game-verified.
