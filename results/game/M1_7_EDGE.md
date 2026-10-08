# M1.7 edge-reachability repair

Status: uncommitted, awaiting renewed human playtesting. No push, merge or RL.
M1.6 checkpoint remains `58ffd60fb60239a911c1ca0baea458ec743774b7` on
`wip/m1-4-enclosure`. This report supersedes the edge-visibility behavior in the
historical M1_7.md report; that report and all earlier evidence remain unchanged.

## Root cause and exact nominal geometry

ROOM is 3840 x 2160 logical units. Its inner wall planes are x=48/3792 and
y=48/2112. A fly collision disk has radius 11, so legal center bounds are
[59,3781] x [59,2101], excluding solid room obstacles. Body length is 24 units.
These bounds and obstacle handling have NOT changed.

Old physical paddle center bounds were [240,3600] x [240,1920]. The inset was
144 (head radius) + 0.3 * 320 (rendered hover lift) = 240 units. Both desired
hand-target clipping and trajectory stopping guards used this presentation-derived
inset. Thus moving the pointer closer to the edge could not move the head closer.

Let S be the paddle-center rectangle and D(r) a radius-r disk. The old union of
possible paddle collision volumes was S + D(144), a rounded rectangle. Hittable
fly centers lie in S + D(155), because the fly contributes radius 11. This is
not an axis-aligned bounding-box collision approximation: near corners the rounded
boundary matters. The guaranteed safe region was the legal fly-center set outside
that rounded rectangle.

| Quantity | Old value |
|---|---:|
| Leftmost paddle material | x=96 |
| Leftmost hittable fly center away from corners | x=85 |
| Leftmost legal fly center | x=59 |
| Straight-edge unreachable center-band depth | 26 units = 1.08333 BL |
| Corner bisector first reachable x=y (top-left) | 130.39845 |
| Corner axis penetration beyond legal corner x=y=59 | 71.39845 units = 2.97494 BL per axis |
| Corner diagonal distance to reachable set | 100.97265 units = 4.20719 BL |

The other three corners/edges are symmetric. The 26-unit band is measured inward
from the legal fly-center boundary, not from screen coordinate zero. The corner
region is curved, not a uniform 26-unit strip. Values describe nominal center
bounds; the controller retains its existing 0.5-unit stopping deadband and finite
integration tolerance. Neither can account for the much larger uncovered region.

Pointer conversion was already correct: screen coordinates are unletterboxed
and divided by display scale, then targets clamp to [0,3840] x [0,2160]. Tests
cover 1280x720, 2560x1440 and letterboxed 1280x1000. Neither fullscreen conversion
nor the swept collider caused the safe zone. The collider already tests full
relative disks; the old center-bound controller prevented those disks from ever
reaching the fly. Rendering uses a lifted/tilted decorative paddle and circular
contact footprint, whereas collision uses the full radius-144 head disk only.

## Repair

Active ROOM config version 8 sets physical `center_inset=0`. Center targets and
stopping guards now use [0,3840] x [0,2160], independently of head radius or
rendered height. No center teleport or instantaneous velocity reset is added.
The nominal head extent can reach -144..3984 in x and -144..2304 in y; its full
collision geometry remains present outside the visible rectangle.

The new static collision union is [0,3840] x [0,2160] + D(144). Every legal fly
center lies inside the paddle-center rectangle itself, so all legal wall/corner
positions are geometrically reachable, with no remaining unreachable perimeter
band. Real approach and strike timing are still required under bounded dynamics.
No offscreen pointer input or negative paddle center is needed for coverage.

VIEWPORT clips presentation only. ROOM WORLD contains fly/environment dynamics.
The SWATTER is a separate player-controlled physical object, whose head may
extend past the viewport. Rendering clips naturally and does not alter swept
segments or collision outcomes.

Fly intelligence, legal area, brain, retina bottleneck, ecology and inward-steering
rules are unchanged. All paddle speed, acceleration, angular limits, phase times,
follow-through and recovery parameters are unchanged: caps 1800/3200 units/s,
18000 units/s^2, 6 rad/s, 24 rad/s^2; phases 100/120/100/140/300 ms.
The existing 0.5-unit stopping deadband is solely for paddle numerical stability;
it is not a new fly safety inset. LAB and GAME retain their prior configurations.

## Recorded failure retained

Original session: `results/game/sessions/20260920T030539.399439Z-cbd62f33`.
All 10 original files are byte-identical, including the archived old source.
The recorded 260.30-second session had 13015 ticks, 12642 living ticks, 17 strikes,
3 hits and 14 misses. 1980 living ticks (39.60 s) lay outside the old reachable
set; 43 of those had active-contact flags. Eight misses resolved while the fly
was within one body length of a wall. These are diagnostics, not proof that every
miss was caused by the bug.

