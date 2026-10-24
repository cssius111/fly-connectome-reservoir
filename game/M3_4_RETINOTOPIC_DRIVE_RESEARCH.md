# M3.4: receptive-field positions of LPLC2 and LC4 from MaleCNS (read-only research)

Status: **research note, 2026-10-23.** No runtime code, configuration, record or frozen system
changed.

**Question.** The user asked whether MaleCNS data can give each LPLC2 and LC4 cell's position
in the visual field. With those positions each cell could be driven only by the part of the
stimulus inside its receptive field, so that the drive grows smoothly with the area the paddle
covers. That might fix both M3.3 defects and separate front from back (E4).

Every computation below is in `tools/m3_4_receptive_fields.py`; raw data go to `artifacts/m3_4/`
(git-ignored). The network tests are **exploratory**:
- seeds 920001-920012 and 920101-920124, unused before;
- any design chosen from them must be preregistered and validated on other seeds.

## 1. Summary

- **Yes, MaleCNS gives the receptive fields directly.**
  - Every MaleCNS synapse in the optic lobe carries its column, as hex coordinates.
  - The column of each input synapse of an LPLC2 or LC4 cell, mapped to the eye, gives the
    cell's receptive field: its centre and its extent.
  - The column-to-eye mapping uses the micro-CT eye map of Zhao et al. 2025, matched by lattice
    position.
- **The fields agree with the literature.**
  - **Size.** The median radius holding 95 % of a cell's column-assigned input is 21.9° for
    LPLC2 and 19.1° for LC4.
    - LC4: about 38° across, against "approximately 40°" (Dombrovski et al. 2023).
    - LPLC2: dendrites about 44° across. The functional field of about 60° (Klapoetke et al.
      2017) adds the spread of the T4/T5 inputs and the optics.
  - **Coverage.** The 185 LPLC2 and 126 LC4 cells tile each eye: azimuth 4-146°, elevation -56°
    to +81°.
- **The connectome already encodes position in its weights onto the descending neurons.** These
  are the gradients Dombrovski et al. 2023 reported in FAFB and the hemibrain:
  - **LPLC2 → DNp01 (giant fiber):** stronger for dorsal fields (Spearman ρ = +0.74 left,
    +0.85 right).
  - **LC4 → DNp02 (backward takeoff):** frontal fields (ρ = -0.76 / -0.85 against |azimuth|).
  - **LC4 → DNp11 (forward takeoff):** posterior fields (ρ = +0.75 / +0.82).
  - **LC4 → DNp01:** no positional gradient.
- **Coverage-weighted drive works in the frozen network, but weakly at the current scale.**
  - **Smooth growth.** The DNp01 input a lateral disk reaches grows from 0.004 at 10° to 0.136
    at 90°, with no step.
  - **Front and back.** The DNp11 share of the LC4 input to DNp02 + DNp11 rises from 0.06 for a
    frontal disk to 0.84 for a posterior one.
  - **Spike output.** In simulation, DNp11 and DNp02 spikes follow the stimulus direction, and a
    ventral disk drives DNp01 least.
  - **Magnitude.** At the M3.3 scale the responses are near spontaneous levels, so the scale
    would need recalibration.
- **The M3.3 left-right asymmetry has a different cause than its report states** (erratum in
  `results/game/M3_3_ESCAPE_DECISION.md`).
  - **Not the stimulus.** The C1 and C2 Retina streams are exact mirror images.
  - **The trigger.** The escapes happen while the paddle controller settles at the end of the
    approach. There θ̇ creeps at +0.0005 to +0.003 rad/s for about 0.4 s. The `ache2019_v1`
    LPLC2 term needs only θ̇ > 0, so it switches on in full: 0.54 V at 28°.
  - **The side difference.** Under identical LPLC2-only drive of 0.55 V, the left DNp01 forms a
    doublet in 24 of 24 seeds and the right in 0 of 24.
  - **Not the weights.** The driven LPLC2 subset's direct and two-hop weights are slightly
    larger on the right, so the difference lies in the network dynamics.
  - **LC4 is not involved:** its drive is about zero during the creep.
- **What retinotopy fixes and what it does not.**
  - **It fixes:**
    - the scalar knife-edge, since recruitment becomes gradual;
    - dorsal against ventral;
    - a front/back code at DNp02/DNp11.
  - **It does not fix by itself:**
    - the creep trigger, unless the per-cell rule needs real edge motion;
    - the side-dependent threshold;
    - E4, which needs an escape-direction readout of DNp02/DNp11, a policy change.

