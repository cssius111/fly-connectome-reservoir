# M1.7.1 human recording and physical swatter

This milestone adds instrumentation and a ROOM interaction model. It does not
train a policy, modify connectome weights, or establish biological fidelity.
LAB/GAME retain legacy paddle dynamics. ROOM retains M1.6 ecology.

## Run and play

```powershell
Set-Location D:\Projects\flybrain-lab
& .\.venv\Scripts\python.exe -m game.app --arena room --record
```

The console prints the unique recording directory. REC remains visible with H
hidden. Optional `--windowed --seed 101` gives a reproducible initial episode.
Move slowly to stalk, then accelerate into left/right/diagonal sweeps and click.
Compare stationary clicks, rapid sweeps and edge-of-room approaches. Observe all
six paddle phases. H reveals neural/ecological diagnostics; F11 switches display
mode; Space/P pauses; R/Enter starts a fresh running episode. In fullscreen Esc
first returns to a window, then exits. Close normally to write the report.

Spend 5-10 minutes testing controllability, strike visibility, misses/hits and
restarts. The human need not photograph or transcribe the HUD. Share the entire
session directory or its REPORT.md and summary.json for review. Synthetic and
native render checks do not substitute for human judgments of balance.

```powershell
& .\.venv\Scripts\python.exe -m game.app --replay 'results/game/sessions/SESSION_ID'
& .\.venv\Scripts\python.exe tools\session_sanity.py
```

Replay is headless and requires the same game source, Python/dependency versions,
dataset hashes and recorded configuration/calibration. It verifies exact SHA256
of every deterministic tick field, including compact neural readouts. It does
not compare render timing or wall-clock pause duration, or claim full-brain
bit equality. CPU/platform differences may fail exact verification; no silent
tolerance fallback exists. A source mismatch fails clearly: restore the archived
source in an isolated checkout with the recorded environment. Archives are never
automatically executed. Current replay supports FixedEscapePolicy only.

## Files and schema 3

```text
results/game/sessions/                   # ignored by Git
  profile.json                          # cumulative counters, zero learning
  <UTC-microseconds>-<random-id>/
    manifest.json                       # config/provenance/source/data hashes
    source_snapshot.zip                 # exact game/*.py, including dirty code
    inputs.jsonl                        # ordered consumed simulation operations
    ticks.jsonl                         # offline WORLD and neural analysis
    policy_observations.jsonl            # unchanged restricted whitelist
    events.jsonl                        # onsets, outcomes, control events
    episodes.jsonl                      # seed, totals and closure reason
    strikes.json                        # inclusive ranges into ticks.jsonl
    summary.json                        # descriptive aggregate measures
    REPORT.md                           # automatic English summary
    replays/<unique-id>.json             # successful verification evidence
```

Each tick is 0.02 seconds (50 Hz), independent of render FPS. Pauses add no brain
samples. Dead-state animation ticks remain logged with `neural.brain_stepped=false`;
neural values are held. `simulation_time` is tick start and `post_step_time` is
its end. Retina and motor observations refer to pre-physics geometry; fly and
swatter fields refer to post-physics state. Presentation values are the latest UI
sample, not a second scientific clock. Large files flush every 50 ticks and at
episode boundaries/close. Forced termination can lose buffered rows and leaves
`closed_cleanly=false`; partial recovery is manual, never presented as exact replay.

The manifest stores schema, timestamp, commit/branch/dirty status, source hashes,
Python/library versions, dataset hashes, the actual full config and canonical
SHA256, raw config-file SHA256, archived matching calibration, arena/mode/seed,
20 ms tick, logical dimensions, body scale and actual ecology override. No dataset
or 166,700-neuron array is copied into a session.

Tick groups are:

