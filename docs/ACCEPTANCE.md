# V1 acceptance and validation plan

29 October 2026 • Required release gates; initial status: NOT RUN

This checklist defines release evidence, not proof of current support. A successful offline export, Swofty installation and game behaviour are separate results. V1 is not accepted while required capabilities or compatibility cells remain unresolved. A structurally valid test package may still be exported with explicit incompleteness.

## Evidence records

For each result record: case ID, project/source identities, add-on version, Blender/game/Swofty versions, variant, mode, conditions, steps, expected/actual result, logs/report paths, tester and status. Allowed statuses: NOT RUN, PASS, FAIL, BLOCKED; N/A requires a documented game-imposed incompatibility, not a way to omit supported scope. Historical results are references until reproduced for the release candidate.

## Core release gates

| ID | Acceptance requirement | Evidence |
|---|---|---|
| A01 | Install/register/reload/uninstall cleanly on every declared Blender version | Actual Blender tests; user data survives disable/reload |
| A02 | Preserve baseline AC import features | Representative default/multi-layout/rotated/shared-asset fixtures plus malformed-input cases |
| A03 | Move assignment and auto terrain create no implicit geometry copies | Object/mesh/material identity counts, transform conservation, undo/redo |
| A04 | Collection roles and variant sharing remain deterministic | Rename/relink/conflicting membership/save-reopen tests |
| A05 | Shared assets remain shared; Make Unique works | Controlled edits affect intended users only |
| A06 | Native no-edit import/export preserves content | Native readback and unchanged-resource/fragment identity, unknown-field preservation |
| A07 | Transform/topology/material/collision edits serialize correctly | Geometry, normals, winding, UVs, bounds, surfaces and placement checks |
| A08 | Native graph is complete | Worlds/layers/resources reachable; no dangling IDs or missing files |
| A09 | Material library works from local files and supported packs | Preview/apply/customise/save/export; missing/versioned asset handling |
| A10 | Facilities preview matches export | Scale/origin/orientation/assembly checks; spawn/stop marker review; no duplicate preview exports |
| A11 | Every required variant is complete | Canonical variant manifest plus individual validation results; no silent fallback |
| A12 | Driving data matches authored track | Main/Pit domains, selectors, category/season coverage, numerical and game acceptance |
| A13 | Cameras/lights/environment work | Native round trip, references, spatial validity and user-run observations |
| A14 | Secondary-system authoring works | Audio/crowds/marshals/animation/triggers each imported, edited/created through supported templates and exported/tested |
| A15 | Full native and Swofty exports work | Reopen package; metadata, UI, mips, names, variants and dependencies verified |
| A16 | Changes-only updates work | Stock and addon bases, changed dependency closure, version mismatch/load-order/conflict cases |
| A17 | Projects are portable | Pack then reopen from a different location without original paths; no undeclared dependencies |
| A18 | Validation is actionable and current | Findings select objects; stale reports, scoped checks and release blocking behave correctly |
| A19 | Failures are recoverable | Cancel, invalid paths, existing output, interrupted builds and stale sources preserve project/source integrity |
| A20 | Production-scale projects remain usable | Representative full-track import/edit/save/check/export timings, memory and cancellation responsiveness; budgets selected and recorded |
| A21 | Distribution is clean | Source/license notices, no licensed game/test assets or local paths accidentally shipped; reproducible package |

## Workflow acceptance fixtures

- Existing stock track: no-op, visual/placement upgrade, topology/collision change and same-structure output.
- Existing addon: retain identity, preserve unrelated operations, full updated export and changes-only addon.
- Derived track: new identity, no accidental dependency on the old namespace, complete Swofty package.
- AC conversion: complete layout with racing/pit inputs, plus missing-input case completed through authoring tools.
- Custom circuit: Blender-authored meshes/curves and imported third-party-tool geometry assigned to F1 roles.
- Include an additional track not used to tune the generators/presets, rather than accepting only development fixtures.

## Variant and game-mode matrix

All compatible combinations require explicit coverage. First enumerate native variant/world/dataset mappings; the retained 2025/2026 F1/MyTeam/F2 branches do not by themselves prove complete enumeration. Include every supported grid size and relevant vehicle category. Do not silently substitute F1 assets for missing F2 or MyTeam setup.

| Mode/session family | Required observations |
|---|---|
| Practice | Spawn/garage placement, pit exit/rejoin, session timing and applicable practice programmes |
| Qualifying | Out/in laps, timed laps, invalidation, traffic and grid assignment |
| Grand Prix/race | Start/grid, complete laps, classification, finish and return flows |
| Sprint/event formats | Applicable session ordering, distances, grids and results |
| Career and MyTeam | Track availability, event/session integration, team garage allocation and persistence |
| F2 | Compatible category assets, race formats, grid/pit/timing and results |
| Time Trial | Start/reset, lap recording/invalidation, timing and presentation |
| Multiplayer/local play where supported | Availability, grid/session consistency and multiplayer-specific behaviour; test only in permitted compatible environments |
| Replays/presentation | Camera activation, animation, maps/menu artwork and session/replay transitions |

Cross-cutting scenarios: dry/wet and changing weather where supported; declared day/night support; pit stops and double-stacking; penalties/limits; DRS/X-Mode where applicable; recovery/reset, safety-car/VSC and red-flag/restart flows where the game supports them; crowds/marshal/trigger responses; audio and object-animation playback. Each condition must be scoped to native game capabilities. Online service acceptance or permission to use mods is not implied by local package validity.

## Test versus release export

Test export blocks malformed/unsafe native data but may carry missing-function warnings. Release export blocks missing required systems/variants and unresolved structural errors. Both include readiness results; neither invents game-verification status. Public V1 requires the complete user-run release matrix, whereas later user-authored tracks carry their own separate validation history.

## Execution boundaries

Offline authoring/tests use private workspace output. Game launch, installation and mode validation are user-run under existing project rules. No integrity bypass, game-install writes by the agent or engine evidence promotion follows from this specification.

Blender compatibility baseline: minimum 4.5, targeting 4.5 and later. Maintain explicit results for tested versions; future versions require regression verification rather than an unconditional compatibility claim.
