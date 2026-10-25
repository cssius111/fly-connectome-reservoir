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

## 7. Functional receptive fields: measured, and not the cause

`tools/m3_5_functional_fields.py` measures how far the columnar inputs of LPLC2 and LC4 spread
across the eye in MaleCNS itself. Spread here means the angular spread of each input cell's own
input synapses; sigma is the per-axis width of an equivalent isotropic Gaussian.
- **Sample.** 30 right-side cells per type, numpy seed 950900.
- **Kernel.** Weighted by each type's input share.

| Input type | T4a-d | T5a-d | Tm5f | Tm20 | T2 | TmY3 | Tm4 | Tm3 | Tm2 |
|---|---|---|---|---|---|---|---|---|---|
| sigma, median | 3.4-3.6° | 3.4-3.8° | 4.3° | 2.2° | 2.9° | 3.7° | 2.8° | 2.5° | 1.3° |
| Columns per cell | 12-14 | 13-15 | 20 | 8 | 14 | 17 | 11 | 8 | 6 |

| | Kernel sigma | r95, dendritic | + optics (7.7° FWHM) | + input spread (functional) |
|---|---|---|---|---|
| LPLC2 | 3.57° | 21.7° | 23.2° | 24.6° (about 49° across) |
| LC4 | 2.85° | 19.1° | 21.1° | 22.1° (about 44° across) |

- **The fields grow little.** Blurred by their inputs' measured spread, the fields grow by only
  about 3° in radius. LPLC2 stays below Klapoetke's 60° upper bound.
- **Recruitment barely changes.** At the calibrated scale 71.3, these are the encoder cells per
  side driven to the cap, LPLC2 + LC4, with the M3.4 blur and the functional blur:

| Disk | 55° | 85° |
|---|---|---|
| overhead (el 85°) | 25 / 27 per side | 43 / 47 per side |
| right, elevation 74° | 35 / 37 (right) | 58 / 59 (right) |
| right, on the horizon | 73 / 76 (right) | 103 / 106 (right) |

  A doublet needs about half of a side's 146 encoder cells (section 5).
- **Lateral looms.** On the horizon a lateral disk reaches that at about 55°. This is why V1's
  lateral E2 matches the real fly.
- **Overhead disks.** They cannot reach it at any size. Few LPLC2/LC4 fields view the zenith
  (15 LPLC2 per side have centres above 40° elevation), and the disk is split between the eyes.
- **The hypothesis of section 5 is refuted.** Functional fields are not the missing factor.

## 8. Each giant fiber sees both eyes in the real fly, and barely in the model

### 8.1 Literature

- **The contralateral eye drives each giant fiber as strongly as the ipsilateral one.**
  - **Source.** Jang, Goodman, Ausborn and von Reyn 2023 (J Exp Biol 226:jeb244790).
  - **Method.** Whole-cell recordings from the GF in tethered flies.
  - **Stimuli.** Looms at -45°, 0° and +45° azimuth, all at 0° elevation, r/v 10-80 ms,
    expanding from 10° to 63°.
  - **Magnitude.** "We found the GF peak response magnitude was not significantly different
    across stimulus locations".
  - **Latency.** "we found no significant difference in the peak latency" (n = 10 flies).
    Their text states no mV or ms values.
- **The signal comes from the contralateral eye itself.**
  - **Test.** They painted the contralateral eye (5 painted flies, 10 controls).
  - **Result.** The occlusion "eliminated the GF response for all but the final expansion" of
    the contralateral loom.
  - **Conclusion.** "the GF receives contralateral information through an unidentified
    commissural pathway".
- **The pathway is probably not the GF's electrical coupling.** The authors argue that input over
  the GF's electrical synapses "would be attenuated and delayed". Contralateral responses are
  neither attenuated nor delayed, so they conclude that "contralateral visual information is not
  arriving through this connection".
- **Two looms do not add up.**
  - **Test.** Simultaneous looms at ±45°.
  - **Sum.** The response was "significantly less than the sum of the individual responses
    across all r/v values".
  - **Single loom.** Dual-loom responses were "not significantly different from a single loom
    response".
  - **Reading.** The GF may "quickly reach an upper bound on its response".
- **Electrical coupling exists, but it is not quantified.**
  - **Dye coupling.** The GF dye-couples to the giant commissural interneurons (GCIs) at about
    55 h of metamorphosis, and the shakB2 mutation prevents it (Phelan et al. 1996, J Neurosci
    16:1101-1113). Dye injected into one GF labels both (Kennedy and Broadie 2018, eNeuro
    5:ENEURO.0346-18.2018).
  - **GCI identity.** Virtual Fly Brain lists GCI as a synonym of AMMC-A1, and Jang et al. 2023
    write "giant commissural interneurons (aka AMMC-A1)".
  - **Synchrony.** "The two GFs are electrically coupled together and thus thought to fire
    synchronously" (Blagburn 2019, bioRxiv 10.1101/796185, citing Phelan et al. 1996). This is an
    inference: no paired GF recording was found.
  - **Strength.** No coupling coefficient was found.
- **No overhead loom has been tested.**
  - **Elevations used.** The studies found used looms at 0° (Jang et al. 2023) and at 45°
    (FlyPEZ, Dombrovski et al. 2023). Card and Dickinson 2008 (Curr Biol 18:1300-1307) used a disk
    falling along a 50° downward trajectory.
  - **Dorsal activation.** Dorsal LPLC2 drive the GF more strongly than ventral LPLC2
    (Dombrovski et al. 2023, ATP activation). MaleCNS carries the same gradient (M3.4 research
    note, section 4).