| Group | Contents |
|---|---|
| Identifiers | global/episode tick, seed, times, config version/hash |
| fly | WORLD position, velocity, speed and BL/s, body/velocity heading, mismatch, finite-difference acceleration, alive |
| retina | theta, theta_dot, azimuth |
| visual_input / sensory_spikes / population | left/right LC4 and LPLC2 drive and activity summaries, selected population counts |
| neural / action | DNp01 and DNa02 left/right, DNp01 total, steering, threshold, refractory, generic policy diagnostics, action strength/turn |
| saccade | kind, remaining time, angle, duration and applied yaw |
| ecology / wall | local sense, state, requested/applied speed, landing approach, wall/perimeter/contact diagnostics |
| swatter / room_world | paddle geometry, target, velocity, acceleration, phase, strike ID and offline room debug |
| event_flags / stats | threat/ALERT/ESCAPE, crossing, strike start/active, hit/miss/death, restart/pause, cumulative outcomes |
| swatter_control | WORLD-only consumed pointer velocity/acceleration, target error, filtered command and first-sample validity |
| edge_analysis | center distance/body clearance to nearest wall, near-wall/corner, reachable/current overlap, offscreen head, near-wall outcomes |
| presentation | last render FPS, brain timing, HUD/fullscreen status |

`inputs.jsonl` records reset seeds, actual clamped pointer observations consumed
at each tick, clicks supplied to that tick, between-tick strike requests with
acceptance, and pause/resume controls. Ordering is retained even when a click is
followed immediately by restart or exit without another tick. Restart seeds are
explicit; display-only controls affect rendering rather than simulation inputs.

The policy file contains only the unchanged M1.5 neural/internal observation
whitelist and four-frame history, with action/outcome as separate fields. It
excludes mouse, paddle, food and obstacle coordinates and all room debug. No
training consumer or new policy inputs are implemented.

## Strike windows and summary definitions

`strikes.json` identifies episode/strike, click tick/time, nearest neural threat
onset within the window, fly poses at onset and strike, approach direction/speed,
acceleration trend, outcome, and an inclusive global row range covering up to
1 second before through 2 seconds after the click. Windows clip at episode
boundaries and are marked truncated. A click immediately followed by reset can
have `no_tick_sample=true` and an empty range (end < start). Retrieve a window:

```python
import json
from pathlib import Path
session = Path("results/game/sessions/SESSION_ID")
strike = json.loads((session / "strikes.json").read_text())[0]
a, b = strike["window_global_ticks"]
with (session / "ticks.jsonl").open() as source:
    rows = [json.loads(line) for i, line in enumerate(source) if a <= i <= b]
```

The summary includes simulation/wall durations, episodes, strikes, hits, misses,
incomplete strikes, hit/first-strike rates, onset/crossing counts, conditional
escape latency, living-tick mean/peak BL/s, state fractions, wall/perimeter/contact
time, odor encounters, landing attempts and eight 45-degree attack bins. Hit-rate
denominators include incomplete attempts, which are also reported separately.
Explicit *_all state fractions include dead ticks; *_alive fractions exclude them.
Alive means post-step fly.alive, so fatal ticks are excluded. Speed and ecology
statistics use these same explicit populations. Legacy unqualified state fields
retain all ticks, and legacy speed_bl_s retains pre-step-alive samples for
compatibility. Use the explicit fields for new analyses. Escape latency is the first new ESCAPE after
the click (within 2 seconds and before the next strike) minus the indexed neural
threat onset. Preexisting escapes and unavailable onset pairs are excluded;
this is a descriptive conditional statistic, not a causal reaction-time estimate.
Landing is an approach-only controller state, not implemented physical perching.

Profile counters start separately from historical `artifacts/game/player-default`.
One running writer per profile is supported; use different `--record-dir` roots
for simultaneous games. `policy_checkpoint` remains null and learning_updates=0.
JSONL is human-auditable but can reach hundreds of MB for a long session; no full
brain dump is enabled. Store/share session data deliberately; Git ignores it.

## Physical ROOM paddle

