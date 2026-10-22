# M1.8-N4B1: lateralized DNp01 readout validation

Status: **research only; complete; recommendation in section 10.** No runtime,
configuration, calibration, provenance, policy-observation, Retina, encoder, MaleCNS,
noise-model, lifecycle, physics or recorder change. DNp04 and all other descending neurons
are not used. Nothing committed or pushed. The rejected N2b working tree is unchanged.

The candidate policies exist only in `tools/n4b1_lateral.py`, as a research subclass of the
runtime `FixedEscapePolicy`. They read `dnp01_left` and `dnp01_right`, which are already in
the policy observation; the whitelist is unchanged.

Tools: `tools/n4b1_lateral.py` (freeze, fresh N0, entry point) and `tools/n4b1_analysis.py`
(mechanism, evaluation, closed loop).

Artifacts (`artifacts/m1_8_n4b1/`, git-ignored; sha256):

| File | sha256 |
|---|---|
| `frozen_candidates.json` | `f6862c9f...d788` |
| `fresh_n0_chunk0..3.npz` | `7034c845...`, `58c82faa...`, `2b0887e4...`, `ea1f09c1...` |
| `mechanism.json` | `bcd5fef0...eeb6` |
| `evaluation.json` | `ae4399f4...014a` |
| `closed_loop.json` | `31eac2d7...c980` |

## 1. Exact candidate definitions (frozen before the fresh N0 data)

Per side, the DNp01 spike count of each sample is recovered from that side's own trace:
`s_t = trace_t - 0.81873 * trace_{t-1}` (flybrain.Trace: +1 per spike, exact to about
1e-7). No spike is inferred on the first observed sample of a replayed segment, because the
previous sample is unknown there. At an episode start the trace is 0 and the previous
value is set to 0.

**Spike form (primary).** A side qualifies on a sample that holds a new spike on that side
while **that same side's** previous spike is at most `gap` samples earlier, and both spikes
come after the last escape or reset. "Within W ms" means the second spike is at most W ms
after the first. A left spike followed by a right spike never counts.

| Rule | Window | Max gap (samples) |
|---|---|---|
| A | 60 ms | 3 |
| B | 80 ms | 4 (this is the N4A rule, "two spikes in a 5-sample window") |
| C | 100 ms | 5 |
| D | 120 ms | 6 |
| E | 160 ms | 8 |

**Trace form (secondary).** `max(dnp01_left, dnp01_right) >= 1 + 0.81873**gap - 1e-4`,
the smallest one-side trace two same-side spikes `gap` samples apart can produce:
A 1.5487, B 1.4492, C 1.3678, D 1.3011, E 1.2018. It is a superset of the spike form,
because older same-side spikes also add to the trace.

**Common semantics.** Strength, escape side, steering, alert state, saccades and the 0.4 s
refractory are the unchanged runtime code; only the trigger differs. No firing during
refractory. The spike form needs the qualifying spike on the current sample, so a pair
completed during refractory never fires later. Evidence is cleared on escape and reset.
No geometry, Retina or encoder value is used as a gate.

The family was written to `frozen_candidates.json` at 2026-09-24T05:18:14Z (sha256
`f6862c9f...`). Only after that were the fresh N0 data generated. Each fresh chunk records
that hash, and the generator refuses to run without the file. No candidate parameter was
changed after the fresh data existed.

## 2. N0 false-trigger validation

**Original N0**: the accepted 150 x 1400-tick arm (70.0 min), with per-side traces rebuilt
from the exact N4A re-simulation (bit-identical to the recorded totals).

**Fresh N0**: 600 new trials x 1400 ticks = 840,000 ticks = **280.0 min**, generated with
the same protocol (`tools/calibrate_escape._trial`: fixed fly, paddle settled at hover
height 30-170 units away, no loom; ROOM config of `3d41113`):

- seeds 30000-30149, 40000-40149, 50000-50149 and 60000-60149, non-overlapping with the
  original N0 (4000-4149), its loom arm (5000-5149) and N1 (6000-10059);
