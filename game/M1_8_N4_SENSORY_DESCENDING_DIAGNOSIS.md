# M1.8-N4A: sensory-to-descending pathway diagnosis

Status: **research only; complete; classification and N4B recommendation below.** No
runtime, configuration, calibration, provenance, Retina, encoder, brain-noise, decoder,
lifecycle, physics or policy-observation change. Nothing committed or pushed.

Baseline: committed HEAD `76806f0` plus the uncommitted, human-rejected N2b working tree
(unchanged). Everything here is offline. Geometry, Retina values, encoder drive, sensory
spikes, DNp01 membrane voltage and other descending neurons (DNs) are used only to
diagnose recorded situations. None of them is, or is proposed here to become, a policy
input.

Tools:

- `tools/n4_resimulate.py`: exact, instrumented re-simulation of recorded runs;
- `tools/n4_diagnosis.py`: all tables in this report.

Artifacts (`artifacts/m1_8_n4/`, git-ignored; sha256):

| File | sha256 |
|---|---|
| `n0.npz` (150 x 1400-tick N0 arm) | `ed722315...a2e9` |
| `n1.npz` (300 N1 trials) | `74060a69...2cd9` |
| `session_20260923T005351.731330Z-38255ec8.npz` (strict-N2 human) | `1efa05bf...86b2` |
| `session_20260924T000111.561327Z-c337a721.npz` (N2b human) | `ab125f00...2b8f` |
| `diagnosis.json` | `5e7a8a07...cc19` |

## 0. N3 conclusion (accepted input to N4)

DNp01-only evidence integration cannot solve the human latency failure while keeping the
accepted N0 constraint (`game/M1_8_N3_NEURAL_EVIDENCE_INTEGRATION.md`). N3 worked on the
**summed** DNp01 trace (left + right), which is what every decoder so far has used.

## 1. Method: exact instrumented re-simulation

The brain is `flybrain.FlyBrain` (leaky integrate-and-fire), with these dynamics per
20 ms step:

- update: v <- 0.8187 v + 3.0 * W @ spikes + 0.14 (tonic) + noise + encoder injection;
- spike at v >= 1, then reset to **0**;
- noise: Bernoulli per neuron per step, p = 1.2 Hz * 0.02 s = 0.024, amplitude +0.22;
- a silent neuron rests at 0.14 / (1 - 0.8187) = **0.772**, so one noise kick lifts it
  only to 0.992;
- the policy's DNp01 value is a `flybrain.Trace` (tau 0.1 s, +1 per spike) of **one
  DNp01 cell per side**.

The encoder adds one voltage to every chosen cell of one side per tick: 91 LPLC2 and
55 LC4 cells per side, and only the side of the Retina azimuth. LPLC2 drive is
`min(0.8, 0.4 * max(0, theta_dot))`. LC4 drive is
`0.8 * min(1, theta / 0.5) * min(1, max(0, theta_dot) / 2)`. `loom_size` is 0, so
LPLC2 ignores angular size.

`tools/n4_resimulate.py` feeds the recorded inputs back into the unchanged brain `step`
under the recorded Numba thread counts (4 for N0/N1, 8 for the human sessions) and
observes it:

- before each step it reads the DNp01 voltages and splits their synaptic input by source
  (the encoder's chosen LC4/LPLC2 cells, other excitatory partners, inhibitory partners);
- it reads the step's noise draw from a deep copy of the brain's random generator, so the
  brain's own stream is untouched;
- after the step it records DNp01 spikes, LC4/LPLC2 spike counts, and every DN spike.

Verification against the recordings (DNp01 recomputed from re-simulated spikes, compared
exactly):

| Dataset | Exact |
|---|---|
| N0, 150 trials (210,000 recorded ticks) | 150 / 150 trials, bit-exact |
| N1, 300 trials | 300 / 300 trials, bit-exact |
| strict-N2 human session | 7025 / 7025 stepped ticks (DNp01 L and R); sensory spikes 7025 / 7025 |
| N2b human session | 4130 / 4130 stepped ticks; sensory spikes 4130 / 4130 |
| DNp01 voltage model (v_pre reconstruction) | 0 mismatching steps in all four datasets |

## 2. Retina characterization

Per-event medians. N1 metrics cover the labelled stimulus window (the click, or expansion
onset, to window end). Human events: bout windows (hover escapes: encoder-bout onset to
escape; direct strikes: 0.5 s before the click to resolution).

| Metric | N1 strong | N1 medium | N1 weak | N1 glancing | N1 aborted | human direct strike (39) | human strike-phase escape (29) | human hover escape (33) | slow-close 610-670 | far perched (ref.) | voluntary takeoff (ref.) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| theta mean (rad) | 1.12 | 0.72 | 0.34 | 0.23 | 0.28 | 0.46 | 0.36 | 0.31 | 0.44 | 0.07 | 0.06 |
| theta_dot peak (rad/s) | 16.2 | 7.17 | 0.43 | 0.45 | 0.58 | 6.52 | 3.19 | 0.97 | 4.38 | 0.12 | 0.001 |
| fraction of samples expanding | 0.93 | 0.93 | 0.92 | 1.00 | 1.00 | 0.70 | 0.96 | 1.00 | **0.51** | 0.95 | 0.33 |
| longest expansion run (s) | 0.28 | 0.28 | 1.55 | 0.61 | 0.65 | 0.40 | 0.32 | 0.34 | 0.28 | 1.60 | 0.50 |
| theta_dot sign flips per s | 0 | 0 | 0 | 0 | 0 | 2.4 | 0.9 | 0 | **7.4** | 1.1 | 0 |
| integrated positive growth (rad) | 1.63 | 0.70 | 0.30 | 0.15 | 0.20 | 0.74 | 0.29 | 0.18 | 0.28 | 0.06 | 0.0005 |
| large theta (> 0.35) with abs(theta_dot) < 0.25 (s) | 0.02 | 0.02 | 0.80 | 0 | 0.02 | 0.02 | 0 | 0 | **0.94 of 1.22** | 0 | 0 |
| azimuth side switches per s | 0 | 0 | 0 | 0 | 0 | 1.2 | 0 | 0 | **3.3** | 0 | 0 |

N0 (fixed fly, paddle settled at hover height 30-170 units away): same protocol as the
settled pre-click samples of N1 committed trials, which give theta 0.34-0.56 rad and
abs(theta_dot) below 5e-11 (a float residue). N0 encoder drive is below 1e-11 throughout.

Findings:

- **The slow-close case is a hovering, large, nearly constant-size object.** theta stays
  about 0.43 rad for 0.94 of 1.22 s with abs(theta_dot) < 0.25 rad/s. theta_dot flips sign
  7.4 times per second and the azimuth flips side 3.3 times per second, because the
  paddle passes back and forth over the fly at hover height.
- At hover height the 3D distance cannot fall below 320 units. Offline, 1000 units/s of
  paddle motion produces a median abs(theta_dot) of only 0.49-0.65 rad/s at horizontal
  distances below 400 units. The human hover speed (median about 378 units/s) therefore
  yields theta_dot around 0.2 rad/s, which is LPLC2 drive of about 0.08.
- **Yes: the current representation makes a large nearby object weak once its angular size
  stops increasing.** LPLC2 drive is `0.4 * max(0, theta_dot)` with no size term, and LC4
  drive is size times growth. A static 0.43 rad paddle produces zero drive. That is by
  design, and N0 relies on it: N0 is itself a static paddle at the same theta (0.34-0.56).
  **Static size therefore cannot separate threat from the N0 condition.** Only expansion
  can, and at the Retina level any expansion does so immediately.

## 3. Encoder characterization (LC4 / LPLC2)

| Metric (median per event) | N1 strong | N1 medium | N1 weak | N1 glancing | N1 aborted | human direct strike | human strike-phase escape | human hover escape | slow-close | far perched | voluntary |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ticks with drive > 0 | 14 | 14 | 78.5 | 34 | 33 | 28 | 20 | 19 | 31 | 90 | 25 |
| LPLC2 drive peak | 0.80 | 0.80 | 0.17 | 0.18 | 0.23 | 0.80 | 0.80 | 0.39 | 0.80 | 0.05 | 0.0004 |
| LC4 drive peak | 0.80 | 0.80 | 0.09 | 0.09 | 0.13 | 0.80 | 0.80 | 0.33 | 0.80 | 0.01 | 0.00005 |
| drive bursts | 1 | 1 | 2 | 1 | 1 | 2 | 2 | 1 | **5** | 2 | 1 |
| sensory spikes, total | 1820 | 1460 | 1860 | 740 | 998 | 1880 | 1040 | 741 | 1240 | 553 | 289 |
| sensory spikes, peak per tick | 149 | 149 | 67 | 69 | 73 | 149 | 146 | 89 | 146 | 52 | 8 |
| sensory spikes per drive tick | 130 | 105 | 24 | 22 | 31 | 64 | 45 | 38 | 35 | 6 | 4 |
| L/R asymmetry of sensory spikes | 0.97 | 0.96 | 0.83 | 0.80 | 0.87 | 0.45 | 0.88 | 0.86 | **0.33** | 0.30 | 0.02 |
| drive side switches | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | **4** | 0 | 0 |

N0: encoder drive is below 1e-11 on every tick. Spontaneous LC4 + LPLC2 activity is a mean
of 2.0 spikes per side per tick, with a maximum of 22 spikes per side per tick (51 per
side in any 60 ms).

Drive to sensory spikes (pooled over N1 and both human sessions, 97,306 side-ticks):

| Drive | ticks | mean sensory spikes / tick (one side) | P(>= 40 spikes) |
|---|---|---|---|
| 0 | 73,507 | 2.0 | 0.0003 |
| 0 - 0.05 | 9,484 | 3.3 | 0.003 |
| 0.05 - 0.1 | 3,907 | 14.3 | 0.07 |
| 0.1 - 0.2 | 4,928 | 23.5 | 0.12 |
| 0.2 - 0.4 | 2,664 | 39.2 | 0.46 |
| 0.4 - 0.8 | 987 | 57.7 | 0.78 |
| >= 0.8 (saturated) | 1,829 | 127.2 | 0.97 |

**How hover chases give 40-146 sensory spikes per tick yet sparse DNp01 output.** The
encoder drives all chosen cells of one side with the same voltage, so they integrate in
step and fire as **synchronized volleys**. At drive >= 0.23 a resting cell fires on the
first tick. It then resets to 0 and needs about two ticks at saturation (0.8) to fire
again, so volleys of up to 146 cells alternate with near-silent ticks. The slow-close
record shows this (tick 624: 90 LPLC2 + 54 LC4 on the right side, then 1). What reaches
DNp01 is set by the wiring and by DNp01's own state (section 4), not by the volley size.

## 4. MaleCNS transfer to DNp01

Wiring from the encoder's chosen cells (ipsilateral only; contralateral weight is 0),
multiplied by gain 3:

| Input to DNp01 | left DNp01 | right DNp01 |
|---|---|---|
| full LPLC2 volley (91 cells) | +0.374 V | +0.415 V |
| full LC4 volley (55 cells) | +0.431 V | +0.482 V |
| threshold minus rest | 0.228 V | 0.228 V |

For comparison, the chosen encoder cells deliver 0.60 (DNp04 L) and 0.70 (DNp04 R) total
weight to DNp04, against 0.27 / 0.30 to DNp01 (section 7).

Measured transfer (pooled N1 and human; DNp01 on the driven side, next tick):

| Sensory spikes on that side | ticks | encoder current into DNp01 (V) | P(DNp01 spike) | inhibitory current (V) |
|---|---|---|---|---|
| 0-1 | 14,086 | 0.000 | 0.007 | -0.030 |
| 1-5 | 64,293 | 0.011 | 0.009 | -0.030 |
| 5-20 | 9,649 | 0.045 | 0.028 | -0.035 |
| 20-50 | 5,868 | 0.165 | 0.22 | -0.047 |
| 50-100 | 1,833 | 0.344 | 0.50 | -0.056 |
| 100-200 | 1,577 | 0.798 | 0.75 | -0.097 |

P(DNp01 spike) by encoder current and DNp01 voltage on the previous tick:

| Encoder current (V) | recovering (v < 0.3) | v 0.3-0.6 | near rest (v >= 0.6) |
|---|---|---|---|
| 0.05-0.2 | 0.00 | 0.001 | 0.26 |
| 0.2-0.4 | 0.00 | 0.03 | 0.76 |
| 0.4-0.7 | 0.01 | 0.67 | 1.00 |
| >= 0.7 | 0.69 | 1.00 | 1.00 |

Per-event transfer (medians):

| Metric | N1 strong | N1 medium | N1 weak | N1 glancing | N1 aborted | human direct strike | human strike-phase escape | human hover escape | slow-close | far perched |
|---|---|---|---|---|---|---|---|---|---|---|
| encoder onset to first DNp01 spike (s) | 0.02 | 0.04 | 0.28 | 0.16 | 0.16 | 0.06 | 0.06 | 0.12 | 0.04 | 1.20 |
| DNp01 inter-spike interval (s) | 0.025 | 0.03 | 0.12 | 0.10 | 0.08 | 0.04 | 0.06 | 0.06 | 0.14 | 0.04 |
| DNp01 spike probability per tick | 0.60 | 0.53 | 0.14 | 0.13 | 0.18 | 0.27 | 0.24 | 0.23 | 0.13 | 0.04 |
| DNp01 spikes per 1000 sensory spikes | 5.1 | 5.6 | 6.4 | 6.1 | 6.3 | 5.7 | 5.7 | 6.0 | 6.5 | 7.2 |
| encoder current peak (V) | 0.80 | 0.90 | 0.37 | 0.35 | 0.40 | 0.90 | 0.73 | 0.51 | 0.88 | 0.23 |
| inhibitory current minimum (V) | -0.20 | -0.19 | -0.16 | -0.14 | -0.15 | -0.18 | -0.16 | -0.15 | -0.23 | -0.15 |

Findings:

- **Latency is short when drive is strong.** Click to theta_dot and to the first sensory
  volley takes one tick (physical swatter plus the Retina finite difference); the volley
  reaches DNp01 one tick later (a single synaptic step). Under saturated drive, DNp01
  then fires every 1-2 ticks, on the driven side only.
- **The transfer ratio is constant: about 5-7 DNp01 spikes per 1000 sensory spikes** in
  every class, from committed strikes to far approaches. MaleCNS does not distinguish
  "many weak volleys" from "few strong ones". It passes a small, fixed fraction.
- **Three mechanisms throw information away before DNp01:**
  1. *Threshold margin.* A volley of 20-50 sensory cells gives about 0.16 V, below the
     0.228 V gap between rest and threshold. Hover chases mostly produce volleys of that
     size, and they spike DNp01 only when noise or other input adds the rest.
  2. *Reset to zero.* After each spike DNp01 drops to 0 V, not to rest. It then ignores
     0.2-0.4 V inputs (P = 0.00-0.03) for several ticks. In the slow-close case, DNp01
     needed about 6 ticks to climb back.
  3. *Side splitting.* Drive goes to one side at a time. The slow-close sensory spikes are
     split 0.33 L/R asymmetry across 4 side switches, so neither DNp01 cell accumulates.
- Feedforward inhibition is present but modest: -0.03 V at rest, -0.10 V during saturated
  volleys, and at most about -0.23 V. There is no evidence of network suppression that
  silences DNp01 during threat.
- Some DNp01 threat spikes need a noise kick (slow-close ticks 605 and 640).

## 5. Spontaneous DNp01 background (full N0, 70.0 min)

| Quantity | Value |
|---|---|
| Rate, left / right DNp01 | 0.345 / 0.417 Hz |
| Spikes needing a noise kick on DNp01 itself | **3072 / 3203 (96 %)**: 2402 kick alone (DNp01 slightly depolarized above rest), 670 kick plus a little net excitatory input |
| Spikes without a kick (synaptic only) | 129 (4 %) |
| DNp01 voltage before a spontaneous spike | median 0.816 (p10 0.764), essentially at rest |
| Largest positive synaptic contributions at spontaneous spikes | spontaneous LPLC2 and LC4 activity, DNp70, SAD064, PVLP122b, PVLP151 (small, diffuse) |
| **Same-side inter-spike interval** | **minimum 8 ticks (160 ms)** on both sides; median 98 (L) and 82 (R) ticks; **0 same-side intervals <= 4 ticks** |
| Pooled (L+R) inter-spike interval <= 4 ticks | 90, **all bilateral** |
| Same-tick L+R pairs (trace about 2.0) | 17, against 12.1 expected if independent |
| L-R cross-correlogram, lags -10 to +10 | 6-18 per lag, flat around the 12.1 expected: **left and right are independent** |
| Close pairs within 4 ticks | bilateral only: lag 0 / 1 / 2 / 3 / 4 = 17 / 17 / 19 / 30 / 24; same-side 0 |
| DNp01 v before threshold | median 0.75; 2.0 % of samples >= 0.95 |

Mechanism:

- each spontaneous DNp01 spike is essentially the neuron's **own Bernoulli noise kick**
  (+0.22) landing while it sits at or slightly above rest (0.772);
- after that spike the cell resets to 0 and cannot fire again from noise for at least
  8 ticks;
- the "two-spike coincidences" that made the legacy 1.45 decoder fire, and that set the
  summed-trace three-spike floor in N3, are therefore **always one independent spike on
  each side**. The ~2.0 trace peaks are same-tick bilateral pairs, at a chance rate. The
  far perched peak of 2.0557 from N3 (strict-N2 session, episode 1, row 2513) is a
  same-tick L+R pair in which both cells received a noise kick, plus residue. The earlier
  1.67 peak of that approach is a bilateral pair two ticks apart (R 2494, L 2496);
- **why the decoder cannot safely react to the second spike: it adds two independent
  0.35-0.42 Hz noise processes and then cannot tell "one spike on each side" from "two
  spikes on the stimulated side".** Threat input is ipsilateral, and spontaneous
  activity never produces two same-side spikes within 160 ms.

Brain noise is not changed and is not proposed to be changed.

## 6. Threat versus background at each processing level

Detection = first sample, after the event onset, at which each level exceeds its N0
envelope (median seconds; `detected / n`). Onset is the click for N1 strong/medium and
human direct strikes, and expansion or bout onset otherwise.

| Level (N0 envelope) | N1 strong | N1 medium | N1 weak | N1 glancing | N1 aborted | human direct strike | human strike-phase escape | human hover escape | chase before 589 | slow-close | far perched | voluntary |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A Retina: theta_dot > 0 (N0: 0) | 0.02 | 0.02 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.02 (tiny) |
| B encoder drive > 0 (N0: < 1e-11) | 0.02 | 0.02 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.02 (tiny) |
| B sensory spikes > 22 on one side | 0.02 | 0.02 | 0.28 | 0.14 | 0.16 | 0.02 | 0.04 | 0.08 | 0.04 | **0.02** | 1.18 | never |
| C first DNp01 spike (not N0-safe) | 0.04 | 0.05 | 0.28 | 0.16 | 0.16 | 0.04 | 0.06 | 0.12 | 0.06 | 0.04 | 1.20 | 0.82 |
| C second DNp01 spike within 80 ms, summed (not N0-safe; legacy) | 0.08 | 0.08 | 0.44 | 0.36 | 0.36 | 0.08 | 0.22 | 0.22 | 0.12 | 0.60 | 1.24 | never |
| **C three DNp01 spikes in 200 ms, summed (N0-safe floor, N3)** | **0.10** | **0.14** | 0.56 (47) | 0.38 (47) | 0.41 (56) | 0.06 (37) | 0.22 | 0.28 | 0.22 | **0.74** | never | never |
| **C lateralized: two same-side DNp01 spikes in 100 ms (N0: never)** | **0.08** | **0.10** | 0.44 (39) | 0.36 (39) | 0.38 (58) | 0.08 | 0.22 | 0.22 (29) | 0.12 | 1.16 | never | never |
| D trace >= 2.10 (FAST) | 0.10 | 0.14 | 0.94 (20) | 0.44 (15) | 0.52 (23) | 0.12 (37) | 0.50 (27) | 0.26 (19) | never | 1.20 | never | never |
| Lead of sensory level over DNp01 N0-safe floor | 0.08 | 0.12 | 0.22 | 0.22 | 0.20 | 0.06 | 0.18 | 0.18 | 0.18 | **0.72** | - | - |

Counts in parentheses are events detected when fewer than all were. Recorded escapes
(median seconds from onset): human direct strike 0.64 (click at 0.50, so 0.14 s after the
click), strike-phase escape 0.50, hover escape 0.40, chase before 589 0.38, slow-close 1.20.

**The central N4 question: can threat be separated from N0 earlier than the DNp01-safe
third-spike point?**

- **A (Retina) and B (encoder): yes, immediately.** N0 has no expansion and no drive, and
  its spontaneous sensory activity never exceeds 22 spikes per side per tick. Threat
  volleys exceed that 1 tick after drive onset in committed strikes, and at tick 611 in
  the slow-close case (0.72 s before the DNp01 floor). Specificity: the voluntary takeoff
  never exceeds the sensory envelope. The far perched approach (1805 units) exceeds it
  only after 1.18 s, with small theta (0.11 rad against 0.44 in the slow-close case).
- **C (DNp01 spikes), summed: no.** This is the N3 floor.
- **C (DNp01 spikes), lateralized: yes for committed strikes; not for the slow-close
  case.** Two same-side spikes within 100 ms never occur in N0 (0 events on the
  selection half, and 0 on the held-out half, section 7). They mark committed strikes at
  0.08 / 0.10 s, legacy-level latency, against 0.10 / 0.14 s summed. In the chase before
  tick 589, DNp01_L fires at 573 and 576, so a lateral reading marks tick 576, 13 ticks
  (0.26 s) before N2b escaped. The slow-close spikes alternate sides (612 L, 625 R,
  638 L, 640 R, 647 R, 666 L, 668 L), so a lateral reading marks only tick 668.
- **D (trace): no better than C summed**; FAST is one form of the three-spike rule.

Both DNp01 cells are already in the policy observation (`dnp01_left`, `dnp01_right`). The
lateral structure is not new information. The summed-trace decoders (legacy, N2, N2b and
all N3 candidates) discarded it.

## 7. Other descending neurons (exploratory, offline only)

Nothing here is wired into any policy, and the whitelist is unchanged.

24 DN cells receive direct weight > 0.05 from the encoder's chosen LC4/LPLC2 cells: DNp04
(0.70 R / 0.60 L), DNp01 (0.30 / 0.27), DNp02 (0.24 / 0.22), DNg40 (0.22 / 0.18),
DNp11 (0.17 / 0.14), DNp71, DNp03, DNpe056, DNp05, DNp103, DNpe025, DNp06.

Rule, per cell: fire when the cell's spike count in a window of 1, 3, 5 or 10 samples
exceeds that cell's maximum on N0 trials 0-74 (the selection half). For every single cell
here that means **two spikes within 100 ms, or three within 200 ms, on one cell**. N0
events are counted on the selection half and on the held-out trials 75-149.

| Readout | N0 events, selection / held-out | strong | medium | weak | glancing | aborted | human direct strike | human hover escape | chase before 589 | slow-close | far perched | voluntary |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DNp01 summed (policy basis) | 0 / 0 | 0.10 | 0.14 | 47 / 0.56 | 47 / 0.38 | 56 / 0.41 | 0.06 (37) | 0.28 | 0.22 | 0.74 | no | no |
| **DNp01 lateralized** | 0 / 0 | **0.08** | **0.10** | 39 / 0.44 | 39 / 0.36 | 58 / 0.38 | 0.06 | 0.22 (29) | 0.12 | 1.16 | no | no |
| DNp02 lateralized | 0 / 0 | 0.08 | 0.10 | 12 / 0.68 | 9 / 0.42 | 27 / 0.48 | 0.10 (37) | 0.25 (22) | 0.38 | 1.16 | no | no |
| DNg40 lateralized | 0 / 0 | 0.08 | 0.10 | 33 / 0.54 | 30 / 0.36 | 49 / 0.38 | 0.08 (38) | 0.24 (26) | 0.26 | 1.18 | no | no |
| DNp11 lateralized | 0 / 0 | 0.10 | 0.14 | 0 | 0 | 3 / 0.56 | 0.14 (35) | 0.21 (10) | no | 1.20 | no | no |
| **DNp04 lateralized** | 0 / 0 | **0.06** | **0.06** | 60 / 0.40 | 59 / 0.30 | 60 / 0.30 | 0.00 | **0.16** | 0.12 | **0.06** | no | no |
| each of the 24 direct-input cells separately | 0 / 0 | 0.06 | 0.06 | 60 / 0.36* | 59 | 60 | 0.00 | 0.16 | 0.12 | 0.06 | no | no |
| pooled count of all 24 direct-input cells | 0 / **5** | 0.04 | 0.06 | 60 | 60 | 60 | 0.00 | 0.14 | 0.10 | 0.06 | yes (1.60) | no |

Weak, glancing and aborted columns show `detected of 60 / median s`. \* Same as DNp04,
which dominates.

- **DNp04**, the strongest LC4/LPLC2 target in this connectome plus encoder, fires at
  about 0.8 Hz spontaneously, like DNp01, and has the same single-cell N0 structure. It
  marks medium strikes at 0.06 s and the slow-close case at tick 613. That is 10 ticks
  before the closest center approach and 57 ticks before the reversal: DNp04_L fires at
  612 and 613.
- The cost is specificity: DNp04 marks essentially every N1 weak, glancing and aborted
  approach (60 / 59 / 60 of 60; N2b fires on 29 / 27 / 44). It does not mark the far
  perched approach or the voluntary takeoff.
- Pooling many cells raises spontaneous coincidences, and 5 held-out N0 events appear.
  Pooling is not safe as tested.
- This is a multiple-comparison exploration over about a dozen readouts. It is not a
  validated decoder. The single-cell N0 safety comes from the same simulator property as
  DNp01's (reset to zero plus independent noise), which is a Class C model property, not
  a biological measurement.

## 8. Human-session case studies

**N2b session, direct strikes (8) and strike-phase escapes.** Onset is the click. Sensory
volleys exceed N0 within 0.02 s. The summed DNp01 floor is often reached before or at the
click (median 0.06 s after it), because the paddle is already chasing at hover height.
Recorded click-to-escape: 0.14 / 0.06 / 0.02 / 0.02 s (N3). The strike-phase escape at
tick 670 is one tick after the click at tick 669.

**Hover-chase escape bouts (33 across both sessions).** Encoder-bout onset to first DNp01
spike: median 0.12 s. Recorded escape at median 0.40 s after onset. The summed DNp01 floor
is at 0.28 s; lateralized DNp01 at 0.22 s (29 of 33); DNp04 at 0.16 s; the sensory level
at 0.08 s.

**Episode 5 (N3 correction preserved).** The paddle chased the airborne fly from at least
tick 570. N2b escaped at **tick 589** (SUSTAINED), and its refractory period ended at
**tick 609**. Tick 670 is **not** the first escape of the bout: it is the strike-phase
FAST escape one tick after the click at tick 669, following the slow-close interval
610-669.

| Tick | Retina / encoder | Sensory (L / R) | DNp01 | DNp04 | Note |
|---|---|---|---|---|---|
| 573, 576 | continuous chase drive | | L 573, 576 | L 573, 576 | a lateral DNp01 reading would mark 576 |
| 585-589 | | | L 585, 588 | L 585, 587, 589 | N2b escape at 589 on the decaying trace (HLLHH); refractory to 609 |
| 610-611 | theta about 0.43, theta_dot +0.18 / +0.40 | 85 L at 611 (73 LPLC2 + 12 LC4) | | | sensory level exceeds N0 at 611 |
| 612-613 | | | L 612 | **L 612, 613** | DNp04 lateral marks 613 |
| 623 | closest center approach, 10.7 units | | | | theta_dot negative, drive 0 |
| 624-625 | theta_dot +4.38, saturated right volley | 90 + 54 R at 624 | R 625 | R 625 | one volley, one spike each |
| 633-637 | drive 0.03-0.08, side flips L to R | 7-35 per tick, unsynchronized | | | volleys below the 0.228 V margin |
| 634-647 | | | L 638, R 640 (kick), R 647 | L 634, 640; R 645 | bilateral; lateral DNp01 not satisfied |
| 663-669 | final loom, drive to 1.39 | 35-91 per tick | L 666, 668 | L 666, 668, 669 | summed floor at 647; lateral at 668 |
| 669-670 | click at 669; theta_dot -0.77 at 670 | | L 670 | | recorded FAST escape at 670 |

**Voluntary takeoff (N2b session, 18.44 s).** Kept separate from threat response. Drive
peaked at 0.0004 (LPLC2) with at most 8 sensory spikes per tick, never above the N0
envelope. One DNp01 spike at 0.82 s before takeoff was spontaneous, and no readout at any
level marks it.

## 9. Dominant-limitation classification

**E. Mixed: C (MaleCNS transfer / DNp01 readout) dominates, with a D component that is
itself a property of the summed readout. A and B are not the limiting stages.**

Quantitative support:

- **Not A or B.** Against N0, threat is separable at the Retina (any expansion) and at the
  sensory-spike level (more than 22 cells per side per tick) essentially at onset. The
  sensory level leads the DNp01 floor by 0.08 / 0.12 s (strong / medium), 0.18 s (hover
  bouts) and 0.72 s (slow-close). The Retina's size-blindness means a hovering paddle
  drives only weak, sign-flipping volleys, but N0 is itself a static large paddle, so
  static size could not separate them anyway. The encoder's one-side-at-a-time drive
  contributes to the side splitting in section 4.
- **C.** MaleCNS passes a constant 5-7 DNp01 spikes per 1000 sensory spikes. The chosen
  encoder cells reach DNp01 with only 0.27-0.30 total weight, against 0.60-0.70 onto
  DNp04. A 20-50-cell volley gives 0.16 V, less than the 0.228 V margin, and reset-to-zero
  blocks 0.2-0.4 V inputs for several ticks. In the same brain, DNp04 marks the slow-close
  case at tick 613 and medium strikes at 0.06 s. DNp01 marks them at tick 647 (summed) and
  0.14 s. **The threat information exists downstream of the encoder; DNp01 is a weak,
  slow readout of it.**
- **D.** 96 % of spontaneous DNp01 spikes are the cell's own noise kicks. Left and right
  are independent. Every N0 close pair is bilateral, and same-side intervals are never
  below 160 ms. The summed trace turns two independent noise processes into the
  coincidence that forces the three-spike rule. Reading the same two cells separately
  removes it: 0 N0 events, and legacy-level strike latency (0.08 / 0.10 s).
- **What explains each human complaint:**
  - "direct attacks sluggish": mainly D, the summed readout (lateral DNp01 recovers
    20-40 ms on N1 and 0.26 s in the tick-589 chase), plus C;
  - "slow approach too insensitive": C. Lateral DNp01 does not help (tick 668, because
    DNp01's sparse slow-close spikes alternate sides). Only a stronger-coupled readout
    such as DNp04 marks it early (tick 613).

## 10. N4B recommendation (not implemented)

**Recommend: N4B alternative descending-neuron readout research.**

Scope for that milestone, research only unless separately authorized:

1. **Lateralized DNp01 readout.** This needs no whitelist change: both cells are already
   observed. Characterize "two same-side spikes within about 100 ms" and neighbouring
   forms:
   - on N0 with fresh seeds (the current envelope is a single 70-minute arm);
   - on N1, both human sessions, a closed-loop ROOM run and the M1.8-A perched cases.
   Check the escape side and strength, which currently use the summed trace, and the
   robustness of the 160 ms same-side gap (a simulator property: reset to zero and noise
   amplitude, Class C).
2. **DNp04, and DNp02 / DNg40 / DNp11, as candidate additional readouts.** This would
   **expand the policy observation whitelist** and therefore needs an explicit decision
   before any runtime use. The research should report:
   - their N0 behavior with held-out seeds;
   - their specificity on weak, far and non-contact approaches (DNp04 fires on all N1
     weak classes);
   - the published evidence for each type's looming role, labelled A / B / C, without
     over-claiming. The DNp01 = Giant Fiber identification and the DNa02 steering sign
     stay as currently documented.
3. Keep Retina, encoder gains, brain noise, decoder, lifecycle and physics unchanged. The
   evidence does not point to them as the dominant limitation. The Retina/encoder
   size-blindness for hovering objects is a modelling question to revisit only if N4B
   readouts prove insufficient.

Not recommended now: Retina/encoder retuning (A/B are not limiting against N0), or
background-noise research (the mechanism is already identified here: per-cell noise
kicks). "Stop" is also not recommended, because the evidence shows the current model
does carry earlier N0-separable threat information.

## 11. Reproduction

    .venv\Scripts\python.exe tools\n4_resimulate.py --dataset session --session results\game\sessions\20260924T000111.561327Z-c337a721
    .venv\Scripts\python.exe tools\n4_resimulate.py --dataset session --session results\game\sessions\20260923T005351.731330Z-38255ec8
    .venv\Scripts\python.exe tools\n4_resimulate.py --dataset n1
    .venv\Scripts\python.exe tools\n4_resimulate.py --dataset n0
    .venv\Scripts\python.exe tools\n4_diagnosis.py

Run times on this machine: about 30 s per session, 18 min for N1, 32 min for N0 (N0 and
N1 can run in parallel), and 30 s for the diagnosis. The N0 and N1 re-simulations use the
configuration at commits `3d41113` and `76806f0` (content-identical ROOM configs), read
with `git show`.

Limitations:

- one tester and two human sessions;
- N1 classes are scripted fixed-fly probes;
- human detections are open-loop descriptions of recorded inputs, not closed-loop outcomes;
- bout onsets use the coarse 200 ms-gap rule from N3;
- the other-DN readouts are an exploratory multiple comparison;
- single-cell N0 safety rests on one 70-minute N0 arm, split into selection and held-out
  halves.