A compact retained fixture [edge_regression_m1_7.json](edge_regression_m1_7.json)
contains file hashes and the actual failure sample at global tick 10998. Its
fly position was provably outside the old reachable set and is now hit by a
bounded, full approach/strike trajectory in a deterministic regression. This is
a geometry fixture, not a claim that changing physics exactly replays the old
human trajectory or would necessarily turn every historical miss into a hit.

## Recorder and provenance

Schema 2 adds `edge_analysis` only to WORLD/debug tick records:
fly center distance and body clearance to nearest wall; near-wall/corner flags;
signed maximum geometric reachable overlap; actual current overlap; whether the
head extends outside the viewport; and near-wall hit/miss outcomes. Near-wall
means body clearance <=24 units; near-corner requires that along both axes.
Reports aggregate the outcome flags. Static reachable overlap is not a guarantee
of immediate interception. Outcome position is the recorded post-step position.

The policy-observation whitelist and all neural/control inputs remain unchanged.
Schema-1 human sessions retain their source archives and require those historical
sources for exact replay; current replay rejects a schema/source mismatch clearly.
New sessions are verified against the new source and matching configuration.

The active calibration is versioned separately at
[calibration_room_m1_7_edge.json](calibration_room_m1_7_edge.json). Re-run command:

```text
python tools/calibrate_escape.py --config game_room_config.json --trials 28
```

Measured threshold remains 1.70: 28/28 detections; 0/2520 no-loom crossing ticks;
no-loom mean/p99/max 0.081292/1.000052/1.670433; loom mean/min/max peak
4.104506/3.441594/4.795575; median click latency 0.10 s. This is measured agreement,
not reuse of a stale record. Fixed-fly and 100-tick paddle settling protocol are
unchanged. LAB 1.45 and GAME 1.35 still match their preserved configurations.

## Actual validation

- 232/232 tests passed in 45.667 s: 217 existing M1.7 tests plus 15 edge tests.
  One obsolete all-head-visible assertion is explicitly updated to the new
  bounded-center/partial-offscreen contract; other M1.7 behaviors remain tested.
- All four walls, all four corners and the recorded failure location are hit by
  actual bounded approach/strike trajectories; test flies are held only in these
  geometry fixtures. No gameplay fly freeze or inward steering was introduced.
- A 3200-units/s grazing sweep hits an edge fly despite both 20-ms endpoints
  missing. A 0.2-unit-farther parallel near miss remains a miss. Partial offscreen
  geometry participates in both cases.
- Zero/one/seven clipped render calls produce identical collision results;
  acceleration/speed/rotation bounds and policy isolation regressions pass.
- Synthetic schema-2 recording: 1200 ticks, 1212 operations, three episodes,
  exact replay. [Session evidence](session_m1_7_edge.json).
- Real Windows renderer: 571 frames, all six phases; partial-offscreen corner
  capture, pause/resume, R restart, window/fullscreen toggles. Native recording
  replay: 247 ticks, 252 operations, two episodes, exact.
  [Native evidence](render_m1_7_edge.json).
- LAB/GAME/ROOM each pass `python -m game.app --arena ARENA --smoke 3`.
- Original verifier: 36 prediction records checked, source hashes match, both
  held-out neural replays exact and frozen weights verified. A write guard checks
  equality of historical verification JSON rather than rewriting it.
- All 20 protected original files, 19 pre-repair result files, 10 human-session
  files and 14 unaffected game modules retain their byte hashes. LAB/GAME configs,
  all fly/ecology settings and all existing paddle dynamic parameters are unchanged.
- `git diff --check` passes. No commit, push, merge or RL.

## Limits and requested human test

Reachability is geometric, not a guarantee of hitting a moving fly. Swept contact
still approximates paddle curves with <=2-ms segments and fly motion linearly
within 20 ms. The cosmetic handle is not a collider. At an edge, part of the head
or its phase label may be offscreen or beneath a HUD overlay; collision retains
the complete disk. This repair makes no difficulty/balance or learning claim.

```powershell
Set-Location D:\Projects\flybrain-lab
& .\.venv\Scripts\python.exe -m game.app --arena room --record
```

Please deliberately attempt strikes against the left, right, top and bottom wall,
and then all four corners. Include stationary aim and fast tangential sweeps,
in windowed and fullscreen modes if practical. Confirm REC and close normally.
Keep the printed session directory/report for review. Do not commit until this
human test is approved; do not start reinforcement learning.

## Files changed by this repair (relative to initial M1.7)

- `README.md`
- `game/ROOM.md`
- `game/SESSIONS.md`
- `game/edge_analysis.py`
- `game/physical_swatter.py`
- `game/replay.py`
- `game/session_recording.py`
- `game/world.py`
- `game_room_config.json`
- `results/game/M1_7_EDGE.md`
- `results/game/calibration_room_m1_7_edge.json`
- `results/game/edge_regression_m1_7.json`
- `results/game/render_m1_7_edge.json`
- `results/game/session_m1_7_edge.json`
- `test_game_edges.py`
- `test_game_m1_7.py`