- a new offset stream, `default_rng(encoder_seed + 424242 + chunk)`;
- 2 Numba threads, four parallel chunks;
- encoder drive on the final settled sample: 1.1e-15.

False events are policy firings under the 0.4 s refractory. The bound is the exact Poisson
one-sided 95 % upper bound per minute. Target: < 0.1 per minute at about 95 % confidence.

| Candidate | Original 70 min: events (L/R) | Fresh 280 min: events (L/R) | Combined 350 min: events | Rate (/min) | 95 % upper (/min) |
|---|---|---|---|---|---|
| **A spike (60 ms)** | 0 | **0** | **0** | 0 | **0.0086** |
| **B spike (80 ms)** | 0 | 1 (0/1) | 1 | 0.003 | **0.0136** |
| C spike (100 ms) | 0 | 2 (0/2) | 2 | 0.006 | 0.0180 |
| D spike (120 ms) | 0 | 3 (1/2) | 3 | 0.009 | 0.0222 |
| E spike (160 ms) | 4 (3/1) | 19 (8/11) | 23 | 0.066 | 0.0931 |
| A trace (>= 1.5487) | 0 | 0 | 0 | 0 | 0.0086 |
| B trace (>= 1.4492) | 0 | 1 | 1 | 0.003 | 0.0136 |
| C trace (>= 1.3678) | 0 | 2 | 2 | 0.006 | 0.0180 |
| D trace (>= 1.3011) | 0 | 3 | 3 | 0.009 | 0.0222 |
| E trace (>= 1.2018) | 4 | 19 | 23 | 0.066 | 0.0931 |
| legacy summed 1.45 | 91 | 415 | 506 | 1.45 | 1.556 |
| strict N2 | 0 | **1** | 1 | 0.003 | 0.0136 |
| N2b | 0 | **2** | 2 | 0.006 | 0.0180 |

Findings:

- Rules A-D pass comfortably on genuinely fresh data. E passes only nominally (0.093 against
  0.1, with an observed rate of 0.066/min) and is rejected: no margin.
- **The fresh data also found false events for the earlier summed decoders**: strict N2 1
  and N2b 2. The original 70 minutes had shown 0 for both. Their 95 % bounds still pass.
- The trace form gives the same N0 counts as the spike form on every rule.

Fresh N0 structure (per-side spikes):

| Quantity | Original 70 min | Fresh 280 min |
|---|---|---|
| Rate L / R | 0.345 / 0.417 Hz | 0.325 / 0.428 Hz |
| **Same-side minimum gap, L / R** | 8 / 8 samples | **6 / 4 samples** |
| Same-side gaps <= 8, L / R | 3 / 1 | 8 / 11 |
| Same-side gaps <= 10 / <= 12 (L+R) | 13 / 30 | 55 / 108 |
| Same-tick L+R pairs (independent expectation) | 17 (12.1) | 64 (46.7) |
| L-R pairs within 4 samples (independent expectation) | 107 (108.9) | 486 (420.3) |

**The 160 ms same-side gap in the original N0 was not structural.** The fresh data contain
gaps of 4, 5 and 6 samples. Left and right are close to independent, with a mild excess of
coincidences (x1.4 at zero lag, x1.16 within 4 samples) that suggests weak common input.

## 3. Why the same DNp01 cell rarely fires twice quickly under N0

From the exact N4A instrumentation of the original N0 (3203 spontaneous spikes):

- **Reset.** A spike sets v to **0**, not to the 0.772 resting level.
- **Recovery** (voltage before step k after a spike; maximum over all spikes, which includes
  kicks and synaptic input): k = 1: 0.00, 2: 0.42, 3: 0.66, 4: 0.78, 5: 0.82, 6: 0.89,
  7: 0.92, 8: 0.99.
- **Noise.** Each sample has an independent kick with p = 0.024 and amplitude +0.22. The
  observed kick fraction during recovery is 0.024.
- **Upstream input during recovery** is small: median -0.002 V, p99.9 +0.13 V,
  maximum +0.18 V, minimum -0.23 V. 96 % of spontaneous spikes need a noise kick on DNp01
  itself (N4A).
