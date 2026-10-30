# User game-test checklist for previews 0.2.6–0.3.1

These features pass offline tests only. Each item below needs an in-game observation before it can be called working. Use a stock track, export a **Swofty Update Addon** (or a full copy in a separate test installation), install it with the launcher, and record the result (PASS/FAIL, track, mode, notes, launcher log). Test one item per addon where possible so failures can be attributed.

| # | Feature (version) | Export | What to check in game |
|---|---|---|---|
| 1 | Moved static prop (0.2.0) | Composable Edits | Object appears at the new position in every variant you load; no load errors |
| 2 | Duplicate as New Placement (0.2.6) | Composable Edits | Copy renders at its new position; drive past it from several angles (precomputed visibility may hide it); note lighting/AO differences; it has **no collision** |
| 3 | Place Edited Asset (0.2.7) | Composable Edits | Edited model renders with the original materials at all distances (LOD changes) |
| 4 | Use Edited Asset for Selected (0.2.8) | Composable Edits | Existing prop shows the edited model; lighting may look baked for the old shape |
| 5 | Delete static prop (0.2.8) | Whole Layers | Track loads; object gone; no flicker/crash near it. Repeat with a PVS-listed prop only if the first test passes |
| 6 | Add Next Race Placement (0.2.9) | Composable Edits | Only with a larger grid setup: new grid slot/garage/pit box usable; do not combine with Swofty Custom Grid Size on the same track |
| 7 | Track markup: move DRS activation start (0.3.0) | Update addon | DRS becomes available at the new point in race/time trial; detection still works |
| 8 | Track markup: move sector 1/2 boundary (0.3.0) | Update addon | Sector times split at the new point; lap timing unchanged |
| 9 | Pit limiter interval (0.3.0) | Update addon | Limiter engages/disengages at the new points; no pit penalty glitches |
| 10 | Rebuild collision with **no edits** (0.3.1, experimental) | Update addon | Drive a full lap including kerbs, run-off and pit lane: no fall-through, normal grip/kerb feel, AI behaves |
| 11 | Rebuild collision with one authored mesh (0.3.1) | Update addon | Car collides with the authored mesh using the chosen code |

Test 10 is the key one for collision: it shows whether the game accepts a legacy-format rebuild of this stock track. If it fails, do not continue with 11.

Report results with the addon file, the editor version and what you observed; failures with screenshots or short clips are as valuable as passes.
