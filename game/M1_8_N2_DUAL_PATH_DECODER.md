# M1.8-N2: dual-path DNp01 escape decoder

Status: **implemented and automatically validated; human re-acceptance FAILED on escape
latency; not committed.** The follow-up FAST-threshold sensitivity study is in
`game/M1_8_N2_FAST_THRESHOLD_REVIEW.md`. Parameters are unchanged pending a decision.

Baseline: `76806f0` (N1, clean committed HEAD). Scope: the escape criterion only. Retina,
LC4/LPLC2 encoder, MaleCNS, brain noise, ecology, lifecycle architecture, physical
swatter, escape impulse, speed caps, `room_kinematic_scale`, recorder schema and RL are
unchanged. 2.20 and 3 samples were not retuned.

Artifacts: `artifacts/m1_8_n2/` (git-ignored). Tools: `tools/n2_decoder_record.py`,
`tools/n2_decoder_replay.py`, `tools/n2_closed_loop.py`. Tests: `test_game_n2_decoder.py`.

## 1. Implementation

### 1.1 Decoder state machine (`game/action.py`, `FixedEscapePolicy.decide`)

Per 20 ms sample, with `total` = summed DNp01 trace:

1. `streak = streak + 1` if `total >= 1.45`, else `streak = 0`. This runs on **every**
   sample, including refractory samples.
2. Side accumulators, alert state, steering and saccade logic run exactly as before.
3. If refractory: decrement the cooldown; no escape is possible on this sample.
4. Otherwise the criterion is evaluated:
   - **FAST** if `total >= 2.20`;
   - else **SUSTAINED** if `streak >= 3`;
   - else no escape (the sample behaves as ALERT/CALM exactly as a sub-threshold sample).
5. On an escape: cooldown = 20 samples (0.4 s), `streak = 0`, channel recorded.

FAST takes precedence when both paths hold on the same sample. Strength
(`min(1, total / (2 * 1.45))`), side/asymmetry, steering, saccade and the alert threshold
(`0.55 * 1.45`) are unchanged and use the actual trigger sample; strength is **not**
rescaled around 2.20.

### 1.2 Persistence accounting

`persistence_samples = 3` means three consecutive qualifying samples **including** the
first: t, t + 20 ms, t + 40 ms. The structural delay is **40 ms**, not 60 ms. Any larger
measured latency comes from signal shape or crossing history (section 5).

### 1.3 Refractory semantics

- The policy cannot fire during the 20 refractory samples.
- Evidence still sustained at expiry fires on the first eligible sample.
- A signal that drops below 1.45 during refractory resets the streak, so stale evidence
  cannot cause a later escape.

### 1.4 Class C status

2.20 and 3 samples are Class C decoder parameters chosen to separate the simulator's
spontaneous DNp01 coincidences from sustained threat evidence. They are not biological
constants.

### 1.5 Scope by arena

The dual-path criterion is enabled only in ROOM, where the N0/N1 evidence was measured.
`game_config.json` (LAB) and `game_play_config.json` (GAME) are frozen files, so they keep
the single-sample decoder and their bytes are unchanged. The single-sample path is proven
bit-identical to the `76806f0` source on 16,000 random samples, and LAB/GAME traces are
bit-identical (section 9).

### 1.6 Diagnostics and the recorder

`diagnostics()` keeps exactly the legacy key set (`escape_threshold`, `refractory_seconds`,
`behavior_state`, `escape_strength`), because the session recorder persists that mapping
verbatim in every tick row. Trigger provenance is exposed only through
`FixedEscapePolicy.criterion_diagnostics()`: `escape_decoder`, thresholds, persistence,
current streak and `escape_trigger_channel` (FAST / SUSTAINED / SINGLE_SAMPLE / NONE). The
recorder does not call it. A future versioned recorder milestone may persist the channel
if needed.

## 2. Configuration, calibration and provenance

`game_room_config.json` (config_version 13 -> 14) adds:

```json
"escape_decoder": {"kind": "dual_path_v1", "sustained_threshold": 1.45,
                   "fast_threshold": 2.2, "persistence_samples": 3}
```

and points `calibration_paths` to `results/game/calibration_room_m1_8_n2.json`. Relative to
`76806f0`, the changed config paths are exactly `config_version`, `policy._comment`,
`policy.calibration_paths` and `policy.escape_decoder`.

