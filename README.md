# fly-connectome-reservoir

A real-time fly-swatter simulation in which a frozen fruit-fly connectome (MaleCNS, 166,700 neurons) drives escape behaviour, plus a preregistered study of learned controllers (behaviour cloning and constrained PPO) trained on top of it. It started as a reproducible Windows CPU reservoir experiment, using FlyBrain 0.1.0 and MaleCNS-derived connectivity.

**Training a classifier on frozen neural activity does not mean that a fly brain learned the task.** The original experiment directly injects LC4/LPLC2 feature neurons; it does not process images through a complete eye. LIF dynamics, connection signs and normalization contain modeling assumptions and have not been validated against recordings of real flies.

The frozen experiment is specified in [PROTOCOL.md](PROTOCOL.md), with historical results in [results/REPORT.md](results/REPORT.md). These protected artifacts retain their original language and bytes for reproducibility. Editable project content is English.


## Project overview

### What runs every 20 ms (50 Hz)

1. **World.** The fly flies, lands and perches in a room; the player moves a physically simulated swatter with the mouse (pygame).
2. **Retina.** The swatter is reduced to three numbers the fly could see: its angular size, how fast that size grows (looming) and its bearing. Mouse and swatter coordinates never reach the brain or the controller; the types enforce this.
3. **Visual input.** The three numbers drive 55 LC4 and 91 LPLC2 looming-sensitive neurons per side.
4. **Connectome.** One step of a leaky integrate-and-fire network with 166,700 neurons and 25,088,107 runtime connections (25,582,938 in the source graph; incoming sensory-neuron edges are removed). The weights are frozen: nothing in the brain learns.
5. **Readout.** Escape (DNp01, the giant fiber) and steering (DNa02) descending neurons, left and right.
6. **Controller.** Either the accepted hand-designed decoder (N4B1C) or a learned 2,315-parameter MLP. The MLP sees only those four neural signals plus the fly's own motion and state (60 inputs over 5 frames) and picks one of 11 maneuvers.
7. **Physics** executes the maneuver, and the next tick starts.

