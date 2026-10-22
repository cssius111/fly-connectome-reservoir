# A frozen fly connectome in a real-time escape game

**Technical report, 2026-10-22.** Covers all work from 2026-09-17 to 2026-10-22:
the original reservoir experiment, the interactive fly-swatter runtime, the escape-decoder
research and the learned-controller study. Every number below is copied from a committed
report or record, named where it appears. Only the test suites in section 10 and the
measurements in section 9 were run while preparing this report.

## 1. Summary

A connectome-derived spiking model of the adult male *Drosophila* central nervous system
(MaleCNS, 166,700 neurons) is run with frozen weights inside a 2-D game in which a human
tries to swat the simulated fly. The swatter reaches the brain only as three numbers per
tick (angular size, its growth rate and bearing), which drive looming-sensitive LC4 and
LPLC2 neurons; escape is read from the DNp01 giant-fiber descending neurons. The project
found:

1. **Reservoir readout (Part I).** A linear readout of descending-neuron activity solves a
   left/right side task perfectly but a short-delay order task only at 56 %, with
   intervals that include chance. Coarse network controls do not support a claim that the
   biological wiring is computationally special.
2. **Real-time runtime (Part II).** The full network runs about 4.9 times faster than real
   time on a laptop CPU in one informal measurement, with a type-enforced boundary that
   keeps all world state out of the brain and the controller. A physical swatter, a
   landing and perching lifecycle and exact session replay were accepted by human
   playtests.
3. **Escape decoding (Part III).** In a fixed-fly measurement with no looming input, the
   original single-sample threshold produced 1.30 false escapes per minute from
   spontaneous activity. A lateralized dual-path decoder
   removed them (3 events in 630 minutes) without slowing strike detection (0.08-0.10 s),
   and a geometry fix removed a foreshortening artifact. A mirror test then showed that,
   under this sensory representation, a slowly approaching swatter and the fly's own
   approach toward a parked swatter are **input-identical**, so no readout can separate
   them.
4. **Learned control (Part IV).** After two failed attempts, a 2,315-parameter controller
   trained with strike-centric constrained PPO was hit less often than the hand-designed
   decoder on a fresh preregistered test set (0.552 vs 0.640, paired p = 0.00026). Its
   blind human test was closed at 13 of 30 sessions without unblinding, so no human-level
   conclusion exists.

The work was run with preregistered protocols, frozen holdouts, single-use test sets and
disclosed deviations (section 7).

## 2. Scope and what is not claimed

- **Nothing in the brain learns.** Connectome weights are frozen and asserted unchanged.
  Classifiers (Part I) and controllers (Part IV) are trained downstream of the
  descending neurons; neither is "the fly learning".
- **The model is not physiologically validated.** LIF parameters, connection signs and
  normalization are modelling assumptions; the runtime removes incoming sensory-neuron
  edges; one anatomical specimen is used; there is no eye model, only direct drive of
  LC4/LPLC2 cells.
- **The world is a 2-D game.** There are no wings, lift, roll, pitch or banking, and
  ROOM speeds are 5-15 times below reviewed free-flight measurements in body lengths per
  second. Ecological behaviours (wind, odor, landing, feeding) are phenomenological.
- **Parameters are classified** A (direct matched measurement), B (literature-inspired
  phenomenology) or C (engineering or game choice). No ecological or kinematic parameter
  is class A ([game/M1_8_EVIDENCE.md](game/M1_8_EVIDENCE.md)).
- **Human evidence is thin.** All playtests and the blind A/B sessions were played by one
  person.

The spiking simulator (FlyBrain 0.1.0) and the MaleCNS v1.0 data (FlyEM / HHMI Janelia,
CC-BY) are third-party; the game, perception pipeline, decoders, learning and evaluation
code belong to this project.

## 3. Part I: the frozen-connectome reservoir experiment

The project began on 2026-09-17 as a small, preregistered reservoir-computing experiment
(`main` @ `309abd9`). Its protocol, [PROTOCOL.md](PROTOCOL.md), was written before the
first classifier run, and its outputs under `results/` are protected: their bytes and
original language are preserved for reproducibility.

### 3.1 Question and framing

Can a linear readout of descending-neuron activity in a frozen, MaleCNS-derived spiking
network solve two simple left/right tasks, and does the real wiring do better than coarse
disruption controls? The experiment is explicitly **not** a test of learning in a fly:
only the linear classifier is trained, the network weights never change, and input is
direct voltage injection into visual feature neurons rather than an image processed by an
eye.

### 3.2 Model, input and readout

- **Network.** FlyBrain 0.1.0 with its prebuilt MaleCNS v1.0 graph: 166,700 neurons and
  25,582,938 signed, normalized neuron-to-neuron edges (edges, not synapses). All neurons
  share one point-neuron LIF parameter set (`config.json`: dt 20 ms, gain 3.0, tonic
  0.14, noise rate 1.2 Hz, noise amplitude 0.22). Sensory feedback stays on
  (`sensory_input = true`), a stated model assumption.
- **Input.** 55 LC4 and 91 LPLC2 cells per side (all of the smaller side's population and
  a seeded subset of the larger side, encoder seed 20260917).
- **Readout.** All 1,314 annotated descending neurons, excluding every stimulated cell;
  features are per-neuron spike rates in a fixed window. The readout never sees labels,
  amplitudes, seeds or trial time.

### 3.3 Tasks and design

Every trial resets the network to zero and runs a 200 ms unstimulated warm-up.

- **Side** (pipeline check): one 400 ms pulse on the left or right; read the last 200 ms.
- **Order** (short-delay recency probe): two 200 ms pulses of equal amplitude, left then
  right or right then left, 100 ms apart; after a further 100 ms, read 200 ms with no
  input. Integrated left and right input is identical, so only timing distinguishes the
  classes.

Amplitudes are Uniform(0.55, 0.95). There are three stochastic replicates (seeds 101,
202, 303) of one anatomical specimen, each with 60 training, 20 validation and 60 test
trials per task, exactly balanced, for 2,520 simulated trials in total. Trial inputs and
noise seeds are shared across network conditions, so comparisons are paired.

The readout is a ridge classifier on standardized features, with alpha chosen from
{1000, 100, 10, 1, 0.1} on validation accuracy, refit on training plus validation and
evaluated once on the test set. Controls: chance (50 %); a classifier on the full
two-channel input history (information available); one on integrated left/right input
(solves Side, cannot solve Order); a global postsynaptic-label permutation of the graph
per replicate; a no-connection network with the same neurons, tonic drive and noise; and
a shuffled-label fit on true-network activity.

### 3.4 Results

Test accuracy, correct out of 60 per replicate, with mean and SD across replicates
(`results/summary.json`, `results/metrics.csv`, `results/REPORT.md`):

| Task | Condition | 101 | 202 | 303 | Mean +/- SD |
|---|---|---:|---:|---:|---:|
| Side | connectome | 60 | 60 | 60 | 100.0 % +/- 0.0 |
| Side | label permutation | 53 | 45 | 53 | 83.9 % +/- 7.7 |
| Side | no connections | 36 | 29 | 25 | 50.0 % +/- 9.3 |
| Side | input history | 60 | 60 | 60 | 100.0 % +/- 0.0 |
| Side | integrated input | 60 | 60 | 60 | 100.0 % +/- 0.0 |
| Side | shuffled labels | 38 | 22 | 38 | 54.4 % +/- 15.4 |
| Order | connectome | 36 | 33 | 32 | 56.1 % +/- 3.5 |
| Order | label permutation | 27 | 28 | 30 | 47.2 % +/- 2.5 |
| Order | no connections | 32 | 31 | 25 | 48.9 % +/- 6.3 |
| Order | input history | 60 | 60 | 60 | 100.0 % +/- 0.0 |
| Order | integrated input | 24 | 32 | 28 | 46.7 % +/- 6.7 |
| Order | shuffled labels | 26 | 23 | 28 | 42.8 % +/- 4.2 |

