# Fly Connectome Simulator & RL Training

A closed-loop fly-swatter simulation in which a frozen fruit-fly connectome drives the fly's
escape behaviour, together with a preregistered study of learned controllers (behaviour cloning
and constrained PPO) trained on the connectome's descending-neuron output.

Pinle (Cassius) Chen · independent project, September 2026 to present · AI-assisted development
(see below)

## Overview

The simulation uses the published MaleCNS v1.0 connectome of the adult male *Drosophila*
(Janelia FlyEM; 166,700 neurons) and the leaky integrate-and-fire simulator FlyBrain 0.1.0.
Each 20 ms tick runs one closed loop:

1. **World.** The fly flies, lands and perches in a room. A player moves a physically simulated
   swatter with the mouse.
2. **Projection and encoding.** The swatter is reduced to what the fly could see: its angular
   size, the growth rate of that size, and its bearing. These values drive 55 LC4 and 91 LPLC2
   looming-sensitive neurons per side. Mouse and swatter coordinates never reach the brain or
   the controller.
3. **Frozen connectome.** One step of the spiking network: 166,700 neurons and 25,088,107
   runtime connections (incoming sensory-neuron edges are removed from the 25,582,938 in the
   source graph). The weights never change.
4. **Readout.** Descending neurons, chiefly DNp01 (the giant fiber, escape) and DNa02
   (steering), left and right.
5. **Controller.** Either a hand-written decoder (the accepted baseline) or a learned policy: a
   2,315-parameter MLP that sees only those readouts and the fly's own motion and state, and picks
   one of 11 maneuvers.
6. **Physics.** The world executes the maneuver, and the next tick starts.

The simulation step is 20 ms, so the design target is 50 Hz. That target is not guaranteed
under every load.

The project started as a reservoir-computing experiment: a linear readout trained on the frozen
network's activity. That experiment is specified in [PROTOCOL.md](PROTOCOL.md), with its
results in [results/REPORT.md](results/REPORT.md); both are kept byte-for-byte.

## How it was built: AI-assisted development

- **My part.** I set the architecture, the experiment protocols, the constraints and the
  acceptance criteria, and I reviewed the results.
- **The AI's part.** AI coding assistants wrote most of the code and ran the training, the
  analyses and the timing measurement.
