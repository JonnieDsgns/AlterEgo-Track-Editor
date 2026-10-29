# Independent static assets - preview 0.2.3

Latest0.2.4 adds [dependency packing and native track copies](dependency-packing.md); the0.2.3 behavior below is historical.

30 October 2026. Asset authoring milestone; not a complete track exporter.

## Workflow

Select an imported native mesh, use Advanced Files > Load Geometry LODs, edit the companion meshes, then Export Independent Asset. Enter a lowercase asset name using digits/underscores as needed. The file chooser uses an ERP filename; independent mode creates a new folder with that filename's stem containing asset.erp and asset.json. Existing folders are rejected. Ordinary geometry test mode remains available.

The new ERP contains only the renamed complete mesh/model/render/buffer family and its copied material context. It keeps the original native material paths as external dependencies, listed in asset.json with catalog availability. This is a direct dependency inventory, not a complete shader/texture closure. It does not install, mount a world object, generate collision, or create a track/Swofty package. Main Native Update remains placement-only.

## Format handling

Reference relocation follows the owned Engine ErpResourceReferenceRewriter and EgoBlenderStaticAssetBuilder source contracts, inspected read-only. Mesh vertex/index URI pools and model LOD URI pools are rebuilt structurally. Material names, graph names, opaque tails and native bindings are preserved. All known moved mesh region offsets, including the draw table, are adjusted. No arbitrary replacement of bytes in opaque resources occurs.

Opaque extra mesh records are not relocated. Such templates require equal-length identities; the Blender exporter deterministically pads shorter names with a hash suffix and rejects names that cannot fit. This leaves every opaque record address unchanged. Templates without extras support variable-length identities. Original graph names remain descriptive names, not renamed resource references.

New ERPs retain the source model archive header/version, resource kinds/unknown fields and fragment flags/names, store payloads uncompressed and recompute resource digests. Publication follows reparse, full-family decode and byte-for-byte fragment checks. Output folders are created exclusively; no source archive is modified.

## Verification

56 Python tests pass (19 project +37 retained baseline). New tests cover variable-length relocation, correct draw offsets, model LOD pools, independent identities, context/dependency retention, opaque data, source hashes, overwrite/traversal guards and equal-length opaque-record handling. Headless Blender4.5.0Beta/5.0.1 actual independent export passed after native LOD editing and save/reopen. Stable4.5 and full interactive verification remain unperformed.

Two read-only Monaco template cases passed: armco_monaco_main_a (3LODs,1material per LOD) and armco_monaco_white_b (3LODs,2materials per LOD). Authored quad families were emitted under independent names and reopened without donor mesh/model resource identities. All direct material paths were available in the selected catalog. Source game assets and local test outputs are excluded from publication.

No game loading/gameplay acceptance is claimed. No game launch, installation write or native backend execution occurred.

## Remaining work

Complete material/shader/texture dependency closure and permissions-aware packing, stable project asset catalog, transactional integration with native track outputs, new world object insertion, collision/terrain and race systems remain open. Independent asset ERP output is not a fully race-ready addon track.