The Wilson 95 % intervals for the connectome are 94.0-100.0 % on Side in every replicate
and 47.4-71.4 %, 42.5-66.9 % and 40.9-65.4 % on Order; all three Order intervals include
chance. The paired connectome-minus-permutation differences are +16.1 percentage points
on Side and +8.9 on Order (descriptive only). The full run took 202.9 s on a laptop CPU.
The verification step confirmed 36 prediction records, exact replay of held-out neuronal
activity and unchanged weights (`results/verification.json`).

### 3.5 Interpretation

- Side is solved, but the raw input history solves it equally well; this shows only that
  a decodable signal reaches the descending neurons.
- Order is weak: 56 % with intervals that include chance. Where it succeeds it can rely on
  the most recent side, so it is not evidence of sequence computation.
- Three permuted graphs are far too few to claim that the biological wiring beats a
  matched random network, and the permutation destroys anatomy and input/output alignment
  together, so no advantage could be attributed to fine topology anyway.
- One specimen, one encoder subset, one parameter set and short reset trials limit every
  conclusion.

This experiment fixed the conventions the rest of the project kept: protocols and seeds
committed before runs, disjoint splits, a single test evaluation, frozen weights asserted
in code, and descriptive reporting without claims beyond the data.

The 1,314 readout neurons are 656 left, 648 right and 10 midline descending neurons;
`results/smoke.json` lists only the two lateral counts. The protected-file list
`artifacts/m1-2/protected-before.json` named in `AGENTS.md` is a local, untracked file, so
the 20-file integrity check cannot be run from a fresh clone.

## 4. Part II: the real-time escape game (M1)

From 2026-09-18 the frozen network was placed in closed loop with a 2-D world, a fly body
and a human-controlled swatter. Each milestone was accepted by automated validation and,
where behaviour changed, by human playtests.

### 4.1 Per-tick pipeline and information boundary

The simulation runs at a fixed 20 ms tick (50 Hz); the swatter integrates in sub-steps
of at most 2 ms. One tick of `Session.tick` (`game/session.py`):

1. **World input.** The pointer target is set and a click may start a committed strike.
2. **Retina** (`game/perception.py`). The swatter is reduced to a frozen
   `Retina(theta, theta_dot, azimuth)`: angular size `2 atan(r / d)` with the 3-D
   distance including paddle height, its finite-difference growth rate, and body-frame
   bearing.
3. **Encoder.** LPLC2 is driven as the loom channel and LC4 as the threat channel
   (`threat = clip(theta / 0.5) x clip(theta_dot / 2.0)`), on 55 LC4 and 91 LPLC2 cells
   per side.
4. **Connectome.** One LIF step of the 166,700-neuron network. The runtime sets
   `sensory_input = false`, which removes incoming sensory-neuron edges: 25,088,107 runtime
   connections against 25,582,938 in the source graph. The source files are not rewritten;
   this is a modified runtime graph, not the untouched MaleCNS graph.
5. **Readout.** DNp01 (giant fiber) and DNa02 traces, left and right, with a 0.1 s decay.
6. **Policy.** `FixedEscapePolicy` turns the traces into an `Action` (escape impulse
   direction and strength, turn, saccade).
7. **Ecology and lifecycle** (ROOM only) choose a behavioural context from local sensing.
8. **Physics** integrates the swatter, the fly and collisions; the recorder captures the
   tick.

The boundary is enforced by types: `FlyLoop.step` accepts only an exact `Retina` and an
exact `MotionState` (forward and lateral speed, yaw rate, remaining pulse time), rejecting
subclasses that could smuggle extra state. Mouse and swatter coordinates, click state,
world position, heading, odor, food and contact variables never reach the brain or the
policy. The policy observation whitelist is the four descending-neuron values, the four
motion values, the policy's own behaviour state and a short history.

Units: one body length (BL) is 24 world units. The GAME and ROOM worlds are 3840 x 2160
units (160 x 90 BL), the paddle is 288 units (12 BL) across, cruise is 216 units/s
(9 BL/s), the escape impulse is 880 units/s and the speed ceiling is 1000 units/s. A
model convention of 2.5 mm per BL makes ROOM about 0.40 x 0.23 m; it is not a
physiological calibration. One headless measurement (idle fly, 8 Numba threads, Intel
i9-13900HX laptop CPU) gave about 4.1 ms of compute per 20 ms tick, roughly 4.9 times
faster than real time; it was run once and is not a formal benchmark.

### 4.2 Milestones

| Milestone | Date | Commit | Main change | Acceptance |
|---|---|---|---|---|
| M1 / M1.1 | 2026-09-18 | `70fa3ed`, `ae2d477` | First connectome-driven game; Retina bottleneck; DNp01 threshold and calibration tool; config-hash provenance | Tests |
| M1.2 / M1.3 | 2026-09-18 | `85253f9`, `85f987b` | Continuous cruise, ALERT at 55 % of threshold, half-sine saccades, `MotionState` | Tests; scripted chase |
| M1.4 | 2026-09-19 | `fe2efb7` (local only) | 24-unit body, flight segments, local `WallCue`, hard containment | 134 tests |
| M1.5 | 2026-09-19 | (in M1.6) | GAME arena 160 x 90 BL, seeded spawns, directional strokes, modes, interaction recorder | 158 tests |
| M1.6 | 2026-09-19 | `58ffd60` (local only) | ROOM ecology: analytic wind and odor, eight ecological states, perch objects | 194 tests |
| M1.7 + edge | 2026-09-20 | `e0f08eb` (local only) | Physical inertial paddle, swept collision, recorder with exact replay, partially offscreen paddle | 232 tests; human session diagnosed |
| M1.7.1 | 2026-09-21 | `cab1184` | Pointer-velocity approach controller; time at >= 95 % of the paddle speed cap fell from 46.9 % to 1.6 % | **Human-accepted**; frozen |
| M1.7.2 | 2026-10-22 | `657e681` ... `b570269` | Line-symmetric paddle axis for the visual geometry, so a reversal no longer spins the paddle (ROOM `config_version` 27; section 9.7) | **Human-accepted 2026-10-22**; frozen |
| M1.8-R0 | 2026-09-21 | `f8f440b` | Evidence lock: 23 primary papers, 147 inventoried parameters, no parameter promoted to class A | Documentation |
| M1.8-A | 2026-09-21 | `bfbef04` | Landing, perching, feeding overlay, voluntary and neural escape takeoff; recorder schema 4 | **Two human playtests**; frozen |
| M1.8-B1 to B2b-ii | 2026-09-21 | `8a8064d` ... `0d8c254` | Kinematics refactor and first sampled speed distribution (section 4.5) | Bit-identical replay, then one attributed divergence |
| M1.8-N2 to N4B5R | 2026-09-22 to 25 | ... `363a1a9` | Escape decoder and visual geometry (Part III) | **Human-accepted**; current runtime |

