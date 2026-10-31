# Development backlog

Internal 0.3.3: new placements receive precomputed-visibility entries (source bits copied; bit index = object id measured on stock tracks) and shared baked-lighting rectangles by default; DRS/Straight Mode edits warn outside the measured stock envelope (no warnings on any unedited track). Formats first described by the GPL-3.0 F1MapEditor toolkit, implemented and checked independently. 53 Python tests and Blender 4.5.0 Beta/5.0.1 checks pass. In-game effect untested. See [visibility and lighting](research/visibility-lighting.md).

Internal 0.3.2 (terrain preview fix, user-reported): native terrain previews stopped at the first draw Blender would have to repair (degenerate or duplicate triangles), leaving large holes. A read-only survey found this in the main terrain of every installed track (for example Spa kept 173 of 2,898 draws, Bahrain 41 of 1,995). Previews now omit only those triangles (reported per record), isolate each draw's errors, and decode half-float RGBA vertex colours (nine terrain resources). Spa now imports 2,898/2,898 and Zandvoort 4,284/4,284; Losail keeps 4 of 2,799 draws as reported warnings (byte-format UV channel). Earlier real-track tests sampled at most two terrain draws, so they could not catch this. Export never used these preview meshes.

Internal 0.3.1: experimental whole-track legacy collision rebuild (native, edited preview and authored collision; base track codes only) following the layout of two community Istanbul ports reported playable in F1 25. Builder now writes the stock name-table header word. Real Monaco/Spa/Bahrain rebuilds read back exactly; 88 Python tests and Blender 4.5.0 Beta/5.0.1 checks pass. Not verified in-game for any stock track. See [collision](research/collision.md). B10 gains a usable (experimental) collision path for new/edited geometry; modern 0x20004 generation stays RESEARCH.

Internal 0.3.0: native routes (main/pit splines, AI racing line and limits) load as previews, and gameplay track markup intervals (sectors, DRS, ERS, X-Mode, speed trap, pit limiter, pit/start zones) can be edited and exported. New byte-exact binary XML codec verified on 1,081 resources across 28 tracks; 85 Python tests and Blender 4.5.0 Beta/5.0.1 checks pass. Route geometry and AI timing remain preview-only. See [routes and markup](research/routes-markup.md). B14 gains native route import and markup editing; geometry/timing regeneration stays RESEARCH.

Internal 0.2.9: Add Next Race Placement extends grid slots, pit boxes, pit garages and F1 garages with per-world contiguous numbering and garage-to-pit-garage links, following Swofty Custom Grid Size rules and real Monaco/Bahrain data. 80 Python tests and Blender 4.5.0 Beta/5.0.1 checks pass. Database grid size and AI pit data are not changed; not game-verified. See [race placements](research/race-placements.md). B14 gains its first functional-placement editor.

Internal 0.2.8: static props can be deleted (whole-layer exports; functional, referenced and, unless explicitly allowed, PVS-listed props refused) and existing props can use an edited asset (Use Edited Asset for Selected). 77 Python tests and Blender 4.5.0 Beta/5.0.1 headless checks pass; real Monaco/Spa deletions match Swofty's serializer. Not game-verified. See [insertion scope](research/native-insertion.md). GEO-01 (place, transform, duplicate, delete, replace) now has a static-prop implementation. Blocked: changes-only updates for addon-based tracks need launcher-resolved archive targets (slot vs natural route).

Internal 0.2.7: edited native LOD families can be placed as new objects (Place Edited Asset) and exported with the main track update: families embedded beside their layer in full exports, or shipped as `copy-resource` ops plus layer edits in Swofty update addons. 74 Python tests, Blender 4.5.0 Beta/5.0.1 headless checks and a real Monaco 3-LOD placement pass. Visual only; not game-verified. See [insertion scope](research/native-insertion.md). Next: functional object editors (grid/garages/pit boxes), addon-base targeting and collision for new geometry.

