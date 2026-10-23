# M3.3: fixing both M3.2 failures (read-only research)

Status: **research note, 2026-10-22.** No runtime code, configuration, record or frozen system
changed.

M3.2 failed on two counts (`results/game/M3_2_ESCAPE_FEATURE_ROLES.md`):
- the implied E2 threshold stayed a gap at 30°;
- no-player escapes rose tenfold.

The user asked to fix both together. Every variant below exists only inside
`tools/m3_3_research.py`.

The results are **exploratory**:
- 6 decoder rules × 6 encoder variants were compared on seeds 700001-700024 and flight
  seeds 9701-9720;
- any design chosen from them must be preregistered and validated on seeds none of this used.

Raw data: `artifacts/m3_3/` (git-ignored).

## 1. Summary

- **The single-spike rule is ruled out.**
  - DNp01 fires spontaneously at 0.30-0.45 Hz per side, so a single-spike trigger would escape
    0.75 times per second at rest.
  - At rest, two spikes on one side are never closer than 6 ticks.
  - So a same-side doublet within 40 ms only occurs under strong feedforward drive. It is the
    model's counterpart of a suprathreshold giant-fiber event.
- **The decision is a hazard process.**
  - Under the M3.2 encoder the LPLC2 drive passes 0.26 V at about 21° for every l/v.
  - The escape then follows 3-11 ticks later, at 41° (l/v 80 ms) up to after collision
    (10 ms).
  - Slow looms sit longer at intermediate drive and fire earlier in size.
- **The summed decoder paths cause both failures.**
  - The N2b paths that N4B1C keeps alongside LATERAL are FAST (a summed trace of 2.1) and
    SUSTAINED (3 of 5 samples at 1.45).
  - They integrate slow, bilateral DNp01 activity.
  - They fired 63 of the 65 inappropriate M3.2 no-player escapes, and they make the loom
    decision early.
- **One decoder rule fixes both under the M3.2 encoder.**
  - The rule: a same-side DNp01 doublet within 40 ms, without the summed paths.
  - No-player false escapes fall from 1.48 per minute to 0 in replayed flight.
  - The loom decision moves to the peak of the LPLC2 size term (42°), with the
    size-threshold-plus-delay pattern.
  - The escape size is independent of the start size.
  - The cost is an escape probability below 1 at some l/v.
- **Rejected:**
  - the legacy encoder with a strict rule, which gives the right timing slope only as a
    velocity threshold;
  - a looming-motion gate on LPLC2, which destabilises timing.

## 2. Evidence