- **Kicks needed to re-fire k samples after a reset, with no synaptic input and the most
  favourable placement:**

| k (samples) | 1-3 | 4 | 5-7 | 8-12 |
|---|---|---|---|---|
| kicks needed | impossible | 4 | 3 | 2 |

- Pure-noise probability of at least 2 kicks within k samples: 0.0017 (3), 0.0033 (4),
  0.0055 (5), 0.0081 (6), 0.0146 (8). At least 3 kicks is about C(k,3) x 1.4e-5.
- **Monte Carlo.** The noise kicks after each observed spike were resampled 20,000 times,
  keeping the recorded synaptic input. Expected same-side re-fires:

| gap <= | 3 | 4 | 5 | 6 | 7 | 8 | 10 |
|---|---|---|---|---|---|---|---|
| expected per 70 min | 0.0006 | 0.012 | 0.097 | 0.41 | 1.24 | 3.05 | 11.4 |
| expected per 280 min | 0.002 | 0.05 | 0.39 | 1.67 | 5.0 | 12.3 | 45.8 |
| observed, original 70 min | 0 | 0 | 0 | 0 | 0 | 4 | 13 |
| observed, fresh 280 min | 0 | 1 | 2 | 3 | - | 19 | 55 |

- The three short fresh gaps were re-simulated with instrumentation. The trials reproduce
  bit-exactly at 2 threads, and each is a multi-kick coincidence during recovery:
  - chunk 0 trial 60 (right, gap 4): kicks at +1, +3 and +4 samples, plus about 0.02 V
    synaptic input per sample;
  - chunk 2 trial 59 (right, gap 5): kicks at +1, +4 and +5, plus +0.10 V from DNp70 on
    the last sample;
  - chunk 0 trial 127 (left, gap 6): kicks at +4, +5 and +6.

Conclusion: the rarity is structurally implied. Reset-to-zero means a re-fire within 4-7
samples needs 3-4 coincident noise kicks, because upstream input is too small to substitute.
But it is a **probability, not a gap**. The original "never closer than 160 ms" was partly
luck: in 70 minutes about 3.1 pairs within 8 samples and 1.2 within 7 were expected; 4 (all
exactly 8 samples apart) and 0 were seen.
Short windows are the robust part (gap <= 3: 0.002 expected in 280 min, 0 observed). The
observed fresh counts sit at or somewhat above the Monte Carlo expectation, so the model
slightly underestimates; the empirical counts are the acceptance evidence.

**This is a simulator property (LIF reset to 0 plus independent Bernoulli noise; Class C).
It is not claimed as a biological refractory property.** The noise model was not changed.

## 4. N1 replay (300 trials, per-side spikes from the exact re-simulation)

Latency is median / p95 in seconds from the click.

| Candidate | strong fired | strong latency | medium fired | medium latency | weak / glancing / aborted fired (of 60) |
|---|---|---|---|---|---|
| legacy summed 1.45 | 60 | 0.08 / 0.08 | 60 | 0.08 / 0.10 | 55 / 51 / 58 |
| strict N2 | 60 | 0.10 / 0.16 | 60 | 0.16 / 0.18 | 16 / 9 / 19 |
| N2b | 60 | 0.10 / 0.12 | 60 | 0.14 / 0.18 | 29 / 27 / 44 |
| **A spike (60 ms)** | 60 | **0.08 / 0.08** | 60 | **0.10 / 0.10** | **14 / 16 / 39** |
| **B spike (80 ms) = N4A lateralized** | 60 | 0.08 / 0.08 | 60 | 0.10 / 0.10 | 39 / 39 / 57 |
| C spike (100 ms) | 60 | 0.08 / 0.08 | 60 | 0.10 / 0.10 | 57 / 53 / 59 |
| D spike (120 ms) | 60 | 0.08 / 0.08 | 60 | 0.10 / 0.10 | 60 / 57 / 59 |
| E spike (160 ms) | 60 | 0.08 / 0.08 | 60 | 0.09 / 0.10 | 60 / 59 / 59 |
| A / B / C / D trace | 60 | 0.08 / 0.08 | 60 | 0.10 / 0.10 | 35/36/57, 51/46/58, 58/54/59, 60/58/59 |

