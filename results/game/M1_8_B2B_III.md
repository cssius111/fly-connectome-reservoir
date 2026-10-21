# M1.8-B2b-iii validation: ODOR_TRACK speed distribution

Status: **implemented and validated; awaiting the user's acceptance.**

Baseline: the accepted runtime `363a1a9` (M1.8-N4B5R, ROOM `config_version` 17). Design,
scope and acceptance checks were fixed before implementation in
[game/M1_8_B2B_III_DESIGN.md](../../game/M1_8_B2B_III_DESIGN.md) (`d42e123`) and approved
by the user on 2026-10-20. Implementation: `7b9fa05`.

Scope is ODOR_TRACK only. Unchanged: `room_kinematic_scale` = 1.0; all three caps =
1000.0 units/s; `escape_impulse` = 880.0; the legacy escape clamp; EXPLORE (B2b-ii),
TRANSIT, ODOR_SEARCH, RECOVER, ALERT, ESCAPE, LAND_APPROACH and TAKEOFF; the N4B1C
decoder, the N4B5R geometry, the M1.7.1 swatter and the M1.8-A lifecycle. No RL.

## 1. What changed

ODOR_TRACK speed was the shared deterministic 8 s sinusoid over the accepted 9-13 BL/s
envelope, lagged by the ecology's 0.5 s speed filter. It is now one draw per ecological
ODOR_TRACK episode from `triangular_symmetric(9.0, 11.0, 13.0)` BL/s
(`kinematics.odor_track_speed_bl_s`), by the B2b-ii method:

| Parameter | Value | Class | Justification |
| --- | --- | --- | --- |
| `distribution` | `triangular_symmetric` | C | No measured shape exists; avoids inventing skew |
| `min_bl_s`, `max_bl_s` | 9.0, 13.0 | B | Inherited from the accepted ODOR_TRACK envelope |
| `mode_bl_s` | 11.0 | C | The midpoint, so the mean equals the accepted sinusoid mean |
| Resample boundary | each ecological entry into ODOR_TRACK | C | Reuses the accepted state machine |
| Persistence | the ODOR_TRACK episode | unchanged | Ends on odor loss, the 8 s bout expiry, a landing attempt or a threat |

No parameter is class A. As for EXPLORE, the sampled target replaces the ecology's lagged
command, so the target steps at episode onset and the WORLD damping (3.0/s) smooths the
actual speed.

**Random stream.** EXPLORE keeps its stream at seed + 24593. ODOR_TRACK draws from its
own stream at seed + 30011, so the EXPLORE draw sequence is unchanged by construction. The
offset uniqueness test now lists every seeded stream, including the room's +6011, which
the earlier test omitted.

**Files.** `game/kinematics.py` (per-context specifications), `game/world.py` (wiring),
`game/session.py` (diagnostic hint for the record command only), `game_room_config.json`
(the new block; `config_version` 17 -> 18; the record path),
`results/game/calibration_room_m1_8_b2b_iii.json` (new record, written by
`tools/b2b_iii_record.py`), tests in `test_game_kinematics.py`, `test_game_lifecycle.py`
and `test_game_n4b5r_geometry.py`, and the tools listed in section 9.

## 2. Check 1: bit-identity and the exact first divergence

`tools/kinematics_trace.py` captures seven deterministic scenarios (4,060 ticks) as exact
float hex strings and every random stream's final state; `tools/kinematics_diff.py`
compares two captures.

**Code alone.** With the new code and the unchanged `config_version` 17, all seven
scenarios are bit-identical to the baseline capture (combined SHA256 `67248389...` before
and after) and every existing stream ends in an identical state. The only addition is the
new, unused `kinematics_odor_track` stream.

**Code and configuration.** With `config_version` 18:

| Scenario | Ticks | Identical | First divergence |
| --- | ---: | --- | --- |
| `room_quiet` | 1200 | no | tick 908, column `x`: the first airborne ODOR_TRACK tick, right after the voluntary takeoff; target 8.3323 -> 11.4818 BL/s |
| `room_perched_threat` | 340 | **yes** | none: the lifecycle owns the actuator throughout |
| `room_approach_threat` | 120 | **yes** | none: the lifecycle owns the actuator throughout |
| `room_airborne_seed101` | 900 | no | tick 85, column `x`: the first ODOR_TRACK tick; target 7.9710 -> 11.1598 BL/s |
| `room_no_ecology` | 600 | **yes** | none |
| `game_preset` | 500 | **yes** | none |
| `lab_preset` | 400 | **yes** | none |