### 8.2 The frozen network

`tools/m3_5_bilateral.py` measures what reaches each DNp01 from each eye (raw data in
`artifacts/m3_5/bilateral/`).

**Weights** (`paths`; normalised weights of `data/weights.npz`):

| Onto DNp01 | from the ipsilateral eye's LPLC2 + LC4 | from the contralateral eye's |
|---|---|---|
| left | 0.311 direct, 0.043 two-hop | 0 direct, 0.0049 two-hop |
| right | 0.299 direct, 0.035 two-hop | 0 direct, 0.0038 two-hop |

The contralateral two-hop weight runs through three cell types, each fed by its own side's eye
and projecting to the opposite DNp01:

| Carrier | Cells per side | Input from its own eye | Onto the opposite DNp01 | Onto its own DNp01 |
|---|---|---|---|---|
| PVLP151 | 2 | LPLC2 0.16-0.18, LC4 0.04-0.05 | 0.016 | 0.0004-0.0008 |
| AMMC-A1 (the GCI) | 3 | LC4 0.22-0.25 | 0.003-0.004 | 0.0004-0.0005 |
| DNp11 | 1 | LC4 0.17 | 0.0052 (right to left), 0.0000 (left to right) | 0.0002-0.0003 |

- **GFC1-4.** The four GF-coupled clusters of Kennedy and Broadie 2018 receive no LPLC2 or LC4
  input in the network.
- **The GCI.** The GCI, which the literature reports electrically coupled to the GF, is thus a
  visual cell in MaleCNS: it is driven by its own eye's LC4 and projects to the opposite DNp01.
  The chemical weight is small. Its electrical coupling, absent from the network, has no
  measured strength.

**Response** (`drive`): a constant 0.8 V on 25, 50 or 100 % of one side's encoder cells. The
input is the extra synaptic input to each DNp01 per tick, mean of 12 seeds over 6 ticks.

| Driven share | 25 % | 50 % | 100 % |
|---|---|---|---|
| ipsilateral DNp01 input (left, right driven) | +0.22, +0.22 V | +0.49, +0.48 V | +0.87, +0.94 V |
| contralateral DNp01 input | +0.003, +0.010 V | +0.010, +0.016 V | +0.010, +0.023 V |
| contralateral / ipsilateral | 0.01-0.05 | 0.02-0.03 | 0.01-0.02 |
| contralateral DNp01 spikes in 72 ticks | 1, 1 | 1, 1 | 1, 1 |

- **Scale.** The gap from rest (0.772 V) to threshold (1.0 V) is 0.23 V. The ipsilateral input
  crosses it within one or two ticks; the contralateral input never fires the cell.
- **The gap to the real fly.** The model's giant fiber responds to the contralateral eye at
  1-5 % of its ipsilateral response. The real GF responds to both alike. This is a fidelity gap
  in its own right, independent of the strike geometry. It is not in the M3.0 scorecard.

### 8.3 What bilateral pooling would do for overhead strikes

v30 on the overhead strike (medians of 12 seeds, from `tools/m3_5_latency.py`). The table gives
the encoder cells at the 0.8 V cap, on the side with more capped cells and on both eyes pooled:

| Tick | 6 | 7 | 8 | 9 | 10 (contact) | 11 | 12 |
|---|---|---|---|---|---|---|---|
| θ | 44° | 52° | 66° | 85° | 103° | 111° | 114° |
| the side with more | 18 | 22 | 31 | 46 | 55 | 59 | 60 |
| both eyes pooled | 33 | 43 | 60 | 84 | 101 | 104 | 104 |

- **The upper bound.** If each giant fiber received both eyes alike, the recruitment v30's
  doublets now need (55-60 capped cells, reached at ticks 10-12) would come about two ticks
  earlier. Linear pooling is an upper bound, since two looms do not add up in the real GF.
- **Still not before contact.** With the network's 2-3-tick floor (section 5), the decision
  would come at about tick 10-11: at contact instead of 2-4 ticks after it.
- **The strike itself is the main limit.** The overhead image passes 55-65° only 2-3 ticks before
  contact (section 1). A size-rule fly with a 40-60 ms delay decides at about contact, as
  section 3 noted for the real fly.

## 9. What this leaves

- **Lateral and frontal looms on the horizon.** The retinotopic drive gives a real-fly size rule
  (E2).
- **Bilateral pooling: a measured gap, sourced but not quantified.**
  - **The gap.** Each real GF responds to the contralateral eye like the ipsilateral one; the
    model's does at 1-5 %.
  - **The likely substrate.** The frozen network contains chemical carriers for it (PVLP151,
    AMMC-A1/GCI, DNp11), but they are weak.
  - **What closing it takes.** It would mean strengthening those carriers or adding an
    electrical term, so it changes the frozen connectome's effective weights. That needs the
    user's explicit authorization.
  - **A target.** Jang et al. 2023 give one: contralateral and ipsilateral responses with no
    significant difference. Their text gives no magnitudes, so the tolerance would have to come
    from their figures.
- **Its effect on overhead strikes is small.** Even full pooling would bring the decision only
  to about contact. Overhead strikes stay at the edge, for two reasons:
  - the eye's sparse zenith coverage, which is real anatomy;
  - the strike's fast final swing.
- **Not supported by the literature.** A GF-GF electrical coupling as the route for visual input:
  Jang et al. 2023 argue against it.

## 10. Left-right balance: the count rule is the cause