Internal 0.2.6: explicit static-prop duplication as new native placements and composable Swofty `patch-pkg` layer edits implemented. The canonical layer writer reproduces 511/511 real layers across six tracks byte-for-byte; 71 Python tests, Blender 4.5.0 Beta/5.0.1 headless checks and five real-track insertion checks pass. New placements are visual only (no collision, PVS or lightmap data). See [scope and evidence](research/native-insertion.md). B09 now covers same-layer insertion of eligible static props; B21 gains composable changes-only edits for stock sources. Next: placing independent/new assets as instances, addon-base targeting, functional object editors and collision for inserted geometry.


Internal0.2.5: native collision preview/surface-only export and explicit legacy collision construction tests implemented.66Python tests,4.5Beta/5.0.1 headless checks, six real native resources and independent managed-reader validation pass. Native0x20004 topology and visual terrain writing are still unfinished. See [format boundary and evidence](research/collision.md).


Internal0.2.4: typed material/texture dependency packing and stock-folder native geometry retargeting implemented.61Python tests and4.5Beta/5.0.1 headless operator checks pass; two real material/texture bundles pass. Shared shader closure, collision/new object insertion/addon/full-track integration remain unfinished. See [exact scope](research/dependency-packing.md).


Internal0.2.3: independent static asset ERP export and direct material dependency inventory implemented.56Python tests plus4.5Beta/5.0.1 headless checks pass; two real native families reopen under independent identities. Complete dependency closure, native world/collision/track/Swofty integration remain open. See [scope and evidence](research/independent-assets.md).


Internal 0.2.2: B10 static compiler now handles multiple existing material submeshes and complete supported LOD families/shared streams. Native LOD loading, per-level preview and companion editing are implemented. Terrain/collision/new identities/world/package integration remain open. See [scope and checks](research/static-writer.md).

Internal 0.2.1: B10 now has an isolated single-submesh/single-LOD static topology compiler and Blender test export; full geometry/terrain/collision acceptance remains open. See [writer scope](research/static-writer.md).

Internal 0.2.0 progress: B05 registry/import mapping, B07 reader packaging and B08 native previews implemented; B09 existing matrix updates only; B11 thumbnail library and B13 facility references partial. Full authoring/game acceptance remains open. See [scope and verification](NATIVE_EDITING.md).



29 October 2026 • All tasks refer to public V1 unless explicitly deferred. Status: READY means enough evidence to start, not completed. Acceptance IDs refer to ACCEPTANCE.md.



| ID | Task / action | Depends on | Completion evidence | Status |

|---|---|---|---|---|

| B01 | Establish licensed 0.10.1 source and exact backend provenance; port test inventory | Audit | Source manifest/notices, reproducible narrow build, baseline regressions | READY; native provenance open |

| B02 | Add-on package/registration for Blender 4.5+ | B01 | Stable 4.5 and supported newer registration/cleanup; A01 | READY |

| B03 | Project schema, stable IDs, source identity, companion storage | B02 | Save/reopen, missing/changed sources, duplicate-ID handling; A17/A19 | READY |

| B04 | Move-only asset assignment and auto terrain | B02/B03 | No copies; hierarchy/sharing/world pose/undo regressions; A03/A05 | READY |

| B05 | Role classification and all-native-variant registry including Classic | B03 | Native world/dataset mapping, conflict cases; A04/A11 | NEEDS MAPPING |

| B06 | Workspace facade, context tools, progress/cancel and stale findings | B02/B03 | No redraw scans; baseline behaviours; A18/A20 | READY |

| B07 | File-format library boundary and dependency packaging | B01/B02 | No browser/runtime-source dependency; codec bounds and clean-machine imports | READY |

| B08 | Native F1/addon scene import with editable provenance | B03/B05/B07 | Mesh sharing/material slots/placement vs local transforms; A06/A08 | ADAPT |