`game.session.resolve_escape_threshold` is stricter, not weaker:
- a dual-path config loads only a record with an identical `escape_decoder` block whose
  `escape_threshold` equals `sustained_threshold`;
- a scalar record cannot load a dual-path config, even with matching provenance;
- a dual-path record cannot load a single-sample config;
- `escape_decoder` accepts only the four criterion keys, so no geometry or contact gate
  can be configured.

The N2 record (`record_kind: dual-path-decoder-provenance-v1`,
`not_a_scalar_calibration: true`, SHA256 `95d09955...c6adf`) is produced deterministically
by `tools/n2_decoder_record.py`. No new measurement was made, and it contains no sweep or
detection fields. It traces:
- the inherited 1.45 through the source record `calibration_room_m1_8_b2b_ii.json` and the
  original measurement `calibration_room_m1_7_1.json`, both by SHA256;
- the N0 evidence (commit `3d41113`) and N1 evidence (commit `76806f0`): documents, tools
  and artifacts, by SHA256;
- `fast_threshold = 2.20` and `persistence_samples = 3` with their stated basis;
- the N2 configuration provenance hash.

`tools/calibrate_escape.py` was not rerun and does not calibrate this decoder; the config
comment says so. Historical calibration records are byte-identical to `76806f0`.

Resolution: LAB 1.45 (single-sample), GAME 1.35 (single-sample), ROOM 1.45 plus dual-path
via the N2 record.

`game/replay.py`: the recorder archives only `{provenance, escape_threshold}`. For a
dual-path session, replay adds the decoder block from the recorded config, which the
provenance hash already binds. For sessions without `escape_decoder` nothing is added,
so pre-N2 sessions do not depend on N2 fields (section 8).

## 3. N0 exact runtime replay (false-trigger acceptance)

The complete accepted N0 no-loom dataset is replayed through the actual runtime policy,
built with `build_policy` from each configuration: 150 trials x 1400 ticks, with a policy
reset per trial and the refractory period active.

| Decoder | Exposure | FAST | SUSTAINED | Total policy events | Events/min | 95% one-sided upper bound |
| --- | --- | --- | --- | --- | --- | --- |
| legacy 1.45 / single-sample | 70.0 min | - | - | 91 | 1.300 | 1.547/min |
| **N2** | **70.0 min** | **0** | **0** | **0** | **0 observed** | **0.0428/min** |

The legacy replay reproduces N0 exactly (91 events). The secondary continuous arm (10 min):
legacy 16 events, N2 0 events (upper bound 0.300/min; too short on its own).

**Acceptance target < 0.1/min at ~95% confidence: met** (bound 0.043/min; two-sided 97.5%
bound 0.053/min). This is an observed zero count, not a zero rate. **< 0.01/min is not
demonstrated.**

## 4. N1 exact runtime replay

All 300 N1 trials are replayed through the runtime policy. Per-class firing counts and
median onset latencies **match the accepted N1 offline hybrid analysis exactly (0
differing trials)**. The legacy replay also matches the N1 legacy row exactly.

| Class | Legacy fired | N2 fired | FAST | SUSTAINED | N2 median onset latency | N2 p95 |
| --- | --- | --- | --- | --- | --- | --- |
| strong_direct | 60/60 | **60/60** | 60 | 0 | 0.10 s | 0.16 s |
| medium_committed | 60/60 | **60/60** | 60 | 0 | 0.16 s | 0.18 s |
| weak_approach | 55/60 | 16/60 | 13 | 3 | 1.17 s | 1.59 s |
| glancing_pass | 51/60 | 9/60 | 6 | 3 | 0.44 s | 0.61 s |
| aborted_approach | 58/60 | 19/60 | 18 | 1 | 0.50 s | 0.66 s |

The weak, glancing and aborted classes are not must-escape targets. Their Retina, LC4/LPLC2
and MaleCNS responses are untouched; only the decoder criterion is less often satisfied.
No trial fired before its response window under N2.

## 5. Strong and medium committed latency (prominent)

Latency is measured from the click, in the fixed-fly N1 replay.