The M1.4, M1.6 and M1.7 commits named in the reports exist only in the original local
repository: the accepted branch starts from the M1.7.1 commit `cab1184`, and those
milestones survive as reports under `results/game/`.

### 4.3 Escape calibration

The escape threshold is measured, not tuned in play (`tools/calibrate_escape.py`). The
fixed-fly-v2 protocol holds the fly still with collisions and escapes disabled, then runs
28 no-loom trials (a paddle hovering 30-170 units away; 2,520 ticks) and 28 committed
strikes through the real Retina, encoder, MaleCNS and DNp01 path. The threshold is the
smallest grid value with zero no-loom crossings; detection must reach 0.90.

| Arena | Threshold | Detection | Median latency |
|---|---|---|---|
| LAB | 1.45 | 28/28 | 0.06 s |
| GAME | 1.35 | 28/28 | 0.06 s |
| ROOM (M1.7) | 1.70 | 28/28 | 0.10 s |
| ROOM (M1.7.1, current measurement) | 1.45 | 28/28 | 0.08 s |

The runtime refuses to start unless a calibration record matches the canonical hash of
the full configuration, the protocol, the FlyBrain version, the encoder and the tick.
Every later ROOM milestone that did not change the fixed-fly input reuses the M1.7.1
measurement through an explicit transfer record naming the exact bytes it transfers from
and the configuration paths that changed. The 42-second calibration sample later proved
too short: N0 (Part III) measured 1.30 false escapes per minute at 1.45.

### 4.4 Swatter, lifecycle and recording

- **Physical swatter (M1.7.1, frozen).** The mouse sets desired hand motion; an inertial
  paddle follows pointer velocity with bounded catch-up and commits a 760 ms strike cycle
  (commit, fast swing, active contact, follow-through, recovery). Only active contact is
  lethal, tested by a swept disk against the fly interpolated within the tick.
- **Lifecycle (M1.8-A, frozen).** A visually guided approach (orient, decelerate, leg
  commit) leads to touchdown at <= 3 BL/s, a stationary perch with live sensing, an
  optional feeding overlay on food, a seeded hazard for voluntary takeoff, and a neural
  escape takeoff that requires a real nonzero escape action. ALERT never launches. In the
  second human playtest a perched fly escaped about 14 s before the first click, from a
  pre-contact neural response.
- **Recorder and replay.** Human sessions are recorded at 50 Hz to a git-ignored
  directory with a manifest, state log, input stream, strike windows and separately
  whitelisted policy observations. Replay re-hashes every deterministic field and must
  match exactly; it restores the recorded Numba thread count, because one session
  diverged at tick 278 with the wrong count. Schema 4 is current; replay accepts 3 and 4.

### 4.5 Flight kinematics (M1.8-B, in progress)

M1.8-R0 found that ROOM flies **5-15 times slower** than reviewed free-flight
measurements in body lengths per second (cruise 9 BL/s against 60-150 BL/s), and that
no reviewed source fixes ROOM's eight speed envelopes or their shapes. The plan
([game/M1_8_B_PLAN.md](game/M1_8_B_PLAN.md)) therefore maps any literature magnitude
through one class C parameter, `room_kinematic_scale`, never rescales simulation time,
and never tunes kinematics for difficulty.

| Stage | Commit | Result |
|---|---|---|
| B1 | `8a8064d` | Context, profile request, executor, physics refactor; bit-identical on 7 scenarios and 4,060 ticks |
| B2a | `4d9566c` | Inert seeded sampler and the scale parameter at 1.0; bit-identical |
| B2b caps and escape/cruise study | `e504499`, `bea44d0` | The shared 1000 units/s ceiling also binds the neural escape; above scale ~3.2 escape would make a fast fly slower, and above ~30 BL/s it erases the graded escape strength |
| B2b-i | `924ccc3` | Three separated class C ceilings, all still 1000 units/s; bit-identical |
| B2b-ii | `0d8c254` | EXPLORE speed: one symmetric triangular draw on the accepted 5-8 BL/s support per EXPLORE episode, replacing a deterministic 8 s sinusoid with a U-shaped time density; mean kept at 6.5 BL/s, sd 1.06 to 0.61. First intended divergence at tick 0; LAB, GAME and no-ecology runs stay bit-identical |
| B2b-iii | `7b9fa05` | ODOR_TRACK speed by the same method on its accepted 9-13 BL/s support, from its own random stream; mean 11.0, sd 1.41 to 0.82. Code alone is bit-identical; the first divergences are exactly the first airborne ODOR_TRACK ticks. Paired 240-minute free-flight check passes (section 9.2). **Accepted 2026-10-21** |
| B3a | `0e463bc` | The ecology receives CALM when the policy reports ALERT but no saccade is requested or executing; the lifecycle keeps the accepted threat. ALERT entries fall from about 45 to about 2 per minute and TRANSIT rises to about 23 % of alive time. Paired check passes; self-approach escapes rise 2 -> 8 (section 9.4). **Accepted 2026-10-21** |
| B2c-B4b | `9e8686f` ... `4fb5ef5` | The remaining stages, preregistered together: an evaluation-metrics tool; ODOR_SEARCH and RECOVER speed sampling; a sampled speed-transition rate; the odor timers replaced by an encounter history; the EXPLORE/TRANSIT dwell timers replaced by hazards; resampled casting and drift periods; the odor derivative and bilateral difference used; a wind reliability term. Every stage passes its automated checks (section 9.5) | **Accepted 2026-10-22** |

On 2026-10-20 the user answered the plan's remaining questions: the arena stays
160 x 90 BL, the recorder moves to schema 5 only when a stage needs new fields, and
M1.8-B stays phenomenological at `room_kinematic_scale` = 1.0. At that scale no ceiling
binds, so the escape/cruise questions are deferred. Section 9 describes B2b-iii, the
ALERT finding, B3a, which follows from it, and the completion of M1.8-B.

## 5. Part III: escape decoding and visual geometry (M1.8-N0 to N4B8)

Between 2026-09-21 and 2026-09-25 a research line replaced the single-sample escape
threshold with a decoder that is both fast and quiet, fixed a visual-geometry artifact,
and finally established a limit of the current sensory representation. Reports are in
`game/M1_8_*.md` on `main`. N0 to N4B1C and N4B5R came with the runtime history. N4B2 to N4B8
and the handoff state `game/CURRENT_PROJECT_STATE.md` (a snapshot of 2026-10-08) came from
`wip/m1-4-enclosure`.

### 5.1 The starting defect

A perched fly under a stationary paddle, with zero looming input on all four LC4/LPLC2
channels, could still launch an escape. Spontaneous MaleCNS activity adds 1.0 per DNp01
spike to a 0.1 s decaying trace, and the legacy rule fired when the summed left plus right
trace reached 1.45 on a single sample: between the one-spike and two-spike levels, with a
calibration margin of 0.00067 over 42 s of no-loom data
(`game/M1_8_NO_LOOM_FALSE_ESCAPE.md`). A 70-minute fixed-fly, no-loom measurement (N0)
then gave **91 false escapes, 1.30 per minute**, almost all from two-spike coincidences
(`game/M1_8_NO_LOOM_CALIBRATION.md`). The decoder also had to stay fast: the legacy
rule detects committed strikes in 0.08 s.

### 5.2 From N2 to the accepted N4B1C decoder

