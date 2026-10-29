# Addon track editor reuse audit — 2026-10-29

User scope: both existing addon-track editing and new circuits, starting with existing tracks; Swofty installation. User requested inspection of AlterEgo Blender tooling.

Read-only inspected external AlterEgo root recorded in ALTEREGO_TRACK_VIEWER_REUSE.md. Found Tools/TrackWorkshop plus an extracted F1-Tracktool/ project with its own AGENTS.md and handover. Track Workshop 0.10.1 is last tested distributed baseline; extracted active 0.11.0 is interrupted WIP, not accepted release. No external files modified or tools launched.

Existing Python components cover AC KN5/layout import, collections, physical surfaces/collision assignment, markers, racing/pit lines and widths, limits, timing, materials, workspace checks and native export jobs. export_build.py invokes a private .NET backend and explicitly labels output structural_test_only, game_verified=false and track_export_ready=false. README describes small native geometry/material/collision output; world mounting, facilities, route/timing/pit/vehicle wiring and game acceptance remain incomplete. Extracted CURRENT_STATE.md corroborates boundaries and notes persistent-ID/profile WIP and obsolete fixtures.

Architecture decision for requested tool: reuse TrackView for opening/previewing existing Swofty addons and reuse validated Track Workshop/backend contracts for authoring. Do not reimplement native writers blindly or assume the AC importer imports native F1 tracks. First milestone needs native F1 placement provenance/edit/readback, project undo/save, preserved dependencies and Swofty export. New-circuit authoring follows existing WIP contract acceptance and world/race-system integration. Swofty TrackPackage requires separate track_code, ERP, activation donor and optional mip copy directories (packages/core/src/map.rs). Existing structural DatabaseEditor ZIP is not automatically a Swofty addon.

Verification this turn: source/document inspection only. No editor implemented yet, no fresh Blender/native tests or game acceptance. Original broader build request remains ongoing.

## Blender rewrite decision and upstream audit — 2026-10-29

User explicitly chose a Blender add-on: rewrite Track Workshop, support both existing addon editing and future new circuits, start with existing tracks. This supersedes a browser/standalone editor UI proposal. Reuse TrackView format code and findings behind Blender import, not its browser UI as the main editor.

### Simplified Track Manager

Inspected public main through GitHub connector on 2026-10-29:
https://github.com/TeamSimplified/simplified-suite/tree/main/Simplified%20Track%20Manager
Core tree identity a964e1421d70e08d0a573a66e6079fb2570e2bed (directory listing, not claimed commit ID). Root LICENSE retrieved: GNU GPL version 3 text. Preserve applicable notices and review component/dependency licenses before copying.

- Track/TrackZip.cs reads package ZIPs and Swofty addons through their track.add source, manifest-selected ERP/UI/mips, track-row set operations and language entries. Unported operations are exposed; current manager warns then omits them. Rewrite must preserve opaque unrelated operations/payloads or block export with an explicit report, rather than silently lose them.
- Track/AddonBuilder.cs supplies a concrete export layout: swofty.json, assets/track.json (track.add), assets/text.json (lang.set), db/track.json (set/create), track/manifest.json, ERP, UI and mips. It preserves unknown manifest fields. It consults StockGame schema to choose set/create and dataset applicability. Its direct output overwrite is not a desired rewrite policy: stage and validate before publishing a new output.
- Track/TrackSettings.cs and TrackTuning.cs provide identity/names, author/version/readme, dataset-aware race laps and sprint layouts, tyres, session times, pit limits, conditions and tuning. TrackErs.cs separates MJ from joules and lap percent from fractions, passing unknown keys through.
- Track/TrackPictures.cs provides menu/map resource slots, fixed array dimensions and picture replacement contracts. Encoding relies on EgoEngineLibrary/Texconv; do not assume these C# dependencies can be imported into Blender Python.
- Track/TrackRecode.cs rewrites PKG through structured serialization and SRV through its reader, but only equal-length embedded-code replacements in unsupported binary string tables. It also relocates AI/track-space stems. Preserve this rejection boundary until proper serializers exist; never arbitrary byte replace different-length names.
- MainWindow.xaml.cs confirms this is a WPF package/metadata manager; no Blender geometry/terrain/AI authoring implementation was identified in inspected Track core files. Do not credit it as a complete track creator.