Combined SHA256 `67248389...` -> `02e660af...`. In `room_quiet` the ecology is in
ODOR_TRACK from tick 5, but the fly lands, perches and feeds while the frozen lifecycle owns
the actuator, so no sample can act until it is airborne again at tick 908. The old target
below 9 BL/s at the divergence is the ecology's 0.5 s lag still approaching the band from
the previous state's speed.

The diff tool also reports the `ecology`, `flight` and EXPLORE `kinematics` streams as
changed in the two diverging scenarios. That is downstream feedback, not stream
consumption: every row before the divergence is identical, and check 2 shows the ODOR_TRACK
draws touch no other stream.

## 3. Check 2: stream isolation

`TestB2biiiOdorTrackSampling` in `test_game_kinematics.py`:

- 2,000 alternating sampler calls (25 ODOR_TRACK episodes) advance only the ODOR_TRACK
  stream: the ecology, flight, lifecycle, world, spawn and room streams and the EXPLORE
  stream stay byte-identical;
- 300 EXPLORE episodes give the identical draw sequence with or without interleaved
  ODOR_TRACK episodes;
- one draw per episode, a direct EXPLORE <-> ODOR_TRACK switch resamples both, no draw on
  threat-priority ticks or unconfigured contexts, and `reset` restores both streams;
- LAB and GAME have no ODOR_TRACK specification and never draw.

## 4. Check 3: offline distribution

200,000 seeded draws (`tools/odor_track_speed_diagnostics.py`), seed reproducibility
confirmed, EXPLORE stream untouched.

| Statistic | Sampled (triangular) | Accepted legacy sinusoid |
| --- | --- | --- |
| min / max | 9.006 / 12.990 | 9.000 / 13.000 |
| mean | **10.998** | **11.000** |
| median | 10.998 | 11.000 |
| sd | **0.8175** | **1.4142** |
| p05 / p95 | 9.629 / 12.368 | 9.025 / 12.975 |
| IQR | 1.177 | 2.828 |

Histogram, 12 equal bins over 9-13 BL/s:

```text
sampled : 0.014 0.042 0.070 0.098 0.124 0.153 0.152 0.125 0.097 0.069 0.042 0.014
legacy  : 0.186 0.081 0.066 0.058 0.055 0.053 0.053 0.055 0.058 0.066 0.081 0.186
```

All preregistered tolerances hold: support inside [9, 13], mean within 0.01 of 11.0
(-0.0018), sd within 0.01 of 0.816 (+0.0015). No comparison with biology is possible or
attempted.

## 5. Check 4: closed-loop diagnostics

Three 180 s no-player ROOM runs with the pointer parked far away, the B2b-ii diagnostic
seeds. Speeds are counted only on ticks where the ecology drives an airborne fly in that
context.

| Seed | Draws (EXPLORE / ODOR_TRACK) | ODOR_TRACK actual mean / sd | ODOR_TRACK requested mean / sd | Saccade interval median | Lifecycle events |
| --- | --- | --- | --- | --- | --- |
| 101 | 96 / 16 | 9.92 / 0.91 | 10.77 / 0.73 | 1.48 s | touchdown 2, feeding 1, voluntary takeoff 2 |
| 255 | 51 / 9 | 9.50 / 1.24 | 10.50 / 0.97 | 1.38 s | touchdown 5, feeding 5, voluntary takeoff 5 |
| 4242 | 96 / 33 | 9.56 / 1.81 | 10.67 / 0.71 | 1.66 s | touchdown 1, feeding 1 |

The requested means sit below 11.0 because each run holds only 9-33 episodes, weighted by
their length. The actual speed lags the requested target because ODOR_TRACK episodes are
short (0.8-1.6 s) against the 0.33 s WORLD damping time constant and start from a slower
state. Landing, feeding, perching and voluntary takeoff still occur in every seed. State
occupancy, which also counts perched ticks because the ecology keeps running while the
fly sits, changes between the configurations as the trajectories diverge (for seed 255,
ODOR_TRACK 0.25 -> 0.44 of alive time). Three seeds cannot separate a systematic effect
from closed-loop divergence, and none is claimed.
No hit rate, survival, escape rate or difficulty measure was computed here.

## 6. Check 5: paired free flight

`tools/b2b_iii_free_flight_check.py`: 80 fresh seeds (9101-9180, absent from every report,
tool and holdout list on every branch), 180 s each, no player, the pointer parked far away,
one Numba thread, run under both `config_version` 17 (read from `363a1a9`) and 18 with the
same code. Every policy escape was classified with the N4B4 counterfactual method: the run is
replayed with that escape withheld for 2 s, and the fly's closest horizontal approach to the
paddle centre within 1.5 s decides near pass or not.

