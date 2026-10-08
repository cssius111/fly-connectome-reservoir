# M1.8-N3: neural evidence integration and threat-acquisition study

Status: **research only; complete; recommendation below. No runtime, configuration,
calibration or provenance change. Nothing committed or pushed.**

Baseline: committed HEAD `76806f0` (N1) plus the uncommitted, human-rejected N2b working
tree, which is kept unchanged as failed-candidate evidence. No brain is run: every result
is a replay of already-recorded DNp01 traces.

Tool: `tools/n3_evidence_integration.py` (single command, deterministic).
Artifact: `artifacts/m1_8_n3/evidence_integration.json` (git-ignored; sha256
`4f2e21298a83e79ac6e544f6167dd716d9605e1bf93c16a12f1a55da8503b49d`).

Inputs (sha256):

| Input | Path | sha256 |
|---|---|---|
| N0 primary arm | `artifacts/m1_8_no_loom_calibration/raw.npz` | `8477668b...96c7` |
| N0 continuous arm | `artifacts/m1_8_no_loom_calibration/continuous.npz` | `06714e98...2fe0` |
| N1 trials | `artifacts/m1_8_loom_robustness/trials.npz` | `70640b72...5a6a` |
| N1 metadata | `artifacts/m1_8_loom_robustness/trials_meta.json` | `94ea48ff...df26` |
| strict-N2 human session | `results/game/sessions/20260923T005351.731330Z-38255ec8` | ticks `5973bfdf...2f43` |
| N2b human session | `results/game/sessions/20260924T000111.561327Z-c337a721` | ticks `041218da...7b95` |

## 1. Second human re-acceptance failure (N2b)

The full record is in `game/M1_8_N2B_WINDOW_DECODER.md`, section 12. In short:

- the tester reported direct attacks as clearly sluggish, slow non-contact approaches as
  much too insensitive ("the paddle can get essentially on top of the fly"), no unexplained
  escapes, and normal escape direction;
- the one perched departure (18.44 s) was verified as `TAKEOFF_VOLUNTARY`
  (`local_history_motivation`) with swatter speed 0, center distance 2969 units,
  theta_dot 0, encoder drive 0, DNp01 0.165, CALM and `Action.escape` false;
- in episode 5, ticks 610-669, the paddle stayed within 100 units of an airborne fly for
  1.2 s without an escape; the first escape came at tick 670 via FAST, after theta_dot had
  turned negative.

Both human sessions replay exactly under their recorded decoders: 0 decision mismatches
over all brain-stepped ticks (strict-N2 session: 9 episodes, 37 escapes; N2b session:
6 episodes, 25 escapes).

## 2. What the policy actually observes

The DNp01 value in `MotorState` is a `flybrain.Trace`: an exponentially decaying spike
trace with tau = `trace_tau_seconds` = 0.1 s, decay 0.81873 per 20 ms tick, **+1 per
spike**, summed over the left and right DNp01 cells. So:

- each sample's DNp01 spike count can be recovered exactly as
  `trace_t - 0.81873 * trace_{t-1}` (N0 residual from an integer below 1.5e-7). That is a
  function of the policy's own neural observation history, not a new input;
- every trace statistic (window sum, window mean, leaky accumulator) is a linear filter of
  the DNp01 spike train. **All information available to a DNp01-only decoder is the timing
  of DNp01 spikes.**
- thresholds read as spike counts: one spike gives 1.0; two spikes in the same tick give
  2.0; two spikes one tick apart give 1.82. The trace can reach 2.10 only with at least
  three recent spikes. 1.45 means "two spikes within about 80 ms".

### 2.1 The N0 spontaneous DNp01 process (210,000 ticks, 70 min)

