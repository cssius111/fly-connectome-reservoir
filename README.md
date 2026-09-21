# fly-connectome-reservoir

A reproducible Windows CPU computational neuroscience experiment and an untrained interactive fly-swatter baseline, using FlyBrain 0.1.0 and MaleCNS-derived connectivity.

**Training a classifier on frozen neural activity does not mean that a fly brain learned the task.** The original experiment directly injects LC4/LPLC2 feature neurons; it does not process images through a complete eye. LIF dynamics, connection signs and normalization contain modeling assumptions and have not been validated against recordings of real flies.

The frozen experiment is specified in [PROTOCOL.md](PROTOCOL.md), with historical results in [results/REPORT.md](results/REPORT.md). These protected artifacts retain their original language and bytes for reproducibility. Editable project content is English.


## M1.8-A: accepted landing, perching and takeoff lifecycle

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

## M1.7.1: accepted physical swatter baseline

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
M1.7.1 measured ROOM threshold **1.45**. The active `calibration_room_m1_8_a.json`
explicitly reuses that unchanged fixed-fly measurement with exact current provenance.
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

## Environment and original experiment

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

## M1.5: fullscreen GAME and controlled LAB

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

## Interactive fly-swatter

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

## Policy and calibration contracts

`Policy` requires only `reset()` and `decide(MotorState)`. Diagnostics are optional and exposed generically by Session; a bare valid policy can render. `FixedEscapePolicy` remains the untrained baseline.

`Action.lateral/forward` define body-relative direction. Independent finite `strength` in [0,1] scales the configured escape impulse; invalid values raise. Direction normalization does not destroy strength. Zero strength or direction gives no impulse. `turn` is separate; signed `saccade` requests a bounded heading pulse. A zero-strength escape cannot create an emergency pulse.

MotionState contains only forward/lateral speed, yaw rate and remaining pulse time. It is appended after the brain step and cannot change retinal injection. DNp01 gates emergency escape, with a lower ALERT gate at 55% of the calibrated threshold. Laterality is smoothed over 0.12 s; DNa02 modulates amplitude by at most 15% without reversing the DNp01 sign. There is no learned policy, optimizer or plasticity.

Calibration holds position and heading fixed, keeps velocity zero, freezes locomotion/pulse timers and disables policy escapes/collision. Run:

```text
python tools/calibrate_escape.py --trials 28
```

The threshold is the smallest predefined grid value with zero crossings across all no-loom samples. Runtime requires exact provenance: canonical full-config SHA256, protocol, FlyBrain version, encoder seed/types/population rule, sensory flag and tick duration. Stale local artifacts cannot override matching committed records. Missing matches fail clearly with the calibration command. Custom configs require matching `--config PATH` in both tools and game.

The LAB fixed-fly threshold is 1.45 and GAME is 1.35; both detect 28/28 with median latency 0.06 s. The current M1.7.1 ROOM threshold is freshly measured at 1.45, detecting 28/28 with median latency 0.08 s after click. Each has zero crossings in its 2,520 no-loom ticks. ROOM uses a 6-second paddle settling interval and verifies that the head is stationary before measurement. These are calibration-sample results, not a guarantee of zero false triggers in arbitrary free flight.

## M1.4 flight and enclosure baseline

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
