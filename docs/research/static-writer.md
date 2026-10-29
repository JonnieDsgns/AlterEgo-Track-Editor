# Static geometry compiler — internal 0.2.1

## Source basis

The owned AlterEgo Engine sources EgoBlenderStaticAssetBuilder, EgoIdfGlbPositionImporter and EgoIdfImportProfiles define the conservative template-based static topology contract. This implementation adapts that contract into Python using the already bundled readers; no C# backend binary is loaded. Source files were inspected read-only. Their hashes are recorded alongside this document. The compiler is project code under AGPL-3.0-or-later.

Verified source fields: mesh header 76 bytes; submesh 88 bytes; stream declarations/bindings use header-relative pools; draw records 16 bytes. The single complete draw retains its flag and submesh identity. POSITION uses float3/39, other half streams use half4/35, colours use RGBA bytes/14, UInt16 indices use format19. Buffer headers retain resource type and update element count. Model header is 64 bytes with an 8-byte-per-LOD table; sphere/AABB fields start at16/36/48. Render-local transforms affect model bounds. Unknown fields/tails, render graph, material slots and unrelated ERP resources are preserved.

## Delivered scope

StaticTemplate validates a direct LOD-0 family with one submesh, one complete draw, one LOD and supported separate streams. It rejects shared buffers referenced by another mesh/LOD, unsupported semantics/layouts and unresolved render graphs. Model node/bone-count fields are preserved; their nonzero values alone do not establish skinning. The accepted vertex declarations exclude skinning weights/indices.

StaticInput supplies explicit positions, indices and every required normal/tangent/UV/colour attribute. The compiler rebuilds stream payloads/counts, submesh ranges/sphere, draw ranges and model bounds. Vertices split at authored corner attribute seams. The Blender adapter evaluates modifiers without applying them to the source mesh, exports local coordinates and preserves native axes. Two Blender UV layers represent the two pairs in each native half4 UV stream. Missing pairs are rejected, not synthesized. Static normals/tangents and native numeric ranges are checked.

Export Selected Geometry Test lives under Project Settings > Advanced Files for imported native mesh objects. It writes a separate full ERP test copy retaining the original family and native material bindings. It does not insert a new family or combine geometry with placement updates. A template shared by multiple placed instances still has one native geometry identity. The main Native Update export continues to reject mesh edits.

## Reproduced evidence

- Two Python regression tests: authored topology, all supported attributes, transformed model bounds, opaque tails/resources and source hashes; invalid indices/numeric values/normals/tangents/UVs/degenerate triangles/profiles and overwrite guards.
- Headless Blender4.5.0Beta and5.0.1: evaluated triangulation, a deliberate per-corner UV seam (4source vertices ->5native vertices), colours, unchanged source mesh/modifier, native readback and missing-UV rejection. Actual operator succeeds on an imported synthetic project.
- Real Monaco scan: first supported template after62candidates was rickety_fence_a;22multi-LOD and39multi-submesh candidates rejected. Authored quad wrote/reopened4vertices/2triangles and12changed fragments. No game-derived fixture or output is committed.

This is offline structural evidence, not game acceptance. No game launch, installation write or native runtime invocation occurred.

## Next work

Multi-submesh/material and complete LOD-family construction; independent resource identities and references; terrain/collision spatial writers; native materials; world mounting and variant composition; complete AC/custom track export and user-run all-mode acceptance. Existing placement export remains a separate path until transactional resource planning supports these new fragments.
