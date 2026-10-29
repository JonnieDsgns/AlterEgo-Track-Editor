# Track editor plan versus Track Workshop 0.10.1

Date: 2026-10-29. Brainstorm comparison; planned capabilities are not implemented claims.

## Baseline and method

Read the actual distributed F1-Tracktool/releases/TrackWorkshop-0.10.1.zip without executing or extracting it. SHA256: 09bb49ec359ff59d96f06545174b79e4afa1b8bcfac36f35df9e528aeb42dbe4. External root is recorded in source-review.md. Inspected ZIP operator inventories, assets.py and component identities; cross-referenced external README and source. Active 0.11.0 is not substituted for the baseline. No fresh Blender/game verification performed.

## Comparison

| Area | 0.10.1 baseline | Agreed direction |
|---|---|---|
| Blender workspace | Dedicated optional workspace already exists; explicit Open Workspace, Solid/Materials modes, HDRI preferences | Retain and make this the primary authoring experience; final panel arrangement remains design work |
| Task/context UI | Project, Geometry, Track, Materials, Checks plus export controls; project selection/pinning and relevant panels | Retain and extend for native tracks, material library and production export |
| AC import | Track/layout discovery, KN5 import, source hierarchy/material metadata, surfaces/markers and line preparation | Keep as baseline, including its good conversion workflow |
| Collections | AC Import; F1 Export/Track Markup; Common terrain/objects/facilities/vegetation; 2025/2026 F1/MyTeam/F2 branches | Keep layout and semantic roles; avoid classification by mutable display names |
| Asset assignment | copy_asset duplicates object, mesh and materials for imported assets; existing prepared assets are moved | Change assignment to MOVE existing objects, with explicit duplication only |
| Automatic terrain | prepare_terrain creates F1 copies from eligible source meshes | Must also reconcile with no-copy rule; fixing only manual assignment is insufficient |
| Roles | Tagged project/collection roles and tw_export_target; export planning checks memberships/conflicts | Keep role-based export. New requirement: direct Blender collection moves must update role or report stale/conflicting assignments |
| Source comparison | AC Source / F1 Preparation / Compare visibility modes assume separate branches | Adapt for moved assets; do not promise untouched full-source comparison without an explicit snapshot |
| Physical surfaces | Assignment, collision participation, restore suggestions and selected-object tools | Retain; separate physical surfaces from visual templates |
| Geometry | Normal Blender geometry authoring and F1 preparation; bounded native test writer | Add native existing-track round trip, topology changes, mesh replacement and dependency-preserving export |
| Racing/pit lines | Import AC lines, selected curve authoring, widths, order, generated road edges/pit connections and checks | Retain; add native F1/addon import/export and complete race-system integration |
| Limits/pit rules/timing | Authored limits from edges, review state, pit position tools and timing/sector checks | Retain; native conversion/export and integration still require acceptance |
| Markers/facilities | Imported/authored marker tools and organised collections | Retain; extend native facilities and guided generators where useful; complete game-mode support is a target |
| Materials | AC source capture and limited F1 terrain/opaque/cutout export contracts | Add curated F1 template cards with preview images, categories/search, Apply, editable instances and guided controls |
| Template assets | No curated game-extracted thumbnail library identified | Game-file setup plus GitHub pack source; track provenance/version/dependencies and redistribution permission |
| Validation | Central errors/warnings/review, scope filters, selection/framing; stale reports and explicit checks | Retain; add structurally-valid test export and stricter release checks with readiness report |
| Export | Check Export and Build Native Test ZIP; limited geometry/material/collision structural output; false game_verified/track_export_ready flags | Add original-format/structure updates, separate variants and Swofty packages; complete race-ready track export is substantial unfinished work |
| Identity/metadata | Imola-first test profile and basic author/build settings | User chooses update vs separate identity; imported addon defaults to same identity; full metadata/artwork/minimap/tuning |
| Modes | Collection branches prepare variants; no full authored track acceptance | Finished goal: race-ready circuits for all modes; requires explicit mode-by-mode validation matrix |
| Curve placement | No barrier/sponsor-board generator identified in inspected baseline | Desired after V1; not a V1 commitment |

