# AlterEgo Track Editor

A Blender **4.5+** add-on project for editing and creating F1 25 tracks, based on Track Workshop 0.10.1, with Swofty package export.

**Status: internal preview 0.2.0, not public V1.** Native F1/Swofty import, existing-object placement updates, variant visibility, material thumbnail libraries and facility references are implemented. Geometry, collision, material and race-data export remain in development. See [native editing scope and checks](docs/NATIVE_EDITING.md). Public V1 still targets complete, race-ready creation across all required variants and game modes.

## Intended workflows

- Upgrade existing F1 and addon tracks, retaining original native format and structure.
- Create separate variants of existing tracks.
- Convert Assetto Corsa tracks.
- Build custom circuits in Blender, including geometry from other authoring tools.
- Export complete tracks or changes-only Swofty update addons.

## Documentation

- [Capabilities and feature list](docs/CAPABILITIES.md)
- [Technical audit and reproduced checks](docs/TECHNICAL_AUDIT.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Development backlog](docs/BACKLOG.md)
- [V1 acceptance checklist](docs/ACCEPTANCE.md)
- [Agreed decisions](docs/research/decisions.md)
- [Track Workshop baseline comparison](docs/research/baseline-comparison.md)
- [Donor policy and category-response findings](docs/research/donor-policy.md)
- [Source review](docs/research/source-review.md)
- [Source and dependency notices](THIRD_PARTY.md)

## Internal build

Run `python tools/build_foundation.py` to create the Blender installation ZIP under ignored `dist/`. Read [installation and foundation limits](addon/alterego_track_editor/README.md) before using it.

## Audit utilities

`tools/audit_baseline.py` inventories a user-supplied 0.10.1 release ZIP and compares it to a supplied source folder. It extracts Python/JSON code into ignored private build storage; it does not install the add-on or run packaged binaries. Run it with `--help` for arguments. `tools/check_baseline_registration.py` is a Blender background registration check for that snapshot.

Game assets, extracted templates/textures, private fixtures, native runtime binaries, research databases and machine-specific inventories are excluded. Requirements describe intended capabilities; they do not claim unresolved formats or game behaviour are implemented or verified.

Project Settings now offers the project name and Save Project. Source references and companion-manifest controls are optional under collapsed Advanced Files; ordinary .blend saving is sufficient for current editing.