## 2. Data and method

**Synapses** (MaleCNS v1.0, public bucket `gs://flyem-male-cns/v1.0/`):
- **Source.** The precomputed synapse annotations, read through their `by_rel_body_post` index:
  all input synapses of each LPLC2 and LC4 cell. The layer holds no synapse with a
  postsynaptic confidence below 0.5.
- **Column property.** Each synapse has an `optic_column` property, hex1 × 100 + hex2.
- **Check.** It was verified against the published column pins
  (`malecns-v1.0-optic-lobe-column-pins`). For one LPLC2 cell, 88 % (lobula) and 91 % (lobula
  plate) of its synapses sit at the nearest pin's column, and 98-100 % within one column.
- **Which synapses count.** A cell's receptive field uses its column-assigned input synapses in
  the lobula and lobula plate of its own side. The median count is 1,523 per LPLC2 cell (over
  67 columns) and 2,133 per LC4 cell (over 55 columns).

**Orientation of the hex lattice** (column pins, least-squares direction of one hex step):
- **Coordinates.** h = (hex1 - 18) - (hex2 - 19) and v = (hex1 - 18) + (hex2 - 19), centred on
  column [18, 19], which the Reiser lab code uses as the eye centre.
- **+v is dorsal** in the medulla, lobula and lobula plate of both sides: about -550, -370 and
  -400 voxels in y per step, where +y is ventral.
- **+h is anterior on the eye.**
  - It points to the posterior medulla (+447 and +434 voxels in z, +z posterior) and to the
    anterior lobula (-264 and -277), as the two optic chiasms require.
  - This is the convention of Zhao et al. 2025: "the +h axis points towards the posterior
    medulla, corresponding to anterior on the eye because of the optic chiasm".

**Eye map** (Zhao et al. 2025, Nature 646:135-142, data in `reiserlab/eyemap_T4`, fly 20240701):
- **Content.** The micro-CT gives 852 right-eye ommatidia with their viewing directions and hex
  indices.
- **Spacing.** The median neighbour angle is 4.78° (10-90 %: 3.9-6.5°).
- **Field of view.** The equator row spans azimuth -4° to 151°, and the central meridian spans
  elevation -70° to +86°. The paper reports a field from directly above to -70° in elevation,
  and from under 10° into the opposite hemisphere to about 155° behind.
- **Matching.**
  - MaleCNS columns and ommatidia are matched by their (h, v) offset from the eye centre. This
    is the from-the-centre matching Zhao et al. used for their own EM data.
  - 97-98 % of the columns a cell uses have an exact match; the rest take the nearest
    ommatidium.
- **Left eye.** It is the mirror image of the right-eye map. One eye map for both sides adds no
  left-right asymmetry of its own.

**Receptive-field measures:**
- **Centre.** The synapse-count-weighted mean of the column directions.
- **Radius.** r50, r80 and r95 are the angular radii around the centre that hold 50, 80 and
  95 % of the column-assigned synapses.

**Limits:**
- The eye map is from a different, female fly. The match by lattice position from the centre is
  exact only near the centre; at the rim an error of one column (about 5°) is likely.
- Synapse position measures dendritic extent, not the functional field, which also includes the
  input neurons' spread and the optics.
- Positions are anatomical. Nothing here measures response strength across the field.

## 3. Receptive fields

| | LPLC2 | LC4 |
|---|---|---|
| Cells (left / right) | 185 (94 / 91) | 126 (71 / 55) |
| Column-assigned input synapses per cell, median | 1,523 | 2,133 |
| Columns per cell, median | 67 | 55 |
| r50, median (IQR) | 9.8° (8.9-10.6) | 10.5° (9.2-11.4) |
| r80 | 15.3° (14.3-16.4) | 14.8° (13.3-16.4) |
| r95 | 21.9° (20.3-23.7) | 19.1° (16.9-20.9) |
| Centres, right eye | azimuth 4 to 146°, elevation -56 to +79° | azimuth 6 to 146°, elevation -55 to +75° |
| Centres, left eye | azimuth -145 to -4°, elevation -51 to +81° | azimuth -150 to -6°, elevation -57 to +78° |

Fields of the cells the ROOM encoder drives (the balanced subsets of `RetinalEncoder`):

