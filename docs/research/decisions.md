# Track Workshop rewrite — agreed product decisions

Updated: 2026-10-29. Brainstorm requirements, not implementation claims.

## Product and release

Blender add-on based on Track Workshop 0.10.1; retain good AC import/conversion, dedicated workspace, collection layout and existing authoring tools. All projects support all variants; public V1 is release-ready for complete race-ready tracks across all game modes. Internal milestones may be incomplete but must not redefine public V1. Existing format/research gaps remain acceptance work, not waived requirements.

## Workflows

- Update existing F1/addon tracks, retaining identity by default for addon imports and exporting original native format/structure.
- Create separate variants as Swofty tracks.
- Convert AC tracks to Swofty tracks; first primary workflow.
- Build fully custom Blender tracks, including geometry from other tools, as Swofty tracks.
- Full export and changes-only update addon export, with base identity/version and dependency validation.

## Authoring

Retain 0.10.1 collection roles/layout. Asset assignment moves objects without copying; duplication explicit. Shared Common content plus editable variant differences; assisted setup and per-variant checks, no silent substitution. Geometry/topology editing, materials, surfaces, collision, routes, limits, grid/pits/facilities, timing and markers. Guided generation and individual editing; import native existing data or convert available AC inputs.

Curated F1 material templates with thumbnail grid, categories/search, Apply to objects/faces, editable instances and guided properties. Game-file extraction or GitHub packs with appropriate redistribution provenance. Visual and physical surfaces separate.

Identity, credits, artwork, generated maps with manual adjustment, integrated camera tooling, custom native-supported Blender light placement. Other lighting from coherent donor/template bundles. Donor policy research and category-response correction in donor-policy.md.

Audio, crowds, marshals, animated objects and event triggers explicitly included in V1 by user. Exact per-domain editable operations and supported native formats require specification/audit; inclusion must not be silently reduced to opaque preservation alone. Generic arbitrary audio synthesis, universal animation baking or unrestricted scripting were not separately promised.

## Project defaults accepted

Windows first; explicit tested Blender version range still to be selected. .blend editable project plus companion assets/textures/build-report folder. Pack Project collects required dependencies for reopening without original source paths; keep license/redistribution constraints and source provenance. Supported content editable, unsupported native resources preserved and reported. Preserve shared meshes/materials with explicit Make Unique. Record base track/version and detect changed sources before update export. Concrete all-variant/all-mode release checklist with user-run game tests.

Checks support actionable findings, object selection, stale status, structurally valid incomplete test exports and stricter release exports. Offline structural checks, installation acceptance and real game verification remain separate statuses. Agent does not launch game or write installation.

## Deferred

Source comparison and curve placement for barriers/sponsor boards are post-V1 possibilities. No automatic source geometry duplicates for comparison.

## Documentation next

Capability specification; 0.10.1 baseline/gap matrix; development/acceptance plan. Still settle exact Blender version range, requirements for each secondary-system editor and mode acceptance coverage. UI layout, preset catalogue, visual styling and name can evolve during implementation. See baseline-comparison.md and source-review.md for inspected evidence and boundaries.

## Accepted facility placement previews

Use actual supported native 3D models for visual placement of garages, pit walls, pit equipment and related facilities, with correct scale/orientation/origins and complete assemblies where appropriate. Existing tracks use their own assets; new tracks use compatible curated templates sourced from user game files or available properly licensed packs. Show functional spawn/stop positions alongside geometry, known clearance overlays, likely overlap warnings requiring review, and preview visibility controls. Separate reference-preview geometry from exported resources to prevent duplication. Preview assists placement but does not alone certify functional or collision clearance.

Blender version decision: minimum Blender 4.5; target 4.5 and later. Each release records tested versions; future versions require compatibility verification. Supersedes earlier unselected version range.
