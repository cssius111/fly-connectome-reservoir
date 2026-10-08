# M1.8-N2b: gap-tolerant dual-path DNp01 escape decoder

Status: **implemented and automatically validated; second human re-acceptance FAILED on
threat-response latency and slow-approach insensitivity; not committed.** The failure
record is section 12. The follow-up research is `game/M1_8_N3_NEURAL_EVIDENCE_INTEGRATION.md`.

N2b replaces the uncommitted strict N2 candidate (FAST 2.20 OR 3 consecutive samples),
whose human re-acceptance failed on escape latency. Baseline: `76806f0`. Scope: the escape
criterion only. Retina, LC4/LPLC2, MaleCNS, brain noise, motor strength mapping,
steering/asymmetry, saccades, refractory duration, lifecycle, swatter physics,
`escape_impulse`, caps, recorder schema, ecology, kinematics and RL are unchanged.

Artifacts: `artifacts/m1_8_n2b/`. Tools: `tools/n2b_decoder_record.py`,
`tools/n2b_validation.py`, `tools/n2b_preclick_diagnosis.py`, `tools/n2_closed_loop.py`.
Tests: `test_game_n2_decoder.py`.

## 1. Exact decoder semantics (`dual_path_window_v1`)

Per 20 ms sample, with total = summed DNp01 trace and H = total >= 1.45:

1. Append the H/L flag of the current sample to a rolling window of the **5 most recent
   samples, including the current one**. This happens on every sample, refractory samples
   included, so the window never holds more than 5 flags.
2. Side accumulators, alert state, steering and saccade logic run exactly as before.
3. If refractory: no escape is possible on this sample.
4. Otherwise:
   - **FAST** if total >= **2.10**;
   - else **SUSTAINED** if **the current sample is H** AND the window holds **>= 3 H**;
   - else no escape. The sample behaves exactly as a sub-threshold sample (ALERT/CALM).
5. On an escape: 20-sample refractory, the window is cleared, and the channel is recorded.
   `reset()` also clears the window.

FAST takes precedence in the channel diagnostic when both paths hold. A current L sample
can **never** fire SUSTAINED. Evidence older than 5 samples (80 ms) cannot contribute, and
evidence from before an escape is discarded. Strength (`min(1, total / 2.9)`), side,
steering and saccade use the actual trigger sample and are unchanged.

Examples (unit-tested): `HHH` fires on the third H; `HLHH`, `HLLHH` and `HHLLH` fire on the
final H. `HHLLL`, `HH`, `LLLHH` and `HLH` never fire. `LLHH` waits for a third H. `HHH` then
L at refractory expiry does not fire. `HHLLLHH` does not fire because the first two H have
left the window.

**Parameters** (explicit in `game_room_config.json`, config_version 15):
`kind dual_path_window_v1`, `sustained_threshold 1.45`, `fast_threshold 2.1`,
`sustained_window_samples 5`, `sustained_required_samples 3`,
`require_current_qualifying true`. `require_current_qualifying` must be `true`; the
configuration and the constructor both reject plain 3-of-5. The values 2.10, 3 and 5 are
Class C engineering decoder parameters, not biological constants.

**Why FAST 2.10.** It is the lowest round value that passes N0. It catches the 2.1197
early-peak level of committed looms, and it does not fire on the recorded far perched
human approach (peak 2.0557) (`M1_8_N2_FAST_THRESHOLD_REVIEW.md`).

**Why the current sample must qualify.** Plain 3-of-5 can fire on a sub-threshold sample at
refractory expiry, from evidence up to 80 ms old collected during the refractory period.
That is a stale post-refractory escape, so it was rejected
(`M1_8_N2_TEMPORAL_REVIEW.md`).

The strict `dual_path_v1` kind is retained, with its own exact key set, so that sessions
recorded under strict N2 still replay exactly (section 7).

## 2. Provenance

`results/game/calibration_room_m1_8_n2b.json` (SHA256 `2b550c73...1085`), produced
deterministically by `tools/n2b_decoder_record.py`:
- `record_kind: gap-tolerant-dual-path-decoder-provenance-v1`,
  `not_a_scalar_calibration: true`; no sweep or detection fields.
- The inherited 1.45 is traced through `calibration_room_m1_8_b2b_ii.json` to the original
  measurement `calibration_room_m1_7_1.json`, both by SHA256.
- Evidence by SHA256:
  - N0 no-loom study (commit `3d41113`);
  - N1 loom robustness (commit `76806f0`);
  - FAST-threshold review;
  - temporal-rule review.