The user chose on 2026-10-24 to leave the bilateral gap open and to work through the remaining
list. `tools/m3_5_side_balance.py` compares four encoder cell selections under the v30
candidate (scale 71.3 V/mV, calibrated for the first). Raw data are in
`artifacts/m3_5/side_balance/`.
- **`count`.** The v30 encoder: `RetinalEncoder` drives min(left, right) cells per type, chosen
  with encoder_seed 20260917.
- **`all`.** Every LPLC2 and LC4 cell, each through its own receptive field.
- **`count_weighted`.** The count subsets, with each side's drive of a type multiplied by the mean
  of the two sides' DNp01 weight over this side's DNp01 weight.
- **`all_weighted`.** Every cell, with the same factor.

**What the count rule drops.** MaleCNS has 94 left and 91 right LPLC2, and 71 left and 55 right
LC4. The count rule therefore drops 3 left LPLC2 and 16 left LC4 cells. The dropped LC4 cells
are not spread over the eye:
- 12 of the 16 have field centres at |azimuth| 60-110°;
- 7 of those 12 lie within 20° of the horizon, where the V1 lateral loom sits.

**Weights onto DNp01** (`weights`):

| Rule | LPLC2 left / right | LC4 left / right |
|---|---|---|
| count | 0.125 / 0.138 | 0.144 / 0.161 |
| all | 0.128 / 0.138 | 0.183 / 0.161 |

**Reach** (`reach`): the coverage-weighted DNp01 weight of mirrored disks, 20-90° across.
Right / left:

| Position | count | all | count_weighted | all_weighted |
|---|---|---|---|---|
| V1 lateral (az 90°, el 0°) | 1.24-1.50 | 0.94-0.96 | 1.12-1.34 | 0.98-1.00 |
| calibration (az 50°, el 11°) | 1.12-1.16 | 0.96-1.00 | 1.00-1.04 | 0.99-1.03 |
| front-lateral (az 30°, el 0°) | 1.04-1.11 | 0.91-0.96 | 0.93-0.99 | 0.94-1.00 |
| rear-lateral (az 130°, el 0°) | 1.32-1.58 | 0.99-1.11 | 1.18-1.41 | 1.04-1.18 |

**Network trials** (`trials`): protocol-E looms at ±90° on the horizon, seeds 970001-970024. Each
cell gives escapes of 24, median time before collision and median size at escape:

| l/v | right, count = all | left, count | left, all | left, count_weighted | left, all_weighted |
|---|---|---|---|---|---|
| 10 ms | 22, -6 ms, 180° | **14**, -26 ms, 180° | 24, -6 ms, 180° | 16, -26 ms, 180° | 24, -6 ms, 180° |
| 20 ms | 24, -11 ms, 180° | 24, -11 ms, 180° | 24, +9 ms, 134° | 24, -21 ms, 180° | 24, +9 ms, 134° |
| 80 ms | 24, +134 ms, 62° | 24, **+94 ms, 81°** | 24, +134 ms, 62° | 24, +84 ms, 87° | 24, +134 ms, 62° |

- **The right side is identical under `count` and `all`.** The count subsets already contain
  every right cell, and no right trial differs. The calibration stimulus sits on the right, so
  `all` leaves the calibrated scale and V3 valid.
- **`count` reproduces the V8a failure on fresh seeds.** At l/v 10 ms it gives right 22 against
  left 14, a difference of 0.33. At l/v 80 ms left escapes come 40 ms later and 19° larger.
- **`all` removes it.**
  - At l/v 10 ms it gives 22 against 24.
  - At l/v 80 ms the two sides have the same median time and size.
  - The one residual: at l/v 20 ms the left decides earlier than the right.
- **Balancing the total weight does not help.** The count rule's deficit is positional: it is
  missing lateral fields, not total weight. `all_weighted` changes a few trials and no median
  over `all`.
- **The network asymmetry seen earlier does not show here.** The M3.4 research note (section 6)
  found that the left DNp01 forms doublets under weaker LPLC2-only drive. Under `all`, this
  shows no side difference on the horizon looms.

## 11. The rear blind spot is the real eye's, and the real-fly rear data are elevated

`tools/m3_5_rear_field.py`; raw data in `artifacts/m3_5/rear_field/`.

- **The eye.**
  - **Model.** Both eyes use the Zhao et al. 2025 micro-CT eye map, whose equator row reaches
    151° (M3.4 research note, section 2).
  - **Real eye.** The paper reports a field reaching about 155° behind.
  - **So:** the posterior blind region, about ±155-180°, is the real eye's.
- **The real-fly rear comparators are elevated threats.**
  - **Card and Dickinson 2008** used "a 14-cm-diameter black disk that fell toward the animals
    along a 50° downward trajectory". Its azimuth relative to the fly varied because the flies
    settled in random orientations. "Ninety-six percent of the flies responded to the
    descending disk by jumping."
  - **FlyPEZ looms** used an "elevation of 45° and azimuth of 0°, 90° or 180° ± 22.5°"
    (Dombrovski et al. 2023).
  - **M3.0.** Its protocol E puts the rear loom on the horizon straight behind the fly, inside
    the blind region.

**Coverage** (`coverage`, `count`): the DNp01 weight a disk reaches, both sides summed:

| Disk centre | 40° | 60° | 90° |
|---|---|---|---|
| az 90°, el 0° | 0.031 | 0.062 | 0.122 |
| az 150°, el 0° | 0.010 | 0.019 | 0.041 |
| az 180°, el 0° | 0.000 | 0.003 | 0.017 |
| az 90°, el 50° | 0.029 | 0.063 | 0.137 |
| az 150°, el 50° | 0.016 | 0.035 | 0.079 |
| az 180°, el 50° | 0.009 | 0.024 | 0.069 |

