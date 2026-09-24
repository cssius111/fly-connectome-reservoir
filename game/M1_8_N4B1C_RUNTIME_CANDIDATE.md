# M1.8-N4B1C runtime candidate: lateral dual-path DNp01 decoder

Status: **accepted and frozen after human review (2026-09-24).** Branch
`feature/m1-8-n4b1c-runtime`, based on the research HEAD `07f4670`. Not merged into
`main`; PR #1 is not merged.

Human acceptance (section 7):

- direct-attack latency: accepted;
- hover/chase responsiveness: accepted;
- escape direction: accepted;
- no further parameter tuning requested; the candidate is accepted as-is;
- slow / gradual approach insensitivity remains a known limitation, deferred to N4B2.

Scope: the escape trigger only. Retina, LC4/LPLC2 encoder, MaleCNS, brain noise, motor
strength/side/steering/saccades, forward bias, refractory duration, lifecycle, physical
swatter, `escape_impulse`, caps, recorder schema and RL are unchanged. The policy
observation whitelist is unchanged: the candidate reads `dnp01_left` and `dnp01_right`,
which were already observed. DNp04 and N4B2 are not touched.

**This candidate addresses** direct-strike latency and alternating-side hover sensitivity.
**It does not solve** slow-approach insensitivity (episode-5 slow-close, tick 668); that
remains N4B2 scope.

## 1. Runtime criterion (`lateral_dual_path_v1`)

Escape when EITHER path qualifies on the current sample outside the shared 0.4 s
(20-sample) refractory period:

- **LATERAL:** the SAME DNp01 side produces two inferred spikes at most 60 ms (3 samples)
  apart.
  - Per side: `spike_t = trace_t - decay * trace_{t-1} >= 0.5`, with
    `decay = float32(exp(-tick / trace_tau))` = 0.81873.
  - No spike is inferred on the first sample after reset, because its previous trace
    value is unknown.
  - Left and right are tracked independently, so a left spike followed by a right spike
    never qualifies.
  - The qualifying spike must be on the current sample.
- **Summed N2b path, unchanged:**
  - FAST when `dnp01_left + dnp01_right >= 2.10`;
  - SUSTAINED when the current summed sample is >= 1.45 AND at least 3 of the last 5
    summed samples are >= 1.45.

Configuration (`game_room_config.json`, `config_version` 16):

```json
"escape_decoder": {"kind": "lateral_dual_path_v1", "sustained_threshold": 1.45,
  "summed_fast_threshold": 2.1, "sustained_window_samples": 5,
  "sustained_required_samples": 3, "require_current_qualifying": true,
  "lateral_same_side_window_ms": 60, "lateral_required_spikes": 2}
```

All values are Class C engineering decoder parameters. The 60 ms window is derived from
the simulator (LIF reset to 0 plus independent per-cell noise); it is not a biological
constant. The window must be a whole number of ticks, and only two-spike lateral
evidence is supported.

**Diagnostic precedence:** LATERAL, then FAST, then SUSTAINED.
`criterion_diagnostics()` reports every path that qualified on the firing sample, for
example `LATERAL+FAST`. The motor output does not depend on the path.

**State:**

| Event | Effect |
|---|---|
| Every sample, refractory included | the summed window/streak update (archived N2b semantics) and per-side spike memory update |
| An escape | clears the summed window/streak and both sides' last-spike memory |
| Reset | clears everything above, plus the previous trace values and the trigger channel/paths |

## 2. Implementation

- `game/action.py`: optional lateral path in `FixedEscapePolicy`, built from the archived
  N2b implementation as source material. With `lateral_window_samples=None`, every earlier
  decoder is unchanged. `diagnostics()` keeps the frozen recorded key set.
- `game/session.py`: the versioned kind `lateral_dual_path_v1`, with an exact key set
  (unknown keys rejected, so no geometry gate can be configured), whole-tick window
  validation and the trace decay taken from `brain.trace_tau_seconds`. The earlier kinds
  `dual_path_v1` and `dual_path_window_v1` remain supported, so their recordings still
  replay exactly.
- `game/replay.py`: decoder-aware replay, unchanged from the archived snapshot.
- `results/game/calibration_room_m1_8_n4b1c.json`: new decoder provenance record,
  written by `tools/n4b1c_decoder_record.py`.
  - It is decoder provenance, not scalar calibration (`not_a_scalar_calibration: true`).
  - It cites N0, N1, N3, N4A, N4B1 and N4B1C by commit and content hash.
  - The strict-N2 and rejected-N2b records are preserved by hash and not modified.
