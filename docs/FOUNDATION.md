# Foundation implementation — 29 October 2026

Internal development build 0.1.0. This is implementation of the approved first batch, not release-ready V1.

## Completed

- Ported baseline top-level Python modules from the pinned 0.10.1 ZIP; retained original SHA256 manifest. No WIP 0.11.0 modules or packaged native runtime substituted. Python runtime dependencies are Blender bpy/mathutils and bundled NumPy; standalone tests use the standard library. Exact legacy native backend source/packaging remains a downstream integration task; it is not a dependency of this foundation.
- Added AlterEgo Track Editor package, Blender >=4.5 guard, conflict guard against simultaneous Track Workshop registration, renamed sidebar/workspace and explicit workspace creation.
- Added new project identity, track code, source identity checks and companion project manifest. State survives .blend save/reopen. Companion updates reject another project's ownership and use atomic replacement. Explicit dependency registration and imported model/layout source hashes are supported.
- Replaced manual assignment and automatic terrain copying with moving original objects. Preserve datablock sharing, original world pose and unrelated collection links. Keep explicit Blender duplication available; source comparison UI is hidden.
- Retained baseline authoring tools and AC importer. Native export reports unavailable in this build instead of invoking an absent/unverified backend.

## Validation

37 retained pure-Python tests and 3 new storage tests PASS. Headless foundation scenarios PASS in installed Blender 4.5.0 Beta and 5.0.1: workspace creation/reuse, manual/automatic no-copy moves, shared mesh/materials, parented mirrored/nonuniform transforms, undo/redo, stable identity, unrelated links, save/reopen, companion manifest and changed-source reporting. Synthetic selected-layout AC import preserves geometry/axes/UV/materials and rolls back failed import in 4.5 Beta.

Initial port test run exposed two omitted synthetic fixture modules; both were restored. Initial workspace test incorrectly expected immediate background activation; it was corrected to verify the created workspace and reuse, since headless activation is deferred. No full interactive activation claim is made. Workspace creation scenarios print Blender's shutdown warning of 35 small allocations (~2.6KB); this remains noted for UI lifecycle investigation. Other assertions pass and processes exit zero.

## Boundaries

Not game-tested; no native-format track exporter, new variant registry, Pack Project or complete donor/material/facility systems yet. The installed 4.5 is Beta, not stable release acceptance. Companion source refs currently retain original paths; automatic relocation/packing belongs to B22. Native backend provenance remains open but no longer affects loading this Python-only foundation. Exact source licence metadata remains a documented distribution task; owner-authorized source reuse retains author attribution.

## Reproduce

Run `python -B -m unittest discover -s addon/alterego_track_editor/tests -v` and `python -B -m unittest discover -s tests -v` from repository root. Run `tests/blender_foundation.py` through Blender background/factory startup with `--python-exit-code 1`, passing repository root and a new ignored build folder after `--`. Run `tests/blender_ac_import.py` in the same background configuration. Build the internal ZIP with `python tools/build_foundation.py`.

## 0.1.1 import dialog correction

User reported an empty Laguna Seca project plus a populated .001 project after one interactive import. The inherited layout dialog also owned the cooperative modal job. Separated it into a non-undoable chooser and a distinct undoable import worker so the dialog can close before worker timer handling. This removes the shared dialog/worker lifecycle, but the exact interactive double-execution cause was not reproduced headlessly. One chooser call creates exactly one project; cancelling a yielded importer removes its partial project while preserving existing content. User interactive retest required. Existing duplicate collections are not automatically deleted.
