# M1.8-N4B1C: combined lateral + summed DNp01 readout

Status: **research only; accepted as a research result (2026-09-24); recommendation in
section 9.** No production runtime, configuration, calibration, whitelist, Retina, encoder,
brain-noise, lifecycle, physics or recorder change. DNp04 is not used. The runtime
candidate is a separate milestone (`feature/m1-8-n4b1c-runtime`).

Question: can the N4B1 Rule A lateralized readout be combined with the rejected N2b summed
path to restore direct-strike speed without losing N2b's alternating-side hover
sensitivity?

## 0. Reproduction environment

- The research branch `wip/m1-4-enclosure` stays clean at `6fb0cc5`, with no N2b runtime.
  The only new files are this report and `tools/n4b1c_candidates.py` /
  `tools/n4b1c_combined.py`, all uncommitted.
- The N2b runtime comes from the archival snapshot `archive/m1-8-n2b-rejected`
  (`2c306174d7bdb4e74b6c5517519ae695bd90cf44`). It is checked out as a **detached**
  worktree at `artifacts/worktrees/n2b-rejected` (git-ignored), with the ignored brain
  `data/` linked by a directory junction. The archive branch is not modified, and the
  worktree stays clean.
- The suggested location `D:\Projects\flybrain-lab-n2b` could not be used: `D:\Projects`
  grants ordinary users only read/execute, so creating a directory there needs
  administrator rights. That ACL was not changed.
- `tools/n4b1c_combined.py` verifies that the worktree is clean at the archive commit, puts
  it first on `sys.path` (so `game.*` and the N4B1 helpers are the archived code), and
  reads data from this repository's ignored `artifacts/` and `results/` folders.

## 1. Frozen candidates

The definitions live in `tools/n4b1c_candidates.py`. The freeze file
`artifacts/m1_8_n4b1c/frozen_candidates.json` (sha256
`8eb273f7bd752e1a1e9731db25696e2683977f2ee785a2ed519d76ae59788487`, written
2026-09-24T15:59:39Z) records:

- the module sha256 `30fc1663c5875e5f5d68026286488e879ed13c30a9a836c41de5ab5a5127fdee`;
- the archive commit;
- the archived ROOM v15 config sha256 (`71c46ea9e4a4...`);
- the holdout protocol.

Every later step refuses to run if the module has changed. Before the holdout existed, the
frozen module was smoke-tested on development data only (N1). No change was needed, so no
re-freeze happened.

| Key | Candidate |
|---|---|
| legacy | summed L+R >= 1.45, single sample (ROOM config at `76806f0`) |
| strict_n2 | FAST L+R >= 2.20 OR L+R >= 1.45 on 3 consecutive samples |
| n2b | FAST L+R >= 2.10 OR (current L+R >= 1.45 AND >= 3 of the last 5 samples >= 1.45); archived runtime |
| A | two inferred DNp01 spikes on the SAME side, the second <= 3 samples (60 ms) after the first |
| B | the same, <= 4 samples (80 ms) |
| **A OR N2b** | **primary** |
| B OR N2b | comparison |

## 2. Combined-decoder semantics (A OR N2b, B OR N2b)

- **Inputs:** `dnp01_left` and `dnp01_right` only (already in the observation). The summed
  path uses their sum, exactly as the archived runtime does. The lateral path uses each
  side separately.
- **Lateral path:** per side, `s_t = trace_t - 0.81873 * trace_{t-1}`. A side qualifies on a
  sample holding a new spike on that side while **that same side's** previous spike, since
  the last escape or reset, is at most `max_gap` samples earlier. A left spike followed by
  a right spike never qualifies.
- **Summed path:** the archived `FixedEscapePolicy._trigger_channel`, unchanged (FAST 2.10;
  SUSTAINED: current sample H and >= 3 H in the last 5).
- **Firing:** an escape fires when **either** path qualifies on the current sample outside
  refractory. There is one shared 0.4 s (20-sample) refractory. The channel lists every
  path that qualified on that sample, lateral first, e.g. `LATERAL_L`, `FAST`,
  `LATERAL_R+FAST`.
- **Every sample, refractory included:** the N2b 5-sample window and streak update
  (archived semantics), and the per-side lateral spike memory updates.