| B09 | Lossless native update and changed-resource planning | B08 | No-op identity, changed layer readback, opaque data retention; A06/A16 | ADAPT/BUILD |

| B10 | Geometry/terrain/collision writers at full-track scale | B05/B07 | Authored geometry readback, surfaces, spatial structures; A07/A20 | RESEARCH/EXTEND |

| B11 | Material library catalog, pack setup and thumbnail browser | B03/B07 | Local/pack setup, face/object Apply and Make Unique; A09 | ADAPT |

| B12 | Native material/texture and terrain-layer export | B10/B11 | Shader-specific channel/UV/alpha/encoding checks; A07/A09 | RESEARCH/EXTEND |

| B13 | Facility assemblies and placement UI | B05/B08 | Actual models/origins, marker alignment, known clearance tests; A10 | ADAPT/BUILD |

| B14 | Routes, limits, timing and functional facilities | B05/B10/B13 | Import/convert/generate/edit round trip, graph closure; A08/A11 | EXTEND |

| B15 | Vehicle category response coverage | B05/B07 | Per-vehicle/season hashes, differences, missing category handling; A12 | ADAPT/RESEARCH |

| B16 | Track-specific AI/performance calibration | B14/B15 | Selector/domain accuracy; held-out native comparisons and user-run tests; A12 | RESEARCH |

| B17 | Environment recipes and authored lights | B05/B07/B10 | Coherent dependency closure, spatial validity, supported-light readback; A13 | RESEARCH/EXTEND |

| B18 | Integrated camera authoring | B03/B07/B08 | Camera-local axes, typed fields, spline/event edits and limits; A13 | ADAPT |

| B19 | Audio/crowd/marshal/animation/event editors | B05/B08/B13/B14 | Typed capability catalog, creation/editing/export for each; A14 | RESEARCH/EXTEND |

| B20 | Identity, tuning, artwork and generated maps | B03/B05/B11/B14 | Dataset applicability, names, image dimensions/map placement; A15 | ADAPT |

| B21 | Complete and changes-only Swofty export | B09/B14/B17/B19/B20 | Resource closure, base/version/order/conflicts and staged publication; A15/A16 | BUILD |

| B22 | Pack Project and dependency manifest | B03/B07/B11 | Reopen relocated packed project; exclusions explained; A17 | BUILD |

| B23 | Test/release readiness and mode matrix | B05/B06/B14/B16/B19/B21 | No false verification, scoped checks, all release blockers explicit; A18 | BUILD |

| B24 | V1 user-run game acceptance and distribution | B01–B23 | All applicable acceptance/mode cells PASS, clean licensed distribution; A01–A21 | NOT READY |



## First implementation batch



B01–B04 and B06: baseline module package, project state and move-only assignment. In parallel in the development schedule, resolve B05/B07 before downstream integration; no extra agents or separate repos are required. Native import provenance (B08/B09) establishes safe update writing early. AC conversion is the first complete workflow to integrate, while all other required workflows remain public V1 gates.



## Detailed test requirements for move-only assignment



Source-linked objects, automatically prepared terrain, existing export objects, parented children, nonuniform/mirrored transforms, shared mesh/material users, multiple project collections, unrelated collection links, undo/redo and save/reload. Verify that hierarchy changes do not alter world placement; reject ambiguous role assignments. Retain distinct functional marker generation, which is not the same as copying visual mesh assets.



## Deferred



D01 source comparison. D02 barriers/sponsor boards along curves. Neither may block V1 unless explicitly brought back into scope by the owner.



## Foundation batch status — 29 October 2026



See FOUNDATION.md. B02/B04 implementation and synthetic verification complete on available builds; stable4.5/UI acceptance remains. B03 implements basic project/source/companion state; portable packing remains B22. B01 pins Python source and dependencies; exact native backend source provenance remains pending before backend integration. B06 retains/adapts baseline workspace; broader facade remains incremental. No public V1 completion claim.