### Swofty

Compared local docs/source with current public main map.rs and activation/mod.rs; remote has additional unusable-package handling, so do not claim local checkout equals remote or update it automatically.
https://github.com/Swofty-Developments/SwoftyLauncher/blob/main/packages/core/src/map.rs

TrackPackage contract: code, ERP, donor activation, optional dataset/track overrides, ERS, mip copies and artwork/minimap files. Existing activation modules cover ailine, db/dbx, ers, grid, place and ui. Local docs/reference/installing-tracks.md describes database cloning, asset group registration/legacy slots, world stand-ins, grid expansion, menu arrays and ERS insertion. These are launcher responsibilities: Blender emits packages, Swofty installs/activates them. Do not duplicate installation logic or bundle a live DLL in the authoring add-on. Existing tools/map_check.py and core track_addons/profile_tracks tests provide validation references, not checks run in this audit.

### Proposed rewrite architecture

1. Blender UI/data layer: native selection, collections, transforms and undo; persistent project/asset/material IDs and provenance; project metadata in .blend. Avoid heavy work in panel draw/depsgraph callbacks.
2. Pure Python project/package layer: bounded archive reads, protected extraction, immutable source identity, retained operations/unknown fields, explicit donor/code/variant separation, staged addon output. Independently testable without Blender.
3. Format adapters: existing ERP/PKG/native scene readers, original placement vs render-local transform separation, material/texture graphs and dependency tracking. Preserve opaque resources. Use existing validated native writers through a narrow background worker when needed; do not copy the whole AlterEgo application.
4. First acceptance slice: open existing addon -> import supported placed geometry with provenance -> move/rotate/scale existing objects -> save/reopen .blend -> patch original layer matrices -> export new Swofty addon -> reimport and compare native transforms and untouched payloads. Unsupported object classes remain preserved and reported. Geometry topology/material creation and object insertion/deletion need their own serializer acceptance before enabling export.
5. Later slices: mesh/material/texture replacement, placement duplication/removal, collision and terrain, route/marker/rule/timing authoring, then new-circuit world/facility/AI integration. Reuse Track Workshop research and stabilize its interrupted ID/profile contracts; no playable-full-track claim from structural writer success.

This audit used source inspection only. No upstream projects modified, builds run, installations performed or game launched. Implementation is still pending.

Brainstorm baseline comparison: see baseline-comparison.md. User confirmed dedicated workspace and 0.10.1 baseline; assignment must move objects rather than copy. Comparison inspected actual release ZIP; no implementation or runtime verification claimed.

Brainstorm decision: source comparison deferred beyond V1; retain collection layout and move-only assignment, without automatic comparison copies. See baseline-comparison.md.

Brainstorm decisions: mandatory all-variant projects and release-ready V1; Common content plus editable variant-specific differences, assisted setup and checks across all variants. No silent variant substitution. See baseline-comparison.md.

Donor investigation 2026-10-29: see donor-policy.md; fresh 28-folder read-only environment survey plus previous Tracktool findings. Recommends coherent preset recipes, separate database/environment/functions/AI provenance; no universal best donor established. Recommendation pending brainstorm agreement.

Consolidated accepted brainstorm requirements in decisions.md, including project portability defaults and explicit V1 audio/crowds/marshals/animated objects/event triggers. Exact per-domain editing scope still needs specification.

2026-10-29: consolidated documentation created under track-editor/docs: CAPABILITIES.md, IMPLEMENTATION_PLAN.md, ACCEPTANCE.md; README entry point. Documentation-only requirements draft; no rewritten add-on implementation or fresh runtime acceptance. Includes accurate facility previews and all agreed V1 systems.