- **On an escape:** the N2b window and streak are cleared (archived runtime), and the
  lateral last-spike memory of both sides is cleared. The per-side previous trace value
  used for spike inference is kept, because it is an observation, not evidence.
- **On reset:** all of the above, plus the previous trace values (no spike is inferred on
  the first observed sample) and all runtime policy state.
- **Unchanged:** strength, side, steering, alert state and saccades are runtime code. No
  geometry, Retina, encoder, distance or contact value is read.
- **Harness check:** the combined class with the lateral path disabled reproduces N2b
  exactly (the same firing ticks on all 300 N1 trials and 40 N0 trials).

## 3. N0 false triggers

- **Development data** (already inspected in N4B1): the original N0 (70 min, seeds
  4000-4149) and the N4B1 fresh N0 (280 min, seeds 30000-60149).
- **New independent holdout**, generated after the freeze:
  - 600 trials x 1400 ticks = **280.0 min**;
  - seeds 210000-210149, 220000-220149, 230000-230149 and 240000-240149, non-overlapping
    with the original N0, its loom arm (5000-5149), N1 (6000-10059), N4B1 (30000-60149)
    and the small scenario and human seeds;
  - offsets from `default_rng(encoder_seed + 616161 + chunk)`;
  - the `calibrate_escape._trial` protocol, fixed fly and no loom (config `3d41113`), with
    2 Numba threads;
  - every chunk records the freeze and module hashes.

Bounds are exact one-sided Poisson 95 %.

| Candidate | Original 70 min (dev) | N4B1 fresh 280 min (dev) | **NEW holdout 280 min** | Holdout 95 % upper (/min) | Holdout trigger paths | All 630 min: events, upper (/min) |
|---|---|---|---|---|---|---|
| legacy | 91 | 415 | 431 | 1.667 | summed single sample | 937, 1.570 |
| strict N2 | 0 | 1 | 1 | 0.0169 | FAST | 2, 0.0100 |
| N2b | 0 | 2 | 1 | 0.0169 | FAST | 3, 0.0123 |
| Rule A alone | 0 | 0 | **0** | 0.0107 | - | 0, 0.0048 |
| Rule B alone | 0 | 1 (lateral R) | 0 | 0.0107 | - | 1, 0.0075 |
| **A OR N2b** | 0 | 2 (N2b FAST) | **1 (N2b FAST)** | **0.0169** | N2b FAST 1; lateral 0 | 3, 0.0123 |
| B OR N2b | 0 | 3 (lateral R 1, FAST 2) | 1 (N2b FAST) | 0.0169 | N2b FAST 1 | 4, 0.0145 |

- Every non-legacy candidate passes < 0.1/min on the new holdout, with large margin.
- **Every A OR N2b false event came from the inherited N2b summed FAST path, never from the
  lateral path.** The holdout event is chunk 0, trial 42 (seed 210042), tick 103: right
  spikes at 98 and 103 (gap 5, too long for Rule A) plus a same-tick left spike at 103,
  for a summed trace of 2.368. It is a bilateral summed-noise coincidence of the kind N4A
  described, and strict N2 fires on it too.
- No candidate re-fired immediately at refractory expiry in any N0 set.

## 4. N1 replay (300 trials)

Latency is median / p95 in seconds from the click.

| Candidate | strong fired / latency | medium fired / latency | weak / glancing / aborted fired | First path, strong | First path, medium |
|---|---|---|---|---|---|
| legacy | 60 / 0.08 / 0.08 | 60 / 0.08 / 0.10 | 55 / 51 / 58 | summed | summed |
| strict N2 | 60 / 0.10 / 0.16 | 60 / 0.16 / 0.18 | 16 / 9 / 19 | FAST 60 | FAST 60 |
| N2b | 60 / 0.10 / 0.12 | 60 / 0.14 / 0.18 | 29 / 27 / 44 | FAST 60 | FAST 55, SUSTAINED 5 |
| Rule A | 60 / 0.08 / 0.08 | 60 / 0.10 / 0.10 | 14 / 16 / 39 | lateral 60 | lateral 60 |
| Rule B | 60 / 0.08 / 0.08 | 60 / 0.10 / 0.10 | 39 / 39 / 57 | lateral 60 | lateral 60 |
| **A OR N2b** | **60 / 0.08 / 0.08** | **60 / 0.10 / 0.10** | 33 / 28 / 49 | lateral 55, lateral+FAST 5 | lateral 57, lateral+FAST 3 |
| B OR N2b | 60 / 0.08 / 0.08 | 60 / 0.10 / 0.10 | 44 / 43 / 57 | lateral 55, lateral+FAST 5 | lateral 57, lateral+FAST 3 |

