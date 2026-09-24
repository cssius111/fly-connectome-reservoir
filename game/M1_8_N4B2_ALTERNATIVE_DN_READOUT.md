# M1.8-N4B2: alternative descending-neuron readout research

Status: **research only; complete; recommendation in section 12.** No runtime,
configuration, calibration, provenance, policy-whitelist, Retina, encoder, MaleCNS,
brain-noise, lifecycle, physics, escape-impulse or recorder change. The accepted
M1.8-N4B1C runtime (`feature/m1-8-n4b1c-runtime`, `e3c55b3`, `lateral_dual_path_v1`) is
the frozen reference and is not modified or retuned. Every descending-neuron (DN) readout
here is evaluated offline in shadow mode; none is a policy input. World geometry is used
only to interpret recorded situations.

Question: can another DN readout give earlier, cleaner neural evidence of slow approach
than N4B1C, while staying specific against no-threat and background activity?

Short answer:

- **DNp04 is the only candidate that does.** It marks the slow-close case 1.1 s before
  N4B1C, and it stays clean on the fixed-fly N0 background (0 events in 910 min, including
  the new 280-min holdout).
- **It is a broad "visual approach" signal, not a selective threat signal.** It fires on
  nearly every weak, glancing and aborted approach. It adds about 30 firings in 3.7 min of
  recorded human play. In held-out no-player ROOM free flight it produces 0.31
  escapes/min, from the fly's own flight near the parked paddle, against 0.083/min for
  N4B1C. That fails the < 0.1/min target on that background.
- **Whitelist expansion is not justified as a drop-in change.** The trade-off is a product
  decision that needs explicit approval (section 12).

## 0. Reproduction environment

- Research branch `wip/m1-4-enclosure` (base `07f4670`); only research files are added.
- The N4B1C runtime reference is the runtime's own `FixedEscapePolicy`, loaded from a clean
  **detached** worktree at `artifacts/worktrees/n4b1c-runtime-detached` (`e3c55b3`, with a
  `data` junction). The tools verify it is clean at that commit before use. The feature
  branch and its own worktree are not touched.
- Tools:
  - `tools/n4b2_record.py`: DN-panel re-simulation (N0 sets) and no-player ROOM shadow runs;
  - `tools/n4b2_connectome.py`: connectivity characterization;
  - `tools/n4b2_criteria.py`: candidate rule, readout family and frozen criteria;
  - `tools/n4b2_analysis.py`: `dev`, `freeze` and `holdout` modes.
- Artifacts: `artifacts/m1_8_n4b2/` (git-ignored); hashes in section 13.

Offline checks that must hold for the results to be trusted:

| Check | Result |
|---|---|
| N4B1 fresh N0 re-simulated with DN recording (600 trials) | 600 / 600 bit-exact DNp01 L and R traces against `artifacts/m1_8_n4b1/fresh_n0_chunk*.npz` |
| N4B1C holdout re-simulated with DN recording (600 trials) | 600 / 600 bit-exact against `artifacts/m1_8_n4b1c/holdout_chunk*.npz` |
| Original N0, N1, both human sessions | N4A exact re-simulations reused; panel DNp01 spikes equal the recorded DNp01 spikes; rebuilt traces equal every recorded `dnp01_left` / `dnp01_right` |
| N4B1C reference replay on development N0 | 0 / 2 / 1 events (original / N4B1 fresh / N4B1C holdout): identical to the N4B1C report |
| N4B1C reference replay on the slow-close case (clean start at 610) | tick 668, LATERAL: identical to the N4B1C report |
| N4B1C reference replay against the live runtime in ROOM (16 runs) | escape ticks identical in every run |
| Maximum encoder drive in every N0 set | below 1e-11 (no loom) |

## 1. Candidate set (defined before the activity analysis)

**Rule (mechanistic, `CANDIDATE_RULE`):** a DN type is a candidate when it has one cell per
side and, on **both** sides, a full ipsilateral volley of the encoder's chosen LC4 + LPLC2
cells alone delivers at least the rest-to-threshold margin: gain 3.0 x direct weight
>= 0.228 V. DNp01 is the frozen reference; DNp04 is the pre-specified primary hypothesis;
the other qualifying types are the comparison set.

- 13 bilateral DN types (26 cells) receive direct weight >= 0.03 from the chosen cells.
  They form the recorded panel.
- **10 types qualify:** DNp04, DNp01, DNp02, DNg40, DNp11, DNp03, DNp05, DNpe056, DNp103,
  DNpe025.
- **3 fail and are descriptive only:** DNp06 (0.86 of margin), DNp71 (right side 0.93),
  DNp35 (0.5).
- **Indirect drive does not add candidates.** A full volley can fire 73-74 non-DN
  intermediates per side from rest (mostly PVLP111, CB0738, AMMC-A1, PVLP151, PVLP122b).
  Their summed input to any DN lacking qualifying direct input is at most 0.09 V (DNp55),
  well below the 0.228 V margin. The largest two-hop drives go to cells that already
  qualify directly (DNp01 0.15-0.17 V, DNp02 0.14-0.15 V).

This is 10 of 1314 DN cells' types, chosen by wiring, not by response.

## 2. Biological evidence (A = published; B = literature-inspired interpretation)

Primary sources were checked for this milestone. Details and DOIs are in section 14.

**DNp04**

- A: Dendrites fill the LC4 glomerulus (light microscopy: Namiki et al. 2018). EM places
  DNp04 among the top downstream partners of LC4, with no anterior-posterior LC4 synaptic
  gradient (Dombrovski et al. 2023). EM also shows LPLC2 input (Moreno-Sanchez et al. 2024).
- A: Whole-cell recordings show that DNp04 fires bursts to looms **without significant
  azimuth tuning** (Dombrovski et al. 2023).
