# M3.0: looming-escape evidence for the fidelity scorecard

Status: **evidence extraction for M3.0, 2026-10-22.** No runtime, configuration or record
changes. This file adds looming-escape comparators to the M1.8-R0 evidence lock
(`game/M1_8_EVIDENCE.md`), which has no numeric escape latency (its row E15).

The scorecard design that uses these values is `game/M3_0_FIDELITY_SCORECARD_DESIGN.md`.

## Method

- **Extraction.** An assistant-run literature search extracted every value from text it fetched
  in the same task. Each row carries a verbatim quote and the URL read.
- **Exclusions.** No value comes from memory, from a review, or from reading a figure. A result
  that appears only in a figure is listed as such, without a number.
- **Restored symbols.** PDF font encoding in S1 and S2 mangled some symbols, and they were
  restored in the quotes: "6" to ±, "q" to θ, "a" to α, and the degree sign.
- **Spot checks.** The assistant re-checked the quotes of X08, X15, X16, X21, X22 and X25 against
  the downloaded text.
- **Citations.** The institutional citation service (LibKey) was not available in this
  environment, so sources are identified by DOI.

Confidence:
- **H**: the value was read in the full text.
- **M**: the value comes from a summary, a figure legend, or has incomplete conditions.
- **abstract only**: only the abstract was accessible.

## Sources

| Key | Paper | DOI | Full text read at |
|---|---|---|---|
| S1 | Card & Dickinson 2008, Curr Biol 18:1300 | 10.1016/j.cub.2008.07.094 | faculty.fiu.edu mirror of the publisher PDF |
| S2 | Card & Dickinson 2008, J Exp Biol 211:341 | 10.1242/jeb.012682 | authors.library.caltech.edu (CARjeb08.pdf) |
| S3 | Fotowat, Fayyazuddin, Bellen & Gabbiani 2009, J Neurophysiol 102:875 | 10.1152/jn.00073.2009 | PMC3817277 |
| S4 | von Reyn et al. 2014, Nat Neurosci 17:962 | 10.1038/nn.3741 | janelia.org (advance online publication PDF) |
| S5 | de Vries & Clandinin 2012, Curr Biol 22:353 | 10.1016/j.cub.2012.01.007 | PMC3298569 (author manuscript) |
| S6 | Zacarias et al. 2018, Nat Commun 9:3697 | 10.1038/s41467-018-05875-1 | PMC6135764 |
| S7 | Muijres, Elzinga, Melis & Dickinson 2014, Science 344:172 (Supplementary Materials only) | 10.1126/science.1248955 | authors.library.caltech.edu (Muijres_SM.pdf) |
| S8 | Fischer & Schnell 2022, iScience 25:105143 | 10.1016/j.isci.2022.105143 | PMC9523382 |
| S9 | Dombrovski et al. 2023, Nature 613:534 | 10.1038/s41586-022-05562-8 | PMC9849133 |
| S10 | Chai et al. 2025, Proc R Soc B 292:20241724 | 10.1098/rspb.2024.1724 | PMC12115834 |

Not accessible (HTTP 403, no open copy):
- von Reyn et al. 2017, Neuron, 10.1016/j.neuron.2017.05.036: probability and short-mode fraction
  across r/v.
- Ache et al. 2019, Curr Biol, 10.1016/j.cub.2019.01.079.
- Williamson et al. 2018, Cell Rep, 10.1016/j.celrep.2018.10.048: directional escape model.
- The main text of S7.

## Values

All rows are for *Drosophila melanogaster* unless stated otherwise.

