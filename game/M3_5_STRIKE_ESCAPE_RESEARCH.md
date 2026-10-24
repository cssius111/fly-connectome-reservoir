# M3.5: escapes from strikes under v27 and the M3.3 and M3.4 candidates (read-only research)

Status: **research note, 2026-10-24.** No runtime code, configuration, record or frozen system
changed.

**Why.** M3.4 (`results/game/M3_4_RETINOTOPIC_DRIVE.md`) found that a fly deciding by angular
size never escapes a hovering paddle. The N4B6 threat matrix has no strike, so whether such a fly
escapes the descending paddle was unknown. The M3.4 report named this as the first next step.

**Method.** All measurements are in `tools/m3_5_strike_escapes.py`; raw data are in
`artifacts/m3_5/strikes/` (git-ignored). The results are exploratory.
- **Protocol.** The fixed-fly strike of `tools/calibrate_escape.py`, with the runtime decoder
  live:
  - collisions, fly motion and wander are disabled;
  - the paddle settles in hover, then one strike is launched and observed for 60 ticks.
- **Positions.** The paddle hovers overhead, or 40, 80 or 150 units away at the fly's front,
  right, rear or left. The paddle radius is 144 units.
- **Seeds.** 950001-950024, 24 per position.
- **Arms.** Each uses its own committed record:
  - v27, the working ROOM configuration;
  - v29, the M3.3 candidate `9830757`;
  - v30, the M3.4 candidate `10e12f6`.

## 1. The strike as the fly sees it

Overhead strike, seed 950001. One tick is 20 ms. The click is tick 0, and contact (ACTIVE_CONTACT)
starts at tick 10 in every trial.

| Tick | 0 | 2 | 4 | 6 | 7 | 8 | 9 | 10 (contact) | 12 | 14 |
|---|---|---|---|---|---|---|---|---|---|---|
| Phase | commit | commit | fast swing | fast swing | fast swing | fast swing | fast swing | active contact | active contact | active contact |
| Height | 315 | 288 | 270 | 223 | 180 | 137 | 103 | 90 | 67 | 31 |
| θ | 33° | 35° | 40° | 44° | 52° | 66° | 85° | 103° | 114° | 131° |
| θ̇ (°/s) | 0 | 97 | 113 | 146 | 422 | 703 | 935 | 900 | 145 | 441 |

- **Commit phase.** The image grows slowly at first: 33-40° over the 100 ms commit phase.
- **Fast swing.** Most of the growth comes in the last 100 ms before contact, at 400-900°/s, like
  the end of a fast loom.
- **The size rule's timing.** A fly that decides at about 55° (the real fly's E2 threshold, and
  v30's 56.5°) reaches that size near tick 7-8. With a decision delay of a few tens of
  milliseconds it decides at or just before contact.

## 2. Results

Escape fraction, fraction decided before contact, and the median decision tick and image size:

| Position | v27 | v29 (M3.3) | v30 (M3.4) |
|---|---|---|---|
| overhead | 1.00, 1.00, tick 4, 40° | 1.00, 0.75, 8, 66° | 0.83, **0.00**, 13, 122° |
| front 40 | 1.00, 1.00, 4, 39° | 0.88, 0.12, 52, 32° | 1.00, **0.00**, 12, 116° |
| right 40 | 1.00, 1.00, 4, 40° | 0.88, 0.00, 42, 32° | 1.00, **0.00**, 12, 112° |
| rear 40 | 1.00, 1.00, 4, 39° | 0.96, 0.12, 45, 31° | 0.29, **0.00**, 14, 112° |
| left 40 | 1.00, 1.00, 4, 40° | 0.96, 0.54, 7, 41° | 1.00, **0.00**, 13, 112° |
| front 80 | 1.00, 1.00, 5, 37° | 0.83, 0.58, 8, 39° | 0.96, **0.00**, 13, 92° |
| right 80 | 1.00, 1.00, 4, 39° | 0.62, 0.33, 7, 32° | 1.00, 0.12, 12, 102° |
| rear 80 | 1.00, 1.00, 5, 37° | 0.83, 0.58, 8, 39° | **0.00** |
| left 80 | 1.00, 1.00, 4, 39° | 1.00, 0.71, 7, 45° | 1.00, 0.04, 12, 93° |
| front 150 | 1.00, 1.00, 7, 40° | 0.92, 0.75, 9, 59° | 0.21, **0.00**, 11, 68° |
| right 150 | 1.00, 1.00, 4, 36° | 0.92, 0.92, 6, 38° | 1.00, 0.08, 11, 78° |
| rear 150 | 1.00, 1.00, 7, 40° | 0.92, 0.75, 9, 59° | **0.00** |
| left 150 | 1.00, 1.00, 4, 36° | 1.00, 0.54, 7, 44° | 1.00, 0.08, 11, 72° |

What each arm does:
- **v27.**
  - It decides every strike at tick 4-7, at 36-40°, well before contact.
  - Its velocity-coded LPLC2 term fires on the slow commit-phase expansion. That is the same early
    decision M3.0 scored as an E2 gap (threshold 18.6°).
- **v29 (M3.3).**
  - It escapes most strikes, but only 0-92 % before contact, depending on the position.
  - At the 40-unit front, right and rear positions the median decision comes after the strike
    (ticks 42-52), from the paddle settling afterwards.
- **v30 (M3.4).**
  - It decides 0-12 % of strikes before contact, at tick 11-14, when the image is already
    92-122°.
  - Rear strikes are rarely escaped, because of the rear blind spot. The same holds for the
    frontal 150-unit strike, whose image stays small (68°).
  - Since v30 also escapes no hovering approach, a v30 fly in the game would be hit by almost
    every strike.

## 3. What this means