The spiking simulator ([FlyBrain](https://github.com/alextitonis/fly.ai) 0.1.0) and the MaleCNS data (Janelia FlyEM) are third-party. The game, the perception pipeline, the controllers and the learning and evaluation code belong to this project.

One headless measurement (idle fly, no threat input, 8 Numba threads, Intel i9-13900HX) gave about 4.1 ms of compute per 20 ms tick, roughly 4.9x faster than real time. It was run once and is not a formal benchmark.

### Learned controllers (M2, `feature/m2-0-learning-infra`)

| Milestone | What was done | Result |
|---|---|---|
| M2.0 | Observation / action contracts, runners, probe policies | Reward v1 could be gamed by never-escape and constant-turn probes, so no training |
| M2.1 | Exposure-controlled benchmark: every threat trial contains exactly one committed strike; background episodes measure unnecessary escapes; reward and constraints derived from probe policies; frozen test set of 320 episodes per policy | GO for constrained training |
| M2.2 | Constrained PPO (NumPy), 5 seeds | NO-GO: all 5 seeds collapsed to never escaping (the unnecessary-escape multiplier overshot early and exploration died); test hit rate 0.738 vs 0.617 |
| M2.3 | PyTorch behaviour cloning of the hand-designed controller (522,651 teacher samples), then KL-anchored constrained PPO with dual warm-up and adaptive entropy, 5 seeds | All 5 seeds stable. Test set: 41% fewer unnecessary escapes (3.02 vs 5.15 per min), no statistically significant hit-rate difference (0.592 vs 0.617, p = 0.53). NO-GO under the preregistered criterion |
| M2.4-R0 | Decision-rate study | Keep 50 Hz |
| M2.4-A | Strike-balanced loss weighting, threat-dense sampling, two-stage checkpoint selection, fresh test set frozen before training | Hit rate 0.552 vs 0.640 (paired McNemar p = 0.00026), 3.48 vs 4.97 unnecessary escapes per min. GO for human testing, with a documented procedural deviation |
| M2.4-B | Blind human A/B test, 30 sessions preregistered | Stopped by the participant after 12 sessions; not unblinded, no conclusion |

**Status:** the learning line is closed. The accepted runtime (`363a1a9`) still uses the hand-designed controller; the learned policy is not integrated.

### Evaluation discipline and disclosed deviations

- Protocols, seeds and success criteria are committed with SHA-256 hashes before runs. Training, validation and test seed ranges are disjoint, and each frozen candidate is evaluated once on its test set.
- M2.3: the paired test (McNemar) was chosen after the test run. No equivalence or non-inferiority margin was ever preregistered, so the hit-rate result means "no significant difference", not "equal".
- M2.4-A: the test runner was repaired after it was frozen (a multiprocessing pickling bug). The formal amendment and the equivalence audit were completed after the test run; TRAIN-only audits showed exactly identical outputs. See [the amendment](game/M2_4_A_EVAL_EXECUTION_AMENDMENT.md).
- M2.4-B: stopped before the preregistered 30 sessions. See [the termination record](game/M2_4_B_EARLY_TERMINATION.md).
- Known model limitation: very slow approaches are not detected, because the visual input encodes only relative geometry.

### Reports

[M2.0](game/M2_0_LEARNING_INFRASTRUCTURE.md),
[M2.1](game/M2_1_EXPOSURE_CONTROLLED_BENCHMARK.md),
[M2.2](game/M2_2_CONSTRAINED_LEARNED_POLICY.md),
[M2.3](game/M2_3_PYTORCH_BC_CONSTRAINED_PPO.md),
[M2.4-R0](game/M2_4_R0_TEMPORAL_ACTION_FEASIBILITY.md),
[M2.4-A](game/M2_4_A_STRIKE_CENTRIC_PPO.md),
[M2.4-B protocol](game/M2_4_B_HUMAN_TEST_PROTOCOL.md).

### Branches

| Branch | Content |
|---|---|
| `feature/m1-8-n4b5r-geometry` | The accepted runtime only, frozen at `363a1a9` (M1.8-N4B5R: N4B1C decoder plus elevation-aware paddle geometry) |
| `feature/m2-0-learning-infra` | The accepted runtime plus all M2 learning work; no accepted runtime file is changed |
| `feature/m1-8-n4b1c-runtime` | The previous accepted runtime (N4B1C decoder layer), frozen at `e3c55b3` |
| `wip/m1-4-enclosure` | M1 escape-decoder research (N2 to N4B8) and the operational handoff state (`game/CURRENT_PROJECT_STATE.md`); proposed for `main` in [pull request 1](https://github.com/cssius111/fly-connectome-reservoir/pull/1), not merged |
| `archive/m1-8-n2b-rejected` | Snapshot of the rejected N2b runtime at `2c30617`; never merged |
| `feature/flyswatter-game` | The M1.3 game baseline at `85f987b` (history) |
| `main` | The original frozen reservoir experiment at `309abd9` |

No branch has been merged into `main`.

### Quick start

From the repository root, with the environment and data set up as described under "Environment and original experiment" below:

```powershell
python -m game.app --arena room     # play against the accepted controller
python -m unittest discover         # run the test suite
```

The M2 learner tests (`test_m2_3_torch.py`, `test_m2_4_a.py`) also need PyTorch from `requirements-learning.txt`. Provenance tests accept a recorded hash of either the LF or the CRLF form of a file, so the result does not depend on the checkout's `core.autocrlf` setting.

## Earlier milestones (history)

The sections below describe the accepted M1 runtime as each milestone was signed off. Statements such as "no reinforcement learning" or "no learned policy" refer to that runtime, which is unchanged; the learned controllers above are separate research.

### M1.8-A: accepted landing, perching and takeoff lifecycle

ROOM now supports local visual approach, physical touchdown, stationary perching,
a minimal food-contact feeding overlay, motivated voluntary departure and neural
escape takeoff. The reference organism is adult male Drosophila melanogaster
(MaleCNS). Ecological behaviors are phenomenological; no landing/feeding neural
circuit, learning or natural activity budget is claimed. Sub-timestep takeoff
dynamics are not explicitly resolved.

Both human acceptance playtests passed: a passive session landed, fed and departed
voluntarily, and a threat session launched a perched fly roughly 14 s before the first
click. See [control architecture and complete parameter evidence table](game/LIFECYCLE.md)
and [validation, human acceptance and playtest procedure](results/game/M1_8_A.md).
The lifecycle pipeline, contact mechanics, takeoff paths, recorder schema and
lifecycle/policy isolation are frozen unless recorded evidence exposes a defect.
A reproducible ordinary spawn for observing a quiet landing is:

```powershell
Set-Location D:\Projects\flybrain-lab
& .\.venv\Scripts\python.exe -m game.app --arena room --seed 255 --record --windowed
```

Keep the pointer away until perched, then approach with the paddle without
clicking to test pre-contact neural launch. Folded wings and a green ring mark
living contact; an amber ring and a FEEDING label mark food contact. Press H for
a HUD that shows effective lifecycle state and motion above the unexecuted
ecological intent. LAB/GAME and the accepted
physical swatter remain unchanged. ROOM schema 4 adds lifecycle events and
alive-only simulator metrics; existing observation whitelists remain unchanged.

### M1.7.1: accepted physical swatter baseline

M1.6 is preserved locally as `58ffd60fb60239a911c1ca0baea458ec743774b7`.
M1.7 and the edge repair are committed at `e0f08ebe55ecefcab69cc7927668c0f2cef7f69c`.
M1.7.1 has passed human acceptance and final regression: ordinary approach follows
pointer velocity with bounded catch-up; fast strikes and edge reachability remain intact. No reinforcement learning,
personalization or M1.5.1 universal-speed calibration is implemented.

```powershell
Set-Location D:\Projects\flybrain-lab
& .\.venv\Scripts\python.exe -m game.app --arena room --record
& .\.venv\Scripts\python.exe -m game.app --arena room --record --windowed --seed 101
& .\.venv\Scripts\python.exe -m game.app --replay 'results/game/sessions/SESSION_ID'
```

Play normally; the REC indicator confirms logging. Each unique directory under
`results/game/sessions/` contains an automatic English report, summary, manifest,
50 Hz state log, consumed input stream, indexed strike windows and separate
whitelisted policy observations. Sessions are ignored by Git. Normal exit
finalizes the report; a force-killed process leaves an explicitly incomplete log.
PLAY records by default; `--no-record` disables it. Use `--record-dir PATH` for
a separate profile. World/debug data never enter the future policy whitelist.

In ROOM the mouse controls desired hand motion. A bounded inertial paddle uses
200 ms of recent input to commit a continuous swing, contact, follow-through and
recovery. LAB and GAME retain their previous swatter dynamics and calibrations.
The ecological ROOM controller and frozen neural threat pathway remain intact.

See [recording, replay, physics and playtest guide](game/SESSIONS.md),
[ROOM ecology](game/ROOM.md), and [actual M1.7 validation](results/game/M1_7.md).
M1.6 evidence remains unchanged in [its historical report](results/game/M1_6.md).
The edge repair allows partially offscreen paddle heads without changing fly bounds
or motor limits. See the [edge audit and validation](results/game/M1_7_EDGE.md).
M1.7.1 measured ROOM threshold **1.45**. The active `calibration_room_m1_8_b2a.json`
reuses that one unchanged fixed-fly measurement with exact current provenance, via a
recorded transfer chain through `calibration_room_m1_8_a.json`. No threshold has been
re-measured since M1.7.1.
See the [pre-tuning human diagnosis](results/game/HUMAN_M1_7_DIAGNOSIS.md) and
[M1.7.1 validation and acceptance checklist](results/game/M1_7_1.md).
Reports separate all-tick and alive-only threat/ecology/speed statistics.
Manifests retain the actual CPU thread count for exact replay.
See [final human acceptance and regression](results/game/M1_7_1_ACCEPTANCE.md).
The swatter, swept collision, offscreen geometry and WORLD/policy boundary remain
frozen. The explicitly authorized M1.8-A recorder extension is described above.
The broader [M1.8 proposal](game/M1_8_PROPOSAL.md) remains a future plan beyond
this lifecycle implementation; M1.8-B and RL are not implemented.

Validation commands:

```text
python tools/calibrate_escape.py --config game_room_config.json --trials 28
python tools/session_sanity.py
```

Historical sections below describe earlier milestones. Use `--arena game` for
the preserved GAME preset and `--mode lab` for LAB.

### Environment and original experiment

The actual virtual environment is `D:\Projects\flybrain-lab\.venv`, inside the repository. Python 3.11.16 and the CPU implementation are the validated path; CUDA/CuPy is not installed.

```powershell
Set-Location D:\Projects\flybrain-lab
$env:FLY_DATA = "$PWD\data"
$env:NUMBA_NUM_THREADS = '4'
& .\.venv\Scripts\python.exe .\first_run.py
& .\.venv\Scripts\python.exe .\test_protocol.py
```

To reproduce the original collection and reporting, use `experiment.py` and `report.py`. Those commands overwrite default results: preserve `results` and `artifacts/results` first. New scientific comparisons should use separate configurations/output directories, for example `experiment.py --config other-config.json --output results-new`; the original report script reads `results/`. Selecting the best test result across parameter choices is not an unbiased evaluation.

To recreate the environment:

```powershell
uv venv --python 3.11.16 .venv
uv pip install --python .\.venv\Scripts\python.exe -r requirements-lock.txt
$env:FLY_DATA = "$PWD\data"
& .\.venv\Scripts\flybrain.exe download
& .\.venv\Scripts\flybrain.exe info
```

`requirements.txt` contains direct dependencies; `requirements-lock.txt` records resolved versions. `requirements-learning.txt` adds PyTorch for the M2 learning code only. If the global uv cache is not writable, `uv pip install --no-cache` avoids it without deleting shared Python installations or caches. Git ignores virtual environments, downloaded connectivity, intermediate activity arrays and logs.

| Files | Purpose |
|---|---|
| `first_run.py` | SHA256/ZIP checks, graph loading, stimulation, timing and replay |
| `config.json`, `PROTOCOL.md` | Frozen experiment parameters and protocol |
| `experiment.py`, `test_protocol.py` | Splits, three networks, raw-input and shuffled-label controls, linear readout and tests |
| `report.py`, `results/` | Original reports, metrics and figures; preserve protected history |
| `artifacts/` | Ignored local arrays, classifiers, logs and render captures |
| `game/`, `game_config.json`, `game_play_config.json` | Interactive game and independent configuration |
| `tools/calibrate_escape.py` | Fixed-fly DNp01 distributions and escape threshold |
| `tools/flight_sanity.py`, `tools/chase_sanity.py` | Isolated locomotion and neural pursuit checks |
| `test_game*.py` | Game regressions and strict perception/action interfaces |

### M1.5: fullscreen GAME and controlled LAB

At M1.5, the default became GAME; current M1.7 defaults to ROOM instead.
H reveals the optional neural HUD. M1.4 was committed separately as
`fe2efb758a10802442edabad01e5a976f4c58b16`; the validated M1.5 foundation is
preserved in the M1.6 checkpoint above. No learning or policy updates occurred.

```powershell
& .\.venv\Scripts\python.exe -m game.app                         # fullscreen PLAY
& .\.venv\Scripts\python.exe -m game.app --windowed --seed 101   # reproducible default ROOM
& .\.venv\Scripts\python.exe -m game.app --mode lab --windowed   # unchanged LAB preset
& .\.venv\Scripts\python.exe -m game.app --mode evaluation --seed 101 --windowed
```

GAME uses 3840×2160 logical units (160×90 body lengths), a 24-unit body,
216 units/s cruise (9 BL/s), and a 288-unit paddle diameter (12 BL). Monitor
resolution changes rendering scale only. Spawns, headings, initial velocity
and flight phases vary deterministically by episode seed. Mouse trajectory
changes physical stroke direction; only retinal consequences reach MaleCNS.
Low-frequency curvature and bounded, gradually realigning sideslip supplement
the existing saccades. No airflow or CFD is added.

See [game/M1_5.md](game/M1_5.md) for architecture, exact observation/log schemas,
mode boundaries, modeling assumptions and the 5–10 minute checklist. Actual
results are in [results/game/M1_5.md](results/game/M1_5.md). Run
`python tools/encounter_sanity.py` to reproduce the new encounter diagnostics.

PLAY/TRAINING use a new base seed per launch unless `--seed` is given;
EVALUATION/LAB default to fixed seeds. All four modes are frozen today.
`--mode training` collects data only. Historical M1.5 logs and counters remain
under `artifacts/game/player-default/`. M1.7 starts a separate recorder/profile
under `results/game/sessions/`; `--record-dir PATH` selects another profile and
`--no-record` disables recording. World/debug data and policy
observations are stored separately. No checkpoint is trained or loaded.

### Interactive fly-swatter

```powershell
Set-Location D:\Projects\flybrain-lab
& .\.venv\Scripts\python.exe tools\calibrate_escape.py --config game_room_config.json --trials 28
& .\.venv\Scripts\python.exe -m game.app
& .\.venv\Scripts\python.exe -m unittest discover -v
& .\.venv\Scripts\python.exe -m game.app --smoke 3
```

Move the mouse to position the swatter; left click strikes. R/Enter restarts, Space/P pauses, H toggles diagnostics, F11 toggles fullscreen, and Escape exits fullscreen or quits. Shortcuts use physical SDL scancodes first, with keysyms as fallback. Text composition and key repeat are disabled at startup/refocus. Restart always resumes a running episode; old-frame clicks do not leak into it.

The threat pipeline is world geometry → frozen `Retina(theta, theta_dot, azimuth)` → balanced LC4/LPLC2 stimulation → frozen MaleCNS-derived runtime graph → descending-neuron activity → fixed policy → physics. Raw mouse/swatter coordinates do not reach the policy. `FlyLoop.step` strictly checks Retina and restricted MotionState types, including rejection of subclasses carrying extra state.

LPLC2 populations are balanced to 91 cells per side (available L94/R91); LC4 to 55 per side (L71/R55), by a fixed encoder seed. The runtime sets `sensory_input=false`, removing incoming sensory-neuron edges: **25,088,107 runtime connections**, compared with **25,582,938 in the original dataset**. The source data are not rewritten. This is not the untouched full MaleCNS graph.

### Policy and calibration contracts

`Policy` requires only `reset()` and `decide(MotorState)`. Diagnostics are optional and exposed generically by Session; a bare valid policy can render. `FixedEscapePolicy` remains the untrained baseline.

`Action.lateral/forward` define body-relative direction. Independent finite `strength` in [0,1] scales the configured escape impulse; invalid values raise. Direction normalization does not destroy strength. Zero strength or direction gives no impulse. `turn` is separate; signed `saccade` requests a bounded heading pulse. A zero-strength escape cannot create an emergency pulse.

MotionState contains only forward/lateral speed, yaw rate and remaining pulse time. It is appended after the brain step and cannot change retinal injection. DNp01 gates emergency escape, with a lower ALERT gate at 55% of the calibrated threshold. Laterality is smoothed over 0.12 s; DNa02 modulates amplitude by at most 15% without reversing the DNp01 sign. There is no learned policy, optimizer or plasticity.

Calibration holds position and heading fixed, keeps velocity zero, freezes locomotion/pulse timers and disables policy escapes/collision. Run:

```text
python tools/calibrate_escape.py --trials 28
```

The threshold is the smallest predefined grid value with zero crossings across all no-loom samples. Runtime requires exact provenance: canonical full-config SHA256, protocol, FlyBrain version, encoder seed/types/population rule, sensory flag and tick duration. Stale local artifacts cannot override matching committed records. Missing matches fail clearly with the calibration command. Custom configs require matching `--config PATH` in both tools and game.

The LAB fixed-fly threshold is 1.45 and GAME is 1.35; both detect 28/28 with median latency 0.06 s. The current M1.7.1 ROOM threshold is freshly measured at 1.45, detecting 28/28 with median latency 0.08 s after click. Each has zero crossings in its 2,520 no-loom ticks. ROOM uses a 6-second paddle settling interval and verifies that the head is stationary before measurement. These are calibration-sample results, not a guarantee of zero false triggers in arbitrary free flight.

### M1.4 flight and enclosure baseline

M1.4 continues Claude WIP `182c5a9` from stable M1.3 `85f987b279dbd2b1f725fa79aa299281259258ab`. The body polygon is 24 px; cruise is 160 px/s (6.67 body lengths/s), with a 1,000 px/s safety cap. There is no conversion to real-world millimeters or physiological speed.

CORRECTION/SACCADE/AVOID/DEPART are seeded phenomenological maneuvers; ALERT/ESCAPE originate in descending-neuron policy decisions. Half-sine pulses integrate continuously, with explicit peak-rate bounds and no instantaneous reversal. Quiet intervals mix short, ordinary and long flight segments. A local WallCue supports pre-contact avoidance, perimeter persistence and departure. It contains no map, absolute wall coordinates or exit waypoint. No opening is configured. Final containment cancels outward velocity rather than bouncing or setting heading.

See [game/FLIGHT.md](game/FLIGHT.md) for the model and human checklist, and [results/game/M1_4.md](results/game/M1_4.md) for measurements and limitations. Run `python tools/flight_sanity.py` and `python tools/chase_sanity.py --label m1-4`. Historical M1.2/M1.3 chase records remain separate. The original 20 protected experiment files, 36 saved prediction records and two exact neuronal replays remain unchanged.

## Biological grounding and modeling assumptions

1. **Direct biological/connectomic evidence:** MaleCNS connectivity and cell annotations distributed through FlyBrain; single anatomical specimen, with a modified runtime graph.
2. **Biologically motivated phenomenological approximation:** coherent flight segments and rapid turns, local wall exploration, manual neural-to-action decoding and modeled LIF dynamics. Numeric parameters are not fitted physiological measurements.
3. **Pure game-engine convention:** cruise drive, damping, collision envelopes, speed/yaw limits, hard containment, swatter animation and rendering.

The model is 2D and omits wings, lift, roll, pitch, banking and complete retinal image processing. High-impulse escapes can require wall fallback. Difficulty and skill-based hittability require human playtesting; successful evasion is neither learning nor proof of a connectome advantage.

## Data attribution

- [MaleCNS official data](https://male-cns.janelia.org/download/): MaleCNS v1.0, FlyEM / HHMI Janelia and collaborators, CC-BY.
- [Community simulator fly.ai](https://github.com/alextitonis/fly.ai): `flybrain==0.1.0` and SHA256-verified `brain-v1` prebuilt data. Point-neuron dynamics are not a complete physiological simulation.

The project retains provenance and checksums without redistributing the downloaded connectivity.