| Step | Question | Result | Outcome |
|---|---|---|---|
| N1 | Can weak, glancing or aborted approaches be told apart from noise one event at a time? | No | The user decided weak, non-contact and receding approaches need not trigger escape, and that geometry must never become a runtime gate |
| N2 | Summed FAST >= 2.20 OR 1.45 on 3 consecutive samples | N0 0 events; strikes 0.10 / 0.16 s against 0.08 / 0.08 s | Rejected after a human test: too slow |
| N2b | FAST 2.10 OR (current sample high and >= 3 of 5 high) | N0 0 events; strikes 0.10-0.18 s | Rejected after a second human test: sluggish strikes, insensitive to slow approaches; archived as `archive/m1-8-n2b-rejected` |
| N3 | Does DNp01-only temporal integration help? | Best rule leaves median latencies unchanged | Closed: the limit is upstream of the decoder |
| N4A | Where is the information lost? | 5-7 DNp01 spikes per 1,000 sensory spikes; 96 % of spontaneous spikes are noise kicks; left and right noise are independent; two same-side spikes within 100 ms mark strikes | Mixed diagnosis; points to a lateralized readout |
| N4B1 | Lateralized DNp01 rules, frozen before a fresh 280-minute N0 holdout | Rule A: 0 events | Primary candidate, but a hover regression |
| N4B1C | Rule A OR the N2b summed path | Holdout 1 event in 280 min; 3 events in all 630 min (upper bound 0.0123/min), all on the summed path; hover 13/13 and 20/20 | **Accepted and frozen**, runtime `e3c55b3` (2026-09-24) |

The accepted decoder `lateral_dual_path_v1` escapes when, outside a shared 0.4 s
refractory period, either:

- **the lateral path** sees two inferred spikes on the **same** DNp01 side within 60 ms
  (3 samples), with the second on the current sample; or
- **the summed path** sees left plus right >= 2.10 (FAST), or the current sum >= 1.45
  with at least 3 of the last 5 samples >= 1.45 (SUSTAINED).

Because left and right noise are independent, requiring same-side coincidence removes the
summed-noise false trigger while keeping strike latency: 60/60 strong and medium strikes
at 0.08 / 0.10 s. All of its values are class C engineering parameters.

### 5.3 The overhead foreshortening artifact (N4B4, N4B5, N4B5R)

N4B4 re-simulated all 21 free-flight escapes the accepted decoder produced in 249 minutes
with no player. **None resembled a spontaneous neural false trigger**: every one followed
a real visual volley. Nine were anticipatory responses to the fly flying toward the parked
paddle, eight occurred while the fly passed beneath it, and four were mixed. In the eight
overhead cases the Retina's tilt foreshortening term depended on horizontal bearing only,
so it produced 2.5-6.9 rad/s of apparent expansion at constant range under a stationary
paddle, against 0.13 rad/s physically. The metric was split into four categories:

| Category | Meaning | Criterion |
|---|---|---|
| A | fixed-fly or no-drive neural false escapes | < 0.1/min at 95 % |
| B | inappropriate free-flight escapes | < 0.1/min at 95 % (provisional engineering criterion) |
| C | foreshortening-driven escapes | tracked, not a failure by itself |
| D | genuine self-approach escapes | tracked, not a failure by itself |

N4B5 compared four geometries and N4B5R implemented G3, which multiplies the tilt term by
cos(elevation): `elevation_aware_tilt_v1`, ROOM only.

| Free flight, 83 runs, 249 min | Bearing-only (G0) | G3 (accepted) |
|---|---|---|
| A | 0 | 0 |
| B | 2 | 3 |
| C | **8** | **0** |
| D | 8 | 5 |
| mixed | 3 | 4 |
| all | 21 (0.084/min, upper 0.121) | **12 (0.048/min, upper 0.078)** |

Peak apparent expansion directly under the paddle fell from 6.86 to 0.17 rad/s, strike
detection was unchanged (60/60 at 0.08 / 0.10 s), and hover detection fell only on bouts
that the artifact had driven. N4B5R was accepted by the human tester on 2026-09-25 and is
the current runtime (`363a1a9`).

### 5.4 The slow-approach limit (N4B2, N4B3, N4B6, N4B7, N4B8)

A remaining complaint was that the fly ignores a paddle that approaches slowly.

- **N4B6** (preregistered; 15 trajectories x 48 noise seeds, fixed fly): approaches at
  130 units/s (about the 25th percentile of human paddle speed) were detected in time in
  0-6 % of trials, 300 units/s in 29 %, 800 units/s in 100 % (0.36 s before closest
  approach). The DNp01 readout is the limit at 130 units/s; the stimulus itself is the
  limit at 50 units/s.
- **N4B2 / N4B3**: of ten wiring-qualified descending-neuron types, only DNp04 gave earlier
  evidence, but it is non-selective in flight (0.31 escapes per minute of no-player free
  flight) and no policy-observable gate made it selective; only a stationary-fly form was
  clean.
- **N4B7**: a preregistered 1 s same-side count of >= 4 DNp01 spikes recovered 100 % of
  130 units/s approaches with a 1.4 s lead, but raised no-player free-flight escapes from 9
  to 167 in 240 minutes, with category B at 44 (upper bound 0.24/min). Rejected.
- **N4B8**: a mirror test moved the fly along the exact relative path of the paddle
  approaches while the paddle stayed parked. The Retina input was bit-identical, every
  candidate neuron's spike train was identical in 48/48 seeds, and external-versus-self
  discrimination was at chance (AUC 0.50).

The conclusion is structural: the brain's only visual input is the triple
(theta, theta_dot, azimuth), so **an external gradual approach and the fly's own approach
toward a parked paddle are input-identical**, and no readout can separate them. The user
closed this line on 2026-09-25 as an accepted architectural limitation, and excluded the
channels that would change it: new visual projection populations, flight-state gating,
efference copy, optic-flow channels, new long-window DNp01 rules and DNp04 runtime input.

### 5.5 Discipline and open items

Each candidate was frozen and hashed before its holdout existed; the holdout tools refuse
to run on a changed module, and each N0 holdout used a fresh seed offset. Seeds used as
holdouts are listed in the handoff state and are not reused for design. The reports
disclose their own weaknesses, among them partly in-sample N3 thresholds, DNp04 having
emerged from exploratory analysis, a noise-realization control added after the N4B5
freeze, and an N4B5 criterion ("every direct strike fires") that failed as written at
38/39.

Known open items: a stop-rotation transient of the frozen swatter controller produces
0.35 rad/s of apparent expansion at constant range and an escape in 17/48 orbit trials
(its frequency in real play was measured on 2026-10-22, section 9.7); a false-trigger rate below 0.01/min has never been
demonstrated; LAB and GAME still use the legacy single-sample decoder; and the evidence
base is one human tester.

## 6. Part IV: learned controllers (M2)

From 2026-09-25 to 2026-10-08 the project asked whether a small learned controller,
reading the same neural signals as the hand-designed decoder, could make the fly harder
to hit. The connectome stayed frozen throughout: only the controller downstream of the
descending neurons learned. All work is on `feature/m2-0-learning-infra`, which changes
no accepted runtime file (a test asserts this), and the reports are `game/M2_*.md` on
that branch.

### 6.1 Contracts

- **Observation:** 60 values, the current frame and four history frames (100 ms) of
  12 values each: a validity flag, DNp01 and DNa02 left and right, forward and lateral
  speed, yaw rate, remaining saccade time, and a one-hot of the controller's own
  CALM / ALERT / ESCAPE state. Pointer, swatter, world geometry, Retina, LC4/LPLC2
  activity, the full descending-neuron trace and every lifecycle, odor or food variable
  are excluded and checked by tests; an import test restricts what policy code may read.