- **Third-party components.** The spiking simulator FlyBrain 0.1.0
  ([fly.ai](https://github.com/alextitonis/fly.ai)), its Numba kernels and the MaleCNS
  connectome data (Janelia FlyEM) were not written in this project.

## Scope and limits

- **The connectome is frozen.** No gradient passes through it. The learned policy is a small
  network on top of the descending-neuron readout; the 166,700 neurons are not trained end to
  end.
- **This is not human BCI work.** It involves no real EEG recordings and no hardware.
- **A simulation with modelling assumptions.**
  - The LIF dynamics, connection signs and normalisation have not been validated against
    recordings from real flies.
  - The visual input is a reduced, hand-designed encoding, not an image processed by a complete
    eye.
  - The world is 2-D.
- **Activity is not learning.** Training a classifier on frozen neural activity does not mean
  that a fly brain learned the task.

## Results: learned controllers (M2)

The main study trained a learned controller in five independent random seeds and compared it
with the hand-written baseline on a frozen test set.

**Training (M2.3).**
- **Behaviour cloning.** 720 teacher episodes from the hand-written controller gave 522,651
  samples. After subsampling the idle (NONE) action to 5 %, 40,511 samples were used for
  training.
- **Constrained PPO.** BC initialisation, a KL anchor to the cloned policy, delayed dual
  (Lagrange-multiplier) updates, adaptive entropy and critic warm-up, in PyTorch on CUDA.
- **Scale.** Five seeds of 60 iterations each: 10,234,749 simulated decisions in total (about
  10.2 M).

**Evaluation.** The selected policy was evaluated once, on a frozen test set of 320 episodes:
240 threat trials and 80 background episodes.

| Measure | Learned policy | Hand-written baseline | Difference |
|---|---|---|---|
| Unnecessary escapes per minute (background) | 3.025 | 5.15 | 41.3 % fewer |
| Hit rate, lower is better (threat trials) | 59.2 % (142 / 240) | 61.7 % (148 / 240) | −2.5 points, 95 % CI [−9.0, +4.0] |

- **Unnecessary escapes.** The reduction concerns escapes in the absence of a threat. It does not
  mean the fly evades strikes 41 % better.
- **Hit rate.** The difference is not statistically significant (paired McNemar exact test,
  p = 0.53). The test was chosen after the evaluation run. No equivalence or non-inferiority
  margin was preregistered, so the result does not show that the two are equivalent.
- **Conclusion: NO-GO.** The preregistered success criterion was not met, and it was not changed
  afterwards.

**The earlier attempt (M2.2).** In a first PPO run without BC initialisation, all five seeds
lost threat-conditioned escaping within 10-20 iterations and collapsed to never escaping. Early
constraint pressure combined with sparse credit assignment is the inferred cause; no ablation
was run.

**All milestones of the learning line.**

| Milestone | What was done | Result |
|---|---|---|
| M2.0 | Observation and action contracts, runners, probe policies | Reward v1 could be gamed by probe policies, so no training |
| M2.1 | Exposure-controlled benchmark with a frozen test set of 320 episodes per policy; reward and constraints derived from probe policies | GO for constrained training |
| M2.2 | Constrained PPO (NumPy), 5 seeds | NO-GO: every seed collapsed to never escaping |
| M2.3 | BC, then KL-anchored constrained PPO (PyTorch), 5 seeds | NO-GO (above) |
| M2.4-R0 | Decision-rate study | Keep 50 Hz |
| M2.4-A | Strike-balanced loss weighting and threat-dense sampling; a fresh test set frozen before training | Hit rate 0.552 against 0.640, lower is better (paired McNemar p = 0.00026); GO for human testing, with a disclosed procedural deviation |
| M2.4-B | Blind human A/B test, 30 sessions preregistered | Stopped by the participant at 13 of 30 sessions; not unblinded, no conclusion |

**Evaluation discipline and disclosed deviations.**
- **Before the runs.** Protocols, seeds and success criteria were committed with SHA-256
  hashes. Training, validation and test seeds are disjoint, and each frozen candidate was
  evaluated once on its test set.
- **M2.3.** The paired McNemar test was chosen after the test run.
- **M2.4-A.** The test runner was repaired after it was frozen (a multiprocessing pickling bug).
  The formal amendment and the equivalence audit were completed after the test run; training-only
  audits showed identical outputs.
- **M2.4-B.** It was stopped before the preregistered 30 sessions
  ([closure record](game/M2_4_B_CLOSURE.md)).
- **Status.** The learning line is closed. The runtime still uses the hand-written controller,
  and no learned policy is integrated.

The learning code and the M2 reports are on the `feature/m2-0-learning-infra` branch:
[M2.0](https://github.com/cssius111/fly-connectome-reservoir/blob/feature/m2-0-learning-infra/game/M2_0_LEARNING_INFRASTRUCTURE.md),
[M2.1](https://github.com/cssius111/fly-connectome-reservoir/blob/feature/m2-0-learning-infra/game/M2_1_EXPOSURE_CONTROLLED_BENCHMARK.md),
[M2.2](https://github.com/cssius111/fly-connectome-reservoir/blob/feature/m2-0-learning-infra/game/M2_2_CONSTRAINED_LEARNED_POLICY.md),
[M2.3](https://github.com/cssius111/fly-connectome-reservoir/blob/feature/m2-0-learning-infra/game/M2_3_PYTORCH_BC_CONSTRAINED_PPO.md),
[M2.4-R0](https://github.com/cssius111/fly-connectome-reservoir/blob/feature/m2-0-learning-infra/game/M2_4_R0_TEMPORAL_ACTION_FEASIBILITY.md),
[M2.4-A](https://github.com/cssius111/fly-connectome-reservoir/blob/feature/m2-0-learning-infra/game/M2_4_A_STRIKE_CENTRIC_PPO.md),
[M2.4-B protocol](https://github.com/cssius111/fly-connectome-reservoir/blob/feature/m2-0-learning-infra/game/M2_4_B_HUMAN_TEST_PROTOCOL.md).
The evidence files for M2.3 are in
[`game/learning/m2_3/`](https://github.com/cssius111/fly-connectome-reservoir/tree/feature/m2-0-learning-infra/game/learning/m2_3)
on that branch.

## In progress: comparison with real fly data (M3)

Since 2026-10-22 the goal has been for the model fly to behave more like a real fly.

- **The scorecard (M3.0).** It compares the model with published *Drosophila* measurements
  ([design](game/M3_0_FIDELITY_SCORECARD_DESIGN.md),
  [results](results/game/M3_0_FIDELITY_SCORECARD.md)). The model escapes too early and in every
  trial. It cannot tell a frontal from a rear threat. Its spontaneous turns are too rare and too
  small.
- **The escape decision.** After read-only research (M3.1), changes to the visual encoding and to
  the escape decoder (M3.2-M3.4) were each checked against preregistered criteria. Each improved
  some measures and failed at least one check, so none has been adopted. Further read-only
  research (M3.5) found that closing the remaining timing gap would need a change to the frozen
  connectome, and that no single-scale design passes both timing checks. That line is paused.
- **Spontaneous turns and odor tracking (M3.7-M3.8).** Only flight-generator parameters changed.
  - Spontaneous turns are now about 80° in 80 ms, at 0.31 per second, within the band around the
    real fly's baseline of about 0.4 per second.
  - The fly no longer turns spontaneously while it tracks an odor upwind.
  - M3.8 passed all six preregistered checks, including unchanged escapes. It was accepted after
    a human playtest on 2026-10-28
    ([design](game/M3_8_SACCADE_ODOR_DESIGN.md), [results](results/game/M3_8_SACCADE_ODOR.md)).
- **Wall-evoked turns (M3.9).** Wall turns of fixed amplitude, as in the real fly, passed their
  primary check but lowered the upwind heading during odor tracking. They were not adopted
  ([results](results/game/M3_9_WALL_SACCADES.md)).
- **The upwind turn on odor entry (M3.10).** A surge turn at the real fly's timescale (about 0.2 s)
  raised the upwind heading during odor tracking from 0.54 to 0.73. It lowered the spontaneous
  saccade rate slightly below its preregistered band, so it was not adopted
  ([results](results/game/M3_10_UPWIND_SURGE.md)).
- **Still open.** Escape timing and the front/back distinction remain gaps. The record of each
  step is in [TECHNICAL_REPORT.md](TECHNICAL_REPORT.md), section 9.6.

## Timing

A single idle/headless timing run measured about 4.1 ms of compute per 20 ms tick.
- **Conditions.** 8 Numba threads on an Intel i9-13900HX laptop CPU; 1,500 ticks measured after
  a 100-tick warm-up, mean 4.101 ms.
- **What it excludes.** Rendering, learned-policy inference and threat stimulation.
- **What it is not.** Each setting was timed once, so it is not a formal benchmark.

## Repository

| Where | What |
|---|---|
| `main` (this branch) | The current accepted game runtime, the original reservoir experiment and the research records |
| [`feature/m2-0-learning-infra`](https://github.com/cssius111/fly-connectome-reservoir/tree/feature/m2-0-learning-infra) | The learned-controller study (M2): code, protocols, checkpoints and reports |
| [TECHNICAL_REPORT.md](TECHNICAL_REPORT.md) | An overview of all work to date. Where the milestone sections below disagree with it about the current state, the report is newer |
| [PROTOCOL.md](PROTOCOL.md), [results/REPORT.md](results/REPORT.md) | The frozen original experiment; these files keep their original language and bytes for reproducibility |

## Quick start

From the repository root, with Python 3.11 (the validated environment is Python 3.11.16 on the
CPU path):

```text
uv venv --python 3.11.16 .venv
# activate .venv, then:
uv pip install -r requirements-lock.txt
# set FLY_DATA to a data directory (for example ./data), then:
flybrain download                       # downloads the connectivity data
python first_run.py                     # data integrity checks and a replay smoke test
python -m game.app --arena room         # play against the hand-written controller
python -m unittest discover             # run the test suite
```

The original instructions are under "Environment and original experiment" below.

## Earlier milestones (history)

The sections below describe the game runtime as each M1 milestone was signed off. Statements
such as "no reinforcement learning" or "no learned policy" refer to that runtime; the learned
controllers above are separate research. Command examples use Windows PowerShell and are run
from the repository root.

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
M1.7.1 measured ROOM threshold **1.45**. The active ROOM record is the record named by `policy.calibration_paths` in `game_room_config.json` (`results/game/calibration_room_m3_8.json` as of M3.8). It
reuses that one unchanged fixed-fly measurement with exact current provenance, via a
recorded transfer chain of later records. No threshold has been re-measured since M1.7.1.
See the [pre-tuning human diagnosis](results/game/HUMAN_M1_7_DIAGNOSIS.md) and
[M1.7.1 validation and acceptance checklist](results/game/M1_7_1.md).
Reports separate all-tick and alive-only threat/ecology/speed statistics.
Manifests retain the actual CPU thread count for exact replay.
See [final human acceptance and regression](results/game/M1_7_1_ACCEPTANCE.md).
The swatter, swept collision, offscreen geometry and WORLD/policy boundary remain
frozen. The explicitly authorized M1.8-A recorder extension is described above.
M1.8-B (flight kinematics and activity budget) is in progress on top of this lifecycle;
its stages, status and accepted runtime branch are in [TECHNICAL_REPORT.md](TECHNICAL_REPORT.md)
section 9 and [the M1.8-B plan](game/M1_8_B_PLAN.md). The learned controllers (M2) live on
`feature/m2-0-learning-infra` and are not part of the runtime; the runtime policy is the fixed
N4B1C decoder.

Validation commands:

```text
python tools/calibrate_escape.py --config game_room_config.json --trials 28
python tools/session_sanity.py
```

Historical sections below describe earlier milestones. Use `--arena game` for
the preserved GAME preset and `--mode lab` for LAB.

### Environment and original experiment

The virtual environment is `.venv`, inside the repository. Python 3.11.16 and the CPU implementation are the validated path; CUDA/CuPy is not installed.

```powershell
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

`requirements.txt` contains direct dependencies; `requirements-lock.txt` records resolved versions. If the global uv cache is not writable, `uv pip install --no-cache` avoids it without deleting shared Python installations or caches. Git ignores virtual environments, downloaded connectivity, intermediate activity arrays and logs.

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