| | strong_direct | medium_committed |
| --- | --- | --- |
| Trials | 60 | 60 |
| Firing, legacy / N2 | 60 / 60 | 60 / 60 |
| N2 FAST / SUSTAINED | 60 / 0 | 60 / 0 |
| Legacy median | 0.08 s | 0.08 s |
| **N2 median** | **0.10 s** | **0.16 s** |
| Legacy p95 | 0.08 s | 0.10 s |
| **N2 p95** | **0.16 s** | **0.18 s** |
| **Delta median** | **+20 ms** | **+80 ms** |
| **Delta p95** | **+80 ms** | **+80 ms** |

**Medium committed strikes fire 80 ms later under N2.** The N1 report quoted only
strong_direct latency, so this was not visible there.

Mechanism (confirmed): the DNp01 rising edge is a spike/decay sawtooth (for example 1.67,
1.37, 2.12, 1.74, 2.42) that repeatedly drops below 1.45. The streak is broken between the
first crossing and firing in **54/60** medium trials (25/60 strong), so no 3-sample streak
forms and those trials wait for FAST >= 2.20. Median extra samples after the first
crossing: 4 (medium), 1.5 (strong). The implementation matches the accepted criterion; this
is a property of the criterion on this signal, not a defect.

## 6. Closed-loop ROOM validation (final run)

Everything runs through `Session.tick`: pointer -> physical swatter -> Retina -> LC4/LPLC2
-> MaleCNS -> DNp01 -> decoder -> Action -> lifecycle/physics. No neural value is injected.
The only WORLD fixture is in scenario A: the paddle is placed at hover height beside the
perched fly and held still for 2 s before the click, as `test_real_loom_aborts_approach`
does. Source: `artifacts/m1_8_n2/closed_loop_final.json`.

**Superseded:** earlier intermediate closed-loop numbers are superseded. The first runs
read the channel through the wrong accessor, and the first perched seed set (255, 101,
4242, 7, 31, 58) included seeds whose fly was not perched at the click.
`closed_loop_superseded_no_prefire_field.json` is a valid run with the corrected seeds but
without the pre-click diagnostic of section 6.2. Only the final run is reported here.

> **Correction (M1.8-N2b diagnosis): the scenario A numbers below are superseded.** The
> scenario A fixture was not a clean no-threat hold. Placing the paddle produced a
> one-sample retinal expansion spike, and the physical swatter treated the placement as
> a pointer jump and drove the paddle (up to 136 units/s) while it settled. That produced
> real expansion during the hold. Most "spontaneous" legacy escapes before the click were
> responses to that transient, not no-loom false triggers.
>
> With the corrected, verified zero-loom fixture (`game/M1_8_N2B_WINDOW_DECODER.md`):
> - legacy is perched at the click in 16/20 runs (2 true zero-loom single-sample false
>   escapes; 2 runs never perch);
> - strict N2 is perched in 20/20;
> - a perched fly under a committed strike is hit in every perched run under every decoder.
>
> Scenarios B-E were not affected.

### 6.1 Natural arm: each decoder controls the whole episode (primary evidence)

**A. Perched committed threat** (10 naturally perching seeds x 2 offsets = 20 runs):

| | Legacy | N2 |
| --- | --- | --- |
| Perched at click | **0/20** | **18/20** |
| Escapes before the click (settle and 2 s hold; no strike yet) | 25 | 2 (FAST) |
| Runs with a post-click escape | 20 | 20 |
| Perched at click and launched by neural TAKEOFF_ESCAPE | - | **18/18** |
| First post-click channel | single-sample 20 | FAST 20 |
| Median / p95 latency from click | 0.16 / 0.18 s | 0.11 / 0.21 s |
| Alive at end (diagnostic only) | 20 | 2 |

Under legacy, **every** fly had already left the perch through a spontaneous false escape
before the click, so its survival reflects false escapes rather than threat responses.
Under N2 the fly stays perched until the strike. It then launches a neural TAKEOFF_ESCAPE
via FAST in 18/18 perched runs, but is usually hit. The controlled arm (6.2) shows that
legacy is hit equally often from the same perched state.

**B. Airborne committed threat** (6 seeds x 2 offsets = 12 runs, ecology off): the
pointer tracks the fly at hover height, then clicks. Pre-click escapes: legacy 27, N2 7
(FAST 6, SUSTAINED 1). Post-click escape: legacy 11/12, N2 12/12 (FAST 11, SUSTAINED 1).
Median / p95 latency from click: legacy 0.08 / 0.22 s, N2 0.12 / 0.15 s. Alive: legacy 0,
N2 1. The natural arms start the click from different states, so these latencies are not a
paired comparison.