- A OR N2b keeps Rule A's committed-strike timing exactly. On committed strikes the lateral
  path always fires first, or together with FAST, and N2b never fires alone.
- On weak / glancing / aborted approaches (not must-escape targets) the union is more
  sensitive than either part: 33 / 28 / 49, against A 14 / 16 / 39 and N2b 29 / 27 / 44.
  First paths for A OR N2b:
  - weak: lateral 13, FAST 15, SUSTAINED 5;
  - glancing: lateral 14, SUSTAINED 7, FAST 5, lateral+FAST 2;
  - aborted: lateral 31, FAST 14, SUSTAINED 3, lateral+FAST 1.

## 5. Both human sessions (open-loop, synced per segment; recorded decoders reproduce with 0 mismatches)

| Candidate | strict-N2 session: met no later / 37 (median lead) | hover (13) | strike phase (24) | N2b session: met no later / 25 (median lead) | hover (20) | strike phase (5) |
|---|---|---|---|---|---|---|
| strict N2 (recorded in strict session) | 37 (0) | 13 | 24 | 6 | 4 | 2 |
| N2b | 37 (0.02 s) | 13 | 24 | 25 (0, recorded) | 20 | 5 |
| Rule A | 30 (0.10 s) | **6** | 24 | 21 (0.02 s) | **16** | 5 |
| Rule B | 30 (0.17 s) | 6 | 24 | 23 (0.06 s) | 18 | 5 |
| **A OR N2b** | **37 (0.10 s)** | **13** | 24 | **25 (0.02 s)** | **20** | 5 |
| B OR N2b | 37 (0.10 s) | 13 | 24 | 25 (0.04 s) | 20 | 5 |

Trigger paths of A OR N2b's first firings:

- strict-N2 session: lateral 27, N2b FAST 5, N2b SUSTAINED 3, lateral+FAST 1,
  lateral+SUSTAINED 1;
- N2b session: lateral 17, FAST 2, SUSTAINED 2, lateral+FAST 2, lateral+SUSTAINED 2.

Direct strikes, latency from the click (negative = fired during the hover chase before the
click):

| Candidate | N2b session, 4 strikes | strict-N2 session, 26 strikes |
|---|---|---|
| N2b | 0.14, 0.06, 0.02, 0.02 | 10 before click, 14 after (median 0.11 s), 2 not by resolution |
| Rule A | 0.10 (L 2268-2270), -0.10 (L 57-60), -0.02 (L 666-668), 0.00 (R 720-723) | 15 before, 11 after (median 0.10 s), 0 missed |
| **A OR N2b** | **0.10 (L), -0.10 (L), -0.02 (L), 0.00 (R)**: identical to A, all via the lateral path | 16 before, 10 after (median 0.09 s), 0 missed |

Special cases (every candidate except legacy):

- **Far perched non-contact approach** (strict-N2 session, episode 1, rows 2434-2528): the
  bilateral noise events there are R 2494 + L 2496 (summed 1.67) and a same-tick L+R pair
  at 2513 (summed 2.0557). **A OR N2b does not fire in the bout.** The lateral path sees no
  same-side pair (L 2496 and L 2513 are 17 samples apart), and the summed path never meets
  N2b's criterion there. Its first firing in that segment is at row 3602 (lateral L
  3599-3602), a later threat. Legacy fires at 2496.
- **Voluntary takeoff** (N2b session, 18.44 s): no candidate fires within 1 s before to
  0.5 s after the takeoff. It is kept separate from threat response.

## 6. Hover-chase question (the reason for this study)

Each recorded hover escape in the strict-N2 session, with each candidate's first firing
relative to the recorded strict-N2 escape (+n = n samples earlier; "-" = not by then):