- **Action:** one of 11 body-frame maneuvers every 20 ms (none; turn left or right; alert
  saccade left or right; full escape left, right, forward or backward; half-strength
  escape left or right), with the accepted 0.4 s escape refractory enforced by the
  actuator.
- **Network:** an MLP 60 -> 32 (tanh) -> 11 with a categorical policy, 2,315 parameters,
  fixed input scaling and seeded sampling that is part of the frozen policy.

### 6.2 Benchmark (M2.1)

The first reward (M2.0) could be gamed: never escaping and constant turning both beat the
accepted controller, partly because uncontrolled exposure let a fly that never perched
avoid the perched attack. M2.1 rebuilt the benchmark around exposure control:

- every threat trial is a fresh reset with **exactly one committed strike**, whose engage
  time and attacker parameters are drawn from the seed before the first tick;
- four threat families (direct, hover, wall, perched-or-fallback) times three attacker
  levels (easy, nominal, hard) give 12 groups;
- separate no-strike background episodes measure unnecessary escapes and movement
  pathologies;
- reward v2 is +1 per avoided strike and -1 per hit, with an unnecessary-escape price of
  0.00589 derived from probe policies; constraints (at most 5.36 unnecessary escapes per
  minute, at least 0.275 perches per minute, wall and speed limits) come from development
  data;
- training, validation, confirmation and evaluation seeds are disjoint; each evaluation
  set is used a fixed, recorded number of times.

**Hit rate is the fraction of committed strikes that hit the fly, so lower is better for
the controller.** The accepted N4B1C controller scores 0.617 on EVAL v2. Never escaping
scores 0.721. A fixed maneuver scores 0.475 but is inadmissible at 11.4 unnecessary
escapes per minute.

### 6.3 Results

| Milestone | Method | One-shot evaluation (candidate vs N4B1C, same trials) | Decision |
|---|---|---|---|
| M2.0 | Contracts, runners, frozen suite, reward v1 | Reward v1 ranks degenerate policies above the baseline | NO-GO for training |
| M2.1 | Exposure-controlled benchmark, reward v2, constraints | Baseline preferred over every degenerate probe | GO for constrained training |
| M2.2 | Constrained PPO from scratch, NumPy, 5 seeds x 100 iterations | Hit **0.738** vs 0.617; threat-window escape 0.00: the policy never escapes | NO-GO |
| M2.3 | PyTorch behaviour cloning of N4B1C (522,651 samples), then KL-anchored constrained PPO with dual warm-up and adaptive entropy, 5 seeds x 60 iterations | Hit **0.592** vs 0.617; paired -0.025 [-0.090, +0.040], McNemar p = 0.53; unnecessary escapes 3.02 vs 5.15 per min | NO-GO: no significant difference |
| M2.4-R0 | Decision-rate and credit analysis, no training | About one effective independent advantage sample per strike at every cadence | Keep 50 Hz |
| M2.4-A | Threat-dense sampling (98 strikes per iteration), strike-balanced actor loss, two-stage checkpoint selection, fresh EVAL v3 frozen before training | Hit **0.552** [0.507, 0.596] vs 0.640; paired -0.0875 [-0.133, -0.042], McNemar p = 0.00026; unnecessary escapes 3.48 vs 4.97 per min; also below behaviour cloning and M2.3 (both p < 0.001) | GO for human testing, with a documented procedural deviation |
| M2.4-B | Blind human A/B test: 30 sessions in 15 blocks, order sealed by HMAC | 12 of 30 sessions played, then stopped by the participant; reopened on 2026-10-22 and closed after session 13; not unblinded, not analysed | No conclusion |

Per attacker level, M2.4-A is hit 0.294 / 0.475 / 0.887 (easy / nominal / hard) against
N4B1C's 0.375 / 0.569 / 0.975. Note that N4B1C's own hit rate differs across sets
(0.617 on v2, 0.640 on v3, 0.646 on TRAIN-VAL); only paired comparisons on the same set
are meaningful.

### 6.4 Why the earlier attempts failed

- **M2.2: premature exploration collapse.** The unnecessary-escape multiplier reached
  1.6-2.1 within 10 iterations, pricing every escape at about twice a strike outcome
  before any threat-conditioned escaping existed. Entropy and gradients went to zero, and
  when the multiplier relaxed the policy no longer explored. Escape probability ended near
  1e-4 at every DNp01 level.
- **M2.3: thin credit.** About 800 decisions per strike, only 3.3-3.5 % of samples with a
  meaningful advantage, critic explained variance 0.11-0.12, and a final KL divergence of
  only 0.003-0.01 from the behaviour-cloned start. Its TRAIN-VAL estimate of 0.490
  regressed to 0.592 on EVAL, a winner's-curse effect of picking the minimum of 24 noisy
  estimates.
- **M2.4-R0: the limit is the number of strikes.** The lag-1 advantage autocorrelation is
  0.965, so the ~44 decisions in a strike window carry about 0.8 effective independent
  samples; coarser cadences reduce redundancy but add no signal. M2.4-A therefore
  increased strike outcomes per update instead (5,880 per seed against 2,520).

M2.4-A changed the strike budget and the loss weighting together, so their contributions
cannot be separated; an equal-budget reference was never run officially.

### 6.5 Disclosed deviations

- **M2.3:** the paired McNemar test was chosen after the evaluation run, and no
  equivalence or non-inferiority margin was preregistered; the result means "no
  significant difference", not "equal". This is disclosed in the README rather than in
  the M2.3 report itself.