**C. Accepted M1.8-A no-click perched threat** (seed 255, pointer on the fly): the real
chain still produces a neural TAKEOFF_ESCAPE under N2, via **SUSTAINED**, at tick 238
(legacy: single-sample at tick 197). No strike occurs.

**D. Non-contact hover approaches** (3 seeds x 3 speed profiles, never committed;
descriptive only): legacy 28 escapes, N2 5 (all FAST); all flies alive; no strikes.

**E. No player / static swatter** (seeds 101, 255, 4242; 3 x 9000 ticks = **9.0 simulated
minutes**): maximum swatter speed **0.0** in every run. Escapes: legacy **20** (7 / 3 / 10,
including 1 perched escape takeoff), N2 **0**. Voluntary takeoffs: legacy 3, N2 7; the
trajectories diverge once legacy false escapes stop occurring. The system test
additionally proves that replaying the recorded MotorState stream alone reproduces every
N2 decision, so no world information gates escape.

### 6.2 Controlled / SwitchAtClick arm (counterfactual diagnostic only)

N2 controls the shared world until the click. Both candidate decoders consume the same
MotorState stream throughout, and the selected candidate controls after the click. This is
**not** a natural legacy trajectory. The inactive legacy candidate did internally "fire"
before the click in every run (those actions were discarded), so its refractory state at
the click is reported:

- **A (20 runs):** legacy candidate internal fires 1-2 per run, the last 69-94 samples
  before the click. Refractory at click is 0 in all 20, so **all 20 are clean latency
  comparisons**. Legacy median / p95 0.08 / 0.14 s; N2 0.11 / 0.21 s. Outcomes are
  identical: 18 hits and 2 alive under both. A perched fly under a committed strike is hit
  equally often under both decoders.
- **B (12 runs):** in **7/12** runs the legacy candidate was refractory at the click (5-12
  samples remaining, from internal fires 9-16 samples earlier; in one of these the N2
  candidate was also refractory, 6 samples), so those latency comparisons are
  **confounded** and excluded. In the 5 clean runs, legacy vs N2: 0.06/0.14, 0.08/0.10,
  0.08/0.16, 0.08/0.12 and 0.08/0.14 s, so N2 is 20-80 ms slower. Survival is identical
  (1 alive under both).

## 7. Recorder and replay preservation

- Recording schema version: **4** (unchanged).
- Every recorded tick row's `neural.diagnostics` key set equals the legacy set; no FAST/
  SUSTAINED field or streak appears in `ticks.jsonl` (test).
- `manifest.calibration` still holds exactly `{provenance, escape_threshold}`.
- A new N2 ROOM session with a perched escape takeoff replays **exactly** (test).
- **Historical pre-N2 recording:** a ROOM session recorded with the `76806f0` source in a
  temporary baseline worktree (legacy decoder, 1 escape takeoff, no `escape_decoder` in its
  config) replays **exactly, 250/250 ticks**, with the N2 code (source strictness off).
  With strict source checking it is rejected, as before, because the game source differs;
  that is the existing policy for historical sessions.
- M1.8-A lifecycle scenarios replay exactly: 1200 / 340 / 120 ticks.

## 8. First intentional divergence from `76806f0`

Pre-N2 and N2 full-precision traces (`tools/kinematics_trace.py`) were compared with
`tools/kinematics_diff.py`. The recorded pre-N2 DNp01 stream was replayed through both
decoders to locate the first decision difference.

| Scenario | First decision divergence | DNp01 total | Legacy | N2 | Streak | Refractory | First trace-row divergence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| room_quiet | tick 1001 | 1.819 | escape | no escape | 1 | not refractory | tick 1001 |
| room_perched_threat | tick 274 | 1.512 | escape | no escape | 1 | not refractory | tick 274 |
| room_approach_threat | tick 56 | 1.623 | escape | no escape | 1 | not refractory | tick 56 |
| room_airborne_seed101 | tick 343 | 1.462 | escape | no escape | 1 | not refractory | tick 343 |
| room_no_ecology | none | - | - | - | - | - | identical |
| game_preset / lab_preset | single-sample decoder, unchanged | - | - | - | - | - | identical |

