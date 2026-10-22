# M3.0: biological fidelity scorecard, results

Status: **measurement complete on 2026-10-22.** The protocols and bands were preregistered in
`game/M3_0_FIDELITY_SCORECARD_DESIGN.md` (`ef9a12f`) before any measurement, and the tool is
`tools/m3_0_scorecard.py` (`66f7344`). Comparators: `game/M3_0_ESCAPE_EVIDENCE.md` (X rows) and
`game/M1_8_EVIDENCE.md` (E rows). Model: `main` @ `032e7cc` (ROOM `config_version` 27). Raw
data are in `artifacts/m3_0/` (git-ignored). No runtime file changed.

## 1. Gap table

| Metric | Model | Real fly | Class | Kind of gap |
|---|---|---|---|---|
| E2 Angular size at escape (timing law) | threshold 18.6° from the fit; 14-32° per l/v | 54° (SD 5°), X15/X16 | **gap** | the decision follows expansion onset, not an angular-size threshold |
| E4 Direction, threat in front | -66.7° (forward-left) | backward, 180° (X04) | **gap** | structural: the encoder uses only the side |
| E4 Direction, threat behind | -66.7° (forward-left) | forward, 0° (X04) | **gap** | structural, same cause |
| E5 Short and long escape modes | one escape action, no wing raise | two modes; the short-mode share falls with l/v (X21-X22) | **not represented** | structural |
| S1 Spontaneous saccade rate | 0.34 per s | 1.37 per s (E12) | **gap** | parametric: hand-written flight generator |
| S2 Intersaccadic interval, mean | 2.65 s (median 1.90) | 0.82 s (E11) | **gap** | parametric, same generator |
| E1 Escape probability | 1.00 (384 of 384 lateral trials) | 0.82 (X13) | partial | parametric: no trial-to-trial misses |
| S3 Saccade amplitude and duration | median 57° in 80 ms | about 90° in under 100 ms (E10) | partial | parametric |
| E4 Direction, threat to the side | -66.7° right threat, +65.6° left threat | halfway between away and forward, ∓45° (X05) | match | |
| C1 Flight speed (context, not scored) | 7.6 body lengths per s | about 107 (E02) | - | frozen gameplay scale, 14 times slower |

## 2. Escape (protocol E)

- **Runs.** 768 trials: l/v of 10, 20, 40 and 80 ms × four azimuths × 48 brain-noise seeds, with
  a fixed fly and a synthetic looming disk from 10° through the Retina.
- **E6, spontaneous escapes.** There were none in the 768 pre-stimulus seconds.

| l/v | Expansion time | Escaped | Mean size at escape | Time before collision, mean (min-max) | Latency after onset |
|---|---|---|---|---|---|
| 10 ms | 0.114 s | 96 / 96 | 32.0° | 0.036 s (0.034-0.074) | 0.079 s |
| 20 ms | 0.229 s | 96 / 96 | 16.1° | 0.143 s (0.109-0.169) | 0.086 s |
| 40 ms | 0.457 s | 96 / 96 | 14.5° | 0.321 s (0.197-0.357) | 0.136 s |
| 80 ms | 0.914 s | 96 / 96 | 19.5° | 0.476 s (0.354-0.714) | 0.438 s |

Lateral azimuths, left and right pooled.

- **E1. Escape probability.** The model escapes in all 384 lateral trials that E1 counts (and in
  the front and rear trials too): 1.00 against 0.82 (X13), which is **partial**. Brain noise changes the escape tick, but never produces a miss.
- **E2. Timing.** The fit `t_before = alpha * (l/v) + delta` gives alpha = 6.1 and
  delta = +14.7 ms. The real fly gives alpha = 2.0 and delta = -6 ms (X16). The implied threshold
  is 18.6° against 54° (X15), a **gap**.
  - For slow looms the model escapes as soon as the expansion is clear, at 14-20°.
  - For the fastest loom its pipeline delay of about 80 ms after onset dominates, so the disk
    has reached 32° by then.
  - A real fly waits for about 54°, and its neural delay to takeoff is 30-46 ms (X24).
