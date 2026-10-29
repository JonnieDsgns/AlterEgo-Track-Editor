# Baseline, gaps and development sequence

29 October 2026 • Companion to CAPABILITIES.md

Status labels: RETAIN = existing baseline authoring behaviour; CHANGE = agreed departure; EXTEND = useful partial implementation; NEW = no complete path identified; RESEARCH = unresolved native correctness. None indicates fresh runtime acceptance.

Baseline: actual TrackWorkshop-0.10.1.zip, SHA256 09bb49ec359ff59d96f06545174b79e4afa1b8bcfac36f35df9e528aeb42dbe4. Do not substitute interrupted 0.11.0 source. Preserve notices and audit dependencies before reuse. External AlterEgo/Tracktool trees remain reference sources; implementation belongs in this workspace.

| Capability | Status | Work required |
|---|---|---|
| AC layout/KN5 import | RETAIN | Port baseline without losing supported layouts, transforms or material metadata |
| Dedicated workspace/context panels | RETAIN | Add new workflows and retain responsive caches, progress/cancel and explicit checks |
| Collection structure | RETAIN | Canonical native variant mapping, direct-move classification and conflict handling |
| Assignment/automatic terrain copies | CHANGE | Move originals, preserve transforms/hierarchy/sharing; explicit duplication only |
| Source comparison | CHANGE | Remove from V1 workflow; retain ordinary visibility and provenance |
| Surfaces, routes, limits, timing, markers | EXTEND | Retain authoring; native import/export plus complete functional integration |
| Native track geometry import | EXTEND | Adapt TrackView readers to Blender with provenance/materials; document omitted classes |
| Native geometry/topology/collision output | RESEARCH | Extend structural writers, dependency graphs, spatial structures and production-scale validation |
| Original-format round trip | NEW | Preserve unknown resources/operations and rebuild only affected content safely |
| Material browser | NEW | Curated native templates, game extraction/pack setup, thumbnails and editable instances |
| Facilities preview/generators | EXTEND | Actual models, assemblies, markers, known clearances and all-variant wiring |
| Donor recipes | EXTEND | Reuse category profiles; validate environment/database/functions independently |
| AI and virtual performance | RESEARCH | Complete selector/state binding, track-specific calibration and all-category acceptance |
| Environment | RESEARCH | Coherent template closure, TrackInfo/probe spatial validity and custom-light export |
| Cameras | EXTEND | Integrate existing camera add-on, preserving pose/activation/animation contracts |
| Audio/crowds/marshals/animation/triggers | RESEARCH | Inventory reusable tools, define editable native types and build complete workflows |
| Track metadata/artwork/maps | EXTEND | Adapt Simplified Track Manager contracts and generation tools |
| Swofty complete/update package | NEW | Use verified schemas, dependencies, addon ordering and output staging; no installer duplication |
| Portable .blend projects | NEW | Companion storage, stable IDs, portable dependencies and Pack Project |
| Test/release checks | EXTEND | Add complete-variant checks and explicit runtime verification records |

## Research tasks that block release claims

1. Blender 4.5 and later compatibility testing, plus native game/Swofty build compatibility.
2. Full mapping between collection branches, world resources, vehicle categories and database datasets; include every required native variant.
3. Production native geometry/terrain/collision generation and reachable world/layer graphs; structural round trip alone is insufficient.
4. AIVPChar/VPTimes calibration and selector/state mapping; per-season/category response coverage including HighDownforce. Existing five-family equality is scoped, not universal.
5. Environment dependencies and spatial TrackInfo/probe handling; generic presets require evidence.
6. Exact supported native audio, crowd, marshal, animation and trigger operations, plus user-run acceptance.
7. Changes-only targeting of generated addon archives and dependency/load-order behaviour.

## Internal implementation sequence

These are internal acceptance milestones, not reduced public releases. Work on independent domains may overlap; dependency gates remain mandatory.

| Stage | Concrete outcome | Gate |
|---|---|---|
| M0 Baseline | Reproducible licensed source snapshot, dependency inventory and tests | 0.10.1 behaviour accounted for; compatibility targets recorded |
| M1 Project foundation | Workspace, project storage, move semantics, roles, IDs and sharing | Save/reopen/undo/pack and source-preservation checks |
| M2 Native editing | Existing track/addon import, placements and unchanged-content round trip | Reopen exported native layers and compare transforms/resources |
| M3 Assets | Geometry/collision writers, materials/templates and facility preview | Geometry/attribute/dependency checks, clipping review, native readback |
| M4 Race systems | Routes, limits, timing, facilities and all-variant composition | Complete functional graph and variant checks |
| M5 Driving data | Compatible category profiles and track-specific AI/performance | Numerical validation and independent-track/user-run tests |
| M6 Presentation | Cameras/lights/environment/maps plus secondary systems | Per-system native round trip and functional validation |
| M7 Packages | Complete original/Swofty output and changes-only updates | Reimport, portability, dependency and activation checks |
| M8 Public V1 | All required features integrated | ACCEPTANCE.md complete; no unresolved release blockers |

AC conversion is the first end-to-end authoring scenario. Native-track preservation is also tested early to establish safe writers. Reuse existing verified codecs/services; do not replace them with parallel unvalidated implementations. Keep heavy native tasks outside UI draw callbacks and bound temporary storage/cache usage.

## Deliverables before implementation begins

This product draft, baseline matrix and acceptance plan establish scope. M0 must turn historical test reports into a reproducible test inventory and identify source/license closure. Do not rerun external deployment scripts, operate prohibited editors, launch the game or alter installation. User performs game-side tests; record evidence without promoting unrelated engine knowledge.

