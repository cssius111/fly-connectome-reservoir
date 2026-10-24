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
