# Native editing preview 0.2.0

0.3.2: terrain previews are complete (degenerate/duplicate triangles omitted from previews only, per-draw error isolation, half-float vertex colours). Earlier imports of stock tracks were missing most of their main terrain; re-import to see it.


Latest 0.2.6 adds explicit static-prop duplication and composable `patch-pkg` update addons. See [insertion scope and limits](research/native-insertion.md). Changes-only export still requires stock-track sources.


Latest0.2.2 adds complete supported static LOD/material family test export and native LOD editing collections. See [current scope](research/static-writer.md).54Python tests pass; main track updates remain placement-only.

0.2.1 adds a separate [static geometry test compiler](research/static-writer.md). Main track update export retains the placement-only limits below. Current Python test total:14project tests +37baseline tests.

29 October 2026. This internal milestone implements part of the five approved development steps. It does not complete public V1.

## Implemented

- Registry for common, F1/MyTeam/F2 2025/2026, Classic and distinct additional native worlds. Read-only inventory of 28 installed tracks informed mapping. Core presence does not prove all-mode readiness.
- Stock F1, Swofty addon and raw track ZIP import: stable identities, shared meshes, dependency references, packed material and terrain previews. Unsupported geometry remains a reported reference.
- Supported existing WorldObject matrix updates retain render-local transforms, native layers, opaque payloads and unrelated files. Changed sources, conflicting mirrored resources and unsupported edits are rejected.
- Separate full updated outputs and stock-source changes-only Swofty replace-resource packages. Addon changes-only targeting awaits launcher-resolved archive paths.
- Thumbnail material curation, .blend pack loading and independent object/face application. Actual-geometry facility curation, reference placement and approximate overlap/bounds checks.
- Ordinary .blend save/reopen; optional bookkeeping under Advanced Files.

## Verification

12 pure Python tests cover native updates, opaque data, mirror conflicts, package preservation, paths, codecs and storage. 37 retained baseline tests cover existing tools. Synthetic headless checks passed on installed Blender 4.5.0 Beta and 5.0.1: transform separation, native matrix readback and save/reopen. Material/facility tests passed on both. Stable Blender 4.5 and interactive UI coverage remain unverified.

A whole Monaco import passed in Blender 5.0.1: 10,022 objects, 1,168 mesh datablocks, 638 materials, 502 images, 894 preview warnings. It preceded subsequent sharing/terrain refinements, so is not a full retest of the final package. An earlier custom-normal upload crash led to finite validation, rejection of geometry requiring repairs and per-corner normal upload.

The final real-source sample covers 24 placed records and at most two terrain draws: 27 objects, 5 packed images, no-op export after save/reopen and one moved placement serialized into one native layer. Two shader previews were explicitly approximate. Proprietary fixtures/output files remain private.

## Remaining approved work

Geometry/terrain/collision writers, native shader/texture export, facility insertion, variant creation, AI/pits/grids/cameras/audio/crowds/marshals/animation/triggers, donor application, pack discovery and complete export validation remain unfinished. Placement changes do not rebuild collision. No game was launched or installation written. No output has been validated by gameplay. V1 acceptance criteria remain unchanged.

## Suggested user checks

1. Import once; confirm one root and expected variants.
2. Switch Variant View; save/reopen and inspect textures.
3. Move one supported existing placement and export separately.
4. Try mesh/material edits; export should explain the unfinished writer.
5. Curate/apply materials and place facility references; inspect thumbnails, anchor and bounds. References are not inserted native game objects yet.
