# Technical audit — 29 October 2026

Internal 0.2.6: explicit static-prop duplication as new native placements and composable Swofty `patch-pkg` layer edits implemented. The canonical layer writer reproduces 511/511 real layers across six tracks byte-for-byte; 71 Python tests, Blender 4.5.0 Beta/5.0.1 headless checks and five real-track insertion checks pass. New placements are visual only (no collision, PVS or lightmap data). See [scope and evidence](research/native-insertion.md).


Internal0.2.5: native collision preview/surface-only export and explicit legacy collision construction tests implemented.66Python tests,4.5Beta/5.0.1 headless checks, six real native resources and independent managed-reader validation pass. Native0x20004 topology and visual terrain writing are still unfinished. See [format boundary and evidence](research/collision.md).


Internal0.2.4: typed material/texture dependency packing and stock-folder native geometry retargeting implemented.61Python tests and4.5Beta/5.0.1 headless operator checks pass; two real material/texture bundles pass. Shared shader closure, collision/new object insertion/addon/full-track integration remain unfinished. See [exact scope](research/dependency-packing.md).


Internal0.2.3: independent static asset ERP export and direct material dependency inventory implemented.56Python tests plus4.5Beta/5.0.1 headless checks pass; two real native families reopen under independent identities. Complete dependency closure, native world/collision/track/Swofty integration remain open. See [scope and evidence](research/independent-assets.md).


This is a source/test audit, not acceptance of the rewritten editor. No game launch, installation writes, upstream modifications or native backend execution occurred.

## Static geometry preview 0.2.2

Shared-stream complete LOD-family compilation and native LOD authoring collections implemented.54Python tests, Blender4.5Beta/5.0.1 synthetic end-to-end checks, two real native template families and one real Blender3LOD/2material deformation/export case pass. Full collision/new identities/world/package integration remain open. See [scope, exact counts and limits](research/static-writer.md).

## Static geometry preview 0.2.1

A conservative template-based Python compiler and Blender evaluated-mesh adapter now write standalone native geometry test ERPs. Two added Python tests, Blender4.5Beta/5.0.1 corner/modifier/operator tests and real-template readback pass. This is not complete geometry/terrain/collision export. See [contract, evidence and limits](research/static-writer.md).

## Native preview 0.2.0

Native-reader integration and existing-placement updates now have synthetic and bounded real-data evidence. See [exact scope, counts and limitations](NATIVE_EDITING.md). New geometry/collision/material/race export and all-mode game acceptance remain open. AGPL source and retained upstream notices are bundled; the original native backend remains excluded.

## Reproduced baseline

The distributed TrackWorkshop-0.10.1.zip contains 90 files and 37 pure-Python test methods across nine test files. Release SHA256: `09bb49ec359ff59d96f06545174b79e4afa1b8bcfac36f35df9e528aeb42dbe4`.

The audit script hashes every member and extracts only Python/JSON preparation code into ignored private build storage. Packaged runtime binaries are not extracted or executed. Comparing the release against the available Tracktool source shows differences in four release Python files: `__init__.py`, `export_build.py`, `export_contract.py`, `export_ui.py`. The active source also adds persistent-ID/profile work. Do not reconstruct 0.10.1 from that WIP indiscriminately. Reconstructing the exact bundled native backend source remains a separate provenance task.

| Check run in this audit | Result | Limit |
|---|---|---|
| 0.10.1 Python tests | 37 passed | AC/source/geometry-policy/export-contract tests, not Blender UI or native generation |
| TrackView tests | 38 passed | Readers, geometry/material/export/addon guards; not Blender importer acceptance |
| Camera-tool tests | 27 passed | Includes a local Spa graph fixture; test assets are not public distribution content |
| 0.10.1 registration twice, Blender 4.5.0 Beta | Passed | Background only; workspace/world/handler state restored |
| 0.10.1 registration twice, Blender 5.0.1 | Passed | Same scope; no native backend or real track import |

The installed 4.5 executable identifies as Beta, so this is NOT a stable Blender 4.5 acceptance result. Future release testing must use supported stable builds. Historical native/export/interactive reports remain historical; none were rerun here.

## Reuse map

Paths below identify inspected components in the supplied source projects; filenames alone do not imply complete functionality.