- **M2.4-A:** a multiprocessing pickling bug in the evaluation worker was repaired
  (`bfd5c42`) after the protocol and evaluation manifest were frozen but before the
  candidate freeze and the evaluation. The formal amendment and the equivalence audit
  were written after the evaluation; TRAIN-only audits found identical outputs for the old
  and repaired workers in every comparison
  ([amendment](https://github.com/cssius111/fly-connectome-reservoir/blob/feature/m2-0-learning-infra/game/M2_4_A_EVAL_EXECUTION_AMENDMENT.md)).
  The evaluation was not re-run. The human reviewer accepted the GO with this deviation
  on 2026-09-27.
- **M2.4-A baselines:** the R0 design listed more baselines for EVAL v3 than were run
  (N4B1C, never-escape and fixed maneuver, plus the behaviour-cloned and M2.3 policies),
  and they ran in the one-shot evaluation after the candidate froze.
- **M2.4-B:** stopped at 12 of 30 sessions against a preregistered "no early stopping"
  rule, reopened, then closed at 13 of 30. Each step is recorded as an amendment (2 to 4),
  and the data stay sealed.

### 6.6 Status

The user closed the learning line on 2026-10-08. The learned policy is not integrated,
the accepted runtime still uses N4B1C, and the learning branch is not merged. Two routes could
reopen M2.4-B. The first is to finish sessions 13-30 under the unchanged protocol. The second
is to amend the protocol before unblinding to define an exploratory six-block analysis, which
also needs a code change because the tools refuse a partial set. On 2026-10-22 the participant
took the first route, played session 13 and then closed the test at 13 of 30 sessions
([game/M2_4_B_CLOSURE.md](game/M2_4_B_CLOSURE.md)). Nothing was unblinded, and the data stay
sealed. Further training needs a new preregistration and a fresh evaluation set, because EVAL v3
has been used.

## 7. Research practice

The same rules were applied from the first experiment to the last study:

- **Preregistration.** Protocols, candidate modules, seeds and success criteria were
  committed, usually with SHA-256 hashes, before the data they govern existed. Holdout
  tools refuse to run when a frozen module's hash changes.
- **Disjoint, single-use test sets.** Training, validation, confirmation and evaluation
  seeds are disjoint. Each evaluation set's uses are counted and recorded (EVAL v2 served
  the M2.1 probe run and two candidate evaluations; EVAL v3 one, guarded in code). The
  decoder research lists its holdout seeds as never to be reused for design.
- **Frozen systems.** Accepted subsystems (the M1.7.1 swatter, the M1.8-A lifecycle, the
  N4B1C decoder, the N4B5R geometry) are not retuned unless recorded evidence shows a real
  defect, and never to change difficulty. The original experiment's 20 output files and
  the historical calibration records are byte-protected.
- **Attributable changes.** Refactors are accepted only on bit-identical replay, and the
  first intended behavioural change of a stage is located to an exact scenario, tick and
  field.
- **Difficulty is reported, never optimized.** Hit and escape rates in the game runtime
  are outcomes to record, not targets for tuning.
- **Deviations are disclosed, not corrected after the fact.** Section 6.5 lists the
  learned-controller deviations. The decoder reports list their own: partly in-sample N3
  thresholds, a control added after a freeze, a criterion that failed as written.

## 8. Limitations

- **One specimen, one parameter set.** All network results come from one anatomical graph
  with hand-set LIF parameters, a modified runtime graph and one encoder subset.
- **Sensory representation.** The brain sees the swatter only through
  (theta, theta_dot, azimuth). Approaches at 130 units/s are detected in time in 0-6 % of
  trials and at 300 units/s in 29 %, and self-motion cannot be distinguished from an
  external approach.
  This is an accepted architectural limitation, not a decoder defect.
- **False-trigger evidence.** The accepted decoder's fixed-fly false-escape rate is bounded
  at 0.0123 per minute; a rate below 0.01 per minute has never been demonstrated.
  Free-flight escape categories B to D remain tracked rather than eliminated.
- **Kinematics.** ROOM speeds are an order of magnitude below the literature in body
  lengths per second, by decision; only EXPLORE and ODOR_TRACK speeds are sampled so far,
  and neural ALERT interruptions override most ecological dwell timers (section 9.1).
- **Learned control.** The M2.4-A improvement rests on one test set, confounds strike budget
  with loss weighting, and was never confirmed by a completed human test.
- **Human evidence.** One player produced every playtest and human session.
- **History.** The M1.4, M1.6 and M1.7 commits exist only in the original local repository;
  those milestones survive as reports. The protected-file manifest and the human session
  recordings are local and untracked, so some integrity checks cannot be run from a fresh
  clone.

## 9. Current state and next steps

As of 2026-10-22 the accepted runtime is ROOM `config_version` 27:
- M1.8-B2b-iii and B3a on top of `363a1a9` (N4B1C decoder, N4B5R geometry), accepted on
  2026-10-21;
- the completion stages B2c-B4b, accepted on 2026-10-22 (`config_version` 26, on `main` since
  that day, tag `v1.0`);
- the M1.7.2 paddle line axis, accepted the same day. The slow-approach line is closed by the user's decision, and M1.8-B is
complete and frozen. On 2026-10-22 the M2.4-B blind test was closed at 13 of 30 sessions and the
stop-rotation audit was recorded. At the user's request, M1.7.2 then fixed the defect the audit had
found. It is ROOM `config_version` 27 and was human-accepted the same day (section 9.7).
The fidelity scorecard is in section 9.6, and the remaining open items are in section 9.7.

### 9.1 A measurement made for this report: where flight time goes

Choosing the next kinematic context required knowing how often each ecological state
actually occurs. `tools/ecology_occupancy_audit.py` ran the accepted runtime with no
player for 180 s on three seeds (design note
[game/M1_8_B2B_III_DESIGN.md](game/M1_8_B2B_III_DESIGN.md), section 1):

- EXPLORE takes 41-50 % of alive time, ODOR_TRACK 21-31 %, RECOVER 14-19 %, ALERT
  8-12 %, ODOR_SEARCH 1-2 % and TRANSIT at most 0.6 %.
- **The ecology enters ALERT 41-56 times per minute.** The fixed policy's ALERT gate is
  0.55 x 1.45 = 0.80 on the summed DNp01 trace, below the 1.0 rise of a single spike, and
  44-59 % of the entries occur with no looming expansion in the preceding 120 ms.
- Each ALERT passes through a 0.2 s RECOVER into a fresh EXPLORE or ODOR_TRACK episode, so
  EXPLORE episodes last about 1 s instead of their configured 3-7 s dwell, and the
  EXPLORE-to-TRANSIT handover almost never happens.

This is the combined behaviour of three frozen, accepted parts (the M1.2 ALERT gate, the
session's threat mapping and the M1.6 ecology), not a defect introduced by any milestone.
It dominates the activity budget that M1.8-B set out to model.

### 9.2 B2b-iii: ODOR_TRACK speed

The design note chose ODOR_TRACK, the largest context still driven by the shared 8 s
sinusoid, and deferred TRANSIT because it barely occurs. The user approved the design, a
research-only ALERT study and a paired free-flight check on 2026-10-20. Validation is in
[results/game/M1_8_B2B_III.md](results/game/M1_8_B2B_III.md):

- with the new code and the old configuration all seven trace scenarios and every random
  stream are bit-identical; with the new configuration each ROOM divergence starts exactly
  at the first airborne ODOR_TRACK tick, and the lifecycle-threat, no-ecology, GAME and LAB
  scenarios stay bit-identical;
- 200,000 offline draws give mean 10.998 and sd 0.8175 against 11.0 and 0.816;
- paired no-player free flight on 80 fresh seeds (240 minutes per arm): 12 escapes under
  the accepted configuration (0.050/min) and 9 under the candidate (0.037/min), with no
  no-drive escape in either and candidate category B at 2 (upper bound 0.026/min, below the
  0.1/min criterion);
- 440 tests pass, and lifecycle and recorder replays are exact. On the local Windows
  checkout the 20 protected files match byte-exactly, `verify_results.py` passes and the
  swatter reproduces the M1.7.1 acceptance recording exactly.
- The user accepted B2b-iii on 2026-10-21.

### 9.3 The ALERT study

`tools/alert_interruption_study.py` changed only the threat handed to the ecology, inside
the tool ([game/M1_8_ALERT_INTERRUPTION.md](game/M1_8_ALERT_INTERRUPTION.md)). Under the
accepted mapping 80-88 % of ALERT entries carry no requested or executing saccade. If the
ecology reacts only to executed responses, ALERT entries fall from 43-48 to about 2 per
minute, EXPLORE episodes last 4.2-4.5 s, TRANSIT rises from about 1 % to 22-24 % of alive
time, and landing, feeding and voluntary takeoff still occur. Requiring the ALERT state to
last the policy's own 0.06 s saccade dwell barely helps. The note lists three options
(keep the mapping, adopt the executed-response mapping for the ecology only as its own
preregistered stage, or design another ecology-side rule) and selects none.

### 9.4 B3a: the ecology reacts to executed responses

At the user's request the executed-response option became M1.8-B3a, preregistered in
[game/M1_8_B3A_DESIGN.md](game/M1_8_B3A_DESIGN.md) and validated in
[results/game/M1_8_B3A.md](results/game/M1_8_B3A.md). Only the threat handed to the ecology
changes; the policy, the decoder, the lifecycle and its threat input are untouched. Code alone
is bit-identical; each diverging scenario diverges exactly at its first ALERT entry from the
policy state alone; and the runtime reproduces the research counterfactual's occupancy and
transitions exactly. In the paired check on fresh seeds 9201-9280 (240 minutes per arm)
escapes go from 6 to 10, category B is 1 (upper bound 0.020/min, criterion met), and
self-approach escapes (D) rise from 2 to 8 (exact conditional p = 0.11), the risk the design
named: the fly now spends about a quarter of its time in TRANSIT, still at the legacy
sinusoidal 9-13 BL/s. 451 tests pass, and the local Windows checks pass. In a 219 s human
playtest no ecology ALERT entry arrived without an executed alert response and no escape was
a fly-driven self-approach (2.2 parked minutes, 0.07 expected); the player found transit fast
but not very fast, which is the configured 9-13 BL/s band. The user accepted B3a on
2026-10-21 and left TRANSIT speed unchanged for now.

### 9.5 Completing M1.8-B

After accepting B3a the user asked to complete every remaining M1.8-B stage in one run, with
TRANSIT speed locked and one combined playtest at the end ([game/M1_8_B_PLAN.md](game/M1_8_B_PLAN.md)
section 14). Eight stages were preregistered together in
[game/M1_8_B_COMPLETION_DESIGN.md](game/M1_8_B_COMPLETION_DESIGN.md) before any code changed and
validated one by one in [results/game/M1_8_B_COMPLETION.md](results/game/M1_8_B_COMPLETION.md):

- **B2c** fixes the evaluation metrics (`tools/kinematics_sanity.py`) and measures the B3a baseline,
  in which 17 of 58 ODOR_TRACK episodes end at the 8 s timer and 23 of 27 searches at 6 s.
- **B2d, B2e** sample ODOR_SEARCH and RECOVER speed per episode and the speed-transition rate
  (mean held at 3.0 /s).
- **B3b** replaces the three odor timers by an encounter history (E17) with an abandonment and a
  give-up hazard; **B3c** replaces the EXPLORE/TRANSIT dwell timers by a minimum dwell and
  hazards gated by local visual structure; **B3d** resamples the casting and drift periods.
- **B4a** uses the odor derivative and bilateral difference (E16, E18); **B4b** adds a wind
  reliability term and a still-air search (E19), which never engages in ROOM's steady wind.

Every new parameter holds the accepted mean where it replaces a mechanism, and every change is
gated by configuration, so code alone stays bit-identical at each step. Each stage passes its
pathology screen and its paired check on seeds 9201-9280 (category B 2 or 3 in 240 minutes at
every stage, upper bounds 0.026-0.032/min). The final check on fresh seeds 9301-9380 gives, for B3a against
the final configuration, 7 against 8 escapes, category B 1 against 2 (upper bound 0.026/min) and
self-approach 5 against 6. 491 tests pass. The report lists the deviations: the no-ecology ROOM
scenario diverges under B3d's drift, contrary to a common preregistered expectation; B3c's
structure gate is nearly inert in ROOM; a habituated fly alternates short tracking and transit
episodes in the plume; and TRANSIT's realized speed shifts slightly (mean 9.69 -> 9.55 BL/s)
because its episodes are shorter, although its speed profile is unchanged. On 2026-10-22 the
local Windows checks passed (491 tests), a 192 s playtest showed no self-approach escape, no
ecology ALERT without an executed response and unchanged TRANSIT speed, and the user accepted
B2c-B4b.

### 9.6 Toward a realistic fly: the M3.0 fidelity scorecard

On 2026-10-22 the user set the project's goal: the model fly should behave more like a real fly,
and difficulty follows from that.

M3.0 was preregistered in [game/M3_0_FIDELITY_SCORECARD_DESIGN.md](game/M3_0_FIDELITY_SCORECARD_DESIGN.md)
and measured in [results/game/M3_0_FIDELITY_SCORECARD.md](results/game/M3_0_FIDELITY_SCORECARD.md).
It compares the accepted runtime with published *Drosophila* data:
- escape comparators, from open full texts: [game/M3_0_ESCAPE_EVIDENCE.md](game/M3_0_ESCAPE_EVIDENCE.md);
- saccade comparators, from the M1.8-R0 evidence lock.

Findings:
- **Escape timing.** The model escapes far too early. The angular size at escape is 14-32°,
  with an implied threshold of 18.6° against 54°.
- **Escape probability.** The model escapes in every trial (1.00 against 0.82).
- **Escape direction.** For lateral threats the model jumps forward and away, as real flies do.
  It cannot tell front from back, because the encoder uses only the side of a stimulus, so
  frontal and rear threats get the right-side response.
- **Escape modes.** The short and long escape modes are not represented.
- **Spontaneous saccades.** They are about four times too rare (0.34 against 1.37 per s) and too
  small (57° against about 90°).
- **Flight speed** (context): it is about 14 times slower in body lengths per second, which is
  the frozen gameplay scale.

The gaps fall into three groups:
- the escape decision, which is frozen;
- the encoder's use of the bearing and the escape pathways, which are structural;
- the flight generator, which is parametric.

The user chose the escape decision first, starting with read-only research. M3.1
([game/M3_1_ESCAPE_DECISION_RESEARCH.md](game/M3_1_ESCAPE_DECISION_RESEARCH.md)) traced it:
- **The model's rule.** The fly escapes when the expansion rate reaches about 40°/s, because the
  encoder drives LPLC2 by expansion velocity alone.
- **The real fly.** Its giant fiber sums an angular-size component from LPLC2 and a velocity
  component from LC4 (Ache et al. 2019; von Reyn et al. 2017).
- **What the connectome has.** MaleCNS already has that circuit: LC4 and LPLC2 are DNp01's two
  largest excitatory inputs.
- **The candidate change.** It assigns the encoder's features as the literature does, and leaves
  the connectome, DNp01 and the decoder rules unchanged.
- **Preregistered, not yet made.** The user supplied the full text of Ache et al. 2019.
  M3.2 ([game/M3_2_ESCAPE_FEATURE_ROLES_DESIGN.md](game/M3_2_ESCAPE_FEATURE_ROLES_DESIGN.md))
  fixes the paper's constants and one scale. The scale is calibrated to the paper's
  giant-fiber model, and behaviour is the test. Implementation waits for the user's
  authorization.

### 9.7 Other open items

- **TRANSIT speed** still follows the legacy shared 8 s sinusoid over 9-13 BL/s. A sampling
  stage that holds the envelope (as B2b-ii and B2b-iii did) would not make transit faster;
  a faster TRANSIT would change the magnitude and reopen the `room_kinematic_scale` = 1.0
  decision, against the frozen 1000 units/s ceilings and swatter. The user left it unchanged
  on 2026-10-21, and the completion stages keep its profile.
- **M2.4-B**, the blind human test:
  - On 2026-10-22 the participant reopened it to finish sessions 13-30 under the unchanged
    protocol ([game/M2_4_B_REOPENING.md](game/M2_4_B_REOPENING.md)). That note was recorded
    before session 13 and declares the pause and the intervening practice as deviations.
  - After session 13 the participant closed the test at 13 of 30 sessions
    ([game/M2_4_B_CLOSURE.md](game/M2_4_B_CLOSURE.md)). Block 7 holds one session of its pair.
  - It is not revealed and not analysed, and it gives no conclusion. The sealed data stay
    unopened on the original local machine.
- **Stop-rotation transient** of the frozen swatter controller (Part III). It was measured in
  recorded human play on 2026-10-22 with the read-only `tools/stop_rotation_audit.py`
  ([results/game/M1_8_STOP_ROTATION_AUDIT.md](results/game/M1_8_STOP_ROTATION_AUDIT.md)).
  - **Rate.** On the accepted runtime (2 sessions, 5.4 min of hover) it occurs 4.65 times per
    hover minute.
  - **Reversal spins.** Half of the transients (2.23/min) are reversal spins. The approach
    controller steers the paddle towards the 360-degree heading of its velocity, so reversing the
    motion spins the paddle by up to 180 degrees, although its visually symmetric axis ends where
    it was.
  - **Escapes.** 4 of 10 evaluated transients are followed by an escape within 0.06-0.8 s,
    against 1.3 % of hover samples at matched distance. That is about 0.63 added escapes per
    hover minute, 0.35 of them from reversal spins; the earlier runtimes give 1.64 and 0.39.
  - **Classification.** The responses are category C, with a real Retina drive. The reversal
    spin is a modelling defect of the controller.
  - **Decision.** The user first chose to record the result and keep the M1.7.1 swatter frozen.
  - **The fix, M1.7.2.** Later on 2026-10-22 the user requested the fix.
    - It is preregistered in [game/M1_7_2_PADDLE_AXIS_DESIGN.md](game/M1_7_2_PADDLE_AXIS_DESIGN.md)
      and validated in [results/game/M1_7_2_PADDLE_AXIS.md](results/game/M1_7_2_PADDLE_AXIS.md).
    - A world-only line axis feeds the tilt term and the sprite. It steers like the heading
      tracker but towards the nearer of the target and its opposite. The tracker, the strike
      direction, the motion and the collision are unchanged.
    - Every run is bit-identical to v26 until the line axis first folds.
    - In the N4B6 orbit-stop control, N4B1C responses fall from 14 to 0 of 48 brain-noise seeds.
      In a reversal on an arc they fall from 39 to 0 of 48.
    - The calibration measurement is not reused exactly, and the threshold is carried over.
    - **Accepted 2026-10-22** after one playtest, in which the line axis showed no reversal spin
      and 2.0 transients per hover minute (before: 4.65).
  - **Same playtest, outside M1.7.2.**
    - The user found the game easy for aggressive play.
    - The green direction line drawn at an escape onset told the player where the fly would
      dash. It was removed, keeping the ring; this is rendering only.
    - The swept strike corridor of M1.7.1 (the paddle disc swept over the 0.1 s contact) stays
      frozen by the user's decision.
- **Stale documentation** was corrected on the session branch on 2026-10-21 (README,
  `game/ROOM.md`, `game/SESSIONS.md` now point to `policy.calibration_paths`); the immutable
  `calibration_room_m1_8_n4b5r.json` keeps its historical status "runtime candidate; not yet
  human-accepted" although the candidate was accepted on 2026-09-25.
- **`main`** received the accepted runtime on 2026-10-22 (pull request 2, merge commit
  `79f5518`, joining the unrelated histories). It then received the N4B2-N4B8 research records
  of `wip/m1-4-enclosure` (pull request 1) through the session branch. The learned-controller
  study stays on `feature/m2-0-learning-infra`.

## 10. Reproducibility

| Branch | Content |
|---|---|
| `main` | **The current accepted runtime** (ROOM `config_version` 27 with M1.7.2), the original reservoir experiment (Part I, up to `309abd9`) and the research records N0 to N4B8 (since 2026-10-22) |
| `feature/flyswatter-game` @ `85f987b` | The first game prototype, M1.0 to M1.3 (2026-09-18), whose commits Part II cites |
| `feature/m1-8-n4b1c-runtime` @ `e3c55b3` | An earlier accepted runtime (the N4B1C decoder layer) |
| `wip/m1-4-enclosure` @ `c953094` | The decoder research N4B2 to N4B8 and the 2026-10-08 handoff state, merged into `main` |
| `archive/m1-8-n2b-rejected` @ `2c30617` | The rejected N2b runtime |
| `feature/m2-0-learning-infra` | The learned-controller study (Part IV) |
| `feature/m1-8-b-complete` | The M1.8-B runtime (`config_version` 26): N4B5R plus M1.8-B2b-iii, B3a and the completion stages B2c-B4b (accepted 2026-10-21 and 2026-10-22), merged into `main` and tagged `v1.0` |
| `feature/m1-8-b3a` @ `6b43c0f` | The previous accepted runtime (M1.8-B3a) |
| `feature/m1-8-b2b-iii` @ `c4f9b8f` | The previous accepted runtime (M1.8-B2b-iii) |
| `feature/m1-8-n4b5r-geometry` @ `363a1a9` | An earlier accepted runtime (N4B5R geometry) |

The validated environment is Windows with Python 3.11.16 and the CPU path; versions are
pinned in `requirements-lock.txt`, and the learning code additionally needs PyTorch
2.13.0. The connectivity data are downloaded by FlyBrain and verified against SHA-256
values (`brain.npz` `cc9bd1ec...`, `weights.npz` `c29919aa...`). On 2026-10-20 the
accepted runtime's suite passed 427 of 427 tests on a Linux checkout, the session branch
with B2b-iii 440 of 440, and the learning branch 516 of 517 with one CUDA-only test
skipped, after a line-ending fix to two provenance tests. On 2026-10-21 the B3a runtime passed
451 of 451 on Linux and on the local Windows checkout, and on 2026-10-22 the session branch
with the completion stages passed 491 of 491 on Linux and on the local Windows checkout, and
496 of 496 on Linux with the stop-rotation audit tests. The M1.7.2 session branch passes 507 of
507 on Linux.

```text
python first_run.py                                   # data integrity and replay smoke test
python experiment.py --config other.json --output results-new   # never overwrite results/
python -m game.app --arena room                       # play the accepted runtime
python tools/calibrate_escape.py --config game_room_config.json --trials 28
python -m unittest discover
```

## Appendix A: glossary

| Term | Meaning |
|---|---|
| BL | Body length; 24 world units |
| MaleCNS | FlyEM connectome of the adult male *Drosophila* central nervous system, v1.0 |
| LC4, LPLC2 | Looming-sensitive visual projection neurons; the only visual input driven here |
| DNp01 | The giant-fiber descending neuron; the escape readout |
| DNa02 | A steering descending neuron; modulates turn amplitude by at most 15 % |
| DNp04 | A descending neuron tested and rejected as an extra slow-approach readout |
| Retina | The three-number swatter summary (theta, theta_dot, azimuth) |
| N0 | Fixed-fly, no-loom false-trigger measurement |
| N4B1C | The accepted lateralized dual-path escape decoder |
| N4B5R | The accepted elevation-aware paddle tilt geometry |
| ROOM, GAME, LAB | The ecological arena, the plain 160 x 90 BL arena and the small controlled arena |
| Hit rate | Fraction of committed strikes that hit the fly; lower is better for a controller |
| Class A / B / C | Parameter evidence: matched measurement / literature-inspired / engineering |