- A: Optogenetic activation of DNp04 alone raised takeoff rates only modestly (at most
  about 25 %). Takeoffs were long-mode and **omnidirectional**. DNp02 + DNp04 gave
  backward-biased takeoffs, and the direction was attributed mainly to DNp02 (Dombrovski
  et al. 2023). DNp04 projects to the lower tectulum (Namiki et al. 2018).
- Not found: no DNp04 silencing result, no flight-state recording, no DNp04 phenotype in
  Cande et al. 2018 or Braun et al. 2024.
- B: The evidence fits DNp04 as a general, location-blind loom "go" signal that biases
  toward long-mode takeoff. It is not a Giant-Fiber-like command neuron, and it does not
  specify direction.

**Comparison types (brief)**

- DNp01 = Giant Fiber (A): receives LC4 + LPLC2; short-mode takeoff via TTMn (von Reyn et
  al. 2014, 2017 *Neuron*; Ache et al. 2019 *Curr Biol*; Dombrovski et al. 2023).
- DNp02 (A): LC4 input biased to anterior LC4; responds more to frontal looms; drives
  backward lean and backward takeoff.
- DNp11 (A): posterior LC4 bias; responds more to rear looms; drives forward takeoff.
- DNp03 (A): a flight-saccade DN whose loom responses are much stronger in flight
  (Buchsbaum & Schnell 2025; Croke et al. 2025). It is not a takeoff DN.
- DNp06 (A): LPLC2 input; involved in loom-evoked wing responses in flight (Kim et al. 2023).
- DNp05 (A, anatomy only): dendrites in the LC4 glomerulus, leg-neuropil projections.
- DNg40, DNp71, DNp103, DNpe056, DNpe025: no looming-specific evidence found.

**Simulator-specific (C)**

- In this graph a full ipsilateral volley puts 1.80 V (L) / 2.09 V (R) into DNp04: 7.9-9.2
  times the threshold margin, against 3.5-3.9 times for DNp01. The chosen LC4/LPLC2 cells
  supply 60-70 % of DNp04's total input weight, against 27-30 % for DNp01.
- DNp04 has almost no direct motor-neuron output here. DNp01's strongest motor target is
  TTMn, consistent with A. DNp04's outputs are VNC interneurons, including GFC3, a
  Giant-Fiber-pathway interneuron.
- In the simulator DNp04 is strictly ipsilateral, because the encoder drives one side at
  a time and DNp04 has no contralateral input from the chosen cells. The published cell is
  not azimuth-tuned. **Any direction information from DNp04 here is a model property, not
  biology.**

## 3. Candidate characterization (development data)

Latencies in seconds. N1 profile columns count from the click (strong / medium) or
stimulus onset (weak). The "pair" readout is two same-side spikes <= 60 ms apart
(`same_side`, k = 2, window 3).

| Type | Cells L / R | Ipsilateral weight L / R | Volley / margin L / R | Inhibitory weight L / R | N0 rate L / R (Hz) | Min same-side ISI (samples) L / R | N1 first spike: strong / medium / weak | Weak: median spikes in 0.5 s | Pair: strong latency | Pair: weak detected / 60, median |
|---|---|---|---|---|---|---|---|---|---|---|
| **DNp04** | 135203 / 1052 | 0.601 / 0.698 | 7.91 / 9.18 | -0.20 / -0.21 | 0.79 / 0.81 | 5 / 4 | 0.04 / 0.04 / 0.21 | 4 | **0.06** | **60, 0.42** |
| DNp01 (ref.) | 6 / 0 | 0.268 / 0.299 | 3.53 / 3.94 | -0.35 / -0.37 | 0.33 / 0.43 | 6 / 4 | 0.04 / 0.05 / 0.28 | 2 | 0.08 | 14, 0.48 |
| DNp02 | 178 / 103 | 0.216 / 0.245 | 2.85 / 3.22 | -0.34 / -0.33 | 0.77 / 0.84 | 5 / 6 | 0.04 / 0.06 / 0.26 | 2 | 0.08 | 6, 0.68 |
| DNg40 | 333 / 853 | 0.177 / 0.222 | 2.33 / 2.92 | -0.34 / -0.30 | 0.63 / 0.72 | 4 / 4 | 0.04 / 0.04 / 0.22 | 3 | 0.08 | 5, 1.02 |
| DNp11 | 238 / 92 | 0.140 / 0.170 | 1.84 / 2.24 | -0.36 / -0.37 | 0.36 / 0.44 | 6 / 6 | 0.04 / 0.06 / 0.32 | 1 | 0.10 | 0 |
| DNp03 | 696 / 915 | 0.134 / 0.084 | 1.77 / 1.10 | -0.22 / -0.22 | 0.83 / 0.76 | 5 / 5 | 0.06 / 0.06 / 0.34 | 1 | 0.18 | 0 |
| DNp05 | 132079 / 945 | 0.101 / 0.114 | 1.33 / 1.49 | -0.34 / -0.34 | 1.10 / 0.89 | 5 / 5 | 0.04 / 0.06 / 0.30 | 1.5 | 0.20 | 0 |
| DNpe056 | 204 / 680 | 0.114 / 0.098 | 1.50 / 1.29 | -0.34 / -0.32 | 0.86 / 0.86 | 5 / 5 | 0.04 / 0.06 / 0.22 | 2 | 0.10 | 0 |
| DNp103 | 384 / 261 | 0.087 / 0.108 | 1.14 / 1.43 | -0.28 / -0.26 | 0.84 / 0.89 | 5 / 5 | 0.04 / 0.06 / 0.21 | 2 | 0.10 | 0 |
| DNpe025 | 413 / 559 | 0.077 / 0.081 | 1.01 / 1.06 | -0.38 / -0.36 | 0.79 / 0.55 | 6 / 6 | 0.06 / 0.06 / 0.28 | 1 | 0.22 | 0 |
| DNp06 (descr.) | 207 / 545 | 0.065 / 0.066 | 0.86 / 0.87 | -0.27 / -0.27 | 0.82 / 0.99 | 5 / 4 | - | - | - | - |
| DNp71 (descr.) | 130350 / 1070 | 0.136 / 0.071 | 1.79 / 0.93 | -0.35 / -0.34 | 0.45 / 0.28 | 4 / 6 | - | - | - | - |
| DNp35 (descr.) | 213 / 520 | 0.036 / 0.039 | 0.48 / 0.51 | -0.28 / -0.26 | 0.41 / 0.51 | 6 / 6 | - | - | - | - |