- `supersedes`: the strict N2 record by SHA256 (`95d09955...c6adf`), marked **not
  modified**. It is byte-identical and still loads for the preserved v14 strict
  configuration.
- The changed config paths relative to `76806f0` are exactly `config_version`,
  `policy._comment`, `policy.calibration_paths` and `policy.escape_decoder`.

The resolver requires an exact match of the kind's key set:
- a scalar record cannot load N2b;
- a strict N2 record cannot load N2b;
- neither dual-path record can load a single-sample configuration;
- any parameter change invalidates provenance;
- no geometry or world key can be configured.

Historical calibration records are byte-identical to `76806f0`. Resolution: LAB 1.45
(single-sample), GAME 1.35 (single-sample), ROOM 1.45 plus `dual_path_window_v1`.

## 3. N0 exact runtime replay (210,000 ticks, 70.0 min)

| Decoder | FAST | SUSTAINED | Total | Events/min | 95% one-sided upper bound |
| --- | --- | --- | --- | --- | --- |
| legacy | - | - | 91 | 1.300 | 1.547 |
| strict N2 | 0 | 0 | 0 | 0 | 0.043 |
| **N2b** | **0** | **0** | **0** | **0 observed** | **0.043** |

The continuous 10-minute arm also has 0 events. **Acceptance < 0.1/min at ~95%: met.**
The N2b replay matches the research subclass exactly (0 = 0). The tail model is not used
as acceptance evidence. < 0.01/min is not demonstrated.

## 4. N1 exact runtime replay (300 trials)

**Every trial's firing ticks and channels match the temporal research study exactly.**

| Class | legacy | strict N2 | **N2b fired (FAST/SUSTAINED)** | N2b median / p95 |
| --- | --- | --- | --- | --- |
| strong_direct | 60 | 60 | **60 (60/0)** | 0.10 / 0.12 s from click |
| medium_committed | 60 | 60 | **60 (55/5)** | 0.14 / 0.18 s from click |
| weak_approach | 55 | 16 | 29 (16/13) | 0.76 / 1.53 s from onset |
| glancing_pass | 51 | 9 | 27 (11/16) | 0.42 / 0.59 s from onset |
| aborted_approach | 58 | 19 | 44 (18/26) | 0.50 / 0.64 s from onset |

Committed-strike latency from the click, median / p95:

| | legacy | strict N2 | N2b |
| --- | --- | --- | --- |
| strong_direct | 0.08 / 0.08 | 0.10 / 0.16 | **0.10 / 0.12** |
| medium_committed | 0.08 / 0.10 | 0.16 / 0.18 | **0.14 / 0.18** |

The N0 150-trial loom arm is 150/150 (148 FAST, 2 SUSTAINED). The weak, glancing and
aborted classes are descriptive only; their firing roughly doubles against strict N2.

## 5. Human-recording counterfactual

Session `results/game/sessions/20260923T005351.731330Z-38255ec8` (strict N2, 31 strikes).
The recorded strict policy, rebuilt from the recorded configuration, reproduces **all 7025
recorded actions (0 mismatches)**. At each click the runtime N2b policy receives the
recorded policy's exact state and a window rebuilt from the recorded neural stream.

| Decoder | Fired | FAST / SUSTAINED | Median | Mean | p95 |
| --- | --- | --- | --- | --- | --- |
| legacy (research counterfactual) | 26/31 | - | 0.08 s | 0.076 s | 0.185 s |
| strict N2 (recorded) | 24/31 | 22 / 2 | 0.14 s | 0.129 s | 0.18 s |
| **N2b (runtime)** | 24/31 | 16 / 8 | **0.12 s** | **0.112 s** | 0.16 s |

These are the actual runtime numbers, and they match the research subclass strike by strike
(latency, channel and pre-click escape). Pre-click hover segments with an escape: 20
(strict 12).

**The far perched non-contact approach (peak 2.0557 at 50.26 s) does not fire under N2b.**
Neither perched interval fires.

## 6. Closed-loop ROOM validation (final run)

`artifacts/m1_8_n2b/closed_loop.json`. Real chain throughout: pointer -> physical swatter
-> Retina -> LC4/LPLC2 -> MaleCNS -> DNp01 -> decoder -> Action -> lifecycle/physics. Three
decoders (legacy, strict N2 from the preserved v14 configuration, N2b) run on identical
seeds, using the natural-perch seed set (255, 101, 14, 15, 16, 21, 28, 39, 46, 57) and
`criterion_diagnostics()`.