**Network trials** (`trials`, seeds 970101-970124). Escapes, escapes before collision, and the
median time before collision:

| Position | l/v 40, count | l/v 40, all | l/v 80, count | l/v 80, all |
|---|---|---|---|---|
| lateral, el 0° | 24, 23, +37 ms | 24, 23, +37 ms | 24, 24, +134 ms | 24, 24, +134 ms |
| lateral, el 50° | 24, 21, +27 ms | 24, 21, +27 ms | 24, 24, +124 ms | 24, 24, +124 ms |
| rear, el 0° | 9, 0, -43 ms | 8, 0, -23 ms | 6, 0, -6 ms | 13, 0, -26 ms |
| rear, el 50° | 21, 0, -23 ms | 21, 0, -23 ms | 23, 7, -6 ms | 24, 13, +14 ms |

- **At the comparators' geometry the model does escape rear threats.**
  - **How often.** Elevated rear looms are escaped in 21-24 of 24 trials, close to the 96 % of
    Card and Dickinson.
  - **How late.** Late: at l/v 40 ms none before collision, at l/v 80 ms 7-13 of 24.
- **Why later than lateral threats.** The disk straight behind is split between the eyes (the
  bilateral gap of section 8), and the DNp01 weight it reaches is about half a lateral disk's,
  pooled over both eyes.
- **No comparator for the timing.** Card and Dickinson give one latency for all directions
  pooled (215 ± 42 ms from stimulus start). Whether real rear escapes also come later is not in
  the accessible texts.
- **So there is no separate rear defect.** The blind region is real anatomy, and the late
  elevated rear escapes share the bilateral cause.
- **A scorecard note.** M3.0's E1/E4 rear and front rows use elevation 0°, while their
  comparators used about 50°. Moving them to the comparators' elevation would change the M3.0
  protocol and needs its own preregistration.

## 12. E4: DNp02 against DNp11 carries front and back, but weakly above the horizon

`tools/m3_5_direction.py`; raw data in `artifacts/m3_5/direction/`.

**The real fly** (Dombrovski et al. 2023):
- **DNp11.** "Activation of DNp11 evoked forward takeoffs".
- **DNp02.** Activating DNp02 with DNp04 "evoked a strong bias towards backward takeoffs".
  DNp04 alone gave "omnidirectional takeoffs".
- **Silencing.** "on average most DNp02-silenced flies took off forwards, directly towards the
  stimulus" for frontal looms.
- **The GF.** It "is not expected to control the escape takeoff direction", and its activation
  gave a "weak forward takeoff bias".

**The current decoder.**
- **Lateral component.** The DNp01 left-right contrast.
- **Forward component.** The constant `forward_bias` 0.35.
- **What it gives.** Side escapes go at ±67-71°, and frontal ones forward.

**At the moment of the doublet decision** (`trials`, l/v 40 ms, seeds 970201-970224, rule
`all`):

| Position | Escapes | Spikes since onset, DNp02 / DNp11 (mean) | Contrast, trace (median; share > 0) | Contrast, spikes (median) |
|---|---|---|---|---|
| front, el 0° | 24 | 6.2 / 1.0 | -0.60 (0.00) | -0.75 |
| right, el 0° | 24 | 2.8 / 1.7 | -0.22 (0.08) | -0.33 |
| rear, el 0° | 10 | 2.6 / 2.3 | -0.09 (0.10) | 0.00 |
| front, el 50° | 24 | 4.7 / 2.3 | -0.20 (0.08) | -0.33 |
| right, el 50° | 24 | 2.6 / 2.2 | +0.02 (0.54) | 0.00 |
| rear, el 50° | 18 | 3.2 / 3.7 | +0.11 (0.67) | 0.00 |

The contrast is (DNp11 - DNp02) / (DNp11 + DNp02), both sides summed. The left side is similar:
-0.13 (trace) and -0.20 (spikes) on the horizon, -0.05 and 0.00 at 50°.
- **The order is right at each elevation.** Front < side < rear.
- **The range is small above the horizon.** An elevated frontal loom gives about the same
  contrast as a lateral loom on the horizon.

**A candidate readout, evaluated offline.** forward = 0.35 + k × contrast, lateral unchanged.
Circular means against the M3.0 E4 bands (match within 45°):
- **k = 1.0, traces.**
  - Front on the horizon reads +162° (match).
  - Sides read -83° / +79° (match, near the 90° edge).
  - Rear reads +19° (match).
  - The elevated front reads -2° (gap).
- **Larger k.** It turns the elevated front backward (+156° at k = 2), but pushes the sides on
  the horizon past 90° (-99°, gap).
- **Spike counts.** They give the same picture.

**What it means.**
- **Where it would work.** A DNp02/DNp11 readout could turn M3.0's horizon front row into a match
  in a narrow gain window, k ≈ 1-1.5.
- **Where it would not.** It would not do so reliably for elevated frontal threats, which is the
  geometry of the real-fly assays and of the game's paddle.
- **The sides.** It also moves side escapes further from the real ±45°.
- **The gain.** It would be a fitted parameter.
- **Recommendation.** Not to build it as the next milestone on its own.

## 13. What the list leaves

- **Left-right balance.**
  - **The cause.** The count rule.
  - **The fix.** Driving every cell (`all`). It is the anatomy, leaves the calibration side
    unchanged, and removed the V8a-type asymmetry on fresh seeds.
  - **What it would need.** It is a runtime change, so it needs a preregistration. It would be a
    component of any later retinotopic candidate. Alone it would not make v30 acceptable,
    because V2 fails on the right side, which `all` leaves unchanged.
