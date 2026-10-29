# Dependency packing and native geometry copies - preview0.2.4

30 October 2026. Experimental asset/track editing; not release-ready V1.

## Independent assets

Export Independent Asset now offers Bundle materials and textures. Its planner reads primary and secondary material texture paths, including texture-valued usage2/type6 inputs, follows GfxSRVResource views to GfxSurfaceRes surfaces and discovers external mip files. Supported material/view/surface resources are copied byte-for-byte; the native URIs and material contexts stay unchanged. External mip files retain complete contents, native relative paths, recorded lengths and SHA256 hashes. Addon mappings take precedence over game roots; missing/ambiguous files, unsafe paths, unsupported structures or resource conflicts stop bundling before publication.

The output contains asset.erp, asset.json and optional mips/ files. Staged dependency readback uses only the new ERP and copied mip root. Shared native shader packages remain explicit external requirements: their transitive binary dependency schema is unverified. dependency_graph_complete and dependency_closure_complete remain false whenever this boundary is present. This is not a fully self-contained package. Inventory-only exports remain available without bundling.

## Native track copy integration

In the same export dialog, Write a native track copy embeds the independent geometry family and copied binding context in the edited layer's archive(s), then retargets the selected existing Model.model and Model.mat binding string fields. It preserves the WorldObject matrix, original identities/variants, opaque resources, original source assets and other systems. The result is a separate complete folder copy. All inserted fragments and changed layer bytes are checked before publication. Conflicting existing resources abort the export. Existing field presence and native archive targets are required.

This mode currently accepts native track folders only, not addon packages/loose operation targeting. It retains original material/texture dependencies and disables bundle mode; bundled independent assets remain a separate workflow. Collision is preserved rather than regenerated, and new world object insertion/race systems are not implemented. It is unsuitable as proof of a complete race-ready conversion. The original Native Update operator retains its placement-only behavior.

## Checks

61Python tests pass (24project +37baseline). New dependency tests cover primary/secondary/type6 edges, shared-resource deduplication, exact material/resident texture/external mip bytes, checksums, missing files, safe paths and no partial output. Native copy tests cover model/context retargeting, geometry readback, preserved matrices/opaque data/mips/source hashes and conflicting-resource rollback.

Headless Blender4.5.0Beta and5.0.1 pass the actual bundled-export and native-copy operators after LOD editing and save/reopen. Stable4.5 and full interactive checks remain unperformed. Real read-only Monaco dependency bundles passed: main_a (3LODs,7material/view/surface resources,3mip files) and white_b (3LODs,14resources,6mip files). Each retains one external native shader. Staged readback succeeds using only copied texture data. A separate real-source leaf check confirms both model/binding fields are typed stri; whole real-track copy/game behavior is not claimed.

No game launch, installation write, native backend invocation or game-derived asset publication occurred. Public source/tests use synthetic fixtures only. Local bundled game assets are excluded from GitHub.

## Next

Collision/terrain writing, addon/native resource targeting beyond stock folders, new object insertion, stable asset catalog and full track/race-system/Swofty integration remain open. Shader binary dependency closure remains unverified.