Spontaneous structure (all types, 630 min of development N0):

- Every type fires about 0.3-1.1 Hz per cell. Left and right are independent: same-tick L+R
  pairs match the independent expectation, for example DNp04 477 against 480 expected.
- **No type ever produces two same-side spikes within 3 samples (60 ms) in 630 min.** The
  shortest same-side interval is 4 samples. This is the same simulator property that
  protects DNp01's lateral path: reset to 0 V plus per-cell Bernoulli noise (N4A, Class C).
- DNp04 fires about twice as often as DNp01 at rest (0.8 against 0.33-0.43 Hz). Its
  spontaneous sensory input from LC4/LPLC2 is proportionally larger.

Left / right structure under threat: on N1 committed strikes, 89-98 % of DNp04 spikes in
the first 0.5 s are on the driven side (DNp01: 88-94 %). DNp04 is bilateral in 18-50 % of
trials, and repeated same-side spiking starts one tick after the first volley.

## 4. DNp04 readout forms and development N0 (630 min)

Events are counted with the runtime semantics: 0.4 s refractory, evidence memory cleared on
an event, qualifying spike on the current sample.

| Readout form | DNp04 N0 events | DNp01 N0 events | Other candidates (range) |
|---|---|---|---|
| single spike | 40,668 | 23,601 | 24,775-46,203 |
| same side, 2 spikes <= 20 / 40 / 60 ms | **0 / 0 / 0** | 0 / 0 / 0 | 0 |
| same side, 2 spikes <= 80 ms | 1 | 1 | 0-2 |
| same side, 2 spikes <= 100 ms | 5 | 3 | 0-12 |
| same side, 2 spikes <= 200 ms | 670 | 118 | 131-1237 |
| same side, 3 spikes <= 100 / 200 ms | 0 / 0 | 0 / 0 | 0 |
| same side, 3 spikes <= 500 ms (integrated) | **106 (0.17/min)** | 4 | 5-285 |
| same side, 4 spikes <= 500 ms | 0 | 0 | 0 |
| bilateral (one spike each side <= 60 ms) | 3,392 | 863 | 882-5,269 |
| pooled L+R, 3 spikes <= 100 ms / 4 <= 200 ms | 0 / 0 | 0 / 0 | 0 |
| pooled L+R, 5 spikes <= 500 ms | 4 | 0 | 0-17 |
| same-side trace (tau 0.1 s) envelope | max 1.50 | - | - |

- A single spike, or any bilateral rule, is not usable: spontaneous rates are about 1 Hz
  per cell.
- **Longer integration windows fail.** A slow approach produces sparse DNp04 spikes, and the
  spontaneous 0.8 Hz background fills 500 ms windows just as easily. Three same-side spikes
  in 500 ms gives 0.17 events/min, above the < 0.1/min target.
- Short same-side bursts are clean on every candidate. The N0 envelope is set by the
  simulator's reset-plus-noise mechanism, not by the cell type.

## 5. Other candidates versus DNp04 (development N1, first firing after onset)

Detected of 60 and median / p95 latency (s). Weak, glancing and aborted approaches are
descriptive stimuli, not must-escape ground truth.

| Readout | strong | medium | weak | glancing | aborted |
|---|---|---|---|---|---|
| **N4B1C (frozen runtime)** | 60, 0.08 / 0.08 | 60, 0.10 / 0.10 | 33, 0.58 / 1.52 | 30, 0.40 / 0.62 | 49, 0.48 / 0.65 |
| **DNp04 pair 60 ms** | 60, **0.06** / 0.08 | 60, **0.06** / 0.10 | **60, 0.42** / 0.56 | **59, 0.30** / 0.56 | **60, 0.31** / 0.46 |
| DNp04 triple 200 ms | 60, 0.08 / 0.10 | 60, 0.10 / 0.14 | 60, 0.43 / 0.56 | 59, 0.30 / 0.52 | 60, 0.31 / 0.48 |
| DNp04 pooled 4 in 200 ms | 60, 0.10 / 0.14 | 60, 0.14 / 0.16 | 56, 0.52 / 1.55 | 43, 0.38 / 0.55 | 58, 0.39 / 0.52 |
| DNp01 pair 60 ms (Rule A) | 60, 0.08 / 0.08 | 60, 0.10 / 0.10 | 14, 0.48 / 0.68 | 16, 0.40 / 0.48 | 40, 0.48 / 0.70 |
| DNp02 pair 60 ms | 60, 0.08 / 0.10 | 60, 0.10 / 0.12 | 6, 0.68 / 1.50 | 6, 0.42 / 0.46 | 9, 0.46 / 0.84 |
| DNg40 pair 60 ms | 60, 0.08 / 0.10 | 60, 0.10 / 0.16 | 5, 1.02 / 2.21 | 10, 0.41 / 0.46 | 18, 0.45 / 0.59 |
| DNp11 pair 60 ms | 60, 0.10 / 0.10 | 60, 0.18 / 0.18 | 0 | 0 | 0 |
| DNp03 pair 60 ms | 58, 0.18 / 0.28 | 48, 0.20 / 0.24 | 0 | 0 | 0 |
| DNp05 pair 60 ms | 59, 0.20 / 0.22 | 60, 0.22 / 0.22 | 0 | 0 | 0 |
| DNpe056 pair 60 ms | 60, 0.10 / 0.20 | 60, 0.20 / 0.22 | 0 | 2, 0.39 | 0 |
| DNp103 pair 60 ms | 60, 0.10 / 0.20 | 60, 0.20 / 0.22 | 0 | 0 | 0 |
| DNpe025 pair 60 ms | 15, 0.22 / 0.29 | 8, 0.22 / 0.23 | 0 | 0 | 0 |