| | Config 17 (accepted) | Config 18 (B2b-iii) |
| --- | --- | --- |
| Alive minutes | 240.0 | 240.0 |
| Escapes (rate, exact 95 % upper bound) | 12 (0.050/min, 0.081) | 9 (0.037/min, 0.065) |
| A: no LC4/LPLC2 drive in the 120 ms before | 0 (upper 0.012) | 0 (upper 0.012) |
| B: never within 310 units in 1.5 s without the escape | 1 (upper 0.020) | 2 (upper **0.026**) |
| C: near pass, expansion mostly from apparent-size change | 2 | 2 |
| D: near pass, expansion mostly from range change | 9 | 5 |
| Perched escapes | 0 | 0 |
| Escape channels (FAST / SUSTAINED / LATERAL) | 8 / 4 / 0 | 8 / 1 / 0 |

- **The preregistered criterion holds:** category B under the candidate is 2 in 240 min,
  upper bound 0.026/min, below 0.1/min.
- 66 of the 80 seeds give identical escape ticks in both arms; in the other 14 the
  trajectories diverge once ODOR_TRACK sampling acts. Between the arms, B goes 1 -> 2, C
  stays 2 and D goes 9 -> 5; with counts this small none of these differences is
  meaningful, and none is claimed. The accepted arm reproduces the N4B5R acceptance rate
  on fresh seeds (0.050/min, against 12 in 249 min = 0.048/min).
- One candidate event needs a plain description. Seed 9150, tick 6487 fires on the summed
  FAST path with almost no visual drive (0.017 over 120 ms) at 2,032 units from the paddle.
  By the rule it is B, not A, because the drive is not exactly zero; it resembles the
  known spontaneous FAST-path events of N4B1C (3 in 630 fixed-fly minutes), not a kinematic
  effect.
- The A and B rules follow N4B4. The C / D split is a reimplementation, not the N4B5
  tooling: it compares the range and apparent-size components of the expansion over the
  120 ms before the escape. Each arm has 2 C events. The accepted arm's two are mixed, with
  range and size components of similar magnitude; the candidate's two (seeds 9103 and 9124)
  are size-driven while the range slightly recedes, the residual tilt foreshortening that
  the accepted G3 geometry keeps at moderate elevation (180-230 units horizontally). C is
  tracked, not a failure.

## 7. Check 6: frozen systems

| Check | Result |
| --- | --- |
| Full unit suite | **440 tests, OK** (427 at the accepted runtime, +13) |
| `git diff --check` | clean |
| Code-only trace (config 17) | bit-identical, all seven scenarios and all streams (section 2) |
| Neural escape mechanics | `tools/escape_cruise_study.py` output identical at `363a1a9` and at `7b9fa05`: 54 cases, 18 that reduce speed |
| M1.8-A lifecycle scenarios | `tools/lifecycle_sanity.py`: voluntary, perched-threat and approach-threat scenarios replay exactly (1200 / 340 / 120 ticks) with their accepted event sets (voluntary takeoff; escape takeoff; approach abort) |
| Recorder exact replay | `tools/session_sanity.py`: `exact: true`, 1,200 ticks and 1,212 input operations, source verified, schema 4 at `config_version` 18; no schema bump was needed |
| Policy observation isolation | unchanged; covered by the suite |
| Calibration provenance | ROOM resolves 1.45 through `calibration_room_m1_8_b2b_iii.json`; the N4B5R record is byte-identical to `363a1a9` and still resolves for its own configuration; LAB 1.45 and GAME 1.35 unchanged |
| M1.7.1 swatter fixtures (`tools/approach_sanity.py`) | the four controlled fixtures are **identical** to `results/game/approach_m1_7_1.json`; the fixed-human-input part needs the M1.7.1 acceptance recording, which exists only on the local Windows checkout |
| 20 protected original files, `verify_results.py` | in git, all 20 files are byte-identical to `main` (`309abd9`); the working-copy check against `artifacts/m1-2/protected-before.json` and `verify_results.py` need the local `artifacts/` directory (section 11) |

## 8. Calibration

`results/game/calibration_room_m1_8_b2b_iii.json` (record kind
`kinematics-transfer-provenance-v1`) resolves to **1.45** with the unchanged N4B1C decoder
block and N4B5R geometry block. It names the N4B5R record by content SHA256, marks it
unmodified, names the original `calibration_room_m1_7_1.json` measurement by content
SHA256, and lists exactly the changed configuration paths: `config_version`,
`kinematics.odor_track_speed_bl_s`, `policy._comment` and `policy.calibration_paths`. No
recalibration is justified: fixed-fly-v2 disables ecology, fly motion and collisions. Unlike
the N4B5R record, this record carries no acceptance status, because records are immutable
and a status would go stale.