- **Trigger spike pairs**: strong 57/60 at gap 2 and 3/60 at gap 1; medium 56/60 at gap 2
  and 4/60 at gap 3. Rule A already captures every committed strike, so the longer windows
  add only weak and non-contact sensitivity and N0 risk.
- **Trigger side** (rule A): strong L 31 / R 29, medium R 36 / L 24. It matches the
  stimulus side (mean azimuth sign in the window) in 56/60 strong trials (the four
  mismatches start 49 units away, almost overhead) and 60/60 medium trials.
- Strong-strike timing equals legacy. Medium is one sample later than legacy at the median
  (0.10 against 0.08 s) and equal at p95 (0.10). Against N2b: 20 ms faster (strong) and
  40 ms faster (medium) at the median, and 40 / 80 ms faster at p95.

## 5. Both human sessions (open-loop, synced per segment as in N3)

The recorded decoders reproduce exactly (0 mismatches in both sessions). The recorded
per-side DNp01 values feed each candidate, which is resynced to the recorded policy state
after every recorded escape, so a candidate's first firing in each segment is exact.

| Candidate | N2b session: recorded escapes met no later / earlier / median lead | hover (20) | strike phase (5) | strict-N2 session: no later / median lead | hover (13) | strike phase (24) |
|---|---|---|---|---|---|---|
| legacy | 25 / 23 / 0.08 s | 20 | 5 | 37 / 0.14 s | 13 | 24 |
| N2b | 25 / 0 / 0 (recorded) | 20 | 5 | 37 / 0.02 s | 13 | 24 |
| **A spike** | 21 / - / 0.02 s | **16** | 5 | 30 / 0.10 s | **6** | 24 |
| **B spike** | 23 / 20 / 0.06 s | **18** | 5 | 30 / 0.17 s | **6** | 24 |
| C spike | 25 / - / 0.08 s | 20 | 5 | 31 / 0.26 s | 7 | 24 |
| D spike | 25 / - / 0.16 s | 20 | 5 | 32 / 0.25 s | 8 | 24 |

- **Strike-phase escapes**: every lateral rule meets or precedes all 29, typically earlier
  (for example B: 0.21 s median lead over the strict-N2 recording).
- **Hover chases: a sensitivity regression.** Rules A and B fire no later than the recorded
  escape in only 6 of 13 strict-N2 hover bouts, and 16-18 of 20 N2b bouts. The missed bouts
  are driven by alternating left/right DNp01 spikes, which the summed rules count and a
  same-side rule cannot. Whether and when A/B would fire there is post-divergence and is
  not known exactly.

Direct strikes, N2b session (4 with a new escape). Latency from the click (negative = fired
during the hover chase before the click), with the qualifying same-side spike rows:

| Candidate | strike 1 | strike 2 | strike 3 | strike 4 |
|---|---|---|---|---|
| N2b (recorded) | 0.14 | 0.06 | 0.02 | 0.02 |
| A | 0.10 (L 2268, 2270) | -0.10 (L 57, 60) | -0.02 (L 666, 668) | 0.00 (R 720, 723) |
| B | 0.10 (L 2268, 2270) | -0.10 (L 57, 60) | -0.02 (L 666, 668) | -0.06 (R 716, 720) |

Strict-N2 session (26 strikes with a new escape): the recorded strict N2 fired after the
click in 24 at a median of 0.14 s. Rule A fires before the click in 15 and after it in 11
(median 0.10 s). Rule B: 16 before, 10 after (median 0.08 s). None missed.

**Far perched non-contact approach** (strict-N2 session, episode 1, rows 2434-2528, about
1805 units away):

- the summed-trace events there are bilateral: R 2494 + L 2496 (summed 1.67; legacy fires
  at 2496), and a same-tick L+R pair at 2513, where both cells received a noise kick
  (summed 2.0557);
- the only same-side neighbours are L 2496 and L 2513, 17 samples apart;
- **every lateral rule A-E rejects the approach.** None fires in the bout; their first
  firing in that segment is at row 3586-3602, a later threat. Legacy fires at 2496.
  Strict N2 and N2b do not fire.