All forms of every candidate are in `dev.json` (`n1`), including the 100 ms, 500 ms and
pooled forms. In brief:

- **Only DNp04 is both faster than DNp01 on committed strikes and more sensitive on weak
  approaches.**
- DNp02, DNg40 and DNp11 are as fast as DNp01 on strong strikes, but more selective
  (fewer weak detections). They could only make slow approach worse.
- DNp03, DNp05, DNpe056, DNp103 and DNpe025 are slower and nearly blind to weak approaches.
- No form in the table fired in the settled static-hover interval before the click
  (pre-onset) of any N1 trial. Only the 200 ms pair form did: DNp04 2, DNp05 1, DNp103 1.

**None of the eight comparison types is carried forward.** This is a negative result for
DNp02, DNg40, DNp11, DNp03, DNp05, DNpe056, DNp103 and DNpe025.

## 6. Slow-close case study (N2b session, episode 5)

Offline geometry only. The paddle is at hover height (320 units) throughout 610-668. The 3D
distance stays 320-334 units while the paddle sweeps back and forth over the fly
(horizontal distance 11-94 units). The true approach starts with the click at 669 (commit):
the 3D distance then falls from 318 to 199 by tick 678.

| Landmark | Tick |
|---|---|
| N2b refractory ends (previous escape at 589) | 609 |
| first positive retinal expansion (theta_dot +0.18) | 610 |
| encoder onset (drive > 0) | 610 |
| first sensory volley above the N0 envelope (85 left cells) | 611 |
| first DNp04 spike (L) | 612 |
| **DNp04 pair 60 ms fires (L 612, 613)** | **613** |
| closest horizontal approach (11 units) | 623 |
| saturated right volley (144 cells, theta_dot +4.4) | 624 |
| DNp04 single left spikes 634 and 640 (gap 6; no pair) | 634-640 |
| final loom begins (drive 0.16 rising to 1.39) | 663 |
| **N4B1C fires (lateral DNp01, L 666 + 668)** | **668** |
| click / strike commit | 669 |
| DNp04 triple 200 ms fires | 669 |
| recorded (N2b FAST) escape | 670 |

All with a clean start at tick 610:

- **DNp04 pair 60 ms fires at 613: 55 samples (1.10 s) before N4B1C, 10 samples before the
  closest horizontal approach, and 56 samples before the click.** *Correction (M1.8-N4B3):*
  the paddle is hovering overhead. At 610-613 its 3D range is increasing (324 to 330
  units). The expansion comes from foreshortening of the tilted paddle
  (`World.visual_half_size`), not from closing distance, so "approaching" is not accurate
  for this moment. The range does not close until the strike at 669
  (`game/M1_8_N4B3_SELECTIVE_DNP04.md`, section 5).
- The DNp04 triple 200 ms does not help: 669, one sample after N4B1C.
- The pooled 4-in-200-ms form fires at 669, and 3 same-side spikes in 500 ms at 634.
- The 613 detection comes from one moderate transient: theta_dot +0.40, one 85-cell volley.
  DNp04's 1.8 V response to it fired twice (612, 613). DNp01 fired only once (612).

What this means: the "slow close" here is a large paddle hovering overhead with weak,
sign-flipping expansion (N4A). DNp04 catches the first weak expansion transient. It will
catch every similar transient, whether or not a strike follows (sections 5 and 8).

## 7. Human sessions (open loop; clean start at each event window)

The human sessions were recorded under strict N2 and N2b. Fly trajectories after a
candidate firing are the recorded ones, so this is evidence timing, not closed-loop
behaviour.

**Direct strikes (39; window 0.5 s before the click to resolution; latency from the click;
negative = fired during the pre-click chase):**

| Readout | fired | before the click | median latency after the click (s) |
|---|---|---|---|
| N4B1C | 39 / 39 | 24 | 0.10 |
| DNp04 pair 60 ms | 39 / 39 | 32 | 0.06 |
| DNp04 triple 200 ms | 38 / 39 | 27 | 0.04 |

**Hover-chase and strike-phase escapes (clean start at bout onset; met = fired no later
than the recorded escape):**

| Readout | hover escapes met / 33 (median lead) | strike-phase escapes met / 29 (median lead) |
|---|---|---|
| N4B1C | 33 (2 samples) | 29 (5 samples) |
| DNp04 pair 60 ms | 32 (8 samples) | 29 (12 samples) |
| DNp04 triple 200 ms | 30 (7.5 samples) | 28 (9.5 samples) |
| DNp04 pooled 4 in 200 ms | 28 (4 samples) | 27 (5 samples) |

A combined N4B1C OR DNp04 decoder fires at the earlier of the two paths, so it meets every
event N4B1C meets and leads by at least as much.

**Special cases:**