- Tests: `test_game_n4b1c_decoder.py` (28 tests, new). `test_game_n2_decoder.py` now
  tests N2b against the archived v15 configuration. `test_game_lifecycle.py` resolves the
  new record.

## 3. Automated validation (runtime code path)

| Check | Result |
|---|---|
| A. Full suite | **414 tests, OK**; rerun at the freeze, see section 7 |
| B. 20 protected original files | all match: 13 raw, 7 after the fresh worktree's CRLF conversion; git shows no content change against `76806f0` |
| B. Tracked-file diff against `07f4670` | only `game/action.py`, `game/session.py`, `game/replay.py`, `game_room_config.json`, `test_game_lifecycle.py`, plus new files |
| C. `verify_results.py` | 36 predictions, source hashes match, 2/2 exact held-out neuronal replays, frozen weights (run on the original-bytes checkout; the fresh worktree's CRLF conversion changes raw source bytes only) |
| D. M1.7.1 swatter controlled fixtures | identical to `results/game/approach_m1_7_1.json` |
| E. M1.8-A lifecycle scenarios | event counts unchanged; exact replay 1200 / 340 / 120; frozen weights; voluntary takeoff tick 907 unchanged |
| F-H. N0 replays (below) | exact match with the frozen N4B1C research |
| I. N1, 300 trials | exact match with the research |
| Independent reference | 0 tick mismatches over 1650 N0 + N1 trials against a separate re-implementation of the frozen rule |
| J. Both human recordings | recorded decoders reproduce with 0 mismatches; candidate results identical to the research |
| K. Closed loop | section 4 |
| L. Recorder, new candidate recording | schema 4; diagnostics key set frozen; no trigger/lateral fields persisted; 550/550 exact replay under strict source |
| L. Pre-N2 recording (v13) | 250/250 exact (relaxed source; strict source correctly rejects the changed source) |
| L. Rejected N2b human recording (v15) | 4791/4791 exact (relaxed source) |
| L. Strict-N2 human recording (v14) | 9387/9387 exact (relaxed source) |

M1.8-A lifecycle event timing:

| Scenario | legacy (accepted) | N2b | candidate |
|---|---|---|---|
| perched-threat escape takeoff | 274 | 283 | 282 |
| approach abort | 56 | 64 | 63 |

These are slow, non-strike threats, consistent with the known slow-approach limitation.

## 4. Required behaviour (actual runtime results)

**N0 false triggers (runtime):**

| Data | Events | 95 % upper bound (/min) | Path |
|---|---|---|---|
| original N0, 70 min | 0 | 0.043 | - |
| N4B1 fresh N0, 280 min | 2 | 0.0225 | FAST 2 |
| N4B1C holdout, 280 min | 1 | 0.0169 | FAST 1 |
| all 630 min | 3 | **0.0123** | all from the summed FAST path |

**N1** (median / p95 from click):

| Class | Fired | Latency | First path |
|---|---|---|---|
| strong | 60/60 | **0.08 / 0.08 s** | LATERAL 55, LATERAL+FAST 5 |
| medium | 60/60 | **0.10 / 0.10 s** | LATERAL 57, LATERAL+FAST 3 |
| weak / glancing / aborted | 33 / 28 / 49 | - | descriptive; not must-escape |

**Human recordings (open-loop, synced per segment):**

| Measure | strict-N2 session | N2b session |
|---|---|---|
| Recorded escapes met no later | 37 / 37 | 25 / 25 |
| Hover escapes met (N2b; Rule A alone) | **13 / 13** (13/13; 6/13) | **20 / 20** (20/20; 16/20) |
| Trigger channels | LATERAL 29, FAST 5, SUSTAINED 3 | LATERAL 21, SUSTAINED 2, FAST 2 |
| Direct strikes | 16 fire during the pre-click chase, 10 after the click (median 0.09 s), 0 missed | -0.10 / -0.02 / 0.00 / +0.10 s from click |

Special cases:

- **Far perched bilateral-noise case** (strict-N2 session, rows 2434-2528; summed
  peak 2.0557): **rejected**. The first firing in that segment is at row 3602, a later
  threat.
- **Voluntary takeoff interval** (N2b session, 18.44 s): no escape.
- **Slow-close, episode 5:** tick 668, both synced and from a clean start (N2b: 670).
  **Not solved.**

**Closed loop** (corrected zero-loom perched fixture; runtime candidate against the
rejected N2b):

| Scenario | candidate | N2b |
|---|---|---|
| Perched committed strike (20): pre-click escapes / neural takeoff / latency | 0 / 20 / **0.08 / 0.08 s** (LATERAL 20) | 0 / 20 / 0.10 / 0.12 s (FAST 20) |
| M1.8-A no-click perched threat | escape takeoff (LATERAL) | escape takeoff (SUSTAINED) |
| Airborne committed strike (12): post-click escape / median / p95 | 11 / 0.08 / 0.18 s | 10 / 0.11 / 0.175 s |
| Hover approach, no click (9) | 13 escapes | 12 escapes |
| No player, 9 min | 1 (FAST; weak real expansion, encoder drive 0.024) | 1 (same event) |

## 5. Re-escape diagnostic (required item)

The N4B1C research reported 83 (A OR N2b) and 81 (N2b) "re-escapes" in the airborne
committed-strike scenario. Per-sample logging of the runtime shows:

- **The large counts were a measurement artifact of the research harness.** After the
  fly is hit, `Session.tick` no longer steps the brain and passes `Action()` to the world,
  but `fly_loop.last_action` keeps the last real decision. The harness
  (`tools/n2_closed_loop.Run`) read that stale value on every post-death tick: 78 stale
  readings for each decoder, identical for both. They are not policy decisions and do not
  reach the world. (The `escape_actions` totals in the closed-loop summaries include those
  readings; first-escape latencies do not, because the first escape precedes death.)
- **Genuine escape decisions:** 28 for the candidate and 26 for N2b.
- **Genuine re-escapes at refractory expiry** (21 samples after the previous escape):

| Measure | candidate | N2b |
|---|---|---|
| Re-escapes at refractory expiry | 5 | 3 |
| Paths | LATERAL+FAST 3, FAST 1, SUSTAINED 1 | FAST 2, SUSTAINED 1 |
| New DNp01 spikes since the previous escape | 6-10 | 6-10 |
| Spikes in the last 5 samples | 2-5 | 2-5 |
| Re-escapes with positive encoder drive in the last 5 samples | 5 of 5 | 3 of 3 |
| Trace left over from before the previous escape | at most 0.030 | at most 0.024 |

  The re-escapes happened during approach, fast-swing and active-contact phases, at a
  median center distance of 69 units.
- **Conclusion:** every genuine re-escape rests on fresh neural evidence gathered after
  refractory, during continued real looming. No stale evidence survives an escape.
  **Retained for human review, not tuned.**

## 6. Human acceptance checklist (ROOM)

Launch from the feature worktree (`artifacts\worktrees\n4b1c-runtime`, which has no
`.venv` of its own):

    D:\Projects\flybrain-lab\.venv\Scripts\python.exe -m game.app --arena room --seed 255 --record --windowed

Judge only:

1. normal direct-attack latency;
2. hover/chase responsiveness;
3. unexplained escapes while the swatter is effectively still;
4. repeated re-escape behaviour while the paddle stays on the fly;
5. escape direction.

Slow-approach insensitivity is expected to remain. It must not be used to retune this
milestone (N4B2 scope). Do not judge by hit rate or difficulty.

Tools: `tools/n4b1c_decoder_record.py` and `tools/n4b1c_runtime_validation.py` (modes
`replays`, `closed-loop`, `record`, `replay`). Artifacts:
`artifacts/m1_8_n4b1c_runtime/` (git-ignored).

## 7. Human acceptance record

The human review of this candidate is complete (2026-09-24). The candidate is **accepted
as-is and frozen**:

| Criterion | Result |
|---|---|
| 1. Normal direct-attack latency | accepted |
| 2. Hover/chase responsiveness | accepted |
| 3. Unexplained escapes | none reported |
| 4. Repeated re-escape behaviour | accepted as-is (section 5: every genuine re-escape rests on fresh neural evidence) |
| 5. Escape direction | accepted |

- No further parameter tuning is requested. Thresholds, windows, refractory behaviour,
  brain noise, Retina, encoder, physics and the policy whitelist are unchanged.
- **Known limitation, accepted for this milestone:** slow / gradual approach sensitivity
  remains unresolved (episode-5 slow-close fires at tick 668). It is deferred to N4B2.
- Review recording: `results/game/sessions/20260924T191815.888754Z-4cd44be5` (git-ignored).
  It was recorded with this candidate: recorder schema 4, ROOM config v16,
  `lateral_dual_path_v1`, branch `feature/m1-8-n4b1c-runtime` at `07f4670` plus the
  uncommitted candidate.
- Freeze validation, rerun on the unchanged working tree:
  - full suite 414 tests OK;
  - 20 protected files unchanged;
  - `verify_results.py`: 36 predictions, 2/2 exact neuronal replays, frozen weights;
  - recorder schema 4;
  - ROOM config v16 with `lateral_dual_path_v1`;
  - `git diff --check` clean.