- **Rear blind spot.** It is real anatomy, and it needs no fix.
- **E4.** It is feasible only marginally (section 12).
- **The remaining blockers of the retinotopic line.**
  - **V2.** The split between early and late decisions at l/v 40 ms (results/game/M3_4_RETINOTOPIC_DRIVE.md,
    section 4).
  - **The gameplay consequence.** A size-rule fly escapes no hovering paddle and decides strikes
    at about contact.

## 14. V2 at l/v 40 ms: one timing distribution, placed late by the stimulus position

The user chose on 2026-10-24 to study why V2 splits into two clusters. The tool is
`tools/m3_5_v2_split.py`, with raw data in `artifacts/m3_5/v2_split/`.
- **Stimulus.** V2's looms (l/v 40 ms) under the v30 candidate.
- **Seeds.** 970301-970348, 48 per condition.

**The network's doublet level.**
- **The update.** The frozen LIF update is v ← 0.8187 v + input + 0.14, plus noise kicks of
  0.22 V at 1.2 Hz. A spike resets v to 0.
- **A second spike within 2 ticks of a reset.** It needs (0.14 + I)(1 + 0.8187) ≥ 1, a constant
  input I ≥ 0.41 V per tick.
- **A first spike from rest.** It needs far less.
- **Encoder cells at the 0.8 V cap.** They fire about every second tick (0.94 V after a reset),
  so DNp01's input reaches this level only when many cells are at the cap.

**Decisions per tick.** Each entry gives τ, the time before collision, then the number of the 48
decisions at that τ:

| Start, position | Decisions per tick (τ: n) | Median τ | Mean τ | Median size |
|---|---|---|---|---|
| 5°, az 90° el 0° (V2) | 76: 7, 56: 11, 36: 10, 16: 19, -4: 1 | 36 ms | 37.7 ms | 95.8° |
| 10°, az 90° el 0° (V2) | 137: 1, 77: 3, 57: 15, 37: 12, 17: 12, -3: 5 | 37 ms | 38.7 ms | 94.2° |
| 20°, az 90° el 0° (V2) | 127: 1, 67: 11, 47: 4, 27: 6, 7: 26 | 7 ms | 29.1 ms | 160.6° |
| 19.144°, az 90° el 0° (grid control) | 77: 2, 57: 10, 37: 4, 17: 31, -3: 1 | 17 ms | 29.1 ms | 133.5° |
| 10°, az 90° el 30° | 97: 2, 77: 3, 57: 8, 37: 24, 17: 10, -3: 1 | 37 ms | 40.3 ms | 94.2° |
| 5°, az 50° el 11° (calibration) | 176: 2, 136: 1, 116: 2, 96: 4, 76: 17, 56: 11, 36: 7, 16: 4 | 76 ms | 69.3 ms | 55.4° |
| 10°, az 50° el 11° (calibration) | 177: 2, 97: 5, 77: 19, 57: 12, 37: 9, 17: 1 | 77 ms | 69.5 ms | 54.8° |
| 20°, az 50° el 11° (calibration) | 127: 5, 87: 7, 67: 22, 47: 2, 27: 11, 7: 1 | 67 ms | 64.9 ms | 61.8° |

On the 10° start's grid, θ at τ = 77, 57, 37, 17 and -3 ms is 55°, 70°, 94°, 134° and 180°.

**Right DNp01 input per tick** (mean of 48, 10° start):

| τ | 117 ms | 97 ms | 77 ms | 57 ms | 37 ms | 17 ms |
|---|---|---|---|---|---|---|
| az 90° el 0° | 0.26 | 0.33 | 0.40 | 0.48 | 0.62 | 0.76 |
| az 50° el 11° | 0.36 | 0.41 | 0.50 | 0.55 | 0.66 | 0.79 |

**Static reach** (`reach`): the right DNp01 weight a 55° disk reaches.
- **The two positions.** The calibration position reaches 0.073, the largest of 12 positions
  (az 30-90°, el 0-30°). V2's position reaches 0.054, the smallest, 27 % less.

What this shows:
- **There is one distribution, not two clusters.**
  - **In time.** The decisions spread over 4-5 consecutive ticks in a single broad peak.
  - **In size.** The two clusters exist only in size: at l/v 40 ms one tick near collision changes
    θ by 15-45°.
- **Why V2's position decides late.**
  - **The doublet level.** The input reaches it at about 55° (τ 77 ms). That is the real fly's
    takeoff size: the X16 law gives 2.0 × 40 - 6 = 74 ms, about 57°.
  - **The wait.** Doublets then form stochastically, so the median decision comes about two
    ticks later (τ 37 ms, 94°).
  - **At the calibration position.** The level is reached a tick earlier, and the median
    decision is at the real fly's time and size (τ 77 ms, 55°).
- **The start size has a small real effect.**
  - **The effect.** Larger starts decide 5-10 ms later on average (5° and 10° against 19.1° and
    20°).
  - **The tick grid.** The 20° start's grid also sits 10 ms closer to collision (t0 modulo 20 ms
    is 6.9 ms, against 17.2 ms for 10°). The grid-matched 19.144° start has the same mean time as
    20°, so the grid changes only which sizes are sampled (161° against 134° at the last tick).
- **V2 passes at the calibration position.** The spread there is 7.0° (55.4°, 54.8°, 61.8°),
  within the 10° tolerance. At V2's position the same model spreads 66.4°.