| Requirement | Source/component | Decision and integration seam |
|---|---|---|
| Workspace/context/import | TrackWorkshop `workflow.py`, `workspace.py`, `jobs.py`, `ui_cache.py`, `source.py`, `kn5.py`, `importer.py` | REUSE stable baseline; add editor facade and Blender 4.5 floor |
| Collections/assignment | `collection_layout.py`, `collection_ui.py`, `assets.py` | MODIFY both copy_asset assignment and automatic terrain; preserve sharing and world transforms |
| Physical surfaces/routes/rules/timing | `surfaces.py`, `surface_ui.py`, `routes.py`, `rules.py`, `timing.py`, geometry helpers | REUSE authoring; add native input/output adapters |
| Project/checks | `diagnostics.py`, `markers.py`, `marker_ui.py` | MODIFY for portable dependencies, stable identities and new systems |
| Native readers | TrackView `scene.py`, `geometry.py`, `materials.py`, `storage.py`, `addons.py`, `formats/erp.py`, `formats/pkg.py` | ADAPT a file/model library without browser/server dependency; preserve original placement separately from render-local transform |
| Native geometry output | Tracktool `EgoBlenderStaticAssetBuilder`, `EgoBlenderMappedStaticCompiler`, `EgoBlenderCollisionCompiler`, `EgoBlenderRaceCompiler` | EXTEND existing C# writers through an explicit worker contract; production/native coverage still needs validation |
| World integration | `EgoBlenderCommonWorldBuilder`, `EgoBlenderReplacementWorldBuilder`, `EgoBlenderRaceBindingBuilder` | ADAPT graph/variant assembly; do not infer public V1 from small structural ZIP |
| Facility previews | `EgoTrackFacilityCatalog`, `EgoBlenderFacilityLayerBuilder`, `EgoBlenderFacilityDependencies` plus native model reader | BUILD Blender assembly previews on existing native catalog/placement support |
| Template library | Tracktool `Tools/F1ShaderTemplates` | ADAPT existing catalog/builders/static nodes, not start from scratch; add requested card UI and native export contracts |
| Vehicle defaults | `EgoTrackCategoryProfiles` | REUSE coherent five-family vehicle/season selection; extend validated categories |
| AI/performance | `EgoTrackDifficultyWriter`, `EgoTrackVirtualTimesCompiler`, selector/domain readers | RESEARCH missing calibration/state binding; retain scoped numerical invariants |
| Environment/lights | `EgoBlenderEnvironmentBuilder`, `EgoTrackLightingMigrationService` | ADAPT coherent bundles; author-light mapping and spatial data remain gaps |
| Cameras | F1 Track Cameras `f1_track_cameras` | ADAPT existing typed fields, spline and graph edits; compressed/general animation limitations remain |
| Audio/crowd/marshal/triggers | `EgoTrackCommonSceneCatalog`, `EgoBlenderCommonSceneBindingBuilder`, `EgoBlenderCommonEventGraphPlan`, `EgoNativeCrowdPlacement`, `EgoEventGraphConnections` | EXTEND partial capture/remapping into real editors; preservation alone insufficient |
| Animation | `EgoNativeAnimationClip`, `EgoCharacterPackedAnimation`, `EgoCharacterAnimationGlbExporter` | RESEARCH type-specific reuse; a character GLB exporter is not native authoring/baking support |
| Metadata/package | Simplified Track Manager `TrackZip`, `TrackSettings`, `TrackTuning`, `TrackPictures`, `TrackErs`, `AddonBuilder`, `TrackRecode`; Swofty schemas | ADAPT contracts/logic with notices; preserve unsupported addon operations, avoid unsafe overwrites/equal-length rename assumptions |

## Important corrections and hazards

1. **Materials are more advanced than the initial gap matrix suggested.** Existing F1ShaderTemplates tooling describes 237 material examples and 48 node groups, an asset-library builder and static shader approximations. These are prior artifact/document counts, not newly reproduced. Its inspected panel has build/prepare/category controls, not the requested thumbnail-card browser. Templates are explicitly not all native-export/game-ready. Keep game-derived catalog/payloads out of public source.
2. **Seven profiles already appear in facility/event code:** F1, MyTeam, F2, Classic, F1 26, MyTeam 26, F2 26. The agreed six visible year/category branches need a canonical mapping including Classic, rather than treating Classic as unsupported. Native keys/datasets must be mapped explicitly.
3. **Facility builder assumptions are narrower than game variety.** It requires five groups, while prior research reports Miami lacks a PIT_BUILDING group. Fixed group counts are not a universal game rule. Some crowd placements are explicitly deferred in that builder.
4. **Common event support exists but is partial.** The planner remaps pit references and returns required non-pit objects; it does not create all required objects merely by planning. The binding builder requires reviewed placements and source graph identity. Build a typed reference model; never drop trigger links to satisfy validation.
5. **Source-preservation requires export provenance.** Current TrackView display matrices combine placement and render hierarchy; editing that combined matrix directly into a WorldObject would double transforms. Record layer URI, instance identity, original world transform, render-local transform and dependency origin.
6. **Native environment builder is scoped.** Hard-coded layer naming/global probe signatures need a catalog-driven resolver; do not blanket-rename or carry local probes onto different geometry.
7. **No single coordinate transform for every object.** Retain the camera-local axes correction; distinguish object placements, camera optics, points, normals and animation channels. Convert once at explicit boundaries.

## Dependency and publication audit

- Python/Blender: native bpy/mathutils; baseline pure helpers use standard-library modules. TrackView uses Pillow and NumPy; Zstandard needs a distributable/available codec. Blender dependency packaging must be tested, not assumed from workstation packages.
- Native backend: .NET 9 executable references Engine -> Core and vendored EgoEngineLibrary (net8.0). Inspected central packages include BCnEncoder.Net 2.1.0, CommunityToolkit.Diagnostics/Mvvm 8.4.0, LZ4 1.3.8, Newtonsoft.Json 13.0.4, SharpGLTF.Toolkit 1.0.5, ImageSharp 2.1.9, System.IO.Packaging 10.0.1 and ZstdSharp.Port 0.8.6. These are inventory, not dependency-upgrade or security recommendations.
- Historical broad Verification/TrackScene build fails against narrowed source; do not import the whole AlterEgo application to make it pass. Use focused harnesses and port relevant tests.
- TrackView identifies AGPL-3.0-or-later; Swofty carries AGPL notices. Local camera project and vendored EgoEngineLibrary carry MIT notices. Simplified Suite root license retrieved previously is GPLv3 text. Dependency-specific licenses still need recording before source integration.
- No top-level LICENSE/COPYING file was found in the inspected Tracktool root listing. Treat permission/notice closure for reused TrackWorkshop/Engine source as unresolved distribution metadata, not authority to strip notices. Public audit/docs/tools here are newly authored; upstream code and native binaries are not uploaded as part of this audit.

## Outcome

The immediate implementation gate is baseline/source provenance plus project identity/collection semantics. Geometry/world integration, AI calibration and secondary-system authoring are substantial V1 tasks with existing partial foundations. Nothing in this audit justifies reducing the agreed public scope.