| Case | N4B1C | DNp04 pair 60 ms | DNp04 triple 200 ms | Note |
|---|---|---|---|---|
| far perched non-contact approach (strict session, episode 1, rows 2434-2528) | no | **no** | no | DNp04 spikes L 45, 56, 69 and R 52, 62, 80: never two on a side within 60 ms |
| voluntary takeoff (N2b session) | no | **no** | no | DNp04 spikes L 5, 48 and R 6, 70 |
| chase before 589 (episode 5) | 576 | 576 | 580 | identical to N4B1C |

**Whole-episode shadow replay** (3.72 min of stepped play; fresh state per episode; open
loop; context from offline geometry):

| Readout | strike | hover < 300 units | 300-800 units | >= 800 units | total | additional to N4B1C (no N4B1C firing within +/- 20 samples) |
|---|---|---|---|---|---|---|
| N4B1C | 23 | 27 | 31 | 1 | 82 | - |
| DNp04 pair 60 ms | 24 | 37 | 44 | 4 | 109 | **20** (near 7, mid 10, far 3) = 5.4 / min |
| DNp04 triple 200 ms | 23 | 31 | 43 | 5 | 102 | 20 (6 / 11 / 3) |
| DNp02 pair 60 ms | 29 | 20 | 2 | 0 | 51 | 1 |
| DNp11 pair 60 ms | 35 | 2 | 0 | 0 | 37 | 0 |

Context minutes: strike 0.18, hover < 300 units 0.49, 300-800 units 0.75, >= 800 units 2.29.

All 20 additional DNp04 firings happen with the fly airborne and the paddle moving
relative to it, through paddle motion or the fly's own flight:

- the paddle rushing in from 900-1100 units (up to 1334 units/s), 48-76 samples before
  N4B1C fired;
- mid-distance chases (300-750 units) with theta_dot +0.1 to +0.5 rad/s;
- close hovers.

Four were within 0.5 s of a recorded escape. So these are
earlier or extra reactions to real paddle motion, not noise. But at about 5 extra escapes
per minute of play, the fly would be noticeably jumpier than with N4B1C.

**Laterality.** At the first firing, the side of the DNp04 pair matches the stimulated side:

- N1 in 299 / 299 cases;
- human events in 88 / 88 cases.

At that moment the DNp01 left-right contrast, which the runtime uses for escape direction,
agrees with it in 296 / 299 N1 cases and 84 / 88 human cases. A DNp04 trigger therefore
does not need a new direction signal: direction can stay DNp01-based. Using DNp04 itself
for direction would rest on a Class C model property (section 2).

## 8. ROOM no-player free flight (shadow mode under the accepted runtime)

The fly flies, lands, perches, feeds and takes off voluntarily in the ROOM. The paddle stays
parked at its spawn point (no pointer command). The accepted N4B1C runtime controls the fly;
candidate readouts are evaluated in shadow.

- Development: seeds 7101-7104, 4 x 9000 ticks = 12 min.
- Holdout: seeds 7201-7212, generated after the freeze, 12 x 9000 ticks = 36 min.

Lifecycle coverage, holdout (36 min):

- 83,882 airborne samples, 20,314 perched, 3,760 in landing approach;
- 23 touchdowns and 21 voluntary takeoffs.

Development (12 min) had 27,454 airborne samples, 6,980 perched, 9 touchdowns and
8 voluntary takeoffs. The replayed N4B1C matches the live runtime's escape ticks in all 16
runs.

| Criterion (frozen) | Development, 12 min | **Holdout, 36 min: events, /min, 95 % upper** | All 48 min: events, 95 % upper |
|---|---|---|---|
| N4B1C (live runtime) | 1 | 3, 0.083, 0.215 | 4, 0.191 |
| DNp04 pair 60 ms | 0 | **11, 0.306, 0.506** | 11, 0.379 |
| DNp04 triple 200 ms | 1 | 12, 0.333, 0.540 | 13, 0.431 |
| N4B1C OR DNp04 pair 60 ms | 1 | **11, 0.306, 0.506** | 12, 0.405 |
| N4B1C OR DNp04 triple 200 ms | 2 | 12, 0.333, 0.540 | 14, 0.456 |
| DNp04 pair 100 ms (margin probe) | 6 | 17, 0.472, 0.708 | 23, 0.679 |

What the holdout ROOM events are (offline interpretation only):

- **Every DNp04 event is airborne.** None falls in perching, landing approach, touchdown or
  voluntary takeoff.
- All are the fly flying close to the parked paddle: 30-315 units horizontally from it,
  with the paddle at hover height. There, theta is 0.39-0.52 rad and theta_dot is +0.10 to
  +0.44 rad/s. **This is real retinal expansion from the fly's own flight toward a large
  stationary object, not spontaneous noise.**
- The 3 runtime N4B1C escapes are the same kind of event, at 40-167 units with theta_dot
  +0.18 to +0.61. The DNp04 pair also fires on each of them, 2-7 samples earlier.
- **The combined decoder therefore adds 8 escapes in 36 min (0.22/min, 95 % upper 0.40)**
  on top of N4B1C's 3.

Background specificity therefore depends on the background:

- On the fixed-fly N0 protocol, DNp04 is as clean as DNp01 (section 9).
- In free flight around a stationary paddle it is not. DNp04 turns weak self-motion
  expansion into escapes about 3.7 times as often as N4B1C. **Measured against the < 0.1
  false escapes/min target, DNp04 fails in ROOM free flight** (point estimate
  0.31/min). N4B1C's own ROOM rate (0.083/min, upper 0.19 over 48 min) is itself not below
  0.1/min at 95 % confidence with this little data. ROOM is a stricter background than N0,
  and the target was defined on N0.

## 9. Freeze and independent N0 holdout