- **The failure is position-dependent timing.**
  - **The sensitivity.** The decision time depends steeply on how much DNp01 weight a disk
    reaches near the doublet level: 27 % less costs about 40 ms.
  - **The same delay in E2.** At the scorecard's position, V1's E2 fit has a delay of -43 ms
    against the real -6 ms. E2 was classed a match because its band applies to the threshold
    implied by the slope.
- **What real-fly data say.**
  - **Azimuth.** The real GF's peak latency does not differ between -45°, 0° and +45° azimuth
    on the horizon (Jang et al. 2023).
  - **These two positions.** No accessible real-fly data compare 50°/11° with 90°/0° directly.
- **A common thread with section 5.** About two ticks pass between reaching the doublet level and
  the decision. This costs most where θ grows fastest: V2 at l/v 40 ms, strikes, and E3 at
  l/v 10 ms.

**Possible next steps.** Each needs the user's decision; a runtime change also needs a
preregistration.
- **A timing map (read-only).** Measure the decision time at l/v 40 and 80 ms over azimuth 0-150°
  and elevation 0-50°. This would show how far the model departs from a position-invariant
  giant fiber over the visual field, including the paddle's elevations.
- **Calibrating where behaviour was measured.** Calibrate the scale on the behavioural
  comparator's geometry (lateral, on the horizon) instead of the Ache et al. 2019
  electrophysiology position. That would move decisions at V2's position earlier, and those at
  the Ache position earlier than the GF-model targets (V3 at risk). It moves the error rather
  than removing it.

## 15. The decision-time map: real-fly timing only where the weight map peaks

The user chose on 2026-10-24 to map the decision time across the visual field. The tool is
`tools/m3_5_timing_map.py`, with raw data in `artifacts/m3_5/timing_map/`.
- **Stimulus.** V2's loom from 10° at l/v 40 and 80 ms, under the v30 candidate.
- **Grid.** Right azimuth 0-150° by elevation 0-70°.
- **Seeds.** 970401-970424, 24 per position.
- **Comparator.** The real-fly law X16, takeoff 2.0 × l/v - 6 ms before collision: 74 ms at
  l/v 40 ms and 154 ms at l/v 80 ms.

**Median decision time before collision, ms** (negative: after collision). Every position
escaped in 21-24 of 24 trials.

| l/v 40 ms | az 0° | 30° | 50° | 70° | 90° | 110° | 130° | 150° |
|---|---|---|---|---|---|---|---|---|
| el 0° | -3 | 47 | 37 | 37 | 37 | 37 | -3 | -23 |
| el 25° | -3 | 57 | 57 | 57 | 37 | 37 | 17 | -3 |
| el 50° | 17 | 17 | 37 | 37 | 37 | 17 | 7 | -3 |
| el 70° | -3 | 17 | 17 | 17 | 17 | 7 | -3 | -13 |

| l/v 80 ms | az 0° | 30° | 50° | 70° | 90° | 110° | 130° | 150° |
|---|---|---|---|---|---|---|---|---|
| el 0° | 54 | 114 | 154 | 154 | 124 | 94 | 34 | -6 |
| el 25° | 74 | 134 | 174 | 164 | 154 | 114 | 74 | 14 |
| el 50° | 54 | 94 | 114 | 144 | 114 | 94 | 54 | 14 |
| el 70° | 44 | 54 | 54 | 54 | 54 | 54 | 14 | 14 |

**Reach** (`reach`): the DNp01 weight a 55° disk reaches on the side with more.

| Region | Reach |
|---|---|
| peak (az 50°, el 25°) | 0.075 |
| lateral band (az 30-90°, el 0-50°) | 0.051-0.071 |
| front (az 0°) | 0.024-0.034, split about equally between the eyes |
| el 70° | 0.024-0.044 |
| rear (az 150°) | 0.016-0.029 |

What the map shows:
- **The weight map sets the timing.**
  - **The correlation.** Decision time follows the reach of the stronger side: r = 0.93 at
    l/v 40 ms and 0.94 at l/v 80 ms, over 32 positions.
  - **Where it matches.** Only around azimuth 30-90° and elevation 0-25° does the model come
    near the real law.
  - **A rough band.** Take the law within two of its parameter SDs: 74 ± 27 ms and
    154 ± 39 ms. That holds at 4 of 32 positions at l/v 40 ms and 8 of 32 at l/v 80 ms.
- **The front contradicts the real fly directly.**
  - **The real fly.** Jang et al. 2023 found no difference in the GF's peak latency between 0°
    and ±45° azimuth on the horizon. With one eye painted, frontal responses fell (at the larger
    r/v), so the real GF pools both eyes for frontal looms.
  - **The model.** On the horizon it decides frontal looms 40-50 ms later than looms at 30-50°
    at l/v 40 ms (-3 against 37-47 ms), and 60-100 ms later at l/v 80 ms (54 against
    114-154 ms).
  - **Why.** A frontal disk is split between the eyes, and each DNp01 receives only its own
    half. This is the bilateral gap of section 8, now measured against a direct real-fly
    comparator.
- **High and rear positions decide late everywhere.**
  - **Where.** At 70° elevation, where the game's paddle often hovers, the model decides at
    -13 to 17 ms (l/v 40) and 14-54 ms (l/v 80). Behind 130° it decides at or after collision.
  - **Why.** Few fields look there, and a disk near the midline is split between the eyes.