The mouse is a desired hand target, never a teleport. Ordinary approach combines
consumed pointer velocity (bounded at 1800) with position correction (6 times error,
bounded at 900), limits the sum to 1800, then filters the commanded velocity with
a 60-ms exponential filter at <=2-ms substeps. The existing 45-ms physical velocity
response and acceleration bounds remain. A large stationary error can therefore
request at most 900, while a deliberate fast pointer burst can still request 1800.
The first observed target after reset anchors the velocity estimate rather than
inventing a burst from initial placement. Recovery blends toward the same approach
command. No fly-distance lookup or hidden stalking mode is introduced. The legacy
position_gain=12 remains only as fallback for archived configs without
approach_tracking; active ROOM uses the new gain 6. Recent pointer history is
200 ms at the simulation clock. Least-squares velocity gives attack direction
and approach speed; first/second-half speed slopes estimate acceleration trend.
A stationary click keeps the current direction and uses the base swing speed.
Input variables stay in WORLD; the fly sees only their retinal consequences.

| Parameter | Current value |
|---|---:|
| Approach speed cap | 1,800 logical units/s |
| Overall speed cap | 3,200 logical units/s |
| Acceleration cap | 18,000 logical units/s^2 |
| Angular speed / acceleration | 6 rad/s / 24 rad/s^2 |
| Positional correction gain / cap | 6/s / 900 units/s |
| Filtered approach command / physical velocity time constants | 0.060 s / 0.045 s |
| Base swing speed | 320 units/s |
| Swing speed target | min(3,200, 320 + 0.9 * approach_speed + 0.025 * positive_acceleration_trend) |
| Internal paddle integration step | at most 2 ms; brain remains 20 ms |

| Phase | Duration |
|---|---:|
| APPROACH | unrestricted |
| COMMIT | 100 ms |
| FAST_SWING | 120 ms |
| ACTIVE_CONTACT | 100 ms |
| FOLLOW_THROUGH | 140 ms |
| RECOVERY | 300 ms |

The committed cycle lasts 760 ms. Height/face change continuously, direction
rotates with bounded angular acceleration, follow-through retains motion, and
recovery blends back to ordinary hand control. The physical center is bounded to [0,3840] x [0,2160], with the existing
0.5-unit stopping deadband. The 144-unit head may extend beyond the viewport.
No fly bounds or motor limits change; rendering clips only presentation. Geometry uses configurable smooth keyframes;
vertical speed/acceleration are not a biomechanical model. The circular head persists in all phases; it may be partially clipped at viewport edges, with color and phase labels.

Contact is lethal only during ACTIVE_CONTACT. Each active paddle subsegment is
tested against the fly's simultaneous interpolated segment using minimum relative
disk separation (paddle radius + fly radius). Phase boundaries split substeps.
This catches crossings missed by endpoint tests. The fly trajectory is linear
within a 20 ms tick, and paddle curves are linear within <=2 ms; this is a swept
collision approximation, not an exact curved/rotating rigid-body solver. The
circular hit area intentionally does not depend on decorative handle orientation.

## Calibration and preserved science

The active ROOM record is `results/game/calibration_room_m1_7_1.json` (threshold
1.45), with exact config/runtime provenance. Run:

```text
python tools/calibrate_escape.py --config game_room_config.json --trials 28
```

The fly is fixed, velocity is zero, wandering/escape/collisions are disabled.
The inertial paddle settles for 300 ticks (6 seconds) before measurement.
LAB/GAME settings, records and historical M1.6 evidence are preserved.
The runtime remains MaleCNS-derived: sensory_input=false removes incoming
sensory-neuron edges (25,088,107 runtime vs 25,582,938 original connections).
The architecture remains physical geometry -> Retina -> LC4/LPLC2 -> frozen
MaleCNS -> descending readout -> fixed action. High hit/escape rates do not
validate biological learning, advantage of true connectivity, or difficulty.

## Optional future brain capture design (not implemented)

A separate opt-in recorder could use sparse active-neuron indices/values at a
configured stride, whole-brain snapshots at 1 Hz or below, or a bounded ring buffer
saved only near strike events. It should record neuron IDs, dtype, sampling clock,
compression and volume limits in a new schema, and store binary chunks separately
from JSONL. It must never expand the policy whitelist or become required for
ordinary play/replay. M1.7 implements none of these full-brain modes.