**Frozen before any holdout seed was simulated** (`frozen_criteria.json`, 2026-09-24T21:22:13Z,
sha256 `507200845d21ac88e29780d9231a0183a09ed348e78e6cbe9376dd747d78118b`; criteria module
sha256 recorded in it; every holdout chunk records the freeze hash).

| Frozen criterion | Role | Parameter source |
|---|---|---|
| DNp04 pair 60 ms (2 same-side spikes, <= 3 samples) | primary DNp04 readout | the N4B1C Rule A form, unchanged |
| DNp04 triple 200 ms (3 same-side spikes, <= 10 samples) | conservative DNp04 readout | the N3 "three spikes in 200 ms" form |
| N4B1C OR DNp04 pair 60 ms | primary candidate architecture | union with one shared 0.4 s refractory |
| N4B1C OR DNp04 triple 200 ms | conservative architecture | same |
| DNp04 pair 100 ms | margin probe only (5 development-N0 events) | shows how close the 60 ms form is to the envelope |

No DNp04 parameter was tuned. The forms and windows were inherited, and their development-N0
counts were read only to exclude failing forms (section 4).

Holdout: 600 trials x 1400 ticks = 280 min, seeds 310000-310149, 320000-320149,
330000-330149 and 340000-340149. These do not overlap the original N0 (4000-4149), its loom
arm (5000-5149), N1 (6000-10059), N4B1 (30000-60149), N4B1C (210000-240149) or the
closed-loop and human seeds. Offsets come from `default_rng(encoder_seed + 717171 + chunk)`,
with the `calibrate_escape._trial` protocol (fixed fly, no loom, config `3d41113`) and
2 Numba threads. Bounds are exact one-sided Poisson 95 %.

All four holdout chunks are 150 / 150 exact against their own policy histories. Each records
the freeze hash `50720084...`. Maximum encoder drive is 7.4e-12.

| Criterion (frozen) | Development N0, 630 min | **NEW holdout, 280 min: events, 95 % upper (/min)** | All 910 min: events, 95 % upper |
|---|---|---|---|
| N4B1C (frozen runtime) | 3 (N2b FAST) | 0, 0.0107 | 3, 0.0085 |
| **DNp04 pair 60 ms** | **0** | **0, 0.0107** | **0, 0.0033** |
| DNp04 triple 200 ms | 0 | 0, 0.0107 | 0, 0.0033 |
| **N4B1C OR DNp04 pair 60 ms** | 3 (all N4B1C) | **0, 0.0107** | 3, 0.0085 |
| N4B1C OR DNp04 triple 200 ms | 3 (all N4B1C) | 0, 0.0107 | 3, 0.0085 |
| DNp04 pair 100 ms (margin probe) | 5 | 2 (L 1, R 1), 0.0225 | 7, 0.0144 |

- **Every frozen criterion passes < 0.1/min on the independent N0 holdout, with a wide
  margin.**
- The DNp04 path added no N0 event anywhere in 910 min.
- The margin probe confirms the envelope sits between 60 and 100 ms:
  - development: 1 event at <= 80 ms and 5 at <= 100 ms;
  - holdout: 2 at <= 100 ms.
  The 60 ms form is one sample inside the shortest spontaneous same-side interval seen
  (4 samples), the same margin DNp01's lateral path has.

## 10. Comparison with the frozen N4B1C

"Earlier" means firing first. N1 and human numbers are development data, first firing, and
clean start (sections 5-7). Background numbers are from sections 8-9.

| Measure | N4B1C (frozen) | N4B1C OR DNp04 pair 60 ms | N4B1C OR DNp04 triple 200 ms | DNp04 pair 60 ms alone |
|---|---|---|---|---|
| N1 strong: detected, median / p95 (s) | 60, 0.08 / 0.08 | 60, **0.06** / 0.08 | 60, 0.08 / 0.08 | 60, 0.06 / 0.08 |
| N1 medium | 60, 0.10 / 0.10 | 60, **0.06** / 0.10 | 60, 0.09 / 0.10 | 60, 0.06 / 0.10 |
| N1 weak / glancing / aborted: detected of 60 | 33 / 30 / 49 | 60 / 59 / 60 | 60 / 59 / 60 | 60 / 59 / 60 |
| N1 weak: median (s) | 0.58 | 0.42 | 0.42 | 0.42 |
| Human direct strikes: fired, before the click, median after the click | 39 / 39, 24, 0.10 s | 39 / 39, 32, **0.06 s** | 39 / 39, 30, 0.08 s | 39 / 39, 32, 0.06 s |
| Human hover escapes met / 33 (median lead) | 33 (2) | 33 (**8**) | 33 (7) | 32 (8) |
| Human strike-phase escapes met / 29 (median lead) | 29 (5) | 29 (**12**) | 29 (9) | 29 (12) |
| **Slow-close (clean start 610)** | **668** | **613** | 668 | 613 |
| Chase before 589 | 576 | 576 | 576 | 576 |
| Far perched non-contact approach | no | no | no | no |
| Voluntary takeoff (human session) | no | no | no | no |
| Voluntary takeoffs / landings in ROOM (29 / 32) | none | none | none | none |
| Open-loop firings over 3.72 min of human play | 82 | 112 (+30) | 110 (+28) | 109 |
| N0 new holdout, 280 min | 0 | 0 | 0 | 0 |
| N0 all 910 min (95 % upper /min) | 3 (0.0085) | 3 (0.0085) | 3 (0.0085) | 0 (0.0033) |
| **ROOM no-player holdout, 36 min** | 3 (0.083/min) | **11 (0.31/min)** | 12 (0.33/min) | 11 (0.31/min) |

- **Direct-strike latency and hover/chase coverage are preserved or improved by
  construction.** The combined decoder fires at the earlier of the two paths, and its first
  firing is never later than N4B1C's. The N4B1C path itself stays unchanged.
