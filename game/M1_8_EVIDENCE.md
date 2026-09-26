# M1.8-R0: Biological Evidence Lock

Research/specification only. Reviewed 2026-09-21 against frozen M1.7.1 commit `cab11842a3375947c5f611cee5433dd565d36a3c`, branch `wip/m1-4-enclosure`. This document refines [the proposal](M1_8_PROPOSAL.md); it does not authorize implementation. No runtime, configuration, calibration, collision, swatter, recorder/replay, experiment or historical result is changed. No training or new neural wiring is proposed for R0.

The evidence supports a richer behavioral repertoire, but does **not** establish a universal flight speed or a natural ROOM activity budget. Numerical observations, inference, model choices and missing evidence are kept separate below. Source IDs identify primary papers; author dissertations are explicitly identified where they supplied accessible original measurements. They are not independent replications of their corresponding papers.

## 1. Scale and measurement contract

Adult *Drosophila melanogaster* total body length is approximately on the order of **2-3 mm**, with sex, genotype, rearing environment and measurement convention affecting size. S01 explicitly uses approximately 2.5 mm for males. S02 establishes genetic and sex variation in component dimensions; its thorax/wing measurements must not be substituted for total body length. The 2-3 mm interval is a rough biological scale and sensitivity bracket, **not** a measured population confidence interval or a guarantee that all adults lie inside it. A matched total-length distribution across rearing conditions remains an evidence gap.

For calculations in this document only, define `L_ref = 2.5 mm/BL`, with sensitivity calculations at 2 and 3 mm/BL. This is a model convention, not a new config value or a universal animal length. The existing `fly.body_length_px = 24` means **24 logical world units per BL**, regardless of display resolution. It is not the collision diameter (`2 * radius = 22`).

```text
distance_BL = distance_logical / 24
speed_BL_per_s = speed_logical_per_s / 24
speed_mm_per_s = speed_BL_per_s * L_ref_mm
speed_m_per_s = speed_BL_per_s * L_ref_mm / 1000
speed_BL_per_s_from_paper = 1000 * speed_m_per_s / L_ref_mm
```

BL/s removes the arbitrary world/display length scale and is the primary gameplay metric. Strictly, it is a body-normalized rate with dimension 1/time, not fully dimensionless unless time is normalized too. Use simulation seconds for biology; wall-clock FPS does not define animal time.

Examples of **conversion, not parameter recommendations**:

| Quantity | BL/s | Logical units/s | Nominal m/s at 2.5 mm/BL | Physical sensitivity at 2-3 mm/BL |
| --- | --- | --- | --- | --- |
| Current EXPLORE target envelope | 5-8 | 120-192 | 0.0125-0.0200 | 0.010-0.024 |
| Current TRANSIT / ODOR_TRACK envelope | 9-13 | 216-312 | 0.0225-0.0325 | 0.018-0.039 |
| Current maximum physical speed | 41.667 | 1000 | 0.10417 | 0.08333-0.12500 |
| Paper speed of 0.15 m/s | 60 nominal; 50-75 by length bracket | 1440 nominal | 0.15 | Length uncertainty changes BL/s, not the measured m/s |

ROOM is a 160 by 90 BL horizontal slice, nominally 400 by 225 mm under this convention; it is not a full-scale domestic room. Current velocity is ground/world-relative. `physical_force_enabled=false` means wind is an environmental/sensory cue with no aerodynamic force. Do not label the current speed as airspeed, or subtract a nominal wind magnitude without a vector-consistent air/ground model. Requested ecological target, applied world target, actual velocity, body heading and course direction are distinct observables.

## 2. Primary evidence table

Confidence refers to the claim **under the source conditions**, not transfer to ROOM. H = direct primary result with checked text/table; M = abstract-level result, approximate summary or incomplete uncertainty metadata. Unknown statistics are explicitly retained as unknown. None of these rows automatically becomes a runtime constant. Unless stated otherwise, all animals below are adult *D. melanogaster*; female behavioral measurements are not automatically male-specific validation of MaleCNS.

### Flight speeds: keep the six contexts separate