| Quantity | Value |
|---|---|
| Spontaneous DNp01 spike rate (L+R) | 0.764 Hz |
| Samples with 0 / 1 / 2 spikes | 206,807 / 3,176 / 17 |
| Trace maximum | 2.0045 (a same-tick L+R double spike) |
| Max spikes in any 60 / 100 / 160 / 200 ms window | 2 / 2 / 2 / 2 |
| Max spikes in any 240 / 300 / 400 / 500 ms window | 3 / 3 / 3 / 3 |
| Max spikes in any 600 ms window | 4 |
| 200 ms windows with 2 spikes | 1,183 |
| Windows with >= 3 spikes: 240 / 300 / 400 / 500 / 600 ms | 1 / 10 / 75 / 256 / 658 |

This is the central constraint. Spontaneous activity routinely produces **two** DNp01
spikes close together, including same-tick pairs at trace 2.0, but never **three** within
200 ms. Every N0-safe DNp01-only rule must therefore wait either for a third spike within
about 200 ms or for a longer, denser train (for example, more than 4 spikes in 600 ms).
The legacy 1.45 rule fires on the second spike, which is why it fails N0 (91 events in
70 min).

## 3. Latency decomposition

Definitions (offline labels; geometry and Retina/encoder values are diagnostics only):
approach start = click (the paddle is settled before the stimulus; N1 committed strikes
approach mostly vertically); encoder onset = first sample with LC4/LPLC2 drive > 0; DNp01
spikes are deconvolved from the trace (ties count as multiple spikes); **3-spike point** =
first sample holding >= 3 DNp01 spikes in the last 200 ms (the N0-safe floor from 2.1);
closest approach = peak retinal angular size theta; reversal = first theta_dot < 0 after it.

### 3.1 N1 committed strikes (60 trials each; median / p95, seconds from click)

| Stage | strong_direct | medium_committed |
|---|---|---|
| Sensory: click to encoder onset (physical swatter + Retina) | 0.02 / 0.02 | 0.02 / 0.02 |
| theta_dot onset to encoder onset | 0.00 / 0.00 | 0.00 / 0.00 |
| MaleCNS: encoder onset to first DNp01 spike | 0.02 / 0.04 | 0.04 / 0.06 |
| First to second DNp01 spike | 0.04 / 0.04 | 0.04 / 0.04 |
| First to third DNp01 spike | 0.06 / 0.08 | 0.08 / 0.10 |
| **Click to 3-spike point (N0-safe floor)** | **0.10 / 0.12** | **0.14 / 0.16** |
| Decoder: legacy fire (second spike) | 0.08 / 0.08 | 0.08 / 0.10 |
| Decoder: strict N2 fire | 0.10 / 0.16 | 0.16 / 0.18 |
| Decoder: **N2b fire** | **0.10 / 0.12** | **0.14 / 0.18** |
| N2b fire minus 3-spike point | 0.00 / 0.00 | 0.00 / 0.02 |
| Closest approach (theta peak) | 0.30 / 0.32 | 0.30 / 0.32 |
| Reversal | 0.32 / 0.34 | 0.32 / 0.36 |

All decoders fire before the closest approach in 60/60 trials of both classes.

**For committed strikes, N2b already fires at the N0-safe floor** (median 0 samples after
the 3-spike point; medium p95 one sample after it). The whole difference from legacy is
one DNp01 inter-spike interval (the second-to-third spike gap, 20-60 ms), which N0 does
not allow a DNp01-only decoder to skip.

### 3.2 Scripted weak and non-contact classes (descriptive, not must-escape)

| Stage (median / p95, s) | weak_approach | glancing_pass | aborted_approach |
|---|---|---|---|
| Encoder onset to first DNp01 spike | 0.28 / 0.44 | 0.16 / 0.30 | 0.16 / 0.36 |
| First to third DNp01 spike | 0.20 / 0.36 | 0.20 / 0.36 | 0.18 / 0.38 |
| Trials with 3 spikes within 200 ms of the first | 25 / 60 | 28 / 60 | 37 / 60 |

Under weak, sustained expansion (for example, encoder drive 0.10-0.25) DNp01 fires as a
**regular train at about 6-7 Hz** (one spike every 7-8 ticks; N1 trial 120). On a 200 ms
window that train is indistinguishable from the spontaneous process: at most two spikes.

### 3.3 Human sessions: recorded escape chains