- **Only the 60 ms pair addresses the slow-close case.** The conservative triple form does
  not (668).
- The cost is non-selective sensitivity:
  - weak, glancing and aborted approaches all trigger;
  - about 30 more firings per 3.7 min of human play (open loop);
  - about 0.22/min extra escapes in no-player free flight near the parked paddle.
- **Escape direction.** The DNp04 side matches the stimulated side, and the DNp01 contrast
  the runtime steers by agrees with it in 296 / 299 N1 cases and 84 / 88 human cases. A
  combined runtime could keep its DNp01-based direction; this was not tested closed loop.

## 11. Multiple-comparison caveat

- The candidate set was fixed by a wiring rule (10 types). The readout family (15 forms)
  was fixed before the development analysis. All 150 type-by-form combinations are
  reported in `dev.json`, including all failures.
- DNp04 was pre-specified as the primary hypothesis from N4A's exploratory analysis. N4A
  had already seen DNp04's slow-close and N1 behaviour on the same development data, so
  **N1, the human sessions and the slow-close case are not independent tests of DNp04.**
  They are the data that suggested it.
- The new N0 holdout and the post-freeze ROOM runs are independent tests of **background
  specificity only**. No new threat data were generated. There is one tester, two sessions
  and one slow-close episode. The slow-close gain rests on a single recorded case plus the
  weak-N1 class.
- The N0 safety of any short same-side burst comes from the simulator's reset-to-zero plus
  independent per-cell noise (Class C). It is not a biological measurement, and it would
  change if noise, reset or refractory parameters changed.

## 12. Recommendation

**N4B2 answers its question as follows:**

1. **DNp04 is the only candidate that gives earlier neural evidence of slow approach.** It
   marks the episode-5 slow-close case at tick 613, 55 samples (1.1 s) before N4B1C and
   before the strike (the paddle is hovering overhead, not closing range; see the
   correction in section 6). It also detects the weak N1 approach class
   60 / 60, against 33 / 60 for N4B1C.
   - The eight other wiring-qualified types (DNp02, DNg40, DNp11, DNp03, DNp05, DNpe056,
     DNp103, DNpe025) do not help and are rejected.
   - Longer integration windows (500 ms) are rejected on N0.
2. **DNp04 is clean on the fixed-fly N0 background**: 0 events in 910 min, including 0 in
   the new 280-min holdout (95 % upper 0.0033/min overall). The margin is the same as
   DNp01's lateral path.
3. **DNp04 is not clean in no-player free flight.** Held out, it produced 11 escapes in
   36 min (0.31/min), all from the fly's own flight near a stationary paddle, against 3
   for N4B1C. This fails the < 0.1/min target on that background. It also makes the fly
   fire on every weak or aborted approach, and about 30 more times in 3.7 min of recorded
   human play.
4. **This matches the biology.** DNp04 is a location-blind loom-burst neuron with a weak,
   omnidirectional long-mode takeoff phenotype (Dombrovski et al. 2023), not a selective
   escape command. In this model it simply receives 60-70 % of its input from the
   encoder's LC4/LPLC2 cells.

**Is whitelist expansion justified? Not on the current evidence as a drop-in runtime
change.** DNp04 fixes the slow-close case, but the frozen, held-out data show a
background-specificity cost in free flight that the accepted runtime does not have (3.7
times the ROOM false-escape rate). Whether a jumpier fly is acceptable is a product
decision for you, not a research outcome. **No runtime, whitelist or configuration change
has been made.**

Options for the next decision (each needs explicit approval):

- **A. Keep N4B1C unchanged.** Slow approach stays insensitive (tick 668).
- **B. Runtime candidate "N4B1C OR DNp04 pair 60 ms".** This expands the policy whitelist
  by DNp04 L/R. Expected: slow-close at 613, strikes 20-40 ms earlier, about 0.2-0.3 extra
  escapes/min in free flight near the paddle, and noticeably more escapes during
  mid-distance chases. It would need a human test to judge the jumpiness.
- **C. Further research (N4B3, research only)** on a more selective DNp04-based signal,
  designed on development data and validated on new ROOM and N0 data. Untested
  hypotheses:
  - require concurrent DNp01 evidence: in the slow-close case DNp01 L also fired at 612;
  - use the restricted MotionState already in the observation to discount self-motion
    expansion, by analogy with published flight-state gating of other visual DNs (Ache,
    Namiki et al. 2019 *Nat Neurosci*, landing DNs; an analogy only, not DNp04 evidence).

  The present ROOM holdout must not be reused to design these.

Recommended default: **A now, with C if slow-approach sensitivity remains a priority.**
Choose B only if a jumpier fly is acceptable, since the specificity cost above is measured,
not hypothetical.

## 13. Reproduction and artifacts

    .venv\Scripts\python.exe tools\n4b2_connectome.py
    .venv\Scripts\python.exe tools\n4b2_record.py n0 --set n4b1_fresh --chunk 0        (chunks 0-3)
    .venv\Scripts\python.exe tools\n4b2_record.py n0 --set n4b1c_holdout --chunk 0     (chunks 0-3)
    .venv\Scripts\python.exe tools\n4b2_record.py room --seed 7101 --ticks 9000         (7101-7104)
    .venv\Scripts\python.exe tools\n4b2_analysis.py dev
    .venv\Scripts\python.exe tools\n4b2_analysis.py freeze
    .venv\Scripts\python.exe tools\n4b2_record.py n0 --set n4b2_holdout --chunk 0      (chunks 0-3)
    .venv\Scripts\python.exe tools\n4b2_record.py room --seed 7201 --ticks 9000         (7201-7212)
    .venv\Scripts\python.exe tools\n4b2_analysis.py holdout

