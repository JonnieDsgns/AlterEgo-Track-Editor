# Development backlog



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

