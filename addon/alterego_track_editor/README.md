# AlterEgo Track Editor — internal preview 0.2.0

Blender 4.5 minimum. Disable Track Workshop before enabling this add-on: retained operators and properties cannot register alongside the original.

Install the ZIP through Preferences > Add-ons > Install from Disk. Open Workspace creates/reuses the dedicated workspace. AC import retains the Workshop workflow. Asset assignment moves objects while retaining shared geometry and world placement.

Open F1 / Swofty Track imports a stock folder (select an ERP inside it), an addon folder/package, or a raw track package ZIP. Addons may need a base track folder for dependencies. Import retains native identities and every discovered variant, including additional story/previous-season worlds. Variant View changes viewport visibility. Unsupported geometry remains named references; the import report lists preview limitations.

Save Project uses ordinary .blend saving. Packed preview textures survive reopening. Keep original source files available for export. Optional source bookkeeping lives under Advanced Files.

Native export supports moving, rotating and scaling supported existing placements. Full Update writes a separate stock-track folder or updated addon/package, preserving original content. Changes-only Swofty packages support stock-track sources only. Outputs must be outside source and game installation. Unsupported edits are rejected. Placement changes do not rebuild separate collision data.

The material library offers thumbnail selection, local .blend pack loading, explicit curation and independent copies for objects/selected faces. Native shaders are approximated. Material edits do not yet export native materials/textures. No game-derived pack is bundled.

The facility library curates selected actual geometry and places shared references at the cursor, with bounds and possible-overlap warnings. These are placement references; native insertion remains in development.

This is not V1. New geometry, terrain, collision, native material export, facility insertion, race systems and complete all-mode game validation remain unfinished. BC7 previews need an available Pillow decoder or are reported unsupported. No game assets, executables or runtime backend are bundled. No game loading/gameplay has been verified. See repository docs/NATIVE_EDITING.md for tests and limits.
