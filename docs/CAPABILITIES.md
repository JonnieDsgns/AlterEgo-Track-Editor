# AlterEgo Track Editor — capability specification

Version: 0.1 • 29 October 2026 • Product requirements draft

Product name: AlterEgo Track Editor. This specifies the agreed public V1, not delivered functionality. Track Workshop 0.10.1 is the implementation baseline. Its unfinished 0.11.0 source is reference material, not an accepted replacement. Smaller internal milestones do not reduce public V1 scope.

## 1. Purpose and audience

A Blender add-on for maintaining and creating complete F1 25 tracks. It combines a dedicated workspace, ordinary Blender editing, guided authoring tools, native format handling and Swofty package export. The primary first workflow is AC conversion. Existing-track upgrades, separate variants and fully custom Blender circuits are equally required V1 workflows.

Public V1 must be release-ready across all required native variants and game modes. Preparation tools or structurally valid exports alone do not meet this requirement.

## 2. Supported workflows

| ID | Workflow | Required output |
|---|---|---|
| WF-01 | Update an existing F1 track | Updated native files retaining original resource/container/folder structure |
| WF-02 | Update an existing addon track | Same identity by default; complete updated package or changes-only Swofty addon |
| WF-03 | Derive a separate track/layout from an existing track | Independent identity and Swofty track package |
| WF-04 | Convert an Assetto Corsa track/layout | Complete Swofty track package |
| WF-05 | Build a custom circuit in Blender | Complete Swofty track package, including meshes/curves made with other tools |

The user chooses update versus separate identity. Export always uses a separate output destination; source files and game installation are not authoring destinations. New identities require consistent namespace, references, IDs, database entries and dependencies, rather than filename-only renaming.

## 3. Workspace and project lifecycle

- Dedicated workspace retains the successful 0.10.1 task/context approach, project selection/pinning, relevant object controls and explicit checks. Normal Blender modelling and undo remain central.
- Logical areas cover project, geometry, materials, driving, race setup, presentation and checks/export. Final tab names and panel arrangement are implementation design, not fixed requirements.
- Long operations show progress and cancellation. Panel drawing/selection must not trigger full-track scans or builds. Preserve the baseline caching and stale-report behaviour.
- Windows is the initial platform. Blender 4.5 is the minimum supported version, with support targeting 4.5 and later. Record the exact versions tested for each release; future Blender compatibility must be checked as versions become available. Minimum system requirements remain to be measured.
- A .blend holds authored scene/project state. A companion folder holds required assets, textures, source snapshots where needed and build reports. Store portable relative references and stable project/asset identities.
- Pack Project collects dependencies so the project can reopen without original source paths. Report excluded/unavailable/licensed dependencies; distinguish a private editable project pack from a redistributable track package.
- Shared meshes, materials and textures remain shared where appropriate. Make Unique and Duplicate are explicit actions.
- Track source identities/versions/hashes. Detect missing or changed inputs and explain which imports, checks or update exports are affected.

## 4. Import and collection semantics

AC import and conversion retain 0.10.1 layout discovery, KN5 handling, source hierarchy/material metadata and available route/marker inputs. Native F1/addon imports expose supported geometry and track systems as editable content. Missing dependencies, unsupported resources and approximation boundaries are reported. Opaque native resources must survive unchanged where safe; opaque preservation does not satisfy an editing requirement for a required V1 system.

Retain the 0.10.1 hierarchy and semantic collection identities:

- Project / AC Import and F1 Export.
- F1 Export / Track Markup: markers, gates, racing/pit lines, road/pit edges, authored limits, pit rules, DRS and X-Mode zones.
- F1 Export / Common: Terrain, Trackside Objects, Facilities, Vegetation.
- F1 Export / 2025 and 2026: F1, MyTeam and F2 branches.

Native imports may need source-appropriate labels, while retaining the same role structure. Names are labels; tagged roles determine meaning. Asset assignment MOVES the existing object into the F1 target, preserving world placement, mesh/material links and provenance. Neither manual assignment nor automatic terrain preparation silently duplicates source geometry. Resolve parent transforms and shared data safely. Direct collection moves must update classification or produce an actionable conflict; multiple incompatible memberships must not export unpredictably.

Source comparison is deferred. Ordinary visibility controls remain available.

## 5. Variants

All projects support all variants; no project-level opt-out reduces readiness requirements. Common content is shared; variant collections contain additions/changes. Shared content need not be duplicated. Guided setup helps create required grids, garages, pit facilities and other variant-specific elements, all editable afterward. Validate missing elements and incompatible references rather than silently substituting another variant.

The six retained collection branches are the minimum authored structure, not proof they enumerate every native variant key used by the installed game. Build a canonical mapping of native worlds, vehicle categories and database datasets; enumerate any further required variants during compatibility audit. Track layout, vehicle/season variant and game mode are separate concepts.

## 6. Geometry, materials and physical surfaces

| ID | Required capability |
|---|---|
| GEO-01 | Place, transform, duplicate, delete and replace trackside objects |
| GEO-02 | Edit road/terrain geometry and topology; add custom meshes and circuit layouts |
| GEO-03 | Assign terrain/object/vegetation/facility and variant roles through retained collections |
| GEO-04 | Preserve shared geometry, native placement and dependency graphs on native round trip |
| PHY-01 | Assign physical surface types independently of visual materials |
| PHY-02 | Generate supported collision from selected geometry or use separate authored collision meshes |
| PHY-03 | Check holes, inconsistent surfaces, invalid geometry and render/collision participation |
| MAT-01 | Edit materials/textures and supported terrain-layer masks and mappings |
| MAT-02 | Curated F1 material template browser with image cards, names, categories, search and Apply |
| MAT-03 | Apply to selected objects or selected faces; create editable instances without changing library masters |
| MAT-04 | Expose relevant texture slots, tint, tiling and supported shader controls with understandable labels |
| MAT-05 | Preserve native shader configuration and identify Blender preview approximations |
| MAT-06 | Setup templates from local game assets or versioned GitHub packs with provenance, dependency and redistribution checks |

