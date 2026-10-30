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
