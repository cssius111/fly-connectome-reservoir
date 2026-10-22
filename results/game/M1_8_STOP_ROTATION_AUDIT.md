# M1.8 stop-rotation audit: the paddle transient in recorded human play

Status: **recorded on 2026-10-22; diagnostic only.** No runtime code, configuration,
calibration, swatter controller, tilt geometry, decoder or recorder schema changed. On
2026-10-22 the user decided to record this result, to keep the M1.7.1 swatter frozen and to run
no further human tests for it.

## 1. Question

N4B6 (`game/M1_8_N4B6_CONTROLLED_SLOW_APPROACH.md`, section 4) found a transient at constant
range:
- when the paddle stops after sideways motion, the approach controller rotates it by about 90
  degrees while it corrects its overshoot;
- through the tilt term this gives about 0.35 rad/s of apparent expansion;
- N4B1C responded in 17 of 48 orbit-control trials.

N4B6 left open how often real play produces this transient and whether escapes follow it.
`AGENTS.md` keeps M1.7.1 frozen unless recorded evidence demonstrates a real defect.

## 2. Mechanism

In the approach phase, `game/physical_swatter.py` steers the paddle orientation towards the
heading of its velocity whenever the paddle moves faster than 20 units/s. The turn is limited
to 6 rad/s and 24 rad/s².

The heading is a full 360-degree direction. The visual tilt term in `game/world.py` uses
`abs(sin(bearing - orientation))`, so it is symmetric under a turn of 180 degrees. Two cases
follow:

- **Turn.** A change in the direction of motion rotates the paddle axis to a new line. This is
  the accepted M1.7.1 design, in which the paddle aligns with its motion.
- **Reversal spin.** A reversal of the motion makes the controller turn the paddle by up to 180
  degrees, although its axis line ends where it started. During the spin the fly sees the
  projected paddle change size at constant range.

## 3. Method

The tool is `tools/stop_rotation_audit.py`, as of `065810f`. The user ran it on the local
Windows checkout at `c6d854c` on 2026-10-22, where it is identical apart from its docstring.
Its docstring gives the full definitions.

- **Sample.** Row t's Retina is projected from row t-1's state. A sample at row t therefore
  counts only when its source rows t-2 and t-1 are in the approach (hover) phase with a live,
  airborne fly.
- **Size-driven episode.** A run of samples whose apparent-size-driven expansion is at least
  0.2 rad/s, while the range-driven part stays below half of it.
- **Transient.** A size-driven episode during which the paddle axis (modulo 180 degrees) turns
  by at least 60 degrees. The turn is counted from 0.3 s before the episode to its end.
- **Reversal spin.** A transient whose paddle turns by at least 120 degrees but ends within 30
  degrees of its starting axis.
- **Evaluation.** An episode is evaluated only when no policy escape onset falls between 1 s
  before it and 0.06 s after it. An escape onset 0.06-0.8 s after its first sample counts as a
  possible response.
- **Baseline.** Hover samples every 0.5 s, at least 1 s from any size-driven episode, binned by
  horizontal distance (< 200, 200-400, 400-600 and >= 600 units). The excess for a group is the
  sum over distance bins of its observed escapes minus its evaluated count times the baseline
  share. The baseline includes range-driven approaches, so the excess is conservative.

Validation:
- **Orbit control.** A scripted orbit-then-hold control in the style of N4B6 F3 (config 26,
  seed 255, fly held still) gives one transient 0.38 s after each of the 4 stops, at 300 units
  and 0.35 rad/s, with an escape after 1 of the 4 stops. N4B6 had responses in 17 of 48 trials.
- **Synthetic recordings.** In `test_game_stop_rotation_audit.py` they check the sample
  alignment, the reversal label and the session selection.

## 4. Data

- **Accepted runtime** (elevation-aware tilt with the N4B1C decoder, `config_version` 17 and
  later): 2 human sessions with 5.4 min of hover.
  - `20261021T054015.211928Z-9e97d496` (config 19, the B3a playtest);
  - `20261022T010423.651486Z-bbe82503` (config 26, the M1.8-B completion playtest).
- **Earlier runtimes:** 15 human sessions from 2026-09-20 to 2026-09-24 (`config_version` 7-16),
  with 18.9 min of hover.
- **Skipped:**
  - 13 evaluation-mode recordings, which are scripted;
  - a second copy of every session directory, recognized by its identical input stream.
- **Not read:** no M2.4-B recording.

## 5. Results

| | Accepted runtime | Earlier runtimes |
|---|---|---|
| Hover | 5.4 min (2 sessions) | 18.9 min (15 sessions) |
| Axis flips (>= 60 degrees in 0.3 s) | 98 (18.2/min) | 693 (36.7/min) |
| Size-driven episodes | 36 | 453 |
| Stop-rotation transients | 25 (4.65/min) | 196 (10.38/min) |
| of which reversal spins | 12 (2.23/min) | 57 (3.02/min) |
| Transient peak size-driven expansion, median / max | 0.34 / 0.61 rad/s | 0.54 / 3.75 rad/s |
| Transients followed by an escape (evaluated) | 4 / 10 (40 %) | 41 / 69 (59 %) |
| Reversal spins followed by an escape (evaluated) | 2 / 5 | 10 / 20 |
| Size-driven episodes without a swing, followed by an escape | 1 / 2 | 38 / 74 (51 %) |
| Baseline hover samples followed by an escape | 7 / 559 (1.3 %) | 148 / 1339 (11 %) |
| Escapes added by transients over the baseline | 3.4 (0.63/min; expected 0.60, P(>= 4) = 0.003) | 31.0 (1.64/min; expected 10.0, P(>= 41) < 1e-12) |
| Escapes added by reversal spins | 1.9 (0.35/min; expected 0.10, P(>= 2) = 0.005) | 7.3 (0.39/min; expected 2.7, P(>= 10) = 0.0005) |