## Important consequences

Preserve source names, provenance, shared meshes/materials and hierarchy when moving objects. Source parents can affect moved children; export must preserve evaluated transforms without silently modifying unrelated objects. Collection relinking alone does not create native world references or serialize a new object. Shared materials need explicit make-unique operations when users want independent edits.

Keep 0.10.1 behaviour as the default baseline except agreed changes. Do not accidentally inherit interrupted 0.11.0 contracts or claim existing preparation tools already produce race-ready native data. The dedicated workspace is inherited, not newly invented.

## Pending design details

How to present source/F1 comparison after move-only assignment; handling multiple export-role memberships and shared assets; material template pack provenance; exact mode readiness matrix; scope/order of first-release native import, edit and export acceptance. These remain discussion items rather than blockers to brainstorming.

## Decision — source comparison deferred

User explicitly confirmed source comparison is unnecessary for now and may be added later. Exclude AC Source / F1 Preparation / Compare comparison workflow from V1 requirements. Keep collection layout and move-only assignment; no automatic source geometry copies or comparison reimport feature required. Retain provenance for asset resolution and round-trip export. Ordinary collection visibility remains available. This resolves the source-comparison pending design item above.

## Decision — release-ready V1 and mandatory variants

All projects must support all variants represented by the retained collection layout; V1 must target all of them as a release-ready add-on, not an F1-2025-only preview. Finished scope includes race-ready circuits across game modes. Smaller internal development milestones do not reduce public V1 requirements. Source comparison and curve barrier/sponsor placement remain deferred.

User accepted shared Common content with editable variant-specific differences, assisted generation of required elements such as grids/pit facilities and validation of every variant. Missing required elements must be reported instead of silently substituting another variant setup. Shared content need not be duplicated per variant. User's recollection that the game behaves similarly is context, not independently verified game behaviour or proof of exact native composition rules.

## Decision — changes-only update addons

User accepts changes-only update export if Swofty supports it. Verified current public docs/reference/ops/erp.md via GitHub connector 2026-10-29: replace-resource ships raw changed fragments, put-resource ships selected resources from a donor ERP, overlay ships resources in a small ERP, patch-pkg supports clone-entry/set-value, set-material edits constants, add-mipmaps supplies external mips. Therefore include changes-only Swofty update addon alongside full export. This is resource/fragment-level patch distribution, not arbitrary binary delta encoding. A changed layer/mesh may need the complete resource or fragment and dependency closure.

Base track/version required for update; addon-track targeting and ordering must be validated against launcher-resolved archive paths rather than assumed. Docs say missing target archives not supplied by earlier addons are skipped with warning. Runtime overlays have stock layout constraints; resized resources/removals may cause launcher-managed archive rewriting. Do not promise every changes-only addon is runtime-overlay-only or universally composable. No activation/game test performed. Source: https://github.com/Swofty-Developments/SwoftyLauncher/blob/main/docs/reference/ops/erp.md

## Decision — presentation, cameras and lighting

User accepted track identity/credits, menu artwork, generated layout/minimap images with manual adjustment, integrated native track camera editing using existing Blender tooling, and manual sponsor placement/replacement. Curve placement remains deferred.

Lighting is editable through Blender within feasible supported native capabilities: place custom lights around tracks and expose only properties with a validated export mapping. Remaining lighting/environment data comes from a donor track or supplied generic template. Do not infer a V1 requirement to author arbitrary sky/weather systems, bake native lighting/probes or translate every Blender light/node. Unsupported settings must be identified; generic templates require validated native dependency closure. This records intended scope, not proof of existing exporter capability.