## 9. Reproduction

```text
python tools/b2b_iii_record.py
python tools/kinematics_trace.py --out artifacts/m1_8_b2b_iii/post-trace.json
python tools/kinematics_diff.py artifacts/m1_8_b2b_iii/pre-trace.json artifacts/m1_8_b2b_iii/post-trace.json
python tools/odor_track_speed_diagnostics.py
python tools/ecology_occupancy_audit.py
NUMBA_NUM_THREADS=1 python tools/b2b_iii_free_flight_check.py run --arm v17   # and --arm v18
NUMBA_NUM_THREADS=1 python tools/b2b_iii_free_flight_check.py classify
python tools/b2b_iii_free_flight_check.py summary
python -m unittest discover
```

The baseline trace must be captured at `363a1a9` or with `config_version` 17. All outputs go
to the git-ignored `artifacts/m1_8_b2b_iii/`.

## 10. Status

All seven preregistered checks pass or are documented as not runnable in this environment:
the working-copy check of the 20 protected files, `verify_results.py` and the
fixed-human-input swatter comparison need the local Windows checkout (section 11). B2b-iii is implemented and
validated; acceptance, including whether a human playtest is wanted for this stage, is the
user's decision.

Not done, deliberately: TRANSIT, ODOR_SEARCH or RECOVER sampling, acceleration or
deceleration models, timer removal, any change to the scale, the caps, the escape impulse,
the ALERT gate or the session's threat mapping, a recorder schema change, and any learning.
The ALERT interruption is documented separately in
[game/M1_8_ALERT_INTERRUPTION.md](../../game/M1_8_ALERT_INTERRUPTION.md); it is unchanged
by this stage.

## 11. Acceptance procedure (local Windows checkout)

Use a separate worktree checked out **with LF line endings**. `verify_results.py` compares
raw bytes of the original source files, and a `core.autocrlf` checkout expands them to CRLF
(the N4B5R report met the same issue).

```powershell
Set-Location D:\Projects\flybrain-lab
git fetch origin
git -c core.autocrlf=false worktree add --detach artifacts\worktrees\b2b-iii origin/claude/gracious-galileo-mxnbs9
$wt = "artifacts\worktrees\b2b-iii"
New-Item -ItemType Junction -Path "$wt\data" -Target "$PWD\data"
New-Item -ItemType Directory -Path "$wt\artifacts" | Out-Null
New-Item -ItemType Junction -Path "$wt\artifacts\results" -Target "$PWD\artifacts\results"
Set-Location $wt
$py = "D:\Projects\flybrain-lab\.venv\Scripts\python.exe"
```

Automated checks, each with its expected result:

```powershell
& $py tools\check_protected_files.py D:\Projects\flybrain-lab\artifacts\m1-2\protected-before.json   # 20 of 20 match
& $py verify_results.py                                  # 36 records, source hashes match, 2 exact replays
& $py -m unittest discover                               # Ran 440 tests ... OK
& $py tools\approach_sanity.py --session D:\Projects\flybrain-lab\results\game\sessions\20260921T013555.126134Z-cb64aa1a --report artifacts\approach.json
```

The last command must finish without an assertion error, which proves the recorded
configuration reproduces the recorded paddle exactly, and in its `fixed_human_input` block
every `old_*` field must equal the matching `new_*` field, because the swatter is unchanged.
(`results/game/approach_m1_7_1.json` used a different recording to compare the M1.7 and
M1.7.1 controllers, so its block is not the reference here.)

`check_protected_files.py` compares each file as it is, with CRLF normalised to LF and
with LF expanded to CRLF. The original `results/` outputs were written by Python on Windows
with CRLF, while git stores them with LF, so in an LF worktree they match in the CRLF form.
Run it with `--root D:\Projects\flybrain-lab` as well to check the main working copy.

Optional human playtest, about 5 minutes:

```powershell
& $py -m game.app --arena room --seed 255 --record --windowed
```

- Keep the pointer away first. The fly should find the odor, track it toward the food,
  land, feed and later leave on its own. Within one tracking bout its speed should stay
  steady instead of drifting with the old 8 s oscillation; separate bouts may differ.
- Then approach and strike with the paddle. Escapes should look and time as before, and a
  parked paddle should not cause new escapes.
- Press H for the HUD with the ecological state. The recording lands under
  `results/game/sessions/` in the worktree and can be replayed with `--replay`.

Acceptance is the user's decision. If the fly is harder or easier to hit, that is recorded
as an outcome, not used to tune anything.