## Edge repair and historical recordings

The original M1.7 inset (144 radius + 0.3 * 320 hover height = 240 units)
created unreachable edge and corner regions. The active config version 9 retains
`swatter.physical.center_inset=0`. Fly centers remain [59,3781] x [59,2101].
Every legal center can be approached by the paddle; full disk geometry participates
in swept collision even when its rendered head extends past the viewport.
The viewport is presentation, the ROOM domain contains fly/environment dynamics,
and the paddle is a separate player-controlled physical object.

Recorder schema 2 adds offline `edge_analysis`. Nearest-wall distance measures
fly CENTER to the inner ROOM wall; body clearance subtracts the 11-unit fly radius.
Near-wall means body clearance <=24 units; near-corner requires this along both
axes. `swatter_reachable_overlap` is (144+11) minus distance to the nominal paddle
center rectangle: a static geometric coverage test, not a claim of immediate
interception under velocity/acceleration limits. Current overlap uses current
centers. Hit/miss flags use the post-step fly position. These privileged fields
are absent from policy observations. Reports add near-wall outcome counts.

Schema-1 recordings and reports remain unchanged and require their archived
schema-1 game source for exact replay. Changed paddle physics intentionally changes
new trajectories; old trajectories must not be represented as new-code exact replay.
See [edge audit and validation](../results/game/M1_7_EDGE.md). Human validation
must now deliberately target the fly along every wall and all four corners.

## M1.7.1 replay runtime and acceptance

Schema 3 records actual `numba_threads` and `numba_threading_layer`. FlyBrain's
float32 reduction order depends on thread count. The real M1.7 recording
20260920T200809.608987Z-32182677 failed at tick 278 with four threads, but all
15,039 ticks replayed exactly with eight using its original source. Its schema-2
manifest had omitted that runtime parameter. This is not corrected by changing
historical data or relaxing equality tolerances.

New replay uses Numba's initialized-pool API to restore the recorded thread count
and restores the caller's count afterward. A late NUMBA_NUM_THREADS environment
change can reload Numba's config without resizing its pool; the actual API, not
that mutable config value, is authoritative. If the recorded count exceeds the
available pool, replay fails with the required environment setting. For example:

```powershell
$env:NUMBA_NUM_THREADS = '8' # use the value from this session's manifest
& .\.venv\Scripts\python.exe -m game.app --replay 'results/game/sessions/SESSION_ID'
```

Schema-1/2 sessions require their archived code and original runtime. New tick
logs include deterministic control diagnostics. Reports give pointer/head speed
percentiles during post-step-alive APPROACH and time >=95% of its speed cap;
pointer derivatives exclude each episode's first tick. Paused wall time and raw
OS mouse-event timing are not reconstructed. Consumed logical target speed is
not physical hand speed.

For a short new recorded human acceptance session, try in sequence: very slow
stalking; medium repositioning; slow stalking then sudden burst; fast lateral
sweep; deliberate edge/corner hit. Close normally, then provide the session path.
The automatic report contains hit/miss counts, all/alive ALERT/ESCAPE fractions,
pointer/head speed distributions and cap fraction. Verify the session with the
replay command. `python tools/analyze_session.py SESSION_DIRECTORY` performs
read-only detailed derivative/geometry analysis into a separate ignored artifact
folder. Synthetic fixed-input comparisons cannot substitute for this new human
session or predict its hit rate.

Human acceptance is now complete using session 20260921T013555.126134Z-cb64aa1a.
All 6,911 ticks replay exactly with the recorded eight-thread OpenMP runtime.
See [final acceptance](../results/game/M1_7_1_ACCEPTANCE.md). The physical controller,
strike phases, swept collision, partial-offscreen geometry, recorder/replay interface
and WORLD/policy separation are frozen unless future recorded evidence shows a defect.
The checklist above remains available for later defect reproduction.