| ID | Quantity | Value as reported | Conditions | Preparation | n | Spread | Source, location | Quote | Conf. |
|---|---|---|---|---|---|---|---|---|---|
| X01 | Escape probability | 96 % jumped | 14 cm black disk falling along a 50° path; accelerating | Free-standing on a 5 x 5 mm platform; 3-day-old females | not stated | - | S1, Results 1 | "Ninety-six percent of the flies responded to the descending disk by jumping into the air and initiating flight." | H |
| X02 | Takeoff latency from stimulus start | 215 ± 42 ms | As X01; takeoff = loss of mesothoracic tarsal contact | As X01 | not stated | SD | S1, Results 1 | "The mean delay between the start of the stimulus and the onset of flight ... was 215 ms ± 42 ms (mean ± SD)." | H |
| X03 | Postural adjustment before takeoff | about 200 ms before takeoff | As X01 | As X01 | - | - | S1, Summary | "approximately 200 ms before takeoff, flies begin a series of postural adjustments that determine the direction of their escape." | H |
| X04 | Takeoff direction, frontal and rear threats | Frontal threat: backward jump; rear threat: forward jump. Per-bin values figure only (Fig. 1F) | α = centre-of-mass direction relative to heading; θ = stimulus azimuth; mirrored; 36° bins | As X01 | not stated | circular SD (figure) | S1, Results 2 | "flies jumped backward in response to looming objects in front of them and jumped forward in response to looming objects behind them" | H |
| X05 | Takeoff direction, lateral threats | About halfway between directly away and directly forward, for 36° < θ < 108° | As X04 | As X01 | not stated | - | S1, Results 2 | "In response to stimuli approaching from the side, however, flies jumped at an angle that was approximately halfway between directly away (α = θ + 180°) and directly forward (α = 0°)" | H |
| X06 | No or partial response | 17 of 147 did not jump | As X01 | Prism platform | 147 | - | S1, Results (Fig. 4) | "Out of the 147 individuals tested, five flies exhibited both leg and wing motion but never jumped ... and six flies exhibited no motion at all." | H |
| X07 | Escape probability in the stimulus window | 95 % within 228 ms | 140 mm disk sliding 190 mm down a rod; 20° to 40° | Pipette tip; 3-day-old mated females | 27 escapes analysed | - | S2, Results | "95% of the flies stimulated with the falling black disk took off between the moment the stimulus was released (t=0) and the time the stimulus reached the end of the rod (t=228 ms" | H |
| X08 | Takeoff latency from stimulus start | median 190.7 ms (IQR 15.3) | As X07 | As X07 | 17 | IQR | S2, Results; Table 1 | "The median escape take-off latency was 190.7 ms (IQR=15.3) from the start of stimulus motion" | H |
| X09 | Stimulus size during the response | 30-40° | As X07 (the stimulus never exceeds 40°) | As X07 | 17 | range | S2, Results | "During this period, the disk diameter had reached a size of 30–40° in the fly's field of view." | H |
| X10 | Wing-leg interval and leg extension | Escape 1.00 (2.67) and 3.33 (0.46) ms; voluntary 34.83 (45.42) and 5.50 (2.00) ms | As X07 | As X07 | 27 escape, 16 voluntary | median (IQR) | S2, Table 1 | "Wing–leg interval (ms) 34.83 (45.42) 1.00 (2.67) ... Leg extension (ms) 5.50 (2.00) 3.33 (0.46)" | H |
| X13 | Escape probability across l/v | 82 % of trials, pooled over l/\|v\| 5-80 ms | Dark square on white; 2-3° to 120-130°; 65 % monocular | Free-standing at a funnel tip; 2-3-day-old wild type | not given | - | S3, Results | "Looming stimuli were highly effective at eliciting escape behaviors in WT Drosophila regardless of their expansion rate in the tested l/\|v\| range, producing jump and flight in 82% of the trials." | H |
| X14 | Escape probability, luminance control | Checkerboard 87 % (wild type) | As X13 | As X13 | not given | - | S3, Results | "PrBW,WT = 82%, PrCB,WT = 87%" | H |
| X15 | Angular size at wing raise and takeoff | Wing raise at 49° (SD 4°); takeoff 6 ms (SD 11) after 54° (SD 5°) | Black square; θ = 2·tan⁻¹(1/slope) | As X13 | not given | SD (Methods say SE) | S3, Results | "on average the WR occurred when the stimulus had reached 49° (SD = 4°) on the retina and TO occurred 6 ms (SD = 11 ms) after the angular size reached 54° (SD = 5°)." | H |
| X16 | Timing law vs l/v (time before collision) | Wing raise slope 2.2 (SD 0.2), intercept 0 ms (SD 10); takeoff slope 2.0 (SD 0.2), intercept -6 ms (SD 11) | As X13 | As X13 | not given | SD | S3, Fig. 2 legend | "WR slope = 2.2 (SD = 0.2) and intercept = 0 ms (SD = 10 ms). TO slope = 2.0 (SD = 0.2) and intercept = −6 ms (SD = 11 ms)." | H |
| X17 | Time to collision at takeoff | 145 ms at l/\|v\| = 60 ms | As X13 | As X13 | - | - | S3, Fig. 1B legend | "average time remaining to collision [TTC] = 145 ms" | H |
| X18 | Wing raise to takeoff | 11 ms (SD 11; median 7.5), constant in l/v | As X13 | As X13 | not given | SD | S3, Results | "the delay between these two events did not significantly change with l/\|v\| and had a mean value of 11 ms (SD = 11 ms; median = 7.5 ms" | H |
| X20 | Threshold in the Discussion (conflicts with X15) | 22 ms after 47° | not specified | As X13 | - | - | S3, Discussion | "22 ms after the looming stimulus reaches a threshold angular size of 47°" | H |
| X21 | Short and long escape modes | Bimodal; minimum at 6.87 ms (< 7 ms = short); means about 5.4 and 13.2 ms | Dark disk 15° to 90°, elevation 45°; r/v 14, 40, 70 ms pooled | Free-standing; 6,000 fps; both sexes | 450 | means only | S4, Fig. 1b legend | "The relative minima (6.87 ms) separated short and long escape modes." | H |
| X22 | Short-mode fraction vs r/v | Rises as r/v falls; slope -19.27 per log(r/v), R² 0.903; per-r/v values figure only | r/v 8, 14, 40, 70, 140 ms | As X21 | 108, 115, 202, 133, 102 | - | S4, Fig. 1f legend | "The fraction of flies choosing a short-mode takeoff was negatively correlated with log(r/v) (slope = −19.27 ms−1, R2 = 0.903" | H |
| X24 | Neural delay to takeoff (fit intercepts) | Short 30.1 ms, long 45.7 ms, GF-silenced 44.5 ms | r/v 8, 14, 40 ms | As X21 | per group | - | S4, Results | "Short escapes ... had a smaller neural delay to takeoff (30.1 ms) than long (45.7 ms) or GF-silenced (44.5 ms) escapes" | H |
| X25 | Takeoff before contact at r/v 8 ms | Short 30 %, long 6 %, GF-silenced 0 % | r/v 8 ms | As X21 | per group | 95 % CI (figure) | S4, Results | "flies using a short escape were significantly more likely to survive (30% takeoff before TOC at r/v = 8 ms) than those employing a long escape or those with silenced GFs (6% and 0% takeoff before TOC at r/v = 8 ms" | H |
| X26 | Giant fiber spike to motor | Leg extension 0.9 ± 0.2 ms, flight start 2.0 ± 0.1 ms after the spike | Dark disk 5° to 90° | Head-fixed, whole-cell recording | 27 trials, 5 flies | unspecified ± | S4, Results | "(0.9 ± 0.2 ms and 2.0 ± 0.1 ms, respectively; 27 of 27 trials in 5 of 5 flies" | H |
| X27 | Escape probability, repeated presentations | 65-76 % of controls | Dark square; up to six presentations per fly | Free-standing | 50 filmed takeoffs | - | S5, Results | "a loom escape response was elicited from approximately 65–76% of control flies, depending on genotype" | M |
| X28 | Escape probability depends on context | 90 % (36/40) after climbing; 6.4 % (384/6000) for repeated inescapable looms while walking | Black disk; l/v 40 ms (see note 1) | Walking arena; Canton-S females | 40; 300 x 20 | - | S6, Results | "In this condition 90% (36/40) of flies jumped in response to the stimulus." | H |
| X29 | Free-flight evasive response latency (*D. hydei*) | 84 ± 17, 75 ± 10, 43 ± 8 ms | Constant angular expansion 0.65, 1.3, 2.1 °/ms | Free flight | 18, 34, 44 | unspecified ± | S7, Supplement | "the response times were 84±17 ms (n=18), 75±10 ms (n=34) and 43±8 ms (n=44)" | H (Supplement) |
| X30 | Evasive saccade, tethered flight | Away from the stimulated side in 62/127 and 74/127 trials | h/v 66.7 ms; ±54° azimuth | Head-fixed tethered flight | 13 flies | - | S8, figure legends | "the fly executed a rapid turn (saccade) away from the stimulated side" | M |