| Episode, row | N2b | Rule A | A OR N2b |
|---|---|---|---|
| 2, 100 | +1 SUSTAINED | +2 lateral | +2 lateral |
| 3, 17 | +0 FAST | +4 lateral | +4 lateral |
| 4, 32 | +0 FAST | - | +0 FAST |
| 4, 53 | +0 FAST | - | +0 FAST |
| 4, 86 | +0 FAST | - | +0 FAST |
| 4, 107 | +0 FAST | - | +0 FAST |
| 4, 418 | +1 SUSTAINED | +2 lateral | +2 lateral |
| 4, 440 | +1 SUSTAINED | - | +1 SUSTAINED |
| 4, 531 | +0 SUSTAINED | - | +0 SUSTAINED |
| 5, 55 | +1 SUSTAINED | +41 lateral | +41 lateral |
| 6, 69 | +0 FAST | - | +0 FAST |
| 6, 166 | +3 SUSTAINED | +7 lateral | +7 lateral |
| 9, 80 | +2 FAST | +4 lateral | +4 lateral |

- **A OR N2b restores all 13** (Rule A: 6). On the 7 escapes Rule A misses, the summed path
  fires on the same sample as N2b. On the other 6, the lateral path fires as early as or
  earlier than N2b.
- In the N2b session, A OR N2b meets or beats the recorded N2b escape on all 20 hover
  escapes: lateral on 13 (+0 to +13 samples), N2b path on 4, both on the same sample on 3.
  Rule A alone misses 4.

Closed-loop hover approach (section 7): A OR N2b 13 escapes in 9 runs, against N2b 12 and
Rule A 6.

## 7. Closed loop (archived runtime; research policies in tools/ only)

These are the `tools/n2_closed_loop.py` scenarios through the full game path, including the
corrected zero-loom perched fixture (every hold is verified zero-loom). Natural arm.

| Scenario | Rule A | N2b | **A OR N2b** | B OR N2b |
|---|---|---|---|---|
| A. Perched committed strike (20): escapes before click | 0 | 0 | 0 | 0 |
| perched at click / neural takeoff after click | 20 / 20 | 20 / 20 | 20 / 20 | 20 / 20 |
| latency median / p95 (s) | 0.08 / 0.08 | 0.10 / 0.12 | **0.08 / 0.08** | 0.08 / 0.08 |
| first path after click | lateral 20 | FAST 20 | lateral 18, lateral+FAST 2 | lateral 18, lateral+FAST 2 |
| M1.8-A no-click perched threat | escape takeoff (lateral) | escape takeoff (SUSTAINED) | escape takeoff (lateral) | escape takeoff (lateral) |
| B. Airborne committed strike (12): escape after click | 9 | 10 | 11 | 11 |
| latency median / p95 (s) | 0.08 / 0.15 | 0.11 / 0.18 | **0.08 / 0.18** | 0.08 / 0.20 |
| escapes during the pre-click hover chase | 16 | 16 | 17 | 20 |
| C. Hover approach, no click (9 runs): escapes | 6 | 12 | **13** | 17 |
| paths | lateral 6 | FAST 6, SUSTAINED 6 | lateral 5, FAST 3, lateral+FAST 3, SUSTAINED 2 | lateral 11, others 6 |
| D. No player, 3 x 9000 ticks: escapes | 0 | 1 | 1 | 1 |

- The no-player escape of N2b, A OR N2b and B OR N2b is the same known event: seed 4242,
  tick 7400, N2b FAST, with weak real expansion (encoder drive 0.024, theta_dot 0.045). It
  is not a zero-loom trigger.
- **Re-escapes at refractory expiry** (a new escape 21 samples after the previous one):
  - airborne committed-strike scenario: 83 for A OR N2b and 86 for B OR N2b, against
    **81 for N2b alone** and 1 for Rule A alone. This is inherited from the N2b summed path
    under a sustained close chase (the pointer keeps the paddle on the fly), where the
    summed trace stays above threshold. It is not a new behaviour of the combination;
  - hover approach: 0 (A OR N2b) and 2 (B OR N2b);
  - no player and perched scenarios: 0 for every candidate.

## 8. Slow-close limitation (episode 5; N2b escaped at 589 and was refractory until 609)