| Cells per side | front, \|az\| < 60° | lateral | back, \|az\| ≥ 110° | ventral, el < 0 | middle | dorsal, el ≥ 40° |
|---|---|---|---|---|---|---|
| LPLC2 left / right (91 each) | 43 / 42 | 32 / 31 | 16 / 18 | 31 / 32 | 45 / 44 | 15 / 15 |
| LC4 left / right (55 each) | 28 / 24 | 15 / 18 | 12 / 13 | 19 / 18 | 24 / 26 | 12 / 11 |

## 4. Positional weight gradients onto descending neurons

Spearman correlation over the ipsilateral cells between the cell's weight onto the DN and its
field position. Weights are the per-postsynaptic normalised MaleCNS weights the network uses;
there are no contralateral connections.

| Connection | Total weight, left / right | ρ with \|azimuth\| | ρ with elevation |
|---|---|---|---|
| LPLC2 → DNp01 | 0.128 / 0.138 | -0.15 / -0.03 (n.s.) | **+0.74 / +0.85** |
| LPLC2 → DNp04 | 0.162 / 0.161 | **-0.81 / -0.68** | -0.17 / -0.13 (n.s.) |
| LPLC2 → DNp02, DNp11 | ≤ 0.005 | | |
| LC4 → DNp01 | 0.183 / 0.161 | -0.09 / +0.13 (n.s.) | +0.13 / +0.22 (n.s.) |
| LC4 → DNp02 | 0.280 / 0.244 | **-0.76 / -0.85** | -0.11 / -0.04 (n.s.) |
| LC4 → DNp11 | 0.174 / 0.169 | **+0.75 / +0.82** | +0.48 / +0.41 |
| LC4 → DNp04 | 0.563 / 0.536 | -0.08 / -0.19 (n.s.) | **-0.67 / -0.64** |

**Agreement with Dombrovski et al. 2023** (Nature 613:534-542, FAFB and hemibrain):
- **LC4.** Frontal LC4 neurons give DNp02 more input, and posterior ones DNp11.
  - "activation of DNp02 and DNp04 together evoked a strong bias towards backward takeoffs".
  - "Activation of DNp11 evoked forward takeoffs".
- **LPLC2.** Its gradient onto the giant fiber runs dorsoventrally: "GF responses following
  activation of dorsal LPLC2 were significantly stronger".
- **Male brain.** The male CNS shows the same gradients.

**Weight by field band.** About half of the LPLC2 → DNp01 weight comes from frontal fields:
- left: 0.064 frontal, 0.043 lateral, 0.021 posterior;
- right: 0.068 frontal, 0.045 lateral, 0.025 posterior.

## 5. Coverage-weighted drive

**The rule** (exploratory, only inside the tool):
- **Coverage.** Each driven cell gets the fraction c_i of its synapse-weighted field that lies
  inside the looming disk. The disk edge is soft, a logistic of 2.5° width (half the
  inter-ommatidial angle).
- **Drive.** That fraction is multiplied by the M3.2 Ache et al. 2019 feature (LPLC2 by size,
  LC4 by angular velocity, in mV) and by a scale, and capped at 0.8 V.

**Static reach.** This is the DN input weight Σ c_i w_i a 40° disk reaches, with no dynamics.

| DNp01 input from LPLC2, right eye | az 10° | 40° | 70° | 100° | 130° |
|---|---|---|---|---|---|
| el +60° | 0.011 | 0.015 | 0.015 | 0.014 | 0.012 |
| el +30° | 0.015 | 0.024 | 0.021 | 0.017 | 0.010 |
| el 0° | 0.010 | 0.018 | 0.017 | 0.012 | 0.006 |
| el -30° | 0.002 | 0.003 | 0.004 | 0.002 | 0.001 |

| LC4 at el 0°, right eye | az 10° | 40° | 70° | 100° | 130° | 150° |
|---|---|---|---|---|---|---|
| DNp11 share of DNp02 + DNp11 input | 0.06 | 0.10 | 0.28 | 0.49 | 0.75 | 0.84 |

**Growth with size.** For a disk at azimuth 70°, elevation 0°, the LPLC2 + LC4 → DNp01 reach
grows smoothly with disk size:

| Disk size | 10° | 20° | 30° | 40° | 60° | 90° |
|---|---|---|---|---|---|---|
| Right | 0.004 | 0.011 | 0.022 | 0.036 | 0.072 | 0.136 |
| Left | 0.004 | 0.010 | 0.019 | 0.030 | 0.058 | 0.113 |