- **The strike is at the edge for a real fly too.** A size rule like the real fly's (about 54°
  plus a short delay) decides at about the moment of contact. The game's 200 ms strike is fast
  even for a real fly.
- **v30 decides too late even by its own law.** Its E2 fit (threshold 56.5°, delay -43 ms)
  predicts a decision at about tick 9-10. The measured ticks are 11-14.
- **The same late decision underlies the M3.4 failures.** Fast looms decide late in V1
  (l/v 10-20 ms after collision), V2 fails at l/v 40 ms, and V8a at l/v 10 ms. The latency of
  the decision to fast expansion is therefore the main defect to study next.
- **The left-right balance is a smaller part of it.** V8a's side difference appears only where
  this late decision is marginal.

## 4. Proposed order of the next steps

The M3.4 report listed four next steps. These results change their order:

1. **Fast-expansion decision latency.** Read-only research into why v30 decides fast looms and
   strikes late, split into its parts:
   - drive onset;
   - recruitment of covered cells, including near the zenith, where both eyes cover the disk
     only partly;
   - the network delay from LPLC2/LC4 spikes to a DNp01 doublet.
   This also covers V2 and V8a.
2. **Left-right balance by DNp01 input weight**, if it is still needed after step 1.
3. **E4**, reading DNp02 against DNp11 for the escape direction.
4. **Rear blind spot.** Whether the posterior blind spot matches the real eye's (about 50°;
   Zhao et al. 2025) for strikes from behind. This is descriptive.

## 5. Where the latency comes from

`tools/m3_5_latency.py` records, tick by tick, the encoder drive, the LPLC2/LC4 spikes and the
DNp01 spikes. It runs on strikes (overhead and right 80, seeds 950001-950012) and on protocol-E
looms (right, l/v 20 and 40 ms, seeds 960001-960012). It also measures a network latency floor:
a constant drive to a fraction of the right side's encoder cells, seeds 960101-960124.

**The network floor.** First right DNp01 doublet under a constant drive to the right encoder
cells (91 LPLC2 and 55 LC4):

| Share of the cells driven | 0.4 V | 0.8 V |
|---|---|---|
| 25 % | none | none |
| 50 % | 1 of 24, tick 11 | 24 of 24, tick 3 |
| 100 % | 24 of 24, tick 3 | 24 of 24, tick 2 |

- **The delay is short.** Once enough cells are driven, the network forms a doublet within 2-3
  ticks (40-60 ms).
- **But only with enough cells.** About half of one side's encoder cells must fire strongly. A
  quarter never suffices, whatever the voltage.

**v30 on an overhead strike** (median of 12 seeds; cells driven and cells at the 0.8 V cap,
both eyes together):

| Tick | 4 | 6 | 7 | 8 | 9 | 10 (contact) | 12 |
|---|---|---|---|---|---|---|---|
| θ | 40° | 44° | 52° | 67° | 85° | 103° | 114° |
| LPLC2 driven / capped | 46 / 22 | 48 / 24 | 52 / 30 | 69 / 37 | 83 / 54 | 96 / 63 | 105 / 67 |
| LC4 driven / capped | 26 / 4 | 28 / 9 | 31 / 13 | 40 / 23 | 48 / 30 | 55 / 38 | 56 / 37 |

- **The disk is split between the eyes.** An overhead disk falls on both eyes, and each DNp01
  receives only its own side's LPLC2 and LC4 (research note section 4). At the real fly's
  decision size (52-67°, ticks 7-8) each side therefore has well under a quarter of its 146
  encoder cells at the cap.
- **When the decision comes.** The doublet comes only once recruitment approaches half a side:
  ticks 10-14, at or after contact.
- **The lateral strike.** The right 80 strike falls mostly on one eye and decides a little
  earlier (ticks 9-13).
- **Looms.** On the right-azimuth looms v30 decides at rows 14-16 for l/v 20 ms (collision at
  row 17) and at rows 24-27 for l/v 40 ms (collision at row 28).

**v29 for comparison.** The M3.3 encoder drives all 91 LPLC2 and 55 LC4 cells of the side given
by the azimuth's sign, at up to 0.74 V.
- Every LPLC2 cell fires from the first tick of the strike, so the doublet comes earlier: ticks
  6-8 overhead and 2-8 at right 80.
- The cost is that it decides on recruitment it does not see.

**The likely cause in v30: receptive fields of dendritic size.**
- **What M3.4 used.** Each cell is driven through its dendritic columns only, seen through the
  7.7° photoreceptor acceptance. The LPLC2 r95 of 21.9° gives a field about 44° across.
- **What was measured.** Klapoetke et al. 2017 give 60° as the upper bound of an individual
  LPLC2's functional receptive field. The research note (section 1) attributes the difference to
  the spatial spread of the T4/T5 inputs, which M3.4 does not model.
- **Why it matters.** A disk of a given size recruits fewer cells through dendritic fields than
  through functional ones, and DNp01 needs about half a side.

## 6. Candidate next steps

Each needs the user's decision and, for any runtime change, a preregistration first.

1. **Functional receptive fields.**
   - Extend the LPLC2 field by the spatial spread of its T4/T5 inputs, so that the field matches
     the measured functional size (sourced from T4/T5 receptive-field measurements, with
     Klapoetke's 60° as the bound).
   - Recalibrate the one scale, and check strikes, V1-V8 and the threat matrix.
   - First, an exploration to see whether functional fields bring strike decisions before
     contact.
2. **Bilateral recruitment.** Whether an overhead disk, split between the eyes, should still
   drive each giant fiber as strongly as a lateral one. This needs literature on GF responses
   to overhead looms, and gap-junction coupling between the two GFs, before any design.
3. The remaining earlier steps:
   - left-right balance by DNp01 weight;
   - E4;
   - the rear blind spot.