Results shown only in figures, with no number extracted:
- **Direction.**
  - Takeoff direction per azimuth bin: S1 Fig. 1B-F.
  - Polar takeoff histograms for looms at 0°, 90° and 180°: S9 Extended Data Fig. 1b. Its legend
    says flies "takeoff in a direction away from the stimulus (with some influence of the heading
    of the fly)".
- **Mode and timing.**
  - Short-mode percentage per r/v: S4 Fig. 1f.
  - Angular-size thresholds by mode: S4 Fig. 5b.
  - Takeoff before contact vs r/v: S4 Fig. 6g.
- **Takeoff rate.** Takeoff rate at l/v 10-80 ms: S9 Extended Data Fig. 2f.

## Comparability notes

1. **l/v.** The half-size convention holds in S3 and S4. S6 has a factor-of-2 ambiguity. S7 has no
   l/v, because it used constant angular expansion. S1 and S2 used falling disks that accelerate
   and start at about 20°, so their latencies from onset do not compare with constant-l/v looms.
2. **Latency reference.** For constant-l/v looms the invariant reference is the time before
   collision (S3, S4). Latency from stimulus onset depends on the starting size.
3. **Short and long mode.** The modes are defined at 6,000 fps from the first wing-raise motion to
   the last tarsal contact (S4). The 400 fps of S3 cannot resolve the 7 ms boundary.
4. **Thresholds.**
   - S3's Results (49° and 54°) and Discussion (47°) disagree.
   - S3's Methods say SE where the Results say SD.
   - The "about 40°" of S10 cites other work.
5. **Escape probability** depends strongly on the assay: 82-96 % for a single loom on a platform,
   65-76 % with repeated presentations, and 6.4 % for repeated inescapable looms while walking.
6. **Direction.** None of the accessible texts give numeric circular means. In the X04 quote, the
   "respectively" clause appears to swap front and rear relative to the verbal description, so
   only the verbal description is used.
7. **Free-flight data.** S7 is *D. hydei*, and S8 is tethered flight.
