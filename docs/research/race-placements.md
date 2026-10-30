# Numbered race placements - preview 0.2.9

30 October 2026. Grid/pit/garage authoring slice; not complete race setup and not game-verified.

## Workflow

Select an imported grid slot, pit box, pit garage or F1 garage (numbered 2 or higher) and choose Project Settings > Add Next Race Placement. Move the new object, then Export Updated Native Track. Numbers, names, `Id` fields and garage links are assigned at export in creation order; the export report lists them. Copies of new race placements also become the next number. Variant-only layers may be hidden by the preview variant; choose All Variants to select them.

## Rules (evidence)

SwoftyLauncher's Custom Grid Size (`packages/core/src/activation/grid.rs` at 97d4488, inspected read-only) extends grids by cloning `PitGarage`, `F1Garage`, `PitBox` and `GridSlot` entries named `<layer prefix>$<Kind><n>`: one pit garage and grid slot per car, one F1 garage and pit box per two cars, `VehPlacement.Id = n`, `F1Garage.id = n` and `F1Garage` left/right car placements = uniqueids of `PitGarage(2n-1)`/`PitGarage(2n)`. Read-only surveys of Monaco and Bahrain agree:

- vehicle placements are template `VehiclePlacement` with `VehPlacement.Group` (`shnm`: GridWheelMarker, Pit, Garage) and `Id` (`ui32` = n); number 1 omits `Id` and is not used as a clone source;
- F1 garages are template `F1Garage` with `id` (`si32` = n) and two `woid` car placements, all 12 linked exactly to pit garages 2n-1/2n;
- base numbers live in the common world's vehicle layer (Monaco 22 grid slots, 20 pit garages, 10 garages/pit boxes); variant layers add 21-24. Variant worlds do not contain the base vehicle layer, so a variant world is evaluated together with the common world.

The editor numbers a new placement as one more than the highest number in every world (common plus variant) that loads its layer, and refuses it if any of those worlds would get a gap. On real Monaco/Bahrain this adds `PitGarage25/26`, `F1Garage13` (linked to them), `PitBox13` and `GridSlot25/26` to `vehicles_current_myteam`, matching the launcher's own example, while additions to the base layer are refused (F1/Classic/F2 worlds stop at 22). Garage links must resolve to exactly one pit garage loaded wherever the garage is. Unique names/uniqueids use the same namespaced MD5 as other new placements.

## Verification

43 project + 37 baseline Python tests (new: per-world numbering and gap refusal, garages linked to pit garages created in the same export, refusal of entries without `Id` and missing pit garages, composable replay). Headless Blender 4.5.0 Beta and 5.0.1: entry 1 refused, creation-order numbering, copy of a new placement, garage links, variant-layer grid slot, composable update addon, save/reopen identical layers, gap refused, source unchanged; all earlier Blender checks still pass. Real read-only Monaco and Bahrain: six additions each, garage links correct, SwoftyLauncher's Python serializer applying the same clones produces identical bytes, base-layer refusal explained.

## Limits

The game database grid size, AI pit/garage data (`AISplineData`, pit lane timing), garage props/crew, timing boards, camera and cutscene placements are not changed. Swofty Custom Grid Size may also extend the same layers at install time: do not combine both for one track without checking the result. Deleting or renumbering race placements, adding the F1 world's own numbers beyond the shared base, and cross-layer placement are not supported. Game behaviour is unverified.