In every ROOM case the trace first diverges on exactly the tick where legacy fires on a
single sample in [1.45, 2.20) with a streak of 1. N2 does not fire because the value is
below 2.20 and the streak is below 3. **No divergence precedes a decoder decision
difference.** The RNG call-order change in `room_airborne_seed101` occurs downstream of that
divergence. The `kinematics_sampler_drew` flags are identical before and after N2
(B2b-ii EXPLORE sampling).

The first divergence overall is `room_approach_threat`, tick 56: legacy action escape,
N2 action no escape, DNp01 1.623, streak 1, not refractory.

## 9. Regression and frozen-system verification

| Check | Result |
| --- | --- |
| Full suite (pre-N2 baseline) | 330 tests, OK |
| **Full suite (N2)** | **365 tests, OK** (+35 N2 tests; 2 lifecycle tests updated, versioned) |
| `git diff --check` | clean |
| 20 protected original files | SHA256 unchanged |
| 58-file frozen baseline | 57 unchanged; **`game/action.py` changed, the intended versioned decoder change** |
| `verify_results.py` | 36 predictions, source hashes match, 2/2 exact neuronal replays, frozen weights |
| M1.7.1 swatter fixtures | identical to `approach_m1_7_1.json` |
| M1.8-A lifecycle scenarios | voluntary / perched_threat / approach_threat event counts as at B2b-ii; exact replay 1200 / 340 / 120 |
| Recorder exact replay | N2 session and pre-N2 session exact |
| Policy-observation isolation | `{neural, motion, behavior_state, history}` only (existing test) |
| Calibration resolution | LAB 1.45, GAME 1.35, ROOM 1.45 plus dual-path via the N2 record |
| LAB / GAME / ROOM-no-ecology traces | bit-identical to `76806f0` |
| Historical calibration records | byte-identical |

The two updated lifecycle tests are `test_stale_ignored_calibration_cannot_override_matching_record`
(now uses the N2 record) and `test_calibration_transfer_only_changes_inactive_protocol_fields`
(also excludes `policy.escape_decoder` and `policy._comment`, and checks the N2 link in the
chain).

## 10. Known limitations

1. **Medium committed strikes are 80 ms slower** (median 0.08 -> 0.16 s) because of the
   sawtooth rising edge (section 5). Strong strikes are 20 ms slower in the median and
   80 ms at p95.
2. **Perched flies are now usually hit by a committed strike.** Legacy perched survival
   came from spontaneous false escapes before the strike. From an identical perched state,
   legacy and N2 have the same hit outcome.
3. Weak non-contact firing drops sharply (weak 55 -> 16, glancing 51 -> 9, aborted 58 -> 19
   of 60). This is accepted by decision, but the fly will visibly ignore many hover-height
   passes it used to react to.
4. The < 0.01/min stretch target is not demonstrated; only < 0.1/min is.
5. N0/N1 evidence is fixed-fly and ROOM-only. LAB/GAME keep the single-sample decoder and
   their 1.30/min-class false-trigger behavior.
6. The recorder's `threshold_crossing` event flag still marks 1.45 crossings, which no
   longer imply an escape.
7. `escape_trigger_channel` is not persisted in recordings, so human sessions cannot be
   split by channel after the fact.
8. Closed-loop samples are small (20 / 12 / 9 / 3 runs) and are diagnostics, not a
   characterisation of difficulty.
9. `tools/escape_cruise_study.py` and `tools/escape_provenance.py` (B2b-ii studies) were not
   rerun; their escape counts are expected to change under N2.

## 11. Narrow human re-acceptance checklist (ROOM)

1. A committed strike on an airborne fly still produces a visible escape that feels
   timely; note any "late" feel, especially on strikes started far from the fly.
2. A committed strike on a perched fly produces a visible escape takeoff. Judge whether the
   perched fly now being hit usually is acceptable.
3. The accepted no-click perched threat (paddle moved over the perched fly) still launches
   the fly.
4. With no player input, the fly no longer makes spontaneous escape jumps; landing,
   feeding and voluntary takeoff still look normal.
5. Hover-height passes that do not strike are mostly ignored; confirm this reads as
   intended rather than as unresponsiveness.
6. Record at least one session and confirm that it saves and replays.

Nothing is committed or pushed. B2b-iii, TRANSIT/ODOR sampling, `room_kinematic_scale`,
caps, `escape_impulse`, brain noise and RL are untouched.
