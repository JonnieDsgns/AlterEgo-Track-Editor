# Native routes and track markup - preview 0.3.0

30 October 2026. First route/race-data slice: previews plus gameplay markup interval editing. Not complete race authoring and not game-verified.

## Workflow

Open a native track, then Native Routes and Markup > Load Native Routes. A `Native Routes and Markup` collection shows reference-only curves: TrackSpace `maintrack` (closed) and `pit_1`, plus the AI racing line and left/right track limits of the `track` and `pit` routes. Gameplay markup intervals appear as coloured tubes along their spline: sectors, speed trap, Time Trial invalidation, DRS detection/activation, ERS override, X-Mode, pit limiter and pit/safety-car/start zones.

Select an interval to edit its exact Start/End fractions, or place the 3D cursor and use Start/End at Cursor. Moving a sector boundary moves the neighbouring sector's boundary too; the lap start (sector 1 start, sector 3 end) is fixed. Refresh Markup Preview redraws edited tubes; Load Native Routes again keeps authored values. Export Updated Native Track writes the markup with any placement edits. Swofty update addons replace the markup resource whole (`replace-resource`), because it is binary XML rather than a `!pkg` layer; that resource conflicts with other addons that replace it.

## Formats

- **Binary XML**: new `native/formats/bxml.py`, an independent implementation from the documented record layout (i16 length = payload + 4, u8 type, u8 pad, i16 count; element type 0, close 5, text 1; other records such as the type-6 document trailer kept raw). Every BXML resource in the 28 installed track folders re-encodes byte-identically: 28 each of AISplineData, TrackSpace, TS, TM and PracticeTA plus 941 camera Splines.
- **Schemas** (match AlterEgo research docs, re-measured): TrackSpace `rootnode/TrackSpaceSpline name/Knot position`; spline names are `maintrack` and `pit_1` on all 28 tracks (resolving the main/pit naming conflict noted in the Istanbul handoff). TS has a closed `main` and an open `pit` volume list on all tracks. TM `TrackspaceMarkup/MarkupList/MarkupElement Name Start End SplineName` with typed attributes/properties; 4,551 intervals on `maintrack`, 420 on `pit_1`; 358 wrap past the lap line (Start > End). AISplineData gates hold position, normal and nine waypoint offsets (racing/track/white-line/run-off limits, racing line); limit points are position + normal x signed length.
- **Position mapping**: shown positions assume arc length along the knot polyline, including the closing segment of the main loop. Main knot spacing is regular (e.g. Monaco 6.47 m mean, 0.66 m SD; Spa 5.31/0.37), and polyline lengths are plausible (Monaco 3,321 m, Spa 7,007 m), but the game's exact parameterization is not established. Stored fractions are exact; positions may differ by metres.

## Edit rules and checks

Only gameplay intervals are editable; audio, accessibility, crowd, reflection and other markup is preserved untouched. Values must be 0..1 (written with at most six decimals, `0`/`1` as stock). Only closed splines may wrap. Sectors stay chained and in lap order. Every export re-decodes the whole markup tree and requires everything except the edited Start/End attributes to be unchanged. A changed source markup resource blocks export until routes are reloaded.

## Verification

48 project + 37 baseline Python tests (new: BXML round trip/text/malformed rejection, fraction formatting, spline mapping/nearest/wrap, AI line offsets, markup rules, full export and update-addon packaging). Headless Blender 4.5.0 Beta and 5.0.1: previews, linked sector boundary from the cursor, fixed lap start, reload keeps edits, save/reopen, full export readback, update addon `replace-resource`, stale source rejected, source unchanged. Real read-only checks: library edits on all 28 track folders with route data; Blender 5.0.1 on Monaco (route previews, cursor-set sector boundary 0.3215 -> 0.3315 linked to sector 2, DRS activation move, update addon) and Spa (0.321 -> 0.331, 38 editable intervals). The first Spa run took 752 s: opening a native track re-hashed the whole layer for every record (54,001 hashes on Spa). 0.3.1 hashes each layer once; the same Spa run now takes 22 s (Spa document open 24.3 s -> 5.6 s outside Blender).

## Not covered

Route geometry (TrackSpace knots, TS volumes, AI gates/waypoints), the QT02 route index, VPTimes/AI timing and pit data are previews only: changing them requires regenerating dependent data whose native generation is not established (see knowledge/ALTEREGO_RESEARCH_SURVEY.md). Adding/removing intervals, property values (DRS/X-Mode IDs, types), camera splines and practice programmes are not edited. Whether the game accepts moved sector/DRS/pit-limiter intervals without other changes (for example DRS pairing, timing gates, AI behaviour) is untested.

0.3.3: export warns when DRS or Straight Mode zones leave the envelope measured on the 28 stock tracks (DRS activation 338–1039 m, detection 108–1938 m before it, Straight Mode 155–1748 m, no overlaps). The F1MapEditor rule ranges (300–1000 m, 50–600 m, 180–1750 m) would flag 18 stock zones on 13 tracks and are not used.