### 6.1 Pre-click escape diagnosis and the corrected fixture

Two N2b system tests initially escaped before the click. Each was diagnosed tick by tick
(`tools/n2b_preclick_diagnosis.py`, `artifacts/m1_8_n2b/preclick_diagnosis.json`). No seed
was changed.

**Perched strike, seed 255.** First pre-click escape at tick 172: 0.70 s after the fixture
and 1.30 s before the click, via SUSTAINED at DNp01 1.806 (R 1.652 / L 0.154), still
TAKEOFF_ESCAPE-eligible. At that tick:
- the paddle was **moving** (10.8 units/s, 11 units from the fly; up to 136 units/s during
  the hold);
- theta_dot was +0.23 (+0.25 to +0.49 over the previous 10 samples);
- LC4-R / LPLC2-R drive was 0.09-0.20.

Window evolution over the previous samples: `LLLLH` -> `LLLHL` -> ... -> `HLLLH` ->
`LLLHH` -> `LHHLL`, then the firing H.

**Classification B: setup transient not settled out.** Placing the paddle instantly
produced a one-sample retinal spike (theta_dot 22 rad/s). The physical swatter also
interpreted the placement as a pointer jump and drove the paddle while it settled.

**Corrected fixture.** Immediately after placement, the projector's own reset (as at a
session reset) and `PhysicalSwatter.reset()` ("initial placement is not an observed
movement") are applied. Each hold is then **verified**: paddle speed 0.0, theta_dot 0.0,
LC4/LPLC2 drive 0.0 for every sample. Peak DNp01 during the hold was 0.022, and the fly was
still perched at the click. An intermediate correction that only reset the projector left
drive up to 0.39, so it was rejected; its run is kept as
`closed_loop_superseded_projector_reset_only.json`.

**Airborne strike, seed 11.** First pre-click escape at tick 105, 0.50 s before the click,
via SUSTAINED at 1.599. The paddle was chasing the fly at hover height (1110 units/s,
332 units away), with theta_dot +0.51 and nonzero drive throughout. **Classification A:
legitimate looming.** The scenario's pre-click phase is a real approach by design, so the
test now asserts that every escape coincides with nonzero LC4/LPLC2 drive, instead of
asserting that no pre-click escape occurs.

**No N2b pre-click escape was a no-loom false trigger (class C).** Under legacy, seed 101
has two zero-loom `LLLLH` single-sample escapes (DNp01 1.4616, 47 samples into a verified
clean hold): the documented legacy defect, which N2b does not reproduce. Under legacy only,
seed 28 never perches (a legacy escape aborts its landing approach); under strict N2 and
N2b it perches normally.

### 6.2 Natural arm: each decoder controls the episode (primary evidence)

| Scenario | Metric | legacy | strict N2 | N2b |
| --- | --- | --- | --- | --- |
| A perched committed strike (20) | perched at click | 16 | 20 | **20** |
| | pre-click escapes | 4 | 0 | **0** |
| | neural TAKEOFF_ESCAPE after click, of those perched | 16/16 | 20/20 | **20/20** |
| | channel | single 20 | FAST 20 | **FAST 20** |
| | median / p95 latency from click | 0.08 / 0.16 s | 0.10 / 0.16 s | **0.10 / 0.12 s** |
| | hit (diagnostic only) | 16 | 20 | 20 |
| B airborne committed strike (12) | post-click escape | 11 | 12 | 10 |
| | median / p95 | 0.08 / 0.22 s | 0.12 / 0.15 s | 0.11 / 0.18 s |
| | pre-click escapes (hover chase) | 27 | 7 | 16 (13 S, 3 F) |
| C accepted M1.8-A no-click perched threat | neural TAKEOFF_ESCAPE | tick 197 | tick 238 SUSTAINED | **tick 221 SUSTAINED** |
| D non-contact hover approaches (9) | escapes, descriptive | 28 | 5 | 12 (6 F, 6 S) |
| E no player (3 x 9000 ticks, 9 min) | escapes | 20 | 0 | **1** |
| | voluntary takeoffs | 3 | 7 | 7 |
| | maximum swatter speed | 0.0 | 0.0 | 0.0 |

**The single no-player N2b escape** (seed 4242, tick 7400, FAST) is flagged. DNp01 jumped
from 0.136 to **2.111** in one sample: a two-spike tick on residual trace, the mechanism the
N0 tail model predicts. The fly was flying toward the static paddle 760 units away, with
weak real expansion (theta_dot 0.045, encoder drive 0.024), so it is not a zero-loom event.
Strict N2 (FAST 2.20) would not have fired on 2.111. Classification: D, another identified
mechanism (a two-spike coincidence reaching FAST during weak self-motion expansion). One
event in 9 minutes gives a 95% interval that cannot distinguish this from the N0 bound.

### 6.3 Controlled arm (counterfactual diagnostic only)

N2b drives until the click; each candidate then takes over from the identical state.
- **Perched A:** all 60 candidate runs start from a verified zero-loom hold and none is
  refractory at the click, so all are clean latency comparisons. Median / p95: legacy
  0.08 / 0.08 s, strict N2 0.10 / 0.16 s, N2b 0.10 / 0.12 s. All perched runs are hit
  under every decoder.
- **Airborne B:** confounded runs, where the candidate is refractory at the click from an
  internal pre-click fire: legacy 5, strict N2 2, N2b 3. They are excluded from latency
  comparison.

## 7. Recorder and replay preservation

- Recording schema remains exactly **4**. `policy.diagnostics()` keeps exactly the frozen
  legacy key set, and the rolling window and trigger channel are not persisted in
  `ticks.jsonl` (tested). `criterion_diagnostics()` remains outside recorder persistence.
- A new N2b ROOM session with a perched escape takeoff replays **exactly** (test).
- A pre-N2 recording (legacy config v13, `76806f0` source) replays **exactly, 250/250
  ticks**.
- The strict-N2 human session (`dual_path_v1`, v14) replays **exactly, 9387/9387 ticks**,
  with its recorded 8 Numba threads.
- Both historical recordings are rejected under strict source checking, as designed for any
  source difference.
- M1.8-A lifecycle scenarios: identical event counts; exact replay 1200 / 340 / 120.

## 8. First intentional divergence

Pre-change DNp01 streams from full-precision traces were replayed through each reference
decoder and N2b. The first trace-row divergence (`tools/kinematics_diff.py`) was then
checked against the first decision divergence.

**vs `76806f0`:**

| Scenario | Tick | DNp01 | legacy action | N2b action | Window (last 5) |
| --- | --- | --- | --- | --- | --- |
| room_quiet | 1001 | 1.819 | escape | none | `LLLLH` |
| room_perched_threat | 274 | 1.512 | escape | none | `LLLLH` |
| room_approach_threat | 56 | 1.623 | escape | none | `LLLLH` |
| room_airborne_seed101 | 343 | 1.462 | escape | none | `LLLLH` |

Legacy fires on a lone qualifying sample; N2b needs FAST (below 2.10 here) or 3 of 5 with
the current sample qualifying (only 1 of 5 here). Before the decision, legacy was not
refractory: it fired.

**vs strict N2:**

| Scenario | Tick | DNp01 | strict action | N2b action | Window | Strict streak / refractory |
| --- | --- | --- | --- | --- | --- | --- |
| room_perched_threat | 283 | 1.518 | none | **SUSTAINED** | `HLLHH` | 2 / 0 |
| room_approach_threat | 64 | 1.596 | none | **SUSTAINED** | `HLLHH` | 2 / 0 |

N2b fires earlier because the window counts 3 H across a two-sample dip while the strict
streak is only 2. `room_quiet` and `room_airborne_seed101` are bit-identical to strict N2.
In every case the trace-row divergence occurs on exactly the decision tick; **no world
divergence precedes a decoder decision difference**. LAB, GAME and ROOM-no-ecology traces
are bit-identical to both baselines.

## 9. Regression and frozen-system verification

| Check | Result |
| --- | --- |
| Full suite | **386 tests, OK** (330 at the `76806f0` baseline + 56 in `test_game_n2_decoder.py`) |
| `git diff --check` | clean |
| 20 protected original files | SHA256 unchanged |
| 58-file frozen baseline | 57 unchanged; `game/action.py` changed (the versioned decoder change) |
| `verify_results.py` | 36 predictions, source hashes match, 2/2 exact neuronal replays, frozen weights |
| M1.7.1 swatter fixtures | identical to `approach_m1_7_1.json` |
| M1.8-A lifecycle scenarios | event counts unchanged; exact replay 1200 / 340 / 120 |
| Recorder | schema 4; N2b, pre-N2 and strict-N2 sessions replay exactly |
| Policy-observation isolation | unchanged (existing test) |
| Calibration resolution | LAB 1.45, GAME 1.35, ROOM 1.45 plus `dual_path_window_v1` |
| Strict N2 record | byte-identical (`95d09955...`) |

## 10. Known limitations

1. **Latency remains above legacy.** Human attacks: mean 0.112 s against 0.076 s (legacy)
   and 0.129 s (strict N2). N1 medium: 0.14 s against 0.08 s. A 3-sample rule has a 40 ms
   structural floor after the first qualifying sample.
2. **More non-contact and hover-approach escapes than strict N2**: N1 weak / glancing /
   aborted 29 / 27 / 44 (strict 16 / 9 / 19); human pre-click segments 20 (strict 12);
   closed-loop hover approaches 12 (strict 5). All are still far below legacy.
3. **One no-player FAST escape in 9 minutes** (section 6.2), from a two-spike coincidence
   during weak expansion. FAST 2.10 is closer to the two-spike-plus-residual level than
   2.20.
4. A perched fly under a committed strike is hit in every perched run under every decoder,
   legacy included. This is pre-existing strike physics, not a decoder effect.
5. The N0 bound is 0.043/min; < 0.01/min is not demonstrated.
6. One human session, one tester. N1 classes are scripted fixed-fly probes.
7. The trigger channel is not persisted in recordings.
8. The scenario A fixture relies on two component resets (projector and physical swatter)
   to represent "the paddle was already there". This is documented and verified zero-loom,
   but it is still a fixture.

## 11. Second human re-acceptance checklist (ROOM)

1. Attacks on an airborne fly: does the escape now feel responsive enough? This is the
   criterion that failed; expect about 17 ms faster on average than the failed strict N2.
2. Committed strikes that start far from the fly: note any residual "late" feel.
3. A committed strike on a perched fly produces a visible escape takeoff.
4. The accepted no-click perched threat (paddle moved over the perched fly) still launches
   the fly.
5. Far, non-contact approaches to a perched fly do not launch it.
6. With no player input: no spontaneous escape jumps during several minutes; landing,
   feeding and voluntary takeoff look normal.
7. Hover-height passes: judge whether the somewhat higher reaction rate (compared with the
   failed candidate) is acceptable.
8. Record a session and confirm that it saves and replays.

Nothing is committed or pushed. B2b-iii, TRANSIT/ODOR, `room_kinematic_scale`, caps,
`escape_impulse`, brain noise and RL are untouched.

## 12. Second human re-acceptance: FAILED

Session: `results/game/sessions/20260924T000111.561327Z-c337a721` (recorded under this
working-tree N2b decoder, config v15, recorder schema 4).

Tester report:

1. Normal direct attacks still feel clearly sluggish.
2. No obvious unexplained escapes were observed.
3. Slow, non-contact approaches are much too insensitive: the paddle can get essentially
   on top of the fly before it appears to react.
4. Escape direction looks normal.

Recorded evidence:

- The single perched departure the tester saw (about 18.44 s) was `TAKEOFF_VOLUNTARY`
  (`local_history_motivation`), not an escape: swatter speed 0, center distance about 2969
  units, theta_dot 0, encoder drive 0, DNp01 total about 0.165, threat state CALM,
  `Action.escape` false. Session lifecycle: voluntary_takeoff 1, escape_takeoff 0.
- Episode 5, ticks 610-669 (about 1.2 s, no strike active, airborne fly): center distance
  below 100 units throughout (median about 62.6, minimum about 10.7 units; 2.6 BL and
  0.45 BL at 24 units/BL), positive encoder drive on 31/60 ticks, DNp01 mean about 0.61
  (far non-strike ticks: about 0.12). DNp01 >= 1.45 on three isolated samples only, never
  >= 2.10, and no 5-sample window held more than one qualifying sample, so N2b could not
  fire by construction. The first escape came at tick 670 via FAST, after theta_dot had
  already turned negative (the paddle was starting to recede).
- Direct strikes with a new escape pulse: click to escape 0.14 / 0.06 / 0.02 / 0.02 s, but
  recorded neural threat onset (policy ALERT onset) to escape 0.22 / 0.96 / 0.08 / 0.16 s.
  The sluggish feel is therefore mostly upstream of motor execution: threat acquisition and
  the conversion of DNp01 evidence into an escape decision.

Decision: N2b is rejected. It is not accepted or frozen, and it is not committed or pushed.
The working tree and these reports are kept as failed-candidate evidence. As planned, the
k-of-n windows and the FAST threshold are not tuned further; the next step is the
research-only M1.8-N3 study.