Each `n0` chunk is one process with `NUMBA_NUM_THREADS=2`: about 45 min with 8 chunks in
parallel on this machine. ROOM runs take 1-3 min each. The analysis modes take under
2 min. The ROOM and reference-replay tools need the detached runtime worktree:

    git worktree add --detach artifacts/worktrees/n4b1c-runtime-detached e3c55b36084cd1d05e5f38d0b178aed0b9a59ddf

plus a `data` junction to `data/`.

Artifacts (`artifacts/m1_8_n4b2/`, git-ignored; sha256 prefixes):

| File | sha256 |
|---|---|
| `connectome.json` | `57c2120697219609` |
| `dev.json` (development characterization) | `0f0e277c6fac7172` |
| `frozen_criteria.json` | `507200845d21ac88` |
| `holdout.json` | `e7f1182728fa5099` |
| `frozen_on_development_threat.json` (frozen criteria on N1 / human data) | `479043516f2f7c1c` |
| `n0_n4b1_fresh_chunk0..3.npz` | `2ef355a62edbdd96`, `28309d75b345bb73`, `e3a7f562766f63b2`, `df6b7ab5eeaad2e3` |
| `n0_n4b1c_holdout_chunk0..3.npz` | `90220a97396f679c`, `122d3cbc8c6f0971`, `1c49f591f0007327`, `ed0bd0f3a333ca32` |
| `n0_n4b2_holdout_chunk0..3.npz` (new holdout) | `d628430cb26c8de7`, `e19f9b72edc240f8`, `3b0e026d2f1030f4`, `c2d70150ccb29021` |
| `room_seed7101..7104.npz` (development) | `4fda175cd1942eed`, `1214bf665053ccff`, `67ec5ecf8ea4d66e`, `2df35dd2e632f7d6` |
| `room_seed7201..7212.npz` (holdout) | `aed2fe4407351d46`, `07b780ef6bb7a26d`, `4164920858100469`, `a0bc7758cba7fbe1`, `e100d0fe40071cdc`, `8b9a49cec51f14ee`, `a647ecac2e723631`, `f5882f3f501c8f8d`, `cc9982530996aa48`, `7b7949c1d71060d3`, `8cc076a69f1187e6`, `dd8ef0104ee2f927` |

Freeze integrity:

- The criteria module sha256 (`6175f124b597f788...`) is unchanged since the freeze.
- After the freeze, `tools/n4b2_analysis.py` changed in one line only: the holdout-mode
  summary `print` indexed the ROOM result without its `criteria` key. The evaluation code
  and every criterion are unchanged, and the evaluation was re-run unchanged.

Validation on the research branch:

- 330 / 330 tests pass (`python -m unittest discover -p "test_*.py"`). The 414-test count
  belongs to the feature branch, which adds the N4B1C runtime tests.
- The 20 protected files match `artifacts/m1-2/protected-before.json`, and none differs from
  `76806f0`.
- `verify_results.py` passes (frozen weights verified).

Limitations:

- one tester, two human sessions, one slow-close episode;
- N1 is scripted fixed-fly probes;
- human analyses are open loop;
- ROOM uses a parked paddle only (no moving no-threat paddle);
- a combined decoder is evaluated as the union of two event streams, not as closed-loop
  behaviour;
- all N0 safety margins are Class C simulator properties.

## 14. Bibliography (primary sources checked)

- Namiki S, Dickinson MH, Wong AM, Korff W, Card GM (2018). The functional organization of
  descending sensory-motor pathways in *Drosophila*. *eLife* 7:e34272. doi:10.7554/eLife.34272
- Dombrovski M, Peek MY, Park J-Y, et al. (2023). Synaptic gradients transform object
  location to action. *Nature* 613:534-542. doi:10.1038/s41586-022-05562-8
- Moreno-Sanchez A, Vasserman AN, Jang H, Hina BW, von Reyn CR, Ausborn J (2024). Morphology
  and synapse topography optimize linear encoding of synapse numbers in *Drosophila*
  looming responsive descending neurons. *eLife* reviewed preprint 99277.
  doi:10.7554/eLife.99277.1
- von Reyn CR, Breads P, Peek MY, et al. (2014). A spike-timing mechanism for action
  selection. *Nat Neurosci* 17:962-970. doi:10.1038/nn.3741
- von Reyn CR, Nern A, Williamson WR, et al. (2017). Feature integration drives
  probabilistic behavior in the *Drosophila* escape response. *Neuron* 94:1190-1204.
  doi:10.1016/j.neuron.2017.05.036
- Ache JM, Polsky J, Alghailani S, et al. (2019). Neural basis for looming size and velocity
  encoding in the *Drosophila* giant fiber escape pathway. *Curr Biol* 29:1073-1081.
  doi:10.1016/j.cub.2019.01.079
- Kim H, Park H, Lee J, Kim AJ (2023). A visuomotor circuit for evasive flight turns in
  *Drosophila*. *Curr Biol* 33:321-335. doi:10.1016/j.cub.2022.12.014
- Buchsbaum E, Schnell B (2025). Activity of a descending neuron associated with visually
  elicited flight saccades in *Drosophila*. *Curr Biol*. doi:10.1016/j.cub.2024.12.001
- Croke H, et al. (2025). *Drosophila* DNp03 descending neurons serve as a hub within a
  flight saccade network. *Curr Biol*. doi:10.1016/j.cub.2025.11.035
- Checked, no DNp04 phenotype found: Cande J, et al. (2018) *eLife* 7:e34275; Braun J, et al.
  (2024) *Nature* 630:686-694.

Most full texts were read through a summarising fetch. The DNp04 statements come from the
Dombrovski et al. 2023 full text. Statements labelled A are what those papers report; they
were not re-derived here.
