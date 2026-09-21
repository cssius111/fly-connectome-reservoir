# M1.7.1 accepted baseline and final regression

The owner accepted M1.7.1 using real human recording `20260921T013555.126134Z-cb64aa1a`. No swatter implementation or parameter changes were made during finalization. The physical approach controller, strike phases, swept collision, partial-offscreen geometry, recorder/replay interface and WORLD/policy separation are frozen unless new recorded evidence demonstrates a defect. Difficulty alone is not a reason to retune them.

## Verified repository history

Before finalization, branch `wip/m1-4-enclosure` pointed to `e0f08ebe55ecefcab69cc7927668c0f2cef7f69c`. That existing commit already contains M1.7 recording, physical swatter and edge repair. Earlier separate commits `58ffd60` and `fe2efb7` contain ROOM and flight work. The branch already tracked `origin/wip/m1-4-enclosure` and was three commits ahead of the locally recorded upstream. The remaining changes are M1.7.1 approach tracking, thread-aware exact replay, all/alive reporting, calibration settlement validation, tests and their documentation/evidence. Finalization preserves the existing commits; no squash, rebase, force push or main merge is requested.

## Independent human-recording checks

Raw tick hashes and indices, all/alive state fractions, median speeds, cap occupancy and edge reachability were checked separately from the recorded summary. Complete machine-readable evidence is [acceptance_m1_7_1.json](acceptance_m1_7_1.json). The original ten session files remain byte-identical and are excluded from Git.

| Metric | Previous human M1.7 | Accepted human M1.7.1 |
|---|---:|---:|
| Total recorded ticks | 15,039 | 6,911 |
| Post-step-alive ticks | 7,752 | 5,425 |
| Alive APPROACH head-speed median, units/s | 1672.64 | 180.23 |
| Alive APPROACH >=95% of 1800 cap | 46.93% | 1.61% |
| Alive CALM | 31.84% | 54.73% |
| Alive ALERT | 20.70% | 23.43% |
| Alive ESCAPE | 47.46% | 21.84% |
| Strikes / hits / misses | 112 / 64 / 48 | 14 / 10 / 4 |

New-session head-speed p75/p90/p95 are 433.86 / 927.46 / 1310.91 units/s over 5,166 alive APPROACH ticks. Pointer-speed p50/p75/p90/p95 are 141.42 / 316.23 / 707.11 / 1240.95 units/s over 5,156 derivative-valid ticks. Pointer derivatives exclude each episode's first sample. The median target error is 8.15 units on those paired samples. All-tick ESCAPE is 38.65%, versus 21.84% among alive ticks; the corrected report preserves both denominators.

The approximately 1,600-units/s strike-speed median specifically refers to the 70 ACTIVE_CONTACT ticks: 1603.95. Combining FAST_SWING and ACTIVE_CONTACT yields a different median, 1385.20 over 154 ticks. This is time-sampled phase speed, not a median of per-strike peaks. All 5,425 alive ticks remain geometrically reachable; two near-wall hits and one near-wall miss were recorded. The previously accepted partially offscreen hits remain historical evidence.

There are two raw target discontinuities above an offline diagnostic threshold of 10,000 units/s. The largest is 85,205.28 at global tick 4,997, where physical head speed is 114.46 and displacement is only 0.971 units. The other is 32,554.45 at tick 6,873. Every within-episode head displacement is bounded by the configured 3200 * 0.02 units; the observed maximum is 47.285. Existing WORLD diagnostics are sufficient, so no behavior or schema field was changed. These sampled target jumps do not identify physical hand acceleration or their OS-level cause.

The sessions contain different player behavior and exposure. Fourteen new strikes do not establish that the fly became easier or harder, nor a causal effect on neural escape. This milestone accepts physical interaction, not biological fidelity or game difficulty.

## Final validation

- Complete suite: **247/247 passed in 49.480 seconds**. It includes all 15 wall/corner/partial-offscreen/swept-collision edge tests, recorder population/isolation tests and exact-replay/runtime tests.
- Newest real human session: **6,911 exact deterministic ticks, 6,924 input operations, 10 episodes**. Recorded runtime is **8 Numba threads, OpenMP**. Replay was called with one active thread, restored eight internally, then restored one afterward. Source/config/dataset checks passed; no historical session files or replay subdirectories were written. Validation took 28.64 seconds. Full-brain snapshots are not compared; recorded deterministic state and compact neural readouts are exact.
- New synthetic fixture: **1,200 exact ticks / 1,212 operations / 3 episodes**, including recorder/replay behavior. Runtime is four threads, OpenMP.
- Fresh native Windows pygame smoke passed all six swatter phases, pause/resume, R restart and fullscreen/windowed controls; its 206 recorded ticks across two episodes replay exactly. LAB, GAME and ROOM each pass a separate three-second headless smoke.
- **20 original protected files, 24 historical game results and ten files in each of the old and new human recordings remain unchanged.** Thirteen core modules including neural policy, perception, flight and ecology remain identical to the M1.7 baseline.
- Original verification passes **36 prediction records, two exact held-out neuronal replays, source hashes and frozen weights**. Identical verification output is checked without rewriting the protected historical output.
- `git diff --check` passes. Session archives, datasets, caches and the virtual environment remain excluded from Git.

| Preset | Matching committed calibration | Threshold | Loom detections | No-loom triggers | Median latency |
|---|---|---:|---:|---:|---:|
| LAB | calibration.json | 1.45 | 28/28 | 0/2520 ticks | 0.06 s |
| GAME | calibration_game.json | 1.35 | 28/28 | 0/2520 ticks | 0.06 s |
| ROOM | calibration_room_m1_7_1.json | 1.45 | 28/28 | 0/2520 ticks | 0.08 s |

All three committed records independently match current canonical provenance. Runtime-selected matching records agree. ROOM calibration uses fixed fly position/heading, zero velocity, no wander/escape/collision, and a checked six-second paddle settlement. The frozen active record was validated, not tuned or recalibrated during acceptance. Its finite no-loom sample is not a guarantee of zero triggers in arbitrary play.

## Freeze and next decision

M1.7.1 is accepted and frozen. The next proposal is [M1.8: Biologically Grounded Activity Budget and Flight-State Kinematics](../../game/M1_8_PROPOSAL.md). It is planning only. No new flight state, touchdown, feeding, takeoff, learning system or RL implementation is part of this milestone.