Offline bout onsets: the first positive encoder drive, or first DNp01 spike, after the
last >= 200 ms gap before the escape (a coarse definition; p90 values include merged
bouts). Median / p90, seconds:

| Session, context | n | encoder onset to first DNp01 spike | first DNp01 spike to escape | encoder onset to escape |
|---|---|---|---|---|
| N2b, hover / approach (no strike) | 20 | 0.17 / 0.68 | 0.26 / 0.41 | 0.46 / 0.91 |
| N2b, strike phase | 5 | 0.46 / 1.66 | 0.22 / 0.34 | 0.68 / 1.83 |
| strict N2, hover / approach | 13 | 0.12 / 0.59 | 0.26 / 0.38 | 0.40 / 0.99 |
| strict N2, strike phase | 24 | 0.24 / 2.96 | 0.30 / 0.48 | 0.63 / 3.08 |

Most human escapes happen during hover-height chases before any click (N2b session: 20
of 25). In those chases, the MaleCNS step (encoder drive to first DNp01 spike) is slower
and more variable than in N1 committed strikes, and the decoder-evidence step (first
DNp01 spike to escape) takes about 0.26 s.

### 3.4 Motor / action latency

`Action.escape` applies the escape impulse on the same tick (`world.py`, velocity impulse;
a perched fly launches through the frozen M1.8-A `TAKEOFF_ESCAPE` path; every recorded
escape in both sessions was airborne). Time from the escape tick to 1 BL (24 units) of
displacement: median 2 ticks (40 ms; strict-N2 session,
n = 37) and 3 ticks (60 ms; N2b session, n = 24), maximum 22 / 26 ticks for low-strength
pulses. This is frozen physics (`escape_impulse`); it is not the dominant component and
is not changed.

### 3.5 Direct strikes in the human sessions

N2b session, 4 strikes with a new escape: click to escape 0.14 / 0.06 / 0.02 / 0.02 s
(median 0.04 s). Recorded neural threat onset (policy ALERT onset, in practice the first
DNp01 spike) to escape: 0.22 / 0.96 / 0.08 / 0.16 s. The click is often late relative to
the neural evidence, because the paddle is already chasing the fly at hover height. The
sluggish feel therefore comes from threat acquisition during the chase and from the
3-spike evidence requirement, not from motor execution after the click.

## 4. Slow-close case study (N2b session, episode 5)

Context that the interval alone does not show: the paddle had been chasing the airborne
fly since at least tick 570. DNp01 fired every 3-5 ticks, and N2b escaped at tick 589
(pattern HLLHH). Refractory ended at tick 609, so the interval 610-669 is a **continued
chase after an escape**.

| Tick | Event |
|---|---|
| 589 | N2b escape (SUSTAINED); refractory until 609 |
| 610 | interval start; first positive encoder drive of the interval |
| 612, 625, 638, 640, 647 | DNp01 spikes |
| 623 | closest center approach, 10.7 units (0.45 BL) |
| 663-668 | final looming run (encoder drive up to 1.39) |
| 666, 668 | DNp01 spikes |
| 669 | swatter enters `commit` (click) |
| 670 | DNp01 spike (third in 5 ticks, trace 2.134): recorded FAST escape; theta_dot already -0.77 |

Offline interval facts: center distance median 62.6 units, minimum 10.7 units; encoder
drive > 0 on 35/60 ticks with this tool's definition (any LC4 or LPLC2 channel); DNp01
mean 0.614, maximum 1.726.

**Before tick 647 the DNp01 output of this interval is four spikes (612, 625, 638, 640)
in 0.74 s.** No 200 ms window holds more than two of them, and the four span 580 ms. N0
contains both patterns (1,183 two-spike 200 ms windows; three 600 ms windows with four
spikes). Before tick 647, no DNp01-only statistic can call this interval a threat without
also firing on the documented spontaneous process. Tick 647 is the first sample with
three spikes inside 200 ms (638, 640, 647).