- **E3. Escape before collision.** At l/v 10 ms the model escapes before collision in 100 % of
  trials. The real fly does so in 30 % of short-mode and 6 % of long-mode takeoffs at r/v 8 ms
  (X25). This follows from the early decision.
- **E4. Direction.**
  - Lateral threats: the model jumps forward and away, about 66° from straight ahead. That
    matches X05.
  - Front and rear threats: the model jumps exactly as for a right-side threat, a **gap** for
    both. The front, right and rear runs are identical in every trial, tick and direction (all
    four l/v values). The Retina carries the full bearing, but the encoder uses only the sign
    of its azimuth, and azimuth 0 counts as right.
- **E5. Modes.** **Not represented.** The model has one escape action, with no wing-raise phase
  and no slower, prepared escape.

## 3. Saccades (protocol S)

- **Runs.** Seeds 9501-9520, each 180 s of no-player ROOM flight: 2951 airborne seconds, after
  excluding perching and the 0.5 s after escapes.
- **Events.** 1002 spontaneous events above 450°/s were detected; 23 threat-evoked events were
  excluded.

| Metric | Model | Real fly | Class |
|---|---|---|---|
| S1 Rate | 0.34 per s | 1.37 per s (E12) | gap |
| S2 Interval | mean 2.65 s, median 1.90 s (947 intervals) | 0.81-0.83 s (E11) | gap |
| S3 Amplitude, duration | median 57°, median 80 ms | about 90° in under 100 ms (E10) | partial |
| C1 Speed (context) | 7.6 body lengths per s | about 107 (E02) | - |

The model fly turns about four times less often than a real fly, and its turns are smaller.
These saccades come from the hand-written flight generator, not from the connectome. The
M1.8-R0 evidence lock already classed its parameters as "B, unfitted".

## 4. Limits of the comparison

- **Tick.** The model's tick is 20 ms. The fastest loom lasts about six ticks, and saccade
  durations are resolved in steps of 20 ms.
- **Takeoff.** The model takes off at its decision, with no motor delay. A real takeoff follows
  wing raise by about 7-11 ms (X18). This makes the model look slightly earlier, not later.
- **Stimulus.** The synthetic disk has no elevation, and the lab disks were at 45-50°.
- **Assay dependence of the probability.** The real escape probability is 82-96 % for a single
  loom on a platform, but much lower for repeated looms (X27, X28).
- **Speed filter.** E12 kept flight above 5 cm/s. ROOM flight is always below that, so no filter
  was applied.
- **Missing sources.** Takeoff probability and short-mode share per l/v (von Reyn et al. 2017;
  Williamson et al. 2018) were not accessible. The direction comparator is qualitative.

## 5. What the gaps point to

The gaps fall into three groups by where the fix would have to go.

1. **The escape decision (E2, E1, E3).** The model escapes far too early, at about 15-30°
   instead of about 54°, and always.
   - This is the part the connectome actually drives: the encoder, MaleCNS, DNp01 and the
     decoder.
   - Closing it needs the escape to depend on angular size as well as on expansion, as the
     giant fiber's integration of LC4 and LPLC2 inputs does in the literature.
   - Every element involved is frozen: the encoder mapping and the accepted N4B1C decoder.
2. **What the fly can see and do (E4, E5).** These gaps are structural.
   - Front and back cannot be told apart, because the encoder uses only the side of the
     stimulus.
   - There is no prepared (long-mode) escape.
   - The fixes are a retinotopic encoder, which can use the bearing the Retina already
     carries, and more descending-neuron pathways. Both are large changes.
3. **Spontaneous flight (S1, S2, S3, C1).** These gaps are parametric, in the hand-written flight
   generator.
   - The saccade rate and amplitude could be set from E10-E12 without touching the connectome.
   - The flight speed is the frozen gameplay scale.

Which group to address first is the user's choice. Each group needs its own preregistered
milestone, and explicit approval wherever it touches a frozen system.