At mirrored positions the right side reaches about 1.2 times the left, because the driven
subsets' weights differ (LC4 0.144 against 0.161).

**Network test.**
- **Stimulus.** The disk follows the Ache et al. 2019 protocol: l/v 40 ms, 10° to 90°, then a
  0.2 s hold.
- **Recording.** Mean spikes per trial from stimulus onset, 12 seeds. Spontaneous counts in the
  same window are about 0.25-0.33.

| Scale 3.0 V/mV | DNp01 R | DNp02 R | DNp11 R | DNp04 R |
|---|---|---|---|---|
| front (az 20°, el 0°) | 2.92 | 2.17 | 0.58 | 5.00 |
| lateral (az 70°, el 0°) | 3.42 | 2.25 | 1.33 | 4.17 |
| back (az 120°, el 0°) | 2.17 | 1.25 | 1.42 | 2.83 |
| dorsal (az 70°, el 50°) | 3.17 | 1.75 | 1.25 | 3.50 |
| ventral (az 70°, el -40°) | 1.33 | 1.33 | 0.83 | 2.92 |

**What the test shows:**
- **Direction of the effects.** The effects follow section 4:
  - DNp02 falls from front to back while DNp11 rises;
  - a ventral disk drives DNp01 least;
  - a mirrored left disk drives the left DNs.
- **Scale 0.3 (the M3.3 value).** DNp01 R reaches only 0.42-1.33 spikes, because coverage-weighted
  drive reaches only the covered cells.
- **Calibration.** A retinotopic mode would need its own scale calibration, at the Ache et al.
  2019 stimulus position: azimuth 50°, elevation 11°.

## 6. The M3.3 defects re-examined

**C1/C2 left-right asymmetry.** N4B6 matrix, fixed fly: C2 (left) escaped in 0.90 of trials,
C1 (right) in 0.04.
- **Mirror check.** The two Retina streams are exact mirror images: the largest θ difference is
  0, and the azimuths are opposite at every tick.
- **Timing.** The C2 escapes cluster at 6.08-6.46 s after onset (43 of 48 trials). C3, the
  closer right approach, escapes in 33 of 48, all but two at 6.84-7.08 s. Both windows are the
  end of the approach.
- **The settling creep.** In C1, θ peaks at 28.25° (5.54 s), falls back to 27.82°, and then
  creeps up at θ̇ = +0.0005 to +0.003 rad/s from 6.0 to 6.4 s.
- **Why the creep drives LPLC2.** The `ache2019_v1` LPLC2 term needs only θ̇ > 0. At 27.8° and
  scale 0.3 it is 0.54 V for every driven LPLC2 cell. LC4 is proportional to θ̇ and stays about 0.
- **Identical drive by side** (LPLC2 only, 0.5 s, seeds 920101-920124):

  | Drive to one side's encoder cells | 0.40 V | 0.55 V | 0.80 V |
  |---|---|---|---|
  | LPLC2 only: left DNp01 doublet | 0/24 | **24/24** | 24/24 |
  | LPLC2 only: right DNp01 doublet | 0/24 | **0/24** | 24/24 |
  | LC4 only: left / right | 1/24 / 4/24 | 1/24 / 5/24 | 24/24 / 24/24 |

  - The side difference depends on the channel. Under LC4-only drive the right side is slightly
    more prone to doublets, the opposite of LPLC2.
  - At 0.30 V and below neither channel alone forms doublets on either side.

- **The left threshold is lower, but not from the weights.** The driven subsets' weights favour
  the right: direct 0.125 left against 0.138 right, and two-hop 0.023 against 0.020. The side
  difference therefore arises in the network's dynamics. Its path is not traced here.
- **The M3.3 attribution is wrong.** The report cited LC4 → DNp01 weights of 0.183 and 0.161.
  Those are all-cell weights. The encoder drives 55 of the 71 left LC4 cells, whose weight is
  0.144, below the right's 0.161, and LC4 carries no drive during the creep anyway.

**Fast frontal hover approaches (B2).** The image stays at 21-31°, below the 42° peak of the
LPLC2 size term. Under coverage-weighted drive a frontal disk reaches the frontal LPLC2 cells.
They carry half of the LPLC2 → DNp01 weight, but in the game the paddle hangs high (elevation
about 20-70°). Whether that drives enough is a question for a calibrated mode, not for this
note.