- **LPLC2 and slow expansion.** LPLC2 responds strongly to slow looms: 10°/s edge speed, or
  20°/s expansion (Klapoetke et al. 2017: "highly responsive to dark looming across all
  measured speeds"). No data exist below that.
  - A motion gate cannot be set from data, and it does not explain the M3.2 false escapes:
    those had a median expansion rate of 2.4°/s.
  - The paper also states that LPLC2 neurons "require looming motion to be active" (Ache et al.
    2019).
- **One spike triggers the escape.** The giant fiber "fires a single action potential to
  activate motor neurons" (Ache, Namiki et al. 2019, *Nat Neurosci*, doi:10.1038/s41593-019-0413-4).
  The GF spike falls near the peak of its looming response (Ache et al. 2019, *Curr Biol*,
  M3.1 Y11).
- **Behavioural state matters.**
  - "Landing responses were only evoked in flight, whereas escape-related leg movements were
    only evoked in non-flying flies."
  - Escape DNs "may ... be decoupled from visual inputs during flight" (Ache, Namiki et al.
    2019).
  - This is suggestive, not measured, and is not used below.

## 3. Measurements

### 3.1 DNp01 at rest

Static 10° disk, 48 seeds × 9 s, v27:

| | Left | Right |
|---|---|---|
| Spontaneous spikes per s | 0.30 | 0.45 |
| Shortest interval between spikes | 17 ticks | 6 ticks |

### 3.2 Offline decoder rules on the loom protocol

M3.0 stimulus from 10° to collision, right azimuth, seeds 700001-700024. Each cell is the
escape fraction / median size at escape, with the fitted implied threshold.

| Encoder | Decoder | 10 ms | 20 ms | 40 ms | 80 ms | 160 ms | Threshold |
|---|---|---|---|---|---|---|---|
| legacy | N4B1C (runtime) | 1.00 / 33° | 1.00 / 15° | 1.00 / 14° | 1.00 / 20° | 1.00 / 23° | 22.6° |
| legacy | doublet 20 ms | 0.96 / 70° | 1.00 / 45° | 1.00 / 33° | 1.00 / 38° | 1.00 / 55° | 53.5° |
| M3.2, 0.28 | N4B1C (runtime) | 0.96 / 180° | 0.83 / 134° | 0.96 / 55° | 1.00 / 45° | 1.00 / 30° | 26.0° |
| M3.2, 0.28 | doublet 40 ms | 0.83 / 180° | 0.58 / 134° | 0.46 / 70° | 0.96 / 55° | 0.92 / 45° | 38.0° |
| M3.2, 0.36 | doublet 40 ms | 0.75 / 180° | 1.00 / 134° | 0.96 / 45° | 1.00 / 38° | 1.00 / 33° | 29.7° |
| M3.2, 0.28 + gate 10°/s | doublet 40 ms | 0.79 / 180° | 0.29 / 134° | 0.42 / 94° | 0.04 / 70° | 0.04 / 55° | (few escapes) |

"Doublet 40 ms" means two same-side DNp01 spikes at most 2 ticks apart. "Doublet 20 ms" means
two on consecutive ticks. Both use a 0.4 s refractory period and no summed paths.

### 3.3 Start-size invariance

Median size at escape for starts of 5°, 10° and 20°:

| Encoder, decoder | l/v 40 ms | 80 ms | 160 ms |
|---|---|---|---|
| legacy, N4B1C | 15 / 14 / 31° | 20 / 20 / 24° | 23 / 23 / 26° |
| legacy, doublet 20 ms | 33 / 33 / 35° | 38 / 38 / 41° | 53 / 55 / 55° |
| M3.2 0.28, N4B1C | 63 / 55 / 35° | 37 / 45 / 45° | 29 / 30 / 33° |
| M3.2 0.28, doublet 40 ms | 71 / 70 / 62° | 55 / 55 / 55° | 45 / 45 / 45° |
| M3.2 0.28 + gate, doublet 40 ms | 71 / 94 / 62° | 72 / 70 / 112° | 104 / 55 / 87° |

- **Legacy, doublet 20 ms.** Start-size invariant, but the size at escape grows with l/v
  (33° to 55°).
  - That is a velocity threshold, near the legacy encoder's 2 rad/s saturation.
  - Its slope of 2.0 is a coincidence of this l/v range.
- **M3.2 0.28, doublet 40 ms.** Start-size invariant, and the size falls with l/v (70°, 55°,
  45°).
  - That is a fixed decision size near 42° plus a fixed delay, which is what a size threshold
    produces.

### 3.4 False alarms

| Condition | N4B1C (runtime) | Any same-side doublet rule |
|---|---|---|
| Rest, 16 min | 1 | 0 |
| Replayed no-player flight, legacy encoder, 60 min | 0.033 per min | 0 |
| Replayed no-player flight, M3.2 encoder, 60 min | 1.48 per min | 0 |
| Replayed no-player flight, M3.2 encoder with the 10°/s gate, 60 min | 0.10 per min | 0 |

The flight replay feeds the Retina recorded in v27 no-player flight (seeds 9701-9720) into each
variant, open-loop. It approximates the closed loop, since the path would change after a
variant's first different action.
- **Legacy check.** The legacy N4B1C rate matches the closed-loop v27 baseline of M3.2 V6b
  (0.04 per min).
- **M3.2 encoder.** The open-loop M3.2 rate is higher than its closed-loop 0.42 per minute.
- **The gate.** It lowers the runtime decoder's false alarms but does not remove them. The
  doublet rule needs no gate.

## 4. Candidate design for M3.3

- **Encoder.** The M3.2 `ache2019_v1` mode, unchanged:
  - LPLC2 by angular size and LC4 by velocity, with the published constants;
  - no motion gate.
- **Decoder.** A new decoder kind beside the existing ones: escape when one DNp01 side produces
  two spikes at most 40 ms apart.
  - The summed FAST and SUSTAINED paths are not used.
  - The refractory period, alert turns and steering are unchanged.
  - Rationale: the single giant-fiber spike that triggers escape is not usable in a model whose
    DNp01 fires spontaneously. The same-side 40 ms doublet is the strongest single-side event
    that noise never produces at rest.
- **Scale.** Recalibrated by the M3.2 procedure (GF-model peak targets, at least 50 % escapes at
  every l/v) with the new decoder. The exploration suggests a value between 0.28 and 0.36.
- **Validation, on unused seeds:**
  - the M3.0 scorecard;
  - start-size invariance;
  - non-looming disks;
  - closed-loop paired no-player flight;
  - the N4B6 threat matrix;
  - a human playtest.
- **Expected outcomes, stated so they can be checked:**
  - **E2.** It should move into the partial band. At 0.28 the exploration gives 38°; a scale
    that makes every l/v admissible gives a somewhat lower value.
  - **E1.** It should fall below 1, towards the real 0.82.
  - **No-player escapes.** They should return to the v27 level or below.

**Consequences and authorization:**
- **What the decoder change does.** It removes the N2b summed paths, which N4B1C kept so that a
  paddle hovering on alternating sides still triggers escapes. A hovering, non-expanding paddle
  would then rarely cause an escape. That is realistic, but it changes the accepted gameplay.
- **Frozen systems.** The decoder is part of the frozen baseline policy (`AGENTS.md`); changing
  it needs the user's explicit authorization. The 20 ms tick and the brain noise stay
  unchanged.

## 5. Reproduction

```
python tools/m3_3_research.py loom
python tools/m3_3_research.py rest
python tools/m3_3_research.py startsize
python tools/m3_3_research.py flight-record
python tools/m3_3_research.py flight-replay
python tools/m3_3_research.py analyze
```