By horizontal distance (escapes / evaluated):

| Group | < 200 | 200-400 | 400-600 | >= 600 |
|---|---|---|---|---|
| Accepted: transients | 1/1 | 2/3 | 0/1 | 1/5 |
| Accepted: reversal spins | 0/0 | 1/1 | 0/1 | 1/3 |
| Accepted: baseline hover | 4/14 | 2/23 | 1/20 | 0/502 |
| Earlier: transients | 9/11 | 13/14 | 6/9 | 13/35 |
| Earlier: reversal spins | 4/4 | 2/2 | 1/2 | 3/12 |
| Earlier: baseline hover | 2/14 | 6/32 | 18/70 | 122/1223 |

Per session on the accepted runtime:
- **Config 19:** 21 transients (11 reversal spins); 9 evaluated, 3 followed by an escape.
- **Config 26:** 4 transients (1 reversal spin); 1 evaluated, followed by an escape.

The probabilities are Poisson tails, with the baseline-expected count treated as known. They
are not a preregistered test.

## 6. Interpretation

1. **Frequency.**
   - Real play produces the transient often: about 4.7 times per hover minute on the accepted
     runtime, half of them reversal spins.
   - The earlier runtimes had about twice the rate. They used the bearing-only tilt term, which
     also turns bearing changes near overhead into apparent size, and the play differed.
2. **Escapes.**
   - Evaluated transients are followed by an escape far more often than hover samples at the same
     distance.
   - On the earlier runtimes, size-driven episodes without an axis swing were followed by an
     escape at a similar share (51 % against 59 %). The response therefore follows the
     apparent-size expansion itself, and the axis swing is its main source during hover (25 of
     36 episodes on the accepted runtime).
3. **Classification.**
   - Under the N4B4 metric split, these responses are category C: apparent size and tilt
     geometry with a real Retina drive. They are not category A neural false escapes, because the
     decoder responds to a stimulus the fly really sees.
   - **The reversal spin is a modelling defect of the controller.** The target heading is taken
     over 360 degrees, but the paddle's visual effect is symmetric under 180 degrees. A reversal
     of the hand therefore spins the paddle although its final axis line is unchanged. It adds
     about 0.35 escapes per hover minute on the accepted runtime and 0.39 on the earlier ones.
   - Turn transients follow from the accepted M1.7.1 design, and this audit does not classify
     them as a defect.
4. **Limitations.**
   - The accepted runtime contributes only 10 evaluated transients (5 of them reversal spins)
     from one participant.
   - An escape within 0.8 s can also follow a lunge that begins after the reversal; the audit
     does not separate the two.
   - Most transients happen during a chase and are not evaluated, because an escape began in the
     second before them.

## 7. Decision

On 2026-10-22 the user chose to record this result and to keep the M1.7.1 swatter frozen,
without further human testing.

The candidate fix is not implemented. In the approach phase, the controller would steer towards
the velocity heading or its opposite, whichever is nearer, so that a reversal no longer spins
the paddle. The strike direction would stay on the 360-degree heading, using the last velocity
heading when the paddle is slow.

Applying the fix would change:
- the frozen M1.7.1 controller;
- the approach_sanity reproduction of the M1.7.1 acceptance recording;
- the game's difficulty.

It requires a subsequent explicit user request and a human acceptance playtest.

## 8. Erratum (2026-10-22, after review)

Sections 1-7 are kept as first recorded. Review found two problems. Neither changes a
conclusion.

1. **Reversal-spin probabilities in section 5.**
   - The expected counts were backed out of the rounded excess (0.10 and 2.7). The expected
     count is the sum over distance bins of the evaluated count times the unrounded baseline
     share.
   - Computed that way, the expectations are 0.137 on the accepted runtime and 2.658 on the
     earlier runtimes.
   - The tails are therefore **P(>= 2) = 0.009** (not 0.005) and **P(>= 10) = 0.0004** (not
     0.0005).
   - The transient rows are unaffected: expected 0.597 with P(>= 4) = 0.003, and expected 10.002
     with P < 1e-12.
   - Since `c9b200d` the tool prints the observed and expected count behind each excess.
2. **Baseline exclusion in the tool used for section 3.**
   - A size-driven episode within 1 s of a restart could also exclude hover samples of the
     neighbouring episode. That is at most four baseline samples per restart, against 559 and
     1339 baseline samples.
   - Since `c9b200d` the exclusion stays inside each episode, and
     `test_game_stop_rotation_audit.py` covers it.
   - The run in section 5 used the earlier version.