- **Even the best region has the wrong delay.**
  - **The fit.** At azimuth 50°, elevation 25°, the two l/v give a slope of about 2.9 and an
    intercept of about -60 ms. The real fly gives 2.0 and -6 ms.
  - **What it means.** The model reacts to a smaller image (an effective threshold of about 38°)
    but needs about 60 ms to decide. At V2's position the same estimate gives 2.2 and -50 ms.
    The roughly two ticks between reaching the doublet level and the decision (section 14)
    appear here as a long delay.
  - **How much longer than the real fly's.** Section 16 places it at 35-55 ms against Fotowat et
    al. 2009 (X16) and 10-30 ms against the GF-driven short mode of von Reyn et al. 2014 (X24).

**What it leaves.**
- **Structural latency.** The extra decision delay is common to every position. It is the
  common factor of V2, E2's delay, E3 and the late strikes.
- **Position dependence.** The decision time depends on position through the receptive-field
  weight map and the split between the eyes. The frontal part is a measured gap against Jang
  et al. 2023.

## 16. The decision delay is the frozen simulator's floor

The user chose on 2026-10-25 to decompose the delay. The tool is `tools/m3_5_latency_parts.py`,
with raw data in `artifacts/m3_5/latency_parts/`.
- **Stimulus.** V2's loom from 10° at azimuth 90°, elevation 0°, l/v 20, 40 and 80 ms.
- **Seeds.** 970501-970524 for the looms; a 10 s rest run with seeds 970601-970624.
- **The fit.** The delay is read as the intercept of a fit of decision time against l/v.

**Two real-fly comparators disagree by 24 ms.**
- **X15/X16, Fotowat et al. 2009.** Takeoff 6 ms after 54°: slope 2.0, intercept -6 ms. This is
  M3.0's E2 comparator.
- **X24, von Reyn et al. 2014.** Recorded at 6,000 fps, which separates the two escape modes. It
  gives a neural delay to takeoff of 30.1 ms for GF-driven short-mode escapes and 45.7 ms for
  long-mode ones.
- **Which applies.** The model decides from DNp01 (the GF), so the short mode is its nearer
  counterpart.

**The parts of the model's delay** (section 14 and offline from these traces):
1. **The Retina to the encoder: 0 ticks.** The encoder drives LPLC2/LC4 in the same tick. No
   photoreceptor or medulla delay is modelled.
2. **LPLC2/LC4 spikes to DNp01: 1 tick (20 ms).** The network's synaptic input acts at the next
   step.
3. **DNp01's first driven spike to the decision: 1-2 ticks.**
   - **The reset.** DNp01 resets to 0 after a spike.
   - **The next tick needs a lot.** To fire again on the next tick it needs about 0.86 V per tick
     of input. The whole right encoder population, all driven at the cap, delivers 0.87-0.94 V
     (section 8.2).
   - **Below that.** From 0.41 to 0.86 V it fires every second tick, so the doublet decision
     comes two ticks after the first driven spike.
   - **Measured.** From the input reaching 0.41 V to the decision: a median of 1-2 ticks.

**Encoder cap.** At the same scale, a cap of 0.86 or 1.0 V raises DNp01's input by 10-20 %
(l/v 40 ms, τ 77 ms: 0.39 → 0.46 V). It barely moves the decision:

| Cap | l/v 20 | l/v 40 | l/v 80 | Fit: slope, intercept |
|---|---|---|---|---|
| 0.80 V (v30) | 9 ms | 37 ms | 134 ms | 2.14, -40 ms |
| 0.86 V | 9 ms | 37 ms | 154 ms | 2.50, -50 ms |
| 1.00 V | 9 ms | 37 ms | 144 ms | 2.32, -45 ms |

The table gives median decision times before collision, 24 trials each. The cap is not the
bottleneck: DNp01's own reset is.

**Decoder rules** (offline, on the same spike trains). Spontaneous rates at rest:

| Cell | Left | Right |
|---|---|---|
| DNp01 | 0.31 Hz | 0.40 Hz |
| DNp02 | 0.72 Hz | 0.80 Hz |
| DNp04 | 0.77 Hz | 0.80 Hz |
| DNp11 | 0.41 Hz | 0.46 Hz |

| Rule | False alarms at rest | Fit at cap 0.80 V |
|---|---|---|
| doublet, at most 2 ticks (runtime) | 0 in 240 s | slope 2.14, intercept -40 ms |
| DNp01 + DNp02/DNp04/DNp11, same tick | 9 in 240 s (0.04 per s) | slope 4.64, intercept -50 ms |
| the same within one tick | 24 in 240 s (0.10 per s) | slope 6.72, intercept -20 ms |

- **The coincidence rules fail on two counts.** They fire at rest every 10-30 s, and they decide
  on sparse early spikes (effective thresholds 17-24°).
- **The single-spike rule.** It was already ruled out by spontaneous DNp01 spikes (M3.3
  research, section 1).
- **Wider doublet windows.** Section 14's offline test shifts every position earlier without
  closing the gap between positions.

What it means:
- **The floor.** The model's minimum decision delay is about 2 ticks (40 ms) after the image that
  first makes the drive sufficient: 1 tick of synaptic transmission and at least 1 tick for the
  second DNp01 spike. A typical delay is 2.5 ticks.
  - **What sets it.** The frozen simulator's 20 ms step and reset-to-zero neurons.
  - **What cannot shorten it.** The encoder cannot. The decoder cannot without false alarms.
- **Against the comparators.** The fitted intercepts are -40 to -60 ms (sections 15-16).
  - **The GF short mode (30.1 ms).** The excess is 10-30 ms, about one simulation step.
  - **Fotowat et al. (6 ms after 54°).** The excess is 35-55 ms.