Physical surface suggestions may accompany visual templates, but must not silently overwrite authored physical assignments. Missing template assets have explicit resolution actions. Barrier/sponsor-board placement along curves is deferred; manual placement and sponsor replacement are V1.

## 7. Driving and race setup

Import native data for F1/addon tracks and convert available AC inputs. Retain 0.10.1 individual tools and add guided generators where appropriate. Generated data stays editable.

- Racing/pit curves, direction, point order, widths and route connections.
- Road/pit edges, authored legal limits and pit entry/exit/speed-limiter rules.
- Start/finish, sectors, speed traps and supported detection/activation zones including DRS/X-Mode.
- Grid positions, garages, pit boxes, in-garage/hotlap positions and other required functional markers.
- Supported session, tyre, pit speed, weather/default conditions, downforce, ERS and race metadata.
- Native vehicle/AI output consistent with authored route geometry and required categories/seasons. Copying donor calibration or scaling lap times is not sufficient acceptance.

## 8. Accurate facilities placement

Use actual supported facility models for garages, pit walls, equipment and related assemblies, with native scale, axes and placement origins. Existing tracks use their own assets; new tracks use compatible curated templates. Supply known clearance envelopes and likely overlap warnings, alongside visible functional spawn/stop positions. Warnings assist review; visual clearance is not a guarantee of collision or race functionality. Keep preview-only geometry separate from export participation and avoid duplicate resources. Provide visibility controls suitable for large scenes.

## 9. Presentation and secondary systems

| System | V1 scope |
|---|---|
| Identity | Track names, country, author, credits, description and version |
| Artwork/maps | Menu pictures/flags; generated layout/minimap images with manual adjustment |
| Cameras | Integrated native track-camera import/edit/export using existing camera tooling; supported animation/activation preservation |
| Lighting | Place custom supported native lights in Blender; expose reliably mapped properties |
| Environment | Coherent donor or generic-template lighting/environment data; preserve compatible source settings on updates |
| Audio | Import/preserve emitters; place, assign supported sounds and edit supported playback properties |
| Crowds | Place/configure crowd areas using reusable supported assets/templates |
| Marshals | Place posts/characters and configure supported roles/references |
| Animated objects | Preserve/import native animation; place instances and configure supported playback; define and validate supported authored-animation exports |
| Event triggers | Visual editing of supported trigger types, conditions, actions and references |

Secondary systems are real V1 features, not preservation-only promises. Exact editable native types, properties and animation contracts require implementation audit and must be enumerated before release. Arbitrary audio synthesis, universal animation baking, unrestricted scripting and a full sky/weather/probe-baking editor have not been agreed.

## 10. Donor and template policy

Existing tracks preserve their own data by default. AC/custom projects use a curated Base Preset with separately tracked compatible categories: database defaults, coherent environment bundle, functional prototypes and vehicle response profiles. Show inherited/authored/unresolved state and provenance. Advanced overrides affect compatible complete categories and preview affected data before applying; preserve authored work.

Reuse the existing category-profile mechanism: five coherent AIAcceleration/AIBraking/AICornering/AICruising/AIThrottle families per vehicle/season. Prior Ferrari-2026 evidence supports Balanced (Bahrain; compared Silverstone/Suzuka) and HighTopSpeed (Miami; compared Spa). Ferrari-2025 differs within these groups. Do not generalise equality or offer an unvalidated HighDownforce profile as complete. AIVPChar and VPTimes remain track-specific.

Database copy_from_track and copy_slot remain separate from identity and environment donors. Keep environment component references and TrackInfo binary/texture pairs together. Local probes/bakes must remain spatially valid or use a validated replacement path. No universal donor winner is established. See research/donor-policy.md for evidence and limits.

## 11. Checks and export

Check Project provides errors, warnings and review items, scope/filter/search and navigation to affected objects. Changes invalidate applicable results. Selection-only checks are not whole-project approval.

- Test Export permits incomplete projects only when output is structurally valid, and includes unresolved findings.
- Release Export requires the full configured completeness checks across every required variant. Runtime verification is a separately recorded status; a successful export never automatically means game-verified.
- Update output preserves original native structure, untouched resources and relevant addon metadata/operations. Unknown operations must be retained safely or block the affected export; never silently discard them.
- Separate-track output produces a complete Swofty package with identity, database/language changes, artwork, archive and external dependencies.
- Changes-only output supplies modified resources/fragments and dependency closure, with base track/version and ordering requirements. This is not arbitrary binary delta encoding. Swofty chooses delivery/rebuild route.
- Stage, validate and reopen outputs before publishing. Reject dangerous paths/collisions. Source overwrite is forbidden; existing output replacement needs an explicit user action and recoverable handling.
- The add-on authors and exports; Swofty performs installation/activation. No automatic game launch or installation is required.

## 12. Release scope and deferred work

V1 includes all four creation/maintenance workflows, all required variants/modes, project portability, secondary systems and accurate facility previews. See ACCEPTANCE.md for release evidence. Source comparison and curve-based barrier/sponsor placement are deferred. Panel styling, tested Blender compatibility matrix, pack catalogue and compatibility minimums remain to be selected without silently reducing scope.

## 13. Reference hierarchy

Agreed decisions: research/decisions.md. Baseline evidence: research/baseline-comparison.md. External-source audit: research/source-review.md. Research findings qualify implementation claims; product requirements do not certify format knowledge or runtime readiness.