Candidate firing, two evaluations: **synced** (candidate takes the recorded state from
the tick-589 escape; evidence gathered during refractory counts) and **clean start**
(evidence empty and no refractory at tick 610; constructed counterfactual that isolates
the interval's own evidence).

| Candidate | N0 safe | Synced fire | Clean-start fire | vs first evidence (610) | vs closest (623) | vs reversal (670) |
|---|---|---|---|---|---|---|
| legacy 1.45 | no (91 events) | 612 | 612 | +2 | -11 | -58 |
| strict N2 | yes | none by 670 | none by 670 | later | later | later |
| N2b | yes | 670 | 670 | +60 | +47 | 0 |
| FAST OR spike count 200 ms >= 3 | yes | **647** | **647** | +37 | +24 | -23 |
| FAST OR leaky tau 100 ms >= 0.933 | yes | 610 * | 648 | +38 | +25 | -22 |
| FAST OR sum 200 ms >= 9.924 | yes | 610 * | 647 | +37 | +24 | -23 |
| FAST OR leaky tau 200 ms >= 0.693 | yes (0 % margin) | 610 * | 642 | +32 | +19 | -28 |
| spike count 500 ms >= 4 | yes | 610 * | 647 | +37 | +24 | -23 |
| sum / leaky 60-100 ms, spike count 60-160 ms | yes | 670 | 670 | +60 | +47 | 0 |

\* Fires at refractory expiry on spikes from the tick 591-605 chase that were received
during refractory: a legitimate re-escape during a continuing chase, but not a response
to the slow approach itself.

The best N0-safe DNp01-only response to this interval is at tick 642-648: 0.64-0.76 s
after the paddle arrived and about 0.4-0.5 s after it passed within half a body length.
This is 0.46 s earlier than N2b and before the reversal, but **it is still clearly late
for the observed failure** ("the paddle is on top of the fly before it reacts").

## 5. Neural-only integration candidates

Semantics (all research-only, in `tools/n3_evidence_integration.py`):

- a candidate is a `FixedEscapePolicy` subclass. Strength, side, steering, alert,
  saccades and the 0.4 s refractory are unchanged runtime code; only the trigger differs;
- the statistic is computed from the summed DNp01 trace only. It is updated on every
  sample, including during refractory, and cleared on escape and reset. It cannot fire
  during refractory. Dual candidates add FAST (trace >= 2.10), which wins the channel label;
- families: A window sum of the trace; B window mean (decision-identical to A, confirmed);
  C normalised leaky accumulator `E = aE + (1-a) trace`; D dual timescale = FAST OR A/C/E;
  E deconvolved DNp01 spike count in a window;
- windows 60 / 100 / 160 / 200 ms (plus 300 / 400 / 500 ms for spike counts, to test the
  slow-close case) and time constants 60 / 100 / 160 / 200 ms are **study values, not
  approved parameters**;
- thresholds: selection-half N0 maximum (trials 0-74) + 2 % (spike counts: maximum + 1).
  The full-N0 count is partly in-sample; the held-out half (trials 75-149, 35 min) and the
  continuous arm (10 min) are not. No fitted tail model is used.

### 5.1 False-trigger table (N0)

Every candidate below, and every other candidate in the artifact, had **0 events** on
all three arms: full N0 (210,000 ticks, 70.0 min, one-sided 95 % bound 0.043/min), held-out
half (35.0 min, bound 0.086/min) and continuous arm (10.0 min, bound 0.30/min). The
full-N0 result passes the engineering target of < 0.1/min at about 95 % confidence. The
held-out half on its own also stays below 0.1/min. Reference: legacy 91 / 54 / 16 events
(1.30/min observed).

Margins to the full-N0 maximum are thin, because these thresholds are set at the N0
envelope by construction:

| Statistic | Threshold | Full-N0 maximum | Margin |
|---|---|---|---|
| spike count 200 ms | 3 | 2 (240 ms windows already reach 3) | one window length step |
| leaky tau 100 ms | 0.933 | 0.924 | 1 % |
| leaky tau 200 ms | 0.693 | 0.693 | < 0.1 % |
| sum 200 ms | 9.924 | 9.729 | 2 % |
| sum 100 ms | 7.118 | 6.990 | 2 % |

### 5.2 Relaxing thresholds (dual FAST OR statistic, full N0)

| Statistic | Threshold | N0 events | N1 medium median | Slow-close fire (synced) |
|---|---|---|---|---|
| sum 100 ms | 7.118 / 6.762 / 6.406 / 5.694 | 0 / 18 / 34 / 53 | 0.14 / 0.14 / 0.14 / 0.12 s | 670 / 670 / 670 / 610 |
| sum 200 ms | 9.924 / 9.428 / 8.932 | 0 / 20 / 65 | 0.14 / 0.14 / 0.14 s | 610 (carry-over) |
| leaky 100 ms | 0.933 / 0.886 / 0.840 / 0.746 | 0 / 4 / 7 / 111 | 0.14 / 0.14 / 0.14 / 0.12 s | 610 (carry-over) |
| leaky 200 ms | 0.693 / 0.658 / 0.624 / 0.554 | 0 / 6 / 12 / 55 | 0.14 / 0.14 / 0.14 / 0.12 s | 610 (carry-over) |
| spike count 200 ms | 3 / 2 | 0 / 222 | 0.14 / 0.08 s | 647 / 610 |
| spike count 400 ms | 4 / 3 | 0 / 17 | 0.14 / 0.12 s | 610 (carry-over) |

Relaxing any integrated threshold below the N0 envelope produces N0 false triggers at once,
without improving committed-strike latency until N0 fails badly (tens to hundreds of
events). Four events in 70 min already gives a 95 % bound of 0.13/min, which fails the
target. The only rule that recovers legacy latency (0.08 s) is "two spikes", and that
is the documented false-trigger problem again.

### 5.3 N1 table (60 trials per class; latency median / p95 from click, s)

| Candidate | strong fired / latency | medium fired / latency | weak / glancing / aborted fired |
|---|---|---|---|
| legacy 1.45 (fails N0) | 60 / 0.08 / 0.08 | 60 / 0.08 / 0.10 | 55 / 51 / 58 |
| strict N2 | 60 / 0.10 / 0.16 | 60 / 0.16 / 0.18 | 16 / 9 / 19 |
| **N2b** | 60 / 0.10 / 0.12 | 60 / 0.14 / 0.18 | 29 / 27 / 44 |
| A sum 60 ms (pure / dual) | 60 / 0.12 / 0.12 ; 0.10 / 0.12 | 60 / 0.14 / 0.18 | 26 / 15 / 24 |
| A sum 100 ms (pure / dual) | 0.12 / 0.14 ; 0.10 / 0.12 | 0.16 / 0.18 ; 0.14 / 0.18 | 34-35 / 27 / 43 |
| A sum 160 ms (pure / dual) | 0.14 / 0.16 ; 0.10 / 0.12 | 0.16 / 0.18 ; 0.14 / 0.18 | 49 / 41 / 55 |
| A sum 200 ms (pure / dual) | 0.14 / 0.16 ; 0.10 / 0.12 | 0.16 / 0.18 ; 0.14 / 0.18 | 52 / 49 / 57 |
| B mean 60-200 ms | identical to A pure | identical to A pure | identical to A pure |
| C leaky 60 ms (pure = dual) | 0.10 / 0.12 | 0.14 / 0.16 | 49 / 44 / 56 |
| C leaky 100 ms (pure / dual) | 0.12 / 0.12 ; 0.10 / 0.12 | 0.14 / 0.16 | 55 / 49 / 57 |
| C leaky 160 ms (pure / dual) | 0.14 / 0.14 ; 0.10 / 0.12 | 0.14 / 0.18 | 58 / 52 / 57 |
| C leaky 200 ms (pure / dual) | 0.14 / 0.16 ; 0.10 / 0.12 | 0.16 / 0.18 ; 0.14 / 0.18 | 60 / 53 / 57 |
| E spikes >= 3 in 60 ms (pure) | **50** / 0.18 / 0.22 | **53** / 0.18 / 0.24 | 0 / 0 / 1 |
| E spikes >= 3 in 100 ms (pure) | 60 / 0.10 / 0.12 | 60 / 0.14 / 0.18 | 3 / 4 / 11 |
| E spikes >= 3 in 160 ms (pure = dual) | 60 / 0.10 / 0.12 | 60 / 0.14 / 0.16 | 32 / 27 / 43 |
| **D FAST OR spikes >= 3 in 200 ms** | 60 / 0.10 / 0.12 | 60 / **0.14 / 0.16** | 47 / 45 / 55 |
| E spikes >= 4 in 300 / 400 / 500 ms (dual) | 60 / 0.10 / 0.12 | 60 / 0.14 / 0.18 | 43-60 / 36-50 / 55-57 |

No N0-safe candidate improves the strong or medium **median** over N2b. The best improves
the medium p95 by 20 ms (0.18 to 0.16 s). All N0-safe candidates are bounded below by the
3-spike point of section 3.1.

### 5.4 Human-recording counterfactual (open-loop, synced per segment)

Each episode is cut at recorded escapes. A candidate takes the recorded policy's exact
state at each segment start and receives the recorded neural stream, so its first firing
in a segment is exact. After a recorded escape it did not make, the world diverges, and
such a segment only yields "not earlier than recorded". Lead = recorded escape tick minus
candidate firing tick (20 ms ticks).

| Candidate | N2b session: fired no later than recorded | earlier | median lead | strict-N2 session: fired no later / earlier / median lead | far perched approach (peak 2.0557) fires | firings without encoder drive in the preceding 6 ticks |
|---|---|---|---|---|---|---|
| legacy (fails N0) | 25/25 | 23 | 4 | 37/37 / 32 / 7 | **yes** (row 2496, at approach onset) | 2 (1 with no drive in 16 ticks: spontaneous) |
| N2b (recorded) | 25/25 | 0 | 0 | 37/37 / 25 / 1 | no | 1 |
| D FAST OR spikes 200 ms | 25/25 | 20 | **2** | 37/37 / 29 / 4 | no | 1 (refractory expiry, drive 1.6 within 16 ticks) |
| D FAST OR spikes 160 ms | 23/25 | 14 | 1 | 37/37 / 28 / 2 | no | 1 (same) |
| D FAST OR leaky 100 ms | 25/25 | 21 | 3 | 37/37 / 31 / 5 | no | 6 (all at refractory expiry) |
| D FAST OR sum 200 ms | 22/25 | 16 | 1.5 | 37/37 / 26 / 3 | no | 4 (all at refractory expiry) |
| D FAST OR sum 60 / 100 ms | 9/25, 21/25 | 0, 2 | 0 | 37/37 / 11, 25 / 0, 1 | **yes** | 1 |
| D FAST OR leaky 160 / 200 ms | 25/25 | 19-20 | 7 | 37/37 / 30 / 19 | **yes** | 12-14 |
| D FAST OR spikes >= 4 in 400 / 500 ms | 23/25 | 18 | 3 / 8 | 37/37 / 29 / 12-16 | **yes** | 12-13 |

"Firings without encoder drive in the preceding 6 ticks" are offline labels. For every
N0-safe candidate, each such firing occurred exactly at refractory expiry, 20 samples into
the segment, with LC4/LPLC2 drive present within the preceding 16 ticks. These are
re-escapes during a continuing chase, carried by spikes received during refractory, not
spontaneous firings. The only human firing with no drive in the preceding 16 ticks is
legacy (N2b session, episode 1, row 2514), a spontaneous two-spike trigger.

Strike-by-strike (N2b session, 4 strikes with a new escape): N2b fires after the click at
0.14 / 0.06 / 0.02 / 0.02 s. The spike-count 200 ms candidate fires before the click in
3 of 4, during the hover chase, and at the click in the fourth.

## 6. Distributions: does integration separate no-loom from threat better than counting?

Per-trial peak of each statistic inside the N1 labelled window, the number of trials
exceeding the N0 maximum (the earliest any zero-N0 threshold could fire), and the human
cases:

| Statistic | N0 max | strong > max | medium > max | weak / glancing / aborted > max | slow-close first > max (synced) | far perched peak (vs max) |
|---|---|---|---|---|---|---|
| instantaneous trace | 2.005 | 60 | 60 | 26 / 17 / 26 | 670 | 2.056 (above) |
| count of samples >= 1.45 in 5 | 2 | 60 | 60 | 29 / 27 / 44 | never | 2 (at) |
| sum 100 ms | 6.99 | 60 | 60 | 37 / 28 / 47 | 670 | 7.17 (above) |
| sum 200 ms | 9.73 | 60 | 60 | 53 / 49 / 57 | 610 * | 9.81 (above) |
| leaky 100 ms | 0.924 | 60 | 60 | 56 / 50 / 57 | 610 * | 0.918 (below) |
| leaky 200 ms | 0.693 | 60 | 60 | 60 / 54 / 57 | 610 * | 0.730 (above) |
| spikes 100 ms | 2 | 60 | 60 | 3 / 4 / 11 | 670 | 2 (at) |
| spikes 200 ms | 2 | 60 | 60 | 47 / 45 / 55 | **647** | 2 (at) |
| spikes 400 ms | 3 | 60 | 60 | 56 / 45 / 57 | 610 * | 4 (above) |

\* carry-over from the chase before the interval (section 4).

Answer to the main hypothesis, "N2b throws away informative subthreshold DNp01 activity":

- **Partly true for weak, sustained and hover-chase stimuli.** Over 160-200 ms windows,
  subthreshold activity carries evidence that binary >= 1.45 counting discards.
  Integration statistics exceed their N0 envelope on more weak / glancing / aborted
  trials, and in 20 of 25 recorded human escapes the spike-count 200 ms rule fires earlier
  than N2b, by a median of 40 ms.
- **False for committed strikes.** Every statistic exceeds its N0 envelope in 60/60
  strong and medium trials, but none does so earlier than the 3-spike point, and N2b
  already fires there (section 3.1).
- **Insufficient for the slow-close failure.** The subthreshold activity in the slow-close
  interval (mean 0.61, about 5.6 Hz DNp01) becomes distinguishable from N0 only at tick
  642-648, about 0.7 s after the paddle arrived.
- **Longer integration windows lose specificity.** Sum 60-100 ms, leaky 160-200 ms and
  400-500 ms spike counts exceed their N0 envelope on the far, non-contact perched approach
  (1805 units away), which N2b correctly ignores (legacy also fires on it). Leaky 160-200 ms also accumulates
  refractory carry-over (12-14 human re-escapes at refractory expiry).
- The best-separating statistic is the **spike count in about 200 ms**. That is expected,
  because trace statistics are linear filters of spike timing. It separates slightly better
  than binary counting, but not enough to change the human-visible outcome.

## 7. Is neural-only integration promising?

**No, not as a fix for the observed human failure.** The best neural-only, N0-safe
candidate found is "FAST 2.10 OR at least 3 DNp01 spikes in the last 200 ms"
(dual D / spike-count E). It would:

1. leave direct-attack latency where N2b already is. The N1 strong / medium medians stay
   0.10 / 0.14 s (legacy 0.08 / 0.08 s), with only the medium p95 improving by 20 ms. The
   sluggish direct-attack feel would not change materially;
2. fire about 40 ms earlier than N2b in hover chases (20 of 25 recorded escapes);
3. respond to the slow-close interval at tick 647. That is 0.46 s earlier than N2b and
   before the reversal, but still 0.74 s after the paddle arrived. **It does not solve the
   observed slow-approach failure.**
4. raise weak / glancing / aborted firing from 29 / 27 / 44 to 47 / 45 / 55 of 60, near
   legacy sensitivity;
5. sit at the edge of the N0 structure. 240 ms windows already contain a three-spike N0
   cluster, so the margin is one window-length step, not a comfortable gap.

It is not proposed as a runtime candidate.

The obstacle is structural, not a threshold choice:

- the spontaneous DNp01 process produces two-spike coincidences, including same-tick L+R
  pairs at trace 2.0, that are identical in DNp01 spike timing to the first two spikes of
  a genuine early response. After a spike, a DNp01-only decoder can only tell the two
  apart by waiting for more spikes;
- under weak or intermittent looming (hover chases, slow approaches), MaleCNS converts
  LC4/LPLC2 drive into a sparse, regular DNp01 train of about 5-7 Hz. Encoder activity of
  40-146 sensory spikes per tick yields 0-1 DNp01 spikes per tick. At that rate three
  spikes in 200 ms is rare, and longer windows needed for N0-safe separation cost 0.5 s
  or more;
- during a paddle hover at height 320, theta stays around 0.43 rad while theta_dot
  flips sign with lateral paddle motion. The looming channel sees brief positive bursts,
  not sustained expansion.

## 8. Sensory-encoding escalation (section 13 rule applied)

All N0-safe neural-only integration candidates remain clearly too late on the human slow
approach (best tick 642-648, about 0.7 s after arrival), and none improves the
direct-attack median. Per the escalation rule, **the study stops here and concludes that
the limitation is upstream of the decoder**:

- **MaleCNS / DNp01 response latency and rate**: the first DNp01 spike comes 20-40 ms
  after encoder onset under committed N1 strikes, but 0.12-0.46 s later (medians across
  human hover, approach and strike contexts); subsequent spikes come at 40 ms (strong) to 150 ms (weak) intervals;
- **the spontaneous DNp01 background** (0.76 Hz, with two-spike coincidences), which sets
  the N0 floor at three spikes;
- **the looming representation of a hovering or slowly moving paddle**: sign-flipping
  theta_dot at a large, nearly constant theta.

Nothing upstream was modified. Retina, LC4/LPLC2 encoding, encoder gain, looming
equations, brain noise, `escape_impulse`, caps, `room_kinematic_scale` and the recorder
schema are unchanged.

## 9. Recommendation

1. Do not commit N2b, and do not start another decoder-threshold or window iteration. The
   decoder is at the N0-safe floor for committed strikes, and the remaining slow-approach
   gap cannot be closed from DNp01 timing alone.
2. If the user approves, open a **separate research-only milestone** (suggested name
   M1.8-N4, "looming sensory transfer and threat-readout study"). Suggested questions, none
   of which should change runtime without a further explicit request:
   - characterise the LC4/LPLC2 encoder to DNp01 transfer function (DNp01 spike rate and
     first-spike latency against theta, theta_dot and encoder drive, including the 1.6
     drive saturation and the per-side population size) from existing N1 and human
     records, then with controlled fixed-fly probes;
   - characterise what a hovering or laterally moving paddle produces in the Retina
     (theta large, theta_dot sign-flipping), and whether the present looming channel is
     the only visual pathway that should respond to it. This is a modelling question,
     with any biological parameter marked A / B / C;
   - characterise, without changing, the sources of the spontaneous DNp01 two-spike
     coincidences (`noise_hz`, `noise_amp`, `tonic`, `gain`) and their effect on the N0
     floor;
   - evaluate, as a policy-observation design decision needing explicit approval, whether
     additional descending-neuron evidence already inside the neural whitelist concept
     (for example, DNp01 left/right timing structure, or DNa02) can resolve a two-spike
     event earlier without geometry.
3. Until then, the runtime stays exactly as it is in the working tree (N2b, human-rejected,
   uncommitted). The committed HEAD `76806f0` stays as it is, and B2b-iii stays paused.

## 10. Reproduction

    .venv\Scripts\python.exe tools\n3_evidence_integration.py

The command reads only the recorded inputs listed above, writes
`artifacts/m1_8_n3/evidence_integration.json`, and prints one summary line per candidate
plus the threshold sweep. It reproduces the recorded N2b and strict-N2 decisions exactly
(0 mismatches) before evaluating any candidate. Runtime: about 10 minutes.

Known limitations of this study: one tester and two sessions; open-loop human replay (exact
only until the first differing decision); bout onsets in section 3.3 use a coarse
200 ms-gap definition; selection-half thresholds make the full-N0 zero partly in-sample;
N1 classes are scripted fixed-fly probes.