**Voluntary takeoff** (N2b session, 18.44 s): no candidate fires within 1 s before to
0.5 s after the takeoff. Kept separate from threat response.

## 6. Slow-close episode-5 case (limitation)

N3/N4A correction preserved: N2b escaped at tick 589 and its refractory period ended at
tick 609.

| Candidate | Chase before 589 (segment from tick 522) | Slow-close, synced | Slow-close, clean start at 610 |
|---|---|---|---|
| N2b (recorded) | 589 | 670 | 670 |
| A / B / C / D spike | **576** (13 samples earlier) | 668 (L 666, 668) | 668 |
| E spike | 576 | 647 (R 640, 647) | 647 |
| legacy | 576 | 612 | 612 |

**The lateral readout does not solve the slow-close failure.** Tick 668 is 45 samples
after the closest center approach (tick 623), only 2 samples earlier than N2b. DNp01's
sparse slow-close spikes alternate sides (612 L, 625 R, 638 L, 640 R, 647 R, 666 L,
668 L). N4A located this limitation in MaleCNS transfer to DNp01; it is the N4B2 question.

## 7. Closed-loop ROOM (research-only policies in tools/)

The `tools/n2_closed_loop.py` scenarios run through the full game path (pointer, physical
swatter, Retina, encoder, MaleCNS, policy, lifecycle, physics). They include the corrected
zero-loom perched fixture (projector and physical swatter reset after placement; every
hold is verified zero-loom). Natural arm: one decoder per episode. Runtime code is
untouched.

| Scenario | legacy | N2b | A | B | C | D |
|---|---|---|---|---|---|---|
| Perched committed strike (20): escapes before click | 4 | 0 | 0 | 0 | 0 | 0 |
| perched at click / neural takeoff after click | 16 / 16 | 20 / 20 | 20 / 20 | 20 / 20 | 20 / 20 | 20 / 20 |
| latency from click, median / p95 (s) | 0.08 / 0.16 | 0.10 / 0.12 | **0.08 / 0.08** | **0.08 / 0.08** | 0.08 / 0.08 | 0.08 / 0.08 |
| M1.8-A no-click perched threat | escape takeoff | escape takeoff | escape takeoff | escape takeoff | escape takeoff | escape takeoff |
| Airborne committed strike (12): escape after click | 11 | 10 | 9 | **12** | 11 | 10 |
| latency median / p95 (s) | 0.08 / 0.22 | 0.11 / 0.18 | 0.08 / 0.15 | 0.08 / 0.15 | 0.10 / 0.20 | 0.08 / 0.18 |
| escapes during the pre-click hover chase | 27 | 16 | 16 | 17 | 21 | 26 |
| Hover approach, no click (9 runs): escapes | 28 | 12 | **6** | 17 | 20 | 27 |
| No player, 3 x 9000 ticks (9 min): escapes | 20 | 1 | **0** | **0** | 1 | 1 |

- Perched committed strike: the lateral rules restore legacy timing, and tighten the p95
  (0.08 against legacy 0.16), without legacy's pre-click false escapes. All perched
  strikes are still hit under every decoder: pre-existing strike physics, not a decoder
  effect (as documented in N2b).
- Airborne strikes: when a rule has no post-click escape, it escaped during the pre-click
  chase and was refractory or already clear.
- No-player escapes of C and D (seed 101) were checked directly. They had real weak
  expansion: encoder drive 0.16 and 0.09, theta_dot 0.20 and 0.13, from the fly flying
  toward the parked paddle. That is the same situation as the known N2b no-player FAST
  event, not a zero-loom trigger.
- Hover approach: A is the least sensitive of all decoders (6 escapes against 12 for N2b),
  which points the wrong way for the human slow-approach complaint. B is more sensitive
  than N2b (17).

## 8. Central decision

**Can a same-side DNp01 readout restore direct-strike response to approximately legacy
timing while retaining the accepted no-loom false-trigger constraint on genuinely fresh
data? Yes.**