## 7. What a retinotopic encoder mode would need

- **Retina.**
  - The current `Retina` carries θ, θ̇ and the bearing; the elevation is lost.
  - The projector has it (`swatter.height` over the horizontal distance). It is a purely visual
    quantity: one more angle of the same image.
  - Adding `elevation` changes the frozen `Retina` dataclass, the bottleneck's interface, so it
    needs explicit authorization.
  - The paddle hovers at height 320, so it sits 20-70° above the horizon. It falls to height 24
    during a strike.
- **Per-cell rule.** This is the main design choice.
  - **Coverage × Ache features** (tested here):
    - smooth recruitment, and it keeps the M3.2 size and velocity roles;
    - but it keeps the creep trigger, because any θ̇ > 0 opens the LPLC2 term.
  - **Edge-based LPLC2:**
    - each cell is driven by the outward-moving edge inside its field;
    - the size tuning then follows from field geometry: the drive ends once the edge leaves the
      field, which for a centred disk is at about 44° (twice r95), close to Ache's 42° peak;
    - creep moves the edge under 0.002° per tick (θ̇/2 · dt) against a 4.8° column spacing, so
      the rule needs a motion-detector time window to separate creep from slow looms;
    - that window must be sourced from T4/T5 or LPLC2 temporal data. M3.3 rejected an
      unsourced θ̇ gate.
  - **LC4:** angular velocity times coverage.
- **Population.** Whether to keep the balanced random subsets (55 LC4 per side) or drive all
  cells. With retinotopy, the subset leaves 16 left LC4 fields undriven.
- **Calibration.** One scale against the Ache GF-model targets, as in M3.2/M3.3, with the
  stimulus at azimuth 50°, elevation 11°.
- **Decoder.** The M3.3 doublet decoder fixed the no-player false escapes and is the natural
  partner; the summed N4B1C paths were the cause of M3.2's false escapes. Both are options for
  a preregistration.
- **E4 (front/back direction).**
  - The front/back code reaches DNp02/DNp11.
  - The escape direction is read from the DNp01 contrast plus a forward bias, a frozen part of
    the fixed baseline policy.
  - Reading DNp02 against DNp11 is a separate, explicitly authorized policy change.
- **Data provenance.**
  - **MaleCNS** data are public. The derived per-cell column table (about 300 cells × 60
    columns) is small enough to commit.
  - **Eye map.** `reiserlab/eyemap_T4` is GPL-3.0. The raw micro-CT data are also published at
    doi:10.25378/janelia.29111339.v1. Before a derived direction table is committed, its
    licence must be checked. The alternative is to generate it at build time, like `flybrain
    build`.

## 8. Possible next steps

Each needs the user's decision and, for any runtime change, a preregistration first.

1. **M3.4 preregistration:**
   - a gated `retinotopic_v1` encoder mode on the ROOM configuration, with the Retina
     elevation;
   - the edge-based LPLC2 rule, with a sourced motion window, and coverage-weighted LC4;
   - the M3.3 doublet decoder;
   - one recalibrated scale;
   - the M3.3 checks V1-V7 on fresh seeds, plus a left-right symmetry check;
   - E4 stays out of scope.
2. **The same as 1, plus a DNp02/DNp11 escape-direction readout for E4.** This is a policy
   change.
3. **First, a smaller fix to the creep trigger alone**, with the current non-retinotopic
   encoder: require real expansion for the LPLC2 term. This is the gate M3.3 rejected, so it
   needs a sourced threshold.

## References

- Ache JM, Polsky J, Alghailani S, et al. (2019) Neural basis for looming size and velocity
  encoding in the Drosophila giant fiber escape pathway. Curr Biol 29:1073-1081.
  doi:10.1016/j.cub.2019.01.079
- Dombrovski M, Peek MY, Park J-Y, et al. (2023) Synaptic gradients transform object location to
  action. Nature 613:534-542. doi:10.1038/s41586-022-05562-8
- Klapoetke NC, Nern A, Peek MY, et al. (2017) Ultra-selective looming detection from radial
  motion opponency. Nature 551:237-241.
- Nern A, Loesche F, Takemura S, et al. (2025) Connectome-driven neural inventory of a complete
  visual system. Nature.
- Zhao A, Gruntman E, Nern A, et al. (2025) Eye structure shapes neuron function in Drosophila
  motion vision. Nature 646:135-142. doi:10.1038/s41586-025-09276-5