| Behavior | Measured quantity | Reported value/range | Species | Experimental context | Free/tethered | Source | Confidence | Applicable to ROOM? | Implementation implication |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E01 Body scale | Total body length | Approximately 2.5 mm male reference; 2-3 mm rough scale, not a confidence interval | D. melanogaster | Male social assay; component-size variation examined separately | Freely moving on substrate | [S01](#s01), [S02](#s02) | M for total-length range | Reference only | Keep 24 logical units/BL; physical conversion must declare its convention |
| E02 Ordinary free flight | Ground-relative intersaccadic speed | 26.7 cm/s checkerboard; 38.1 cm/s horizontal stripes; Table 1 summaries, mean/median aggregation not explicitly labeled there | D. melanogaster | 1 m diameter, 0.6 m high cylinder; water-only controls; food-deprived, mated females aged 2-4 days; 24 replicates/condition | Free | [S04](#s04), Table 1 and Methods | H for reported values; M for aggregation metadata | Conditional comparison, not a default | Visual texture changes the reference; do not treat pooled model constants in this paper as measurements |
| E03 Controlled straight flight | Mean steady groundspeed across wind conditions | Approximately 0.15-0.20 m/s; range of condition means, not individual percentiles | D. melanogaster | 1.5 x 0.3 x 0.3 m tunnel; static visual background, headwinds up to 1 m/s; females aged 2-3 days | Free | [S06](#s06), Results, p. E1186 | H | Conditional visual-speed-control reference | Distinguish fly speed from imposed wind and moving-wall speed |
| E04 Long straight/dispersal flight | Field arrival-based groundspeed inference | Approximately 1 m/s longitudinal regulation; wind-assisted fastest arrivals reach approximately 2.5 m/s | D. melanogaster | Desert releases and baited traps on a 1 km radius ring; arrival distance/time with concurrent wind | Free field dispersal | [S07](#s07), Results | H for study inference; M for individual speed | No direct indoor cruise mapping | These are arrival-based estimates/bounds and a model interpretation, not a tracked mean cruise distribution or a species maximum |
| E05 Wind-tunnel odor tracking | Horizontal airspeed; ground-relative upwind component | Before/after narrow banana-plume contact: airspeed 0.55 +/- 0.11 / 0.59 +/- 0.08 m/s; upwind component 0.090 +/- 0.140 / 0.153 +/- 0.083 m/s; means +/- SD | D. melanogaster | 1.55 x 0.305 x 0.305 m tunnel; 0.4 m/s wind; females aged 3-5 days, food-deprived 20-24 h | Free | [S11](#s11), author thesis pp. 12, 16, 21, 38 | H; primary thesis extraction | Conditional odor-response comparison | Airspeed and upwind groundspeed are different quantities; neither is an ODOR_TRACK setpoint |
| E06 Pre-landing approach | Ground-relative flight speed at 10 cm from post | Landing trajectories 0.37 +/- 0.13 m/s (177 trajectories); fly-bys 0.32 +/- 0.12 (1047); table labels mean/spread as m +/- s | D. melanogaster | Still-air 1.5 x 0.3 x 0.3 m arena, vertical post 1.9 cm diameter; females aged 3-5 days | Free | [S08](#s08), author thesis Table 3.2, pp. 60-61 | H values; spread notation retained | Conditional approach reference | This is upstream approach, not touchdown speed; do not turn it into a fixed LAND speed |
| E07 Final landing | Speed at first leg contact | Average 7.1 +/- 3.2 cm/s, n=30; reported spread retained, not treated as SEM | D. melanogaster | High-speed subset of the same post-landing assay; stopping continued after first contact | Free | [S08](#s08), author thesis p. 70 | H mean; M uncertainty metadata | Conditional contact reference | First contact and complete stop are distinct; published constant-deceleration calculation is not a measured universal acceleration |
| E08 Voluntary takeoff | 3-D COM speed, first 2 ms airborne | 0.28 +/- 0.02 m/s, mean +/- SEM | D. melanogaster | Three-camera 6000 fps launches; 3-day-old mated females; voluntary condition | Free launch | [S09](#s09), author thesis p. 54, Fig. 2.11 | H; figure checked | Different profile warranted, numeric transfer limited | Includes vertical motion; not a 2-D cruise target |
| E09 Visually elicited escape takeoff | 3-D COM speed, first 2 ms airborne | 0.48 +/- 0.01 m/s, mean +/- SEM | D. melanogaster | Same high-speed assay; approaching visual disk elicits escape | Free launch | [S09](#s09), same measurement window | H; figure checked | Different profile warranted, numeric transfer limited | Faster launch with less rotational steadiness under these conditions; not the airborne escape impulse parameter |

E02 excludes short recordings and analyzes flying periods; E06 uses approach-selected trajectories and cannot retain individual identity across the entire recording. They do not estimate whole-day activity budgets. The E04 field model's assumed airspeed bounds are not direct measurements. Do not pool E02-E09 into a universal cruise-speed range, and do not transplant measurements from blowflies, houseflies, mosquitoes or hoverflies.

### Saccades, landing and takeoff sequencing

| Behavior | Measured quantity | Reported value/range | Species | Experimental context | Free/tethered | Source | Confidence | Applicable to ROOM? | Implementation implication |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E10 Saccadic flight | Turn angle and duration | Approximately 90 degrees in less than 100 ms; characteristic description, not a complete distribution | D. melanogaster | Circular laboratory arena with manipulated visual surroundings | Free | [S03](#s03), abstract | M | Architectural support | Preserve distinct rapid turns and comparatively stable intervals; do not impose identical turns |
| E11 Saccade timing | Intersaccadic intervals | 809 ms checkerboard / 826 ms horizontal-stripe condition; Table 1 summaries, aggregation unspecified | D. melanogaster | Same flight assay as E02 | Free | [S04](#s04), Table 1 | M for statistic metadata | Conditional comparator | Saccade detector used 450 degrees/s; rates cannot be compared without matching detection/filtering |
| E12 Saccade occurrence | Pooled event rate | 6613 events / 4814 eligible seconds = 1.37/s; 88 flies; only speed above 5 cm/s retained | D. melanogaster | Circular arena, multi-camera flight tracking | Free | [S05](#s05), event statistics | H | Conditional comparator | Rate is not a periodic timer; its reciprocal is not an interval distribution |
| E13 Landing modules and fly-by | Deceleration cue; angular triggers | Deceleration depends jointly on apparent target size and expansion; leg extension approximately 60 degrees; fly-by aversion approximately 33 degrees | D. melanogaster | Still-air vertical-post assay, trajectory tracking and high-speed landing images | Free | [S08](#s08), abstract and author thesis ch. 3 | H qualitative; M approximate triggers | Modules yes; thresholds require matched geometry | Separate orientation, approach, deceleration, leg extension and contact; retain fly-by branch |
| E14 Takeoff preparation | Wing-opening to leg-extension interval; leg-extension duration | Median (IQR), ms: voluntary 34.83 (45.42) / 5.50 (2.00); escape 1.00 (2.67) / 3.33 (0.46) | D. melanogaster | Same assay as E08/E09 | Free launch | [S09](#s09), author thesis Table 2.1, p. 47 | H; table checked | Sequence distinction only at current resolution | Voluntary wings prepare earlier; escape preparation is compressed; these are not stimulus-to-response latencies |
| E15 Escape action selection | Relationship of GF timing to launch sequence | Short and long escape sequences; no single latency imported here | D. melanogaster | Looming-evoked behavior with targeted neural interventions | Free behavioral launches plus neural assays | [S10](#s10) | H mechanism; no numeric lock | Threat-channel research | Not every threat launch is an identical giant-fiber reflex |

### Odor, feeding and longer activity

| Behavior | Measured quantity | Reported value/range | Species | Experimental context | Free/tethered | Source | Confidence | Applicable to ROOM? | Implementation implication |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E16 Odor encounter / loss | Delay to surge / casting | 190 +/- 75 ms after entry; 450 +/- 165 ms after loss; reported uncertainty retained, not relabeled SD/SEM | D. melanogaster | Odor-plume free flight under varied wind and visual conditions | Free | [S12](#s12), abstract | M for uncertainty definition | Conditional behavioral timescale | Entry debounce is not total response latency; visual feedback matters |
| E17 Repeated encounters | History dependence of heading response | Later encounters elicit weaker upwind responses in the analyzed conditions; no fixed memory duration locked | D. melanogaster subset | Reanalysis/model comparison of wind-tunnel trajectories; mosquito data not transferred | Free | [S13](#s13) | H conditional | Yes, architecture | Preserve recent encounter history; no source-coordinate estimate is supplied |
| E18 Bilateral odor sensing | Odor-gradient steering | Bilateral olfactory input contributes to tracking; no transferable steering gain extracted | D. melanogaster | Antennal manipulation, narrow odor plume and visual stimuli | Magnetic tether, yaw free; translation constrained | [S14](#s14) | H within tether assay | Candidate local signal | Does not justify a global odor-to-source vector or exact ROOM antenna spacing |
| E19 Wind-dependent search | Turn time, angle and frequency | Upwind turn approximately 100 ms; still-air search approximately 60-degree turns at 3-4 Hz; descriptive values | D. melanogaster | Orco optogenetic activation; laminar wind versus still air | Free | [S15](#s15), published abstract and Results | H context; M summaries | Conditional repertoire | Wind reliability gates strategy; static-wind casting is not universal; 2-D ROOM omits sinking |
| E20 Feeding microstructure | Food interaction and ingestion-associated events | Feeding organized into distinguishable events/bouts; no ROOM dwell constant extracted | D. melanogaster | flyPAD food-electrode assay, nutritional-state manipulation | Freely moving on substrate in small assay chambers | [S16](#s16) | H distinction | Yes, separate annotation/mode | Food proximity, food contact and feeding must not be counted interchangeably |
| E21 Post-meal rest | Change in sleep probability after a meal | Elevation lasts approximately 20-40 min, condition-dependent; not a fixed duration for each meal | D. melanogaster | Simultaneous food-volume and activity tracking; control strains, both sexes; arousal tests | Freely moving in constrained chambers | [S17](#s17), Results/Fig. 2 | H in assay | Qualitative non-flight support; no time-budget transfer | Not every stationary fly sleeps; no circadian sleep implementation in M1.8 |
| E22 Long-duration activity measurement | Rest detection and measurement bias | Video and beam-crossing estimates differ with age/genotype and small movements; no flight fraction established | D. melanogaster | Long-duration monitoring, young/old flies, video versus activity monitors | Freely moving in constrained chambers | [S18](#s18) | H | Measurement design only | Separate locomotion, stationary activity, rest and sleep criteria |
| E23 Food-associated local search | Excursions and returns after food cues | Local searches can use self-motion information without external landmarks; no aerial search rate imported | D. melanogaster | Food/optogenetic stimulation; starvation dependence | Free walking and tethered treadmill assays | [S19](#s19) | H walking behavior | Optional future surface-search module | Walking post-food search is not evidence for sinusoidal airborne casting |

## 3. Evidence-supported modules and their limits

### Flight and saccades

Substantial course changes concentrated into discrete events are supported by E10-E12. Small intersaccadic corrections remain possible. Body heading and velocity direction must stay distinct: course-change detectors are not direct body-yaw measurements. The current half-sine actuator and interval mixture are engineering abstractions, not fitted animal distributions. In particular, the 0.3 s duration ceiling and 2.6-6 s long interval component are not established biological bounds by the reviewed evidence. Even a plausible 25-105 degree range is class B until an appropriate distribution and cohort are fitted.

E19 reinforces that turn rates change with sensory context; its still-air search rate must not become the rate of ordinary flight. The current two-dimensional model cannot reproduce banking, pitch, roll, wing mechanics or vertical escape trajectories.

### Landing and fly-by

Proposed modules are **target orientation -> approach -> deceleration / leg preparation -> touchdown -> surface support**. Deceleration and leg extension are separately gated modules, not necessarily a rigid timer sequence. E13 supplies their empirical rationale. Engineering design must use local apparent target size, its derivative, bearing, estimated closing motion and surface affordance; coordinates stay in WORLD. Current `surface_expansion` is a derivative of a contrast/distance/facing-weighted affordance score, **not retinal angular expansion**. The current 0.14 affordance threshold cannot be compared with 60 degrees.

An approach can end in a fly-by, an abort, a failed contact or a landing. Geometry/expansion, relative bearing and target appearance have evidence support. Hunger, remembered value and a probabilistic commitment rule are plausible candidates, but no conditional landing-probability model is locked here. An unconditional coin flip, compulsory landing on every approach, or a fixed landing timer would all be phenomenological. Do not import the landing fraction of a selected laboratory trajectory sample as a ROOM probability.

The approximately 0.2 m/s leg-extension speed cutoff discussed in the S08 thesis is explicitly a **hypothesis**, not an experimentally established trigger. Similarly, its constant-deceleration calculation is not a measured acceleration profile. Neither is released as a parameter. Contact geometry, capture tolerances and any stopping transient require a future specification; R0 does not change frozen collision geometry. First leg contact and complete rest need separate semantics.

### Activity, perching and feeding

E20-E23 justify a repertoire with meaningful non-flight behavior. They do **not** quantify the percentage of time a fly would spend airborne in this ROOM. Small monitoring chambers constrain flight, and hungry flight-tracking cohorts select for flying; neither produces a general natural activity budget.

Minimum future repertoire: **FLYING, LAND_APPROACH, TOUCHDOWN, PERCHED, FEEDING, TAKEOFF**. FEEDING needs a distinct observable state or substate because ingestion requires more than being still on food. PERCHED should mean supported and not feeding; stationary grooming or orientation can be annotated separately. Food interaction can occur without ingestion. A local post-feeding search is a separate optional surface-locomotion module, not an automatic consequence of every meal. Longer rest and sleep require distinct evidence; immobility alone is not sleep. Circadian phase, sleep homeostasis and an energy-metabolism simulator are outside the first implementation scope.

Measure activity fractions over alive simulated time, reporting both quiet and attacked conditions, episode resets, right-censored bouts and animal/seed variation. Report feeding attempts separately from completed feeding; only call an internal quantity simulated intake if its fictional units are stated. Do not optimize the budget to achieve a human hit rate.

### Takeoff

E08/E09/E14 require different voluntary and visually triggered profiles. A future voluntary launch can combine local support, a phenomenological motivational variable and readiness; a threat launch must use the existing legitimate neural threat signal. These are design abstractions, not new claims about a specific initiation circuit. E15 rules out treating all visually triggered launches as one stereotyped neural program.

At `tick_seconds=0.02`, neither the 2 ms speed window nor the shorter preparation intervals can be resolved directly. A future launch must either be explicitly coarse-grained with integrated effects, or use an independently justified fly-side time resolution without changing the frozen swatter timing. Do not silently multiply published timing to make an animation visible. Voluntary and threat launch types can share a TAKEOFF mode with a cause/profile tag; they need not become two top-level enums.

### Odor controller audit

Current `EcologicalSense` contains local concentration, its derivative, a bilateral difference, body-relative wind and visual proxies. Current ecology uses concentration hysteresis and body-relative wind, but **does not consume `odor_rate` or `odor_bilateral`**. This is an architectural opportunity, not evidence that either unused signal already affects behavior.

The scalar concentration is not a bearing. The wind vector is an ideal estimate of ambient flow rotated into body coordinates, not apparent airflow measured by an antenna. It does not reveal source coordinates, but is more informative than an unprocessed animal measurement. Future imperfect wind estimation should retain this distinction and include a reliability variable. E19 means no-wind/uncertain-wind behavior needs a separately declared choice; current validation requires positive wind.

The current ODOR_SEARCH target oscillates around **upwind**, with amplitude 1.05 rad (about 60 degrees). It is therefore not automatically a faithful alternating crosswind course. E16 motivates delayed casting, but not the 3.6 s sine period. A visual-contrast multiplier is also not an optic-flow feedback controller. E17 adds history dependence to the reflex picture; it does not establish a universal memory horizon or an internal global map. Future comparisons should distinguish encounter onset, response initiation and completed reorientation rather than equating all delays.

## 4. Parameter classification and frozen implementation audit

The **R0 evidence classes** are:

- **A:** direct numerical measurement, with matching quantity, context and traceable statistic.
- **B:** literature-inspired mechanism; numerical value/distribution is phenomenological.
- **C:** engineering, scene construction, numerical safety or gameplay choice.
- **D:** temporary placeholder for an unimplemented behavior.

These letters do **not** reuse the different architectural A/B/C/D categories in existing code comments (for example, code category C means the threat pathway). No current ecological numerical value is promoted to evidence class A simply because it resembles a published value. A verified repository constant is not thereby a biological measurement.

The inventory below is generated from the frozen ROOM config. Numeric arrays remain one parameter; object fields are expanded individually. It covers every non-comment leaf of `sim`, `world`, `fly`, `saccades`, `flight`, `arena`, `spawn`, `room`, `ecology`, and `policy`. The frozen `brain`, `encoder` and `swatter` sections are outside ecological parameter selection; they are not biologically retuned or endorsed by this inventory.

Config SHA256: `7ca805cf7d393f075a75ff02bb91643cea810161321da63017dba8ae7f01b3e2`. Inventory: **147 parameter records** (array entries remain grouped).

| Config path | Frozen value | R0 class | Reason / interpretation |
| --- | --- | --- | --- |
| `sim.tick_seconds` | `0.02` | C | Integration cadence / reproducible seed; not biological randomness. |
| `sim.seed` | `20260917` | C | Integration cadence / reproducible seed; not biological randomness. |
| `world.width` | `3840` | C | Frozen arena geometry / display lifecycle in logical units or seconds. |
| `world.height` | `2160` | C | Frozen arena geometry / display lifecycle in logical units or seconds. |
| `world.margin` | `48` | C | Frozen arena geometry / display lifecycle in logical units or seconds. |
| `world.splat_seconds` | `1.6` | C | Frozen arena geometry / display lifecycle in logical units or seconds. |
| `fly.radius` | `11.0` | C | Collision disk radius in logical units; not body length. |
| `fly.damping_per_second` | `3.0` | C | Velocity relaxation gain, not an aerodynamic coefficient. |
| `fly.max_speed` | `1000.0` | C | Physical speed cap, not a species flight maximum. |
| `fly.escape_impulse` | `880.0` | C | Velocity-increment scale before damping/capping; not E09 takeoff speed. |
| `fly.escape_forward_bias` | `0.35` | C | Engineered neural-action direction mapping. |
| `fly.turn_rate` | `4.0` | C | Scale from policy turn command to yaw rate. |
| `fly.wander_interval_seconds` | `1.6` | B | Random-wander scheduling; curvature replaces its drift in this ROOM. |
| `fly.baseline_speed` | `216.0` | C | Fallback/active-threat tonic target: 9 BL/s, not measured cruise. |
| `fly.wander_turn_rate` | `0.08` | B | Random drift amplitude; superseded by configured curvature in ROOM. |
| `fly.wander_turn_tau_seconds` | `0.8` | B | Random drift smoothing; superseded by configured curvature in ROOM. |
| `fly.max_yaw_rate` | `31.0` | C | Final actuator cap in rad/s; not a biological maximum. |
| `fly.body_length_px` | `24.0` | C | Logical units per BL; display-independent model scale. |
| `fly.curvature.amplitudes_rad_s` | `[0.16, 0.06]` | B | Hand-selected background yaw amplitudes; no fitted intersaccadic curvature. |
| `fly.curvature.periods_seconds` | `[7.0, 13.0]` | B | Deterministic periods with random phases, not measured oscillations. |
| `fly.sideslip.max_degrees` | `80.0` | C | Kinematic slip bound; no matched biological limit. |
| `fly.sideslip.realignment_tau_seconds` | `0.28` | B | Phenomenological body/course realignment, not aerodynamic dynamics. |
| `saccades.enabled` | `true` | C | Actuator switch. |
| `saccades.min_duration_seconds` | `0.06` | C | Minimum pulse duration; tick-resolution choice, not universal minimum. |
| `saccades.max_duration_seconds` | `0.3` | C | Actuator feasibility ceiling; extends beyond E10 characteristic turn time. |
| `saccades.max_degrees` | `120.0` | C | Requested-turn clipping bound. |
| `saccades.peak_rate_cap_deg_per_second` | `1500.0` | C | Actuator peak-rate safety cap, not measured maximum. |
| `saccades.alert_max_degrees` | `55.0` | C | Frozen neural-action-to-pulse amplitude/rate mapping, not an animal measurement. |
| `saccades.alert_peak_rate_deg_per_second` | `900.0` | C | Frozen neural-action-to-pulse amplitude/rate mapping, not an animal measurement. |
| `saccades.escape_max_degrees` | `110.0` | C | Frozen neural-action-to-pulse amplitude/rate mapping, not an animal measurement. |
| `saccades.escape_peak_rate_deg_per_second` | `1350.0` | C | Frozen neural-action-to-pulse amplitude/rate mapping, not an animal measurement. |
| `flight.interval.short_seconds` | `[0.3, 0.7]` | B | Uniform component of hand-selected eligible-clock mixture. |
| `flight.interval.ordinary_seconds` | `[0.8, 1.9]` | B | Uniform component; E11/E12 do not identify these endpoints. |
| `flight.interval.long_seconds` | `[2.6, 6.0]` | B | Unfitted tail component; cannot label 6 s a biological upper bound. |
| `flight.interval.short_probability` | `0.28` | B | Unfitted mixture probability. |
| `flight.interval.long_probability` | `0.18` | B | Unfitted mixture probability; ordinary probability is residual 0.54. |
| `flight.interval.perimeter_multiplier` | `1.7` | B | Wall-context schedule modifier, not measured interval scaling. |
| `flight.correction.degrees` | `[5.0, 18.0]` | B | Unfitted correction-angle interval. |
| `flight.correction.peak_rate_deg_per_second` | `[250.0, 600.0]` | B | Unfitted correction peak-rate interval. |
| `flight.correction.probability` | `0.42` | B | Unfitted correction-versus-saccade mixture. |
| `flight.saccade.degrees` | `[25.0, 105.0]` | B | Saccade architecture supported by E10; endpoints not measured quantiles. |
| `flight.saccade.peak_rate_deg_per_second` | `[700.0, 1400.0]` | B | Unfitted peak-rate interval; no speed/angle covariance fitted. |
| `flight.boundary.sense_range` | `150.0` | C | Finite geometric proxy horizon in logical units. |
| `flight.boundary.avoid_time_to_contact_seconds` | `0.55` | B | TTC-motivated avoidance threshold, not E13 landing threshold. |
| `flight.boundary.avoid_inward_degrees` | `14.0` | B | Chosen tangent/inward bias, not an observed turn-angle statistic. |
| `flight.boundary.avoid_refractory_seconds` | `0.2` | C | Avoidance chatter suppression. |
| `flight.boundary.avoid_peak_rate_deg_per_second` | `[700.0, 1300.0]` | B | Unfitted avoidance pulse-rate interval. |
| `flight.boundary.perimeter_enter_proximity` | `0.45` | B | Hysteresis on synthetic nearness, not measured wall-following onset. |
| `flight.boundary.perimeter_leave_proximity` | `0.2` | B | Hysteresis on synthetic nearness, not measured departure onset. |
| `flight.boundary.patience_seconds` | `[1.2, 4.5]` | B | Forced perimeter-departure timer, not a fitted hazard. |
| `flight.boundary.depart_degrees` | `[40.0, 85.0]` | B | Unfitted departure-angle interval. |
| `flight.boundary.depart_peak_rate_deg_per_second` | `[600.0, 1100.0]` | B | Unfitted departure peak-rate interval. |
| `arena.name` | `"room"` | C | ROOM identity / logical body-length scene scale. |
| `arena.width_body_lengths` | `160` | C | ROOM identity / logical body-length scene scale. |
| `arena.height_body_lengths` | `90` | C | ROOM identity / logical body-length scene scale. |
| `spawn.randomized` | `true` | C | Reproducible initialization and clearance, not a natural launch distribution. |
| `spawn.wall_clearance_body_lengths` | `6.0` | C | Reproducible initialization and clearance, not a natural launch distribution. |
| `spawn.swatter_clearance_body_lengths` | `3.0` | C | Reproducible initialization and clearance, not a natural launch distribution. |
| `spawn.speed_fraction` | `[0.8, 1.05]` | C | Reproducible initialization and clearance, not a natural launch distribution. |
| `spawn.max_slip_degrees` | `12.0` | C | Reproducible initialization and clearance, not a natural launch distribution. |
| `room.wind.speed` | `45.0` | C | World transport/cue speed in logical units/s; not a biological flight speed. |
| `room.wind.direction_degrees` | `0.0` | C | Chosen scene wind direction. |
| `room.wind.direction_amplitude_degrees` | `12.0` | B | Analytic wind variability, not a measured wind distribution. |
| `room.wind.direction_period_seconds` | `45.0` | B | Deterministic wind-direction period. |
| `room.wind.speed_fraction` | `0.15` | B | Fractional sine modulation; no measured turbulence. |
| `room.wind.speed_period_seconds` | `31.0` | B | Deterministic wind-speed period. |
| `room.wind.physical_force_enabled` | `false` | C | False: wind is a cue/transport field only; true is currently rejected. |
| `room.food.x` | `1050.0` | C | Chosen WORLD-side source geometry; never a controller input. |
| `room.food.y` | `1120.0` | C | Chosen WORLD-side source geometry; never a controller input. |
| `room.food.radius` | `65.0` | C | Chosen WORLD-side source geometry; never a controller input. |
| `room.food.emission_strength` | `3.0` | C | Arbitrary odor units, not a chemical concentration. |
| `room.food.base_width` | `100.0` | B | Analytic plume width in logical units; not fitted to an odorant. |
| `room.food.spread` | `0.09` | B | Analytic plume spread coefficient; no measured dispersion model. |
| `room.food.decay_length` | `2400.0` | B | Analytic downwind decay scale in logical units. |
| `room.food.upwind_softness` | `60.0` | C | Smooth field boundary scale. |
| `room.food.meander_amplitude` | `45.0` | B | Analytic lateral plume modulation in logical units. |
| `room.food.meander_period_seconds` | `11.0` | B | Deterministic plume meander period. |
| `room.food.intermittency_fraction` | `0.35` | B | Sinusoidal concentration modulation, not measured whiff intermittency. |
| `room.food.intermittency_period_seconds` | `9.0` | B | Deterministic concentration modulation period. |
| `room.food.landing_surface` | `true` | D | Affordance eligibility only; no supporting-contact mechanics. |
| `room.objects[0].name` | `"column"` | C | Scene object identity, geometry, appearance or solid-contact switch; WORLD only. |
| `room.objects[0].x` | `2480.0` | C | Scene object identity, geometry, appearance or solid-contact switch; WORLD only. |
| `room.objects[0].y` | `780.0` | C | Scene object identity, geometry, appearance or solid-contact switch; WORLD only. |
| `room.objects[0].radius` | `95.0` | C | Scene object identity, geometry, appearance or solid-contact switch; WORLD only. |
| `room.objects[0].contrast` | `1.0` | C | Scene object identity, geometry, appearance or solid-contact switch; WORLD only. |
| `room.objects[0].solid` | `true` | C | Scene object identity, geometry, appearance or solid-contact switch; WORLD only. |
| `room.objects[0].landing_surface` | `false` | C | Scene object identity, geometry, appearance or solid-contact switch; WORLD only. |
| `room.objects[1].name` | `"perch"` | C | Scene object identity, geometry, appearance or solid-contact switch; WORLD only. |
| `room.objects[1].x` | `2850.0` | C | Scene object identity, geometry, appearance or solid-contact switch; WORLD only. |
| `room.objects[1].y` | `1610.0` | C | Scene object identity, geometry, appearance or solid-contact switch; WORLD only. |
| `room.objects[1].radius` | `75.0` | C | Scene object identity, geometry, appearance or solid-contact switch; WORLD only. |
| `room.objects[1].contrast` | `0.8` | C | Scene object identity, geometry, appearance or solid-contact switch; WORLD only. |
| `room.objects[1].solid` | `false` | C | Scene object identity, geometry, appearance or solid-contact switch; WORLD only. |
| `room.objects[1].landing_surface` | `true` | D | Visual landing affordance flag; supporting/perching mechanics absent. |
| `room.sensing.antenna_half_spacing` | `6.0` | B | Ideal sample spacing in logical units; E18 does not calibrate it. |
| `room.sensing.visual_range` | `450.0` | C | Attenuation length for ideal local cues, not eye resolution. |
| `room.sensing.background_contrast` | `0.6` | C | Synthetic contrast floor, not a matched visual stimulus. |
| `room.sensing.derivative_tau_seconds` | `0.12` | C | Numerical sensory filter; contributes to end-to-end latency. |
| `room.sensing.derivative_cap` | `20.0` | C | Derivative clipping bound for proxy signals. |
| `ecology.enabled` | `true` | C | Feature switch. |
| `ecology.odor_on` | `0.1` | B | Arbitrary concentration threshold; no ppm/receptor calibration. |
| `ecology.odor_off` | `0.065` | B | Hysteresis in arbitrary concentration units. |
| `ecology.encounter_dwell_seconds` | `0.12` | B | Debounce choice; not the total encounter-to-action delay in E16. |
| `ecology.loss_dwell_seconds` | `0.45` | B | Resembles E16 casting delay, but threshold debounce has different semantics and added downstream delays. |
| `ecology.search_seconds` | `6.0` | B | Fixed search expiry; no matched persistence distribution. |
| `ecology.odor_bout_seconds` | `8.0` | B | Forces departure despite continued odor; no fitted biological bout law. |
| `ecology.relocation_seconds` | `4.0` | B | Ignores detected odor for this duration; anti-sticking convention. |
| `ecology.recover_seconds` | `1.2` | B | Escape recovery duration; no matched recovery measurement. |
| `ecology.explore_duration_seconds` | `[3.0, 7.0]` | B | Uniform dwell draw, not an observed activity-budget distribution. |
| `ecology.transit_duration_seconds` | `[2.0, 5.0]` | B | Uniform dwell draw, not an observed activity-budget distribution. |
| `ecology.speed_bl_s.EXPLORE` | `[5.0, 8.0]` | B | Unfitted BL/s target envelope; not measured percentiles or guaranteed actual speed. |
| `ecology.speed_bl_s.TRANSIT` | `[9.0, 13.0]` | B | Unfitted BL/s target envelope; not measured percentiles or guaranteed actual speed. |
| `ecology.speed_bl_s.ODOR_SEARCH` | `[4.0, 7.0]` | B | Unfitted BL/s target envelope; not measured percentiles or guaranteed actual speed. |
| `ecology.speed_bl_s.ODOR_TRACK` | `[9.0, 13.0]` | B | Unfitted BL/s target envelope; not measured percentiles or guaranteed actual speed. |
| `ecology.speed_bl_s.LAND_OR_PERCH` | `[1.0, 3.0]` | D | Positive approach placeholder, not perching. |
| `ecology.speed_bl_s.ALERT` | `[8.0, 12.0]` | B | Unfitted BL/s target envelope; not measured percentiles or guaranteed actual speed. |
| `ecology.speed_bl_s.ESCAPE` | `[12.0, 18.0]` | B | Unfitted BL/s target envelope; not measured percentiles or guaranteed actual speed. |
| `ecology.speed_bl_s.RECOVER` | `[5.0, 8.0]` | B | Unfitted BL/s target envelope; not measured percentiles or guaranteed actual speed. |
| `ecology.speed_tau_seconds` | `0.5` | B | Target-speed smoothing, distinct from world velocity damping. |
| `ecology.steering_tau_seconds` | `0.18` | B | Steering smoothing; not a measured neural time constant. |
| `ecology.steering_cap_rad_s` | `0.9` | C | Bound on ecological yaw command. |
| `ecology.upwind_gain` | `1.3` | B | Anemotaxis-inspired proportional gain; E05/E16/E19 do not fix it. |
| `ecology.search_period_seconds` | `3.6` | B | Unfitted sine period; E16 does not imply periodic casting. |
| `ecology.search_amplitude_radians` | `1.05` | B | Angle about upwind, not a measured crosswind-heading distribution. |
| `ecology.visual_gain_floor` | `0.15` | B | Contrast scaling of steering, not calibrated optic-flow feedback. |
| `ecology.landing_affordance_threshold` | `0.14` | D | Weighted visibility-score threshold; not retinal size in degrees. |
| `ecology.landing_dwell_seconds` | `0.16` | D | Approach eligibility debounce; no implemented touchdown. |
| `ecology.landing_attempt_seconds` | `0.9` | D | Timeout for moving approach placeholder, not a landing duration. |
| `ecology.landing_cooldown_seconds` | `8.0` | D | Placeholder retry suppression, not measured perch residence. |
| `ecology.spontaneous_clock_rate.EXPLORE` | `1.0` | B | Chosen eligible-clock multiplier; not a measured context-specific event-rate ratio. |
| `ecology.spontaneous_clock_rate.TRANSIT` | `0.45` | B | Chosen eligible-clock multiplier; not a measured context-specific event-rate ratio. |
| `ecology.spontaneous_clock_rate.ODOR_SEARCH` | `1.35` | B | Chosen eligible-clock multiplier; not a measured context-specific event-rate ratio. |
| `ecology.spontaneous_clock_rate.ODOR_TRACK` | `0.35` | B | Chosen eligible-clock multiplier; not a measured context-specific event-rate ratio. |
| `ecology.spontaneous_clock_rate.LAND_OR_PERCH` | `0.0` | D | Placeholder suppresses turns during approach. |
| `ecology.spontaneous_clock_rate.ALERT` | `0.0` | B | Chosen eligible-clock multiplier; not a measured context-specific event-rate ratio. |
| `ecology.spontaneous_clock_rate.ESCAPE` | `0.0` | B | Chosen eligible-clock multiplier; not a measured context-specific event-rate ratio. |
| `ecology.spontaneous_clock_rate.RECOVER` | `0.7` | B | Chosen eligible-clock multiplier; not a measured context-specific event-rate ratio. |
| `ecology.alert_recover_seconds` | `0.2` | B | Alert recovery duration; no matched recovery measurement. |
| `policy.escape_threshold` | `null` | C | Null delegates to exact-provenance empirical simulation calibration; not a biological voltage threshold. |
| `policy.calibration_paths` | `["artifacts/game/calibration_room_m1_7_1.json", "results/game/calibration_room_m1_7_1.json"]` | C | Record lookup paths; no recalibration in R0. |
| `policy.refractory_seconds` | `0.4` | C | Frozen action refractory; not takeoff preparation from E14. |
| `policy.turn_gain` | `0.8` | C | Frozen readout-to-action gain. |
| `policy.alert_threshold_fraction` | `0.55` | C | Frozen alert mapping relative to calibrated escape threshold. |
| `policy.steering_tau_seconds` | `0.12` | C | Frozen policy smoothing, not measured neural kinetics. |
| `policy.alert_saccade_strength` | `0.6` | C | Frozen action amplitude mapping. |
| `policy.saccade_interval_seconds` | `0.8` | C | Frozen neural-request pacing, not spontaneous E11 intervals. |
| `policy.alert_saccade_dwell_seconds` | `0.06` | C | Frozen alert persistence gate, not biological latency. |

### Hard-coded rules and effective behavior

| Location / rule | Current value or semantics | R0 class | Consequence |
| --- | --- | --- | --- |
| `ecology.py` speed modulation | Shared 8 s sinusoid between each state's limits; random initial phase | B | No measured oscillation supports its period or shape; envelopes are not empirical quantiles |
| Ecological state dwell | Uniform explore/transit draws; odor bout can force departure despite odor | B | Artificial persistence/relocation, not evidence-driven motivation |
| `ecology.py` landing eligibility | Affordance above threshold, increasing affordance, detected odor | D | Blocks odorless perching and has no contact confirmation |
| `ecology.py` obstacle steering | Gain 2; fallback if absolute turn <0.01 and front score >0.08; seeded side | B | Hand-selected local avoidance rule |
| Ecology command bounds | Nonnegative speed; clock rate 0-2; absolute steer <=2 rad/s | C | Interface validation, not biological limits |
| `room.py` visual projection | `2*atan2(radius,distance)/pi`, exponential attenuation; front weight cosine^4, landing weight cosine^2 | B | Ideal geometric proxies; neither a complete eye nor a calibrated landing sensor |
| `room.py` derivatives | Exponential filtering and clipping of concentration / weighted affordance derivatives | C | Pipeline delay must be included when comparing E16 |
| `room.py` plume | Analytic Gaussian cross-section, softplus downstream distance, tanh gate, deterministic sinusoidal modulation | B | Not CFD, not measured turbulent whiff statistics; emission units arbitrary |
| WORLD-only scene access | Food/object coordinates remain in environment/projector; controller receives local summaries | C | Correct information boundary; it does not make the sensor biologically validated |
| `room.py` spawn clearance | Additional 24 logical units from solid objects | C | Initialization safety |
| Random streams | Environment seed+6011, ecology seed+7013, flight seed+3907 | C | Reproducibility, not independent animals by itself |
| `flight.py` spontaneous scheduler | Eligible clock pauses during pulse/neural activity; ecological multiplier changes clock | B | Config interval distribution is not the realized wall-clock interval distribution |
| `saccade.py` pulse | Half sine; duration max(minimum, abs(angle)*pi/(2*peak)); reject infeasible duration | B | Motion convention; do not equate requested peak with achieved peak at minimum duration |
| `saccade.py` priority | CORRECTION 1; SACCADE/DEPART 2; AVOID/ALERT 3; ESCAPE 4 | C | Priority/preemption design |
| `world.py` speed arbitration | Active neural action or ALERT/ESCAPE pulse replaces ecology target with baseline 216 units/s | C | ALERT/ESCAPE ecological target ranges are not necessarily applied speeds |
| `world.py` neural activity test | escape, saccade, or abs(turn)>0.03 | C | Arbitration threshold, not an animal neural threshold |
| `world.py` escape impulse | Normalize direction; add `880 * strength` to velocity before damping/capping | C | Impulse is a velocity increment, not a takeoff speed measurement |
| `world.py` tonic drive | Euler velocity relaxation with damping 3/s, then cap at 1000 units/s | C | Actual speed differs from command; no aerodynamic model |
| `world.py` curvature | Configured sinusoids replace filtered random wander when present | B | Wander values remain configured but curvature controls drift in shipped ROOM |
| Wall sensing / containment | Local inverse-TTC proxy, proximity and bearings; hard clamp/slide after failed avoidance | C | Geometry is not a measured reflex; hard containment is not a neural response |
| Landing actuation | Command only marks an approach attempt; all state speed lower limits >0 | D | No supported contact, stationary perch, ingestion or takeoff exists yet |

Machine epsilons used for zero distances, finite arithmetic and collision-root tolerances are class C numerical safeguards, not behavioral parameters. Their exact values remain in frozen source, and R0 does not reinterpret them as biological constants.

The clearest arbitrary biological-looking values are the shared 8 s speed cycle, independent uniform explore/transit timers, 8 s forced odor departure with 4 s odor ignoring, 6 s search expiry, 3.6 s sinusoidal casting, 0.9 s approach timeout, 8 s landing cooldown, and the 7/13 s curvature periods. Odor thresholds have arbitrary concentration units. All state speed envelopes and spontaneous-clock multipliers lack matched numerical fits. These are documented limitations, **not authorization to retune frozen M1.7.1**.

## 5. Proposed hierarchy: design only

```text
Phenomenological motivation/context + local encounter/contact history
                              |
Legal local sensory evidence (odor, wind estimate/confidence, vision, support)
                              |
Mode manager + behavior modules -> candidate flight/surface command
                              |
Frozen MaleCNS threat/action -> arbitration -> fly kinematics/contact dynamics
                              |
                 next local sensory observation
```

Threat arbitration must occur **before** applying a candidate ecological command, not as an after-the-fact position correction. The exact existing threat behavior stays frozen. Future interaction with surface support requires an explicit integration design; this diagram is not a request to alter its thresholds or action interface.

| Concept | Suggested representation | Transition evidence / role |
| --- | --- | --- |
| FLYING | Top-level locomotor mode | Airborne with no supporting contact |
| LAND_APPROACH | Reversible flight submode, separately logged | Local surface evidence, apparent size/expansion, bearing and feasible closing motion; abort on lost/unsafe evidence |
| TOUCHDOWN | Contact event plus short transient if dynamics require it | WORLD detects physical contact; controller sees a local support/contact result, not target coordinates |
| PERCHED | Supported mode with non-feeding activity tag | Valid support and completed landing; minimum dwell only prevents chatter |
| FEEDING | Explicit supported substate/mode and observable bout | Local food contact/taste proxy plus permissive motivation; terminate on withdrawal, support loss, satiation proxy or threat |
| TAKEOFF | Launch mode with VOLUNTARY or THREAT cause | Voluntary readiness/context versus legitimate neural threat; distinct preparation profiles |
| EXPLORE / TRANSIT | Intent labels or continuous persistence/speed preferences within FLYING | Local cue availability, history and bounded phenomenological motivation; not compulsory timer alternation |
| ODOR_SURGE / ODOR_TRACK | Encounter-driven navigation module | Recent odor encounters, body-relative wind estimate/confidence and visual self-motion; TRACK can be telemetry rather than enum |
| ODOR_SEARCH | History-conditioned search module | Time since loss and encounter history modulate search; reacquisition closes the loop |
| ALERT / ESCAPE | Orthogonal frozen neural threat channel | Not duplicated as ecological decision states; can preempt flight or request a threat launch when supported |
| RECOVER | Continuous relaxation/readiness variable, optionally logged phase | Threat cessation, velocity/support and time since action; safety refractory allowed |
| Hunger, persistence, confidence, readiness | Bounded continuous model variables | Explicitly phenomenological without an implemented/validated circuit or metabolic assay |
| Leg extension / deceleration | Independently gated landing submodules | Different local visual evidence; leg preparation is not proof of touchdown |
| Post-feeding local search | Optional surface module, outside minimum implementation | Requires walking/support design and self-motion history; no food-coordinate waypoint |

A contact-conditioned surface mode is preferable to multiplying every ecological intent by every threat enum. Feeding must remain independently measurable even if implemented under a common supported superclass. No mode manager may import food coordinates, mouse position, click state, target identity or a global map. WORLD can use geometry to create local cues and determine physical outcomes. Controller history may retain experienced cues and self-motion, not privileged source locations.

Timers are allowed for numerical debouncing, minimum dwell, refractory periods and safety timeouts, with class C bounds. They must not be the main claim of why the fly changes motivation. A future stochastic hazard for voluntary departure is acceptable only as a declared phenomenological decision conditioned on available history, with seeds and bounded sensitivity tests; it is not a measured neural decision law.

## 6. Neural claim boundary and candidate research

Current validated model path: **WORLD visual projection -> Retina -> LC4/LPLC2 feature-neuron stimulation -> frozen MaleCNS-derived dynamics -> DNp01/DNa02 readout -> fixed threat/action mapping**. Retina is a model sensory bottleneck, not a complete compound-eye image-processing system. With `sensory_input=false`, incoming sensory-neuron edges are removed: original dataset **25,582,938** connections; current game runtime approximately **25,088,107**. Neither the runtime graph nor its output dynamics should be described as an untouched/full biological brain.

The existing readout-to-action mapping is engineered. A named DN or an anatomical connection does not by itself prove the action is its natural flight function. Ecological EXPLORE, food search, wind estimation, landing attempts and tonic motion are currently external phenomenology. Feeding and voluntary takeoff are not implemented. No claim that the connectome learned these behaviors is permitted.

| Candidate | Primary evidence to investigate | Limit before any future wiring |
| --- | --- | --- |
| Olfaction: ORNs, antennal-lobe local/projection neurons, downstream lateral-horn / mushroom-body pathways | [S20](#s20) establishes interactions between olfactory processing channels; [S15](#s15) links Orco activation to flight search | Identify MaleCNS cells, sensory encoding, odor identity/valence and downstream action readout; topology alone is insufficient |
| Central-complex heading/navigation: E-PG and related CX networks | [S21](#s21) landmark/self-motion heading activity; [S22](#s22) candidate CX connectivity motifs | Walking tether evidence is not proof of ROOM flight navigation; coordinate conventions and required inputs need validation |
| Flight initiation: GF/DNp01 and parallel non-GF takeoff pathways | [S09](#s09), [S10](#s10) distinguish launch performance and action selection | Escape evidence does not identify a complete spontaneous-launch circuit; voluntary initiator remains open |
| Landing: DNp07 / DNp10 and their visual/state-dependent inputs | [S23](#s23) landing-related leg extension with flight-state gating | Does not alone implement approach, deceleration, contact or feeding; cell availability and mapping need verification |

These are candidate circuits, not additions to the current encoder. R0 neither trains nor rewires them. The architectural boundary is preserved even if later phenomenological behavior looks convincing.

## 7. Parameter release policy for a later milestone

Every new numerical parameter must have a record containing: name and units; evidence class; E/S reference or explicit GAME decision ID; measured quantity; species/sex/age/state; arena and wind/visual conditions; free/tethered; air/ground frame; mean/median/quantile and uncertainty type; exact table/figure/page; extraction method/version; conversion formula; ROOM applicability; selected bounds and validation plan. Use source-body-length uncertainty separately from measurement uncertainty. An inferred mean, digitized point, model fit and measured maximum are different records.

For example: **under the E05 narrow-plume assay, S11 measured a change in horizontal airspeed**; a later ROOM surge target requires its own mapping decision. Do not write "real Drosophila speed = X". Do not label a gameplay distribution as a biological prior merely because its bounds overlap one paper.

When evidence is insufficient, a bounded phenomenological choice is legitimate if named as such. It must declare finite bounds, units, initial value, reason, sensitivity range and failure criteria before code is accepted. R0 deliberately does not assign new speed, perch-duration or feeding-duration defaults. Suggested design bounds such as nonnegative speed, probability in [0,1], or separate contact/no-contact modes are mathematical/interface constraints, not empirical biology.

Later validation should compare conditional distributions, not just means: quiet versus threatened flight, speed versus visual geometry, turn angle/duration/intervals, land/fly-by/abort outcomes, supported-time fraction, feeding bouts and voluntary/threat launches. Use matched stimulus conditions and seed-level uncertainty. Preserve unchanged replay/contact regression cases. Proposed controls include constant-speed and timer-only phenomenological baselines, odor absent, visual contrast reduced, wind reliability varied, encounter history ablated and bilateral cue ablated. Those are **future tests**, not R0 runs or authorization to change the frozen system.

## 8. Questions that remain open before implementation

1. Which quiet ROOM context is the intended comparator: short food-seeking flights in a small enclosure, or longer transit? What sex, age, strain, hunger state, illumination and observation window define it?
2. What joint distribution of airborne, perched, walking, feeding and stationary non-feeding time exists in an enclosure that actually permits flight? Existing flight-selected and constrained-chamber studies cannot supply that budget.
3. Will physical scale be nominal 2.5 mm/BL with sensitivity reporting, or matched to a measured cohort? What total-length convention and rearing-condition distribution should be used?
4. Which speed statistics transfer after accounting for arena/texture/wind? E02 aggregation and E06/E07 spread definitions need explicit metadata before numerical fitting; do not turn unspecified spreads into a sampler.
5. What local observations discriminate landing commitment from fly-by, and with what conditional probability? Are target texture, orientation and feeding state sufficient in a matched assay?
6. How will a horizontal slice represent supporting surfaces, leg extension, failed landings and contact-to-stop dynamics without altering frozen collision geometry or creating invulnerable perches? This needs an explicit scope decision before implementation.
7. What are distributions of perch residence, feeding bouts and voluntary departure under those conditions? How will a simulation distinguish food contact from actual simulated intake?
8. Which fly-side coarse-graining faithfully preserves a launch while the simulation tick is 20 ms? Which 3-D launch quantities can legitimately project into horizontal velocity?
9. How should the current ideal ambient-wind signal acquire uncertainty, and what behavior applies when direction is unreliable or absent? The existing field cannot represent still air.
10. What encounter-history horizon and bilateral-odor gain are supported for free flight, rather than tethered turning? What sensor/filter delay separates odor thresholds from observed response latency?
11. What observed saccade distributions, including correlations with speed/geometry, should replace the arbitrary interval mixture if a later implementation requests this? The detector and smoothing protocol must match.
12. Which candidate MaleCNS identities and downstream pathways are actually present and functionally supported? Until validated, ecological control and voluntary takeoff remain phenomenological.

These gaps prevent a claim of quantitatively validated biological ROOM behavior. They do not prevent a later explicitly authorized, clearly labeled phenomenological prototype. R0 stops at this evidence/specification boundary.

## 9. Source ledger and extraction provenance

Twenty-three primary papers were reviewed, at the depth specified below, plus three author dissertations used as primary measurement access copies. Review is targeted, not a systematic meta-analysis. Sources with only abstract/indexed text access are not represented as fully read PDFs. Caltech article-download links and some publisher/PMC pages returned access errors; accessible author dissertations and institutional copies were used instead. No values were inferred from an axis maximum. Research PDFs were read in memory, not added to the repository.

<a id="s01"></a>
**S01.** Lim et al. (2014), *How Food Controls Aggression in Drosophila*. [PLOS ONE, doi:10.1371/journal.pone.0105626](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0105626). Full-text Results checked for the approximate male total-body-length statement. Not a size-distribution study.

<a id="s02"></a>
**S02.** Carreira, Mensch & Fanara (2009), *Body size in Drosophila: genetic architecture, allometries and sexual dimorphism*. [Heredity, doi:10.1038/hdy.2008.117](https://www.nature.com/articles/hdy2008117). Abstract/method description reviewed for variation; no total-body-length distribution extracted.

<a id="s03"></a>
**S03.** Tammero & Dickinson (2002), *The influence of visual landscape on the free flight behavior of the fruit fly Drosophila melanogaster*. [JEB, doi:10.1242/jeb.205.3.327](https://pubmed.ncbi.nlm.nih.gov/11854370/). Abstract checked; article PDF access failed. Only its explicit characteristic turn description is used numerically.

<a id="s04"></a>
**S04.** Stewart, Baker & Webb (2010), *A model of visual-olfactory integration for odour localisation in free-flying fruit flies*. [JEB, doi:10.1242/jeb.026526](https://doi.org/10.1242/jeb.026526), [institutional primary PDF](https://ir.soken.ac.jp/record/3525/files/1886.full.pdf). Methods pp. 1887-1888, Table 1 p. 1892 and Discussion p. 1898 read. Only animal observations are extracted; model fit coefficients are excluded.

<a id="s05"></a>
**S05.** Censi et al. (2013), *Discriminating External and Internal Causes for Heading Changes in Freely Flying Drosophila*. [PLOS Computational Biology, doi:10.1371/journal.pcbi.1002891](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1002891). Full-text event statistics and eligibility filter checked.

<a id="s06"></a>
**S06.** Fuller et al. (2014), *Flying Drosophila stabilize their vision-based velocity controller by sensing wind with their antennae*. [PNAS, doi:10.1073/pnas.1323529111](https://doi.org/10.1073/pnas.1323529111), [author PDF with supplement](https://faculty.washington.edu/minster/files/fuller_straw_peek_murray_dickinson_flying_drosophila_stabilize_by_sensing_wind_with_SI_pnas14.pdf). Methods and steady-headwind Results p. E1186 checked; moving-pattern stimulus speed is excluded as an animal measurement.

<a id="s07"></a>
**S07.** Leitch et al. (2021), *The long-distance flight behavior of Drosophila supports an agent-based model for wind-assisted dispersal in insects*. [PNAS, doi:10.1073/pnas.2013342118](https://pmc.ncbi.nlm.nih.gov/articles/PMC8092610/). Indexed primary Results/Methods reviewed. Arrival estimates, model assumptions and endurance extrapolations kept separate.

<a id="s08"></a>
**S08.** van Breugel & Dickinson (2012), *The visual control of landing and obstacle avoidance in the fruit fly Drosophila melanogaster*. [JEB, doi:10.1242/jeb.066498](https://authors.library.caltech.edu/records/ve6y5-s8h29). Abstract plus author primary account: van Breugel (2014), [*Complex behavior and perception in Drosophila*, ch. 3](https://thesis.caltech.edu/8047/1/vanBreugel_floris_2014_thesis.pdf), printed pp. 49-70, 81, 85. Table 3.2 (PDF page 77) visually checked; S08 numerical rows explicitly identify this thesis version. Its trajectory-count discrepancies between table and prose prevent treating counts as a precise independent-animal denominator. Retain `m +/- s`/reported-spread labels until full statistical metadata is reconciled.

<a id="s09"></a>
**S09.** Card & Dickinson (2008), *Performance trade-offs in the flight initiation of Drosophila*. [JEB, doi:10.1242/jeb.012682](https://pubmed.ncbi.nlm.nih.gov/18203989/). Abstract plus author primary account: Card, [*Neural Control and Biomechanics of Flight*, ch. 2](https://thesis.caltech.edu/2225/1/GCard_Thesis-revised.pdf), printed pp. 33, 47, 54-56. Table 2.1 and Fig. 2.11 (PDF pages 64, 73) visually checked; speed error bars are SEM, timing summaries median/IQR.

<a id="s10"></a>
**S10.** von Reyn et al. (2014), *A spike-timing mechanism for action selection*. [Nature Neuroscience, doi:10.1038/nn.3741](https://www.nature.com/articles/nn.3741). Abstract/mechanism reviewed; no detailed launch-number extraction used.

<a id="s11"></a>
**S11.** Budick & Dickinson (2006), *Free-flight responses of Drosophila melanogaster to attractive odors*. [JEB, doi:10.1242/jeb.02305](https://pubmed.ncbi.nlm.nih.gov/16857884/). Abstract plus Budick (2007), [*Resource localization and multimodal flight control in Drosophila melanogaster*, chs. 2-3](https://thesis.caltech.edu/2248/1/S.A.Budick.pdf). Printed pp. 12, 16, 18, 21, 38, 40-42 checked. Linear means use SD; horizontal groundspeed and derived horizontal airspeed are explicitly defined. Dissertation and paper are the same experimental program, not replications.

<a id="s12"></a>
**S12.** van Breugel & Dickinson (2014), *Plume-tracking behavior of flying Drosophila emerges from a set of distinct sensory-motor reflexes*. [Current Biology, doi:10.1016/j.cub.2013.12.023](https://pubmed.ncbi.nlm.nih.gov/24440395/), [author record](https://authors.library.caltech.edu/records/5wxex-trp60). Abstract checked; thesis study-condition table consulted. The abstract's +/- latency terms are preserved without assigning an unverified error definition.

<a id="s13"></a>
**S13.** Pang et al. (2018), *History dependence in insect flight decisions during odor tracking*. [PLOS Computational Biology, doi:10.1371/journal.pcbi.1005969](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005969). Full-text Results/model comparisons reviewed; only Drosophila inference used.

<a id="s14"></a>
**S14.** Duistermars, Chow & Frye (2009), *Flies require bilateral sensory input to track odor gradients in flight*. [Current Biology, doi:10.1016/j.cub.2009.06.022](https://pmc.ncbi.nlm.nih.gov/articles/PMC2726901/). Indexed primary text/assay description reviewed. Translationally constrained magnetic tether is explicitly retained as a limitation.

<a id="s15"></a>
**S15.** Stupski & van Breugel (2024), *Wind gates olfaction-driven search states in free flight*. [Current Biology, doi:10.1016/j.cub.2024.07.009](https://pubmed.ncbi.nlm.nih.gov/39067453/), [primary manuscript](https://pmc.ncbi.nlm.nih.gov/articles/PMC11461137/). Published abstract, figure captions and indexed Results reviewed; cite the published study, not its earlier preprint. Optogenetic activation is not an odor-concentration calibration.

<a id="s16"></a>
**S16.** Itskov et al. (2014), *Automated monitoring and quantitative analysis of feeding behaviour in Drosophila*. [Nature Communications, doi:10.1038/ncomms5560](https://pubmed.ncbi.nlm.nih.gov/25087594/). Abstract/figure descriptions reviewed for feeding-event structure; no numerical residence-time prior extracted.

<a id="s17"></a>
**S17.** Murphy et al. (2016), *Postprandial sleep mechanics in Drosophila*. [eLife, doi:10.7554/eLife.19334](https://elifesciences.org/articles/19334). Full-text Results/Fig. 2, feeding/activity/arousal distinctions checked. Meal-conditioned probability change is not a deterministic sleep duration or an airborne fraction.

<a id="s18"></a>
**S18.** Zimmerman et al. (2008), *A Video Method to Study Drosophila Sleep*. [SLEEP primary article](https://pmc.ncbi.nlm.nih.gov/articles/PMC2579987/). Indexed primary Results reviewed for video/beam disagreement and age dependence; no ROOM time fraction extracted.

<a id="s19"></a>
**S19.** Corfas, Sharma & Dickinson (2019), *Diverse Food-Sensing Neurons Trigger Idiothetic Local Search in Drosophila*. [Current Biology, doi:10.1016/j.cub.2019.03.004](https://pubmed.ncbi.nlm.nih.gov/31056390/). Abstract/assay description reviewed; walking and treadmill results kept distinct from flight.

<a id="s20"></a>
**S20.** Olsen, Bhandawat & Wilson (2007), *Excitatory interactions between olfactory processing channels in the Drosophila antennal lobe*. [Neuron, doi:10.1016/j.neuron.2007.03.010](https://pubmed.ncbi.nlm.nih.gov/17408580/). Primary abstract/author PDF description reviewed for candidate early olfactory processing; no ROOM controller gain inferred.

<a id="s21"></a>
**S21.** Seelig & Jayaraman (2015), *Neural dynamics for landmark orientation and angular path integration*. [Nature, doi:10.1038/nature14446](https://www.janelia.org/publication/neural-dynamics-landmark-orientation-and-angular-path-integration). Author primary abstract checked; head-fixed walking VR, not free-flight validation.

<a id="s22"></a>
**S22.** Hulse et al. (2021), *A connectome of the Drosophila central complex reveals network motifs suitable for flexible navigation and context-dependent action selection*. [eLife, doi:10.7554/eLife.66039](https://pubmed.ncbi.nlm.nih.gov/34696823/). Primary abstract reviewed for candidate anatomy; anatomical motifs are not implemented dynamics.

<a id="s23"></a>
**S23.** Ache et al. (2019), *State-dependent decoupling of sensory and motor circuits underlies behavioral flexibility in Drosophila*. [Nature Neuroscience, doi:10.1038/s41593-019-0413-4](https://pmc.ncbi.nlm.nih.gov/articles/PMC7444277/). Indexed primary Results/Discussion reviewed for DNp07/DNp10 and state gating. No full landing or feeding controller follows from those cells alone.
