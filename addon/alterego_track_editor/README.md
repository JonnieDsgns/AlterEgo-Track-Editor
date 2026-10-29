# AlterEgo Track Editor — internal foundation 0.1.0

Blender 4.5 minimum. Disable Track Workshop before enabling this add-on: stable internal Workshop operators and properties are retained for compatibility and the two cannot register together.

Install the ZIP through Blender Preferences > Add-ons > Install from Disk, then enable AlterEgo Track Editor. The sidebar is AlterEgo Track Editor. Open Workspace creates/reuses its dedicated workspace; no startup workspace is replaced automatically. New Track Project creates the retained collection structure. AC folder import retains the 0.10.1 workflow.

Assign Selected Assets and automatic terrain preparation MOVE existing mesh objects. Shared mesh/material data and parented world placement are retained. Source comparison controls are hidden. Duplicate or make data single-user explicitly through Blender when required.

Project Storage records track identity, source-file hashes and a companion folder. Save the .blend normally; Save Companion Manifest writes/updates project.json for the same project only. Record Source File adds a dependency; Check Source Files detects missing/changed files. AC imports record selected model/layout inputs automatically. Re-save the companion manifest after identity/source changes. Source references are currently original paths; Pack Project/automatic relocation is a later implementation task.

This is NOT public V1 or a complete track exporter. Native export is unavailable and reports that explicitly. The native runtime/backend is not bundled. Source codecs and existing preparation tools remain for staged integration. Game assets, templates and local tests are not bundled.

Verification: 37 retained pure Python tests plus 3 storage tests; headless foundation checks in installed Blender 4.5.0 Beta and 5.0.1 cover workspace creation/reuse, no-copy assignment, shared data, parented mirrored/nonuniform transforms, undo/redo, save/reopen, companion storage and source changes. Synthetic AC import/rollback passes in 4.5 Beta. Stable 4.5 and full interactive UI verification remain unperformed. Workspace-creation test runs print a small Blender shutdown allocation warning; no native/game execution was performed.