- Timing:
  - N1 strong: 0.08 / 0.08 s (legacy 0.08 / 0.08);
  - N1 medium: 0.10 / 0.10 (legacy 0.08 / 0.10);
  - closed-loop perched strikes: 0.08 / 0.08 (legacy 0.08 / 0.16);
  - closed-loop airborne strikes: 0.08 median.

  This holds for every rule A-D.
- N0 on fresh, non-overlapping seeds under a frozen family: A 0 events in 280 min
  (combined 350 min: upper bound 0.0086/min); B 1 event (0.0136/min). Both are an order of
  magnitude below the 0.1/min target.
- The far perched bilateral-noise case (summed 2.0557) is rejected by every lateral rule.

Limits, stated plainly:

1. It does **not** fix the slow-close / slow-approach failure (tick 668 against N2b's 670).
2. On its own it **loses hover-chase sensitivity** where DNp01 evidence alternates sides
   (A/B meet only 6 of 13 strict-session hover escapes, against 13 of 13 for N2b).
3. The same-side gap is a Class C simulator property with a measurable, nonzero
   probability. It is not a hard limit, and it is sensitive to the noise model and reset
   rule, both unchanged here.
4. One tester, two sessions, open-loop human replay; scripted N1 and closed-loop scenarios.

## 9. Candidate ranking within the frozen family

The ranking is by the criteria stated in the task: legacy-level committed-strike timing,
then fresh-N0 safety, then specificity.

1. **A (60 ms)**: legacy strike timing, 0 fresh N0 events, the most specific (weak 14/60).
   It is also the least sensitive to hover approaches (closed-loop 6 escapes; human hover
   6/13 and 16/20).
2. **B (80 ms, the N4A rule)**: the same strike timing, 1 fresh N0 event, more hover
   sensitivity than N2b in closed loop (17 escapes) and in the N2b session (18/20).
3. C / D: the same timing, more weak and non-contact firing and more N0 events.
4. E: rejected (0.066/min observed, nominal pass only).

The fresh-N0 ordering (A 0 < B 1 < C 2 < D 3 < E 19) matches the Monte Carlo ordering
predicted from the original data. No parameter was moved.

## 10. Recommendation

**Recommend a future N4B1-runtime candidate milestone**, to be implemented only on explicit
request, for a same-side DNp01 trigger from this frozen family: **A as primary and B as the
alternative**. The human test should decide between them on hover-chase feel. The runtime
milestone should also settle, and then freshly validate:

- **Whether to keep a summed path alongside the lateral trigger** (for example "A OR N2b"),
  so that alternating-side hover evidence is not lost. The false-trigger rate of a union is
  at most the sum of its parts (fresh: A 0 + N2b 2 in 280 min). It is a new candidate and
  needs its own frozen fresh-N0 validation. It was not tested here, to avoid tuning.
- Recorder and provenance: the trigger channel should stay out of the frozen recorder
  diagnostics, as for N2/N2b.
- Human acceptance on direct strikes, which is the complaint this addresses.

**Keep N4B2 separate.** The slow-approach insensitivity is not solved by any lateral DNp01
rule. N4A found that DNp04 marks it early (tick 613), but DNp04 would expand the
whitelist, came from an exploratory multiple comparison, fires on nearly all weak N1
approaches, and needs its own research decision. Nothing about DNp04 was used or changed
here.

## 11. Reproduction

    .venv\Scripts\python.exe tools\n4b1_lateral.py freeze
    .venv\Scripts\python.exe tools\n4b1_lateral.py fresh-n0 --chunk 0 --trials 150   (chunks 0-3, NUMBA_NUM_THREADS=2, in parallel; about 43 min)
    .venv\Scripts\python.exe tools\n4b1_lateral.py mechanism
    .venv\Scripts\python.exe tools\n4b1_lateral.py evaluate      (about 15 min)
    .venv\Scripts\python.exe tools\n4b1_lateral.py closed-loop   (about 20 min)

The mechanism and evaluate modes also read the N4A re-simulations in `artifacts/m1_8_n4/`
(`tools/n4_resimulate.py`).