- **What is left that the rules allow.** Anticipation in the drive: for example, the balance of
  the LC4 velocity term against the LPLC2 size term, which sets how early the drive becomes
  sufficient for fast looms. That would be a new calibration against the behavioural law, with
  the Ache et al. 2019 GF-model targets as a competing constraint.
- **The larger remaining gap is positional (section 15).**
  - **Its cause.** The split between the eyes and the receptive-field weight map.
  - **What closing it takes.** The bilateral part can only be closed in the frozen network.

## 17. How strong a commissural pathway would need to be

The user chose on 2026-10-25 to explore, read-only, the strength the bilateral pathway would
need. The tool is `tools/m3_5_bilateral_gain.py`, with raw data in
`artifacts/m3_5/bilateral_gain/`.
- **The change explored.** It multiplies, in one research process's memory only, the weights from
  the three carrier types of section 8.2 (PVLP151, AMMC-A1, DNp11) onto the opposite DNp01 by a
  gain g. That is 11 synapse entries. Nothing in data/, the configuration or the runtime
  changes.
- **Stimulus.** V2's loom from 10° at l/v 40 and 80 ms.
- **Seeds.** 970701-970724 for the looms, and 970801-970824 for 10 s at rest.

**Against Jang et al. 2023's physiology.** The right DNp01 under looms at +45° (ipsilateral) and
-45° (contralateral) on the horizon. The peak synaptic input above rest is taken while the disk is
at most 63°, Jang et al.'s largest size:

| Gain | Contra / ipsi peak, l/v 40 | Contra / ipsi peak, l/v 80 | Contra peak later by |
|---|---|---|---|
| 1 (v30) | 0.07 | 0.05 | - |
| 5 | 0.23 | 0.25 | 1 tick |
| 10 | 0.48 | 0.44 | 2-5 ticks |
| 20 | 0.95 | 0.92 | 1 tick |
| 40 | 2.14 | 2.11 | 1-2 ticks |

**Against Jang et al.'s latency invariance, behaviourally.** Median decision time before
collision, ms. "±45°" gives the +45° and -45° values.

| Gain | front, l/v 40 | ±45°, l/v 40 | front, l/v 80 | ±45°, l/v 80 |
|---|---|---|---|---|
| 1 | -3 | 57, 57 | 54 | 114, 154 |
| 5 | 17 | 57, 57 | 94 | 154, 144 |
| 10 | 37 | 67, 37 | 164 | 154, 154 |
| 20 | 127 | 77, 57 | 334 | 194, 164 |
| 40 | 297 | 277, 307 | 574 | 574, 574 |

**Elsewhere and at rest:**

| Gain | lateral 90°/0° | calibration 50°/11° | high 90°/70° | rear 180°/50° | DNp01 at rest, L / R | Decisions at rest |
|---|---|---|---|---|---|---|
| 1 | 37 / 114 | 77 / 214 | -3 / 74 | -23 / -6 | 0.33 / 0.42 Hz | 0 in 240 s |
| 5 | 37 / 114 | 77 / 194 | 17 / 74 | -23 / 14 | 0.53 / 0.68 Hz | 0 |
| 10 | 37 / 134 | 77 / 194 | 27 / 114 | -3 / 34 | 1.23 / 1.31 Hz | 0 |
| 20 | 57 / 154 | 97 / 254 | 77 / 254 | 17 / 114 | 2.09 / 1.99 Hz | 0 |
| 40 | 247 / 554 | 247 / 574 | 197 / 544 | 67 / 244 | 2.60 / 2.28 Hz | 42 |

The position columns give the median decision time before collision at l/v 40 / 80 ms.

What it shows:
- **The required strength.**
  - **The comparators disagree.** The two readings of Jang et al. point to different gains:
    - the physiological one (equal magnitude up to 63°) to g ≈ 20;
    - the behavioural one (frontal decisions as at ±45°) to g ≈ 10.
  - **What that weight means.** At g = 10-20 the carriers' summed weight onto the opposite DNp01
    is 0.19-0.5, against 0.30 for the direct ipsilateral LPLC2 + LC4 input.
  - **So:** the pathway would have to be roughly as strong as the ipsilateral one, 10-20 times
    what the EM synapse counts give these carriers.
- **What g ≈ 10 would change.**
  - **Front.** Frontal looms are decided like those at ±45°.
  - **High and rear.** High and rear looms are decided 20-40 ms earlier. They still come later
    than lateral ones.
  - **Lateral and calibration positions.** They move by at most one tick.
- **The side effects grow with g.**
  - **Rest.** The spontaneous DNp01 rate rises three- to six-fold at g = 10-20. AMMC-A1 also
    carries auditory input. The doublet rule stays silent at rest up to g = 20; at g = 40 it
    fires 42 times in 240 s.
  - **Overshoot.** At g = 20 the front is decided 50-170 ms before ±45°, and every position moves
    earlier, so the scale would need recalibration.
  - **The cause.** Concentrating the pathway in six cells per side makes it spiky: a single
    PVLP151 spike at g = 20 gives the opposite DNp01 about 0.5 V.
- **Limits of the exploration.**
  - **The pathway is a stand-in.** The real pathway is unidentified (Jang et al. 2023).
  - **The timing.** The contralateral peak comes one tick or more after the ipsilateral one,
    through the two-hop route. Jang et al. report no significant latency difference.
  - **So:** these gains describe this stand-in only, not the real circuit.
- **What a runtime version would need.**
  - **Authorization.** It would change the frozen connectome's effective weights, so it needs
    the user's explicit authorization.
  - **A preregistration.** It would also need one that fixes beforehand which Jang et al.
    criterion sets g.