| Candidate | Chase before 589 | Slow-close, synced | Slow-close, clean start at 610 |
|---|---|---|---|
| N2b (recorded) | 589 | 670 | 670 |
| Rule A | 576 | 668 (L 666, 668) | 668 |
| **A OR N2b** | **576** | **668** (lateral L 666, 668) | **668** |
| B OR N2b | 576 | 668 | 668 |

**The combined rule fires at the same late point as Rule A:** tick 668, 45 samples after the
closest center approach (623) and only 2 samples before N2b. It does not solve the
slow-approach failure. **N4B2 remains necessary.**

## 9. Decision

| Criterion | A OR N2b | Result |
|---|---|---|
| New independent N0 holdout < 0.1/min (95 %) | 1 event in 280 min, upper 0.0169/min (all 630 min: 0.0123/min) | **pass** |
| Direct-strike timing about Rule-A / legacy level | N1 strong 0.08 / 0.08, medium 0.10 / 0.10 (identical to A); closed-loop perched 0.08 / 0.08; airborne median 0.08; human direct strikes identical to A | **pass** |
| Hover/chase sensitivity materially restored relative to Rule A | strict session 13/13 (A 6/13), N2b session 20/20 (A 16/20); closed-loop hover approach 13 (A 6, N2b 12) | **pass** |
| Far perched bilateral-noise case rejected | no firing in the bout | **pass** |
| No new pathological re-escape | N0 0; closed-loop re-escapes at refractory expiry equal N2b's (83 against 81), inherited, not new | **pass** (see note) |

**Recommendation: A OR N2b is suitable as a future runtime candidate** (N4B1-runtime
milestone, only on explicit request), in preference to B OR N2b. B OR N2b adds weak and
non-contact firing (44 / 43 / 57) and a lateral development-N0 event, and gains no
strike speed.

Points the runtime milestone and human test must carry forward:

1. **The combination's false-trigger floor is N2b's.** All observed A OR N2b N0 events are
   N2b summed FAST bilateral coincidences: about 0.005/min observed, upper 0.0123/min over
   630 min. The lateral path added none.
2. **Sustained-chase re-escapes** (a new escape at each refractory expiry while the paddle
   stays on the fly) come with the N2b path. They should be judged in the human test, not
   assumed acceptable.
3. **Sensitivity to weak and non-contact approaches is higher** than N2b's (N1
   weak / glancing / aborted 33 / 28 / 49 against 29 / 27 / 44).
4. **The slow-approach failure is not addressed** (tick 668). N4B2 remains a separate,
   necessary research decision. DNp04 was not used.
5. The recorder schema and `diagnostics()` key set must stay frozen; trigger-path
   provenance belongs in `criterion_diagnostics()`, as for N2b.

## 10. Reproduction

From the research branch, with the archive worktree at `artifacts/worktrees/n2b-rejected`
(`git worktree add --detach artifacts/worktrees/n2b-rejected archive/m1-8-n2b-rejected`,
plus a `data` junction to `data/`):

    .venv\Scripts\python.exe tools\n4b1c_combined.py freeze
    .venv\Scripts\python.exe tools\n4b1c_combined.py holdout --chunk 0 --trials 150   (chunks 0-3, NUMBA_NUM_THREADS=2, parallel; about 25 min)
    .venv\Scripts\python.exe tools\n4b1c_combined.py evaluate
    .venv\Scripts\python.exe tools\n4b1c_combined.py closed-loop                       (about 18 min)

The tools also read the N4A re-simulations (`artifacts/m1_8_n4/`) and the N4B1 fresh N0
(`artifacts/m1_8_n4b1/`).

Artifacts (`artifacts/m1_8_n4b1c/`, git-ignored; sha256 prefixes):

- `frozen_candidates.json` `8eb273f7bd752e1a`;
- `holdout_chunk0..3.npz` `4f0da1ed3b28440f`, `54eb3e953396785b`, `9ce2ca7b9148a207`,
  `790a8117ebe24dca`;
- `evaluation.json` `aed58cf178fe20eb`;
- `closed_loop.json` `5b9fcd56c12584c7`.

Limitations: one tester and two sessions; open-loop human replay; scripted N1 and
closed-loop scenarios. The same-side gap is a simulator (Class C) property.
