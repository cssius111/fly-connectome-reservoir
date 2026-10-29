# M3.9 research: wall-evoked turns against the real fly (read-only)

Status: **research only, 2026-10-29.** No runtime file changed. Under the user's standing instruction
to follow the recommended steps (game/M3_7_SACCADE_DESIGN.md).

**Why this gap.**
- **The rest of the M3.0 scorecard.** The remaining gaps (E1, E2, E4 front/back, E5) all concern the
  escape decision. Changing it needs the frozen encoder or decoder. The escape-timing line is paused
  by the user, and E4 alone is only marginally feasible (game/M3_5_STRIKE_ESCAPE_RESEARCH.md,
  section 12).
- **What the scorecard left out.** M3.7 found that the real fly's saccades are about 90 %
  stimulus-driven (Censi et al. 2013). The scorecard compared only their rate.
  - **In the real fly.** Most of these saccades are evoked by the expansion of nearby surfaces.
  - **In the model.** They are the wall turns AVOID and DEPART of `game/flight.py`.
  - **Their status.** The M1.8-R0 evidence lock (game/M1_8_EVIDENCE.md) lists every AVOID parameter
    as class B or C, "not an observed turn-angle statistic".

## 1. The real fly

**Tammero and Dickinson 2002** (J Exp Biol 205:327-343; full text from the Caltech repository).
- **The setup.** Free flight in a 1 m cylinder with a textured or a uniform wall, about 30 cm/s.
  1,579 saccades were recorded with the textured wall and 1,080 with the uniform one.
- **Amplitude.** Fixed, about ±90°, and independent of the approach angle:
  - "two clusters of points are evident, one centered at +90° and the other at –90°";
  - "no more than 1 % of the variance in saccade angle can be explained by variation in approach
    angle" (slopes 0.05 and 0.14, not different from zero);
  - the same with the uniform wall (r² < 0.05).
- **Direction.** It depends on the approach angle: "asymmetries in the output of the local motion
  detectors … affect the direction (left versus right) but not the amplitude". The probability of
  turning away from the nearer wall is greater the larger the approach angle (their Fig. 3C). It is a
  probability, not a rule.
- **Trigger.** It is not time to collision.
  - The textured wall slows the flies, "Calculating time to collision, slowly flying flies should
    approach the walls more closely than rapidly flying flies. The flies, however, do just the
    opposite, saccading at a greater distance from the walls within the textured background".
  - Their explanation: "a threshold in large-field image expansion that triggers a saccade".
  - That expansion is the summed output of motion detectors, so it depends on the wall's contrast.
- **Between saccades.** Flies drift away from the side with more visual motion, a centering
  response.

**van Breugel and Dickinson 2012** (J Exp Biol 215:1783-1798; full text from the Caltech
repository). This is the comparator for a post, not a wall.
- **The trigger.** Flies that do not land make an aversive saccade at a mean retinal size of the post
  of 33 ± 17°, an angular-size trigger.
- **The turn.** It heads the fly away from the post, to post angles of about ±140° (SD 50°).

## 2. The model

`tools/m3_9_wall_saccades.py`: ROOM v32, no player, pointer parked, 12 × 180 s on seeds
974001-974012 (1,741 airborne s). Every accepted AVOID and DEPART request was recorded with the
wall's approach angle, the clearance, the speed and the requested turn.

| | AVOID | DEPART |
|---|---|---|
| Events (per airborne s) | 165 (0.095) | 44 (0.025) |
| Amplitude, median (p10-p90) | 81° (42-98°) | 65° (45-80°) |
| \|Approach angle\|, median (p10-p90) | 23° (6-62°) | 95° (82-111°) |
| Signed turn on signed approach angle, per direction | slope 1.00, r² 1.00 (both) | slopes −0.03 and −0.28, r² ≤ 0.08 |
| Turns away from the wall | 100 % | 100 % |
| Clearance at the request, median (p10-p90) | 3.5 BL (1.8-5.5) | 2.7 BL (1.2-4.1) |
| Clearance on speed | slope 0.43 BL per BL/s, r² 0.45 | r² 0.04 |
| Time to contact, median | 0.54 s | (parallel to the wall) |

For comparison, the same runs have SACCADE requests at 0.307 per airborne s and CORRECTION
requests (near-wall trims) at 0.048 per airborne s.

- **AVOID's amplitude is set by the approach angle.** It is exactly 104° − |approach angle|: the turn
  onto the wall tangent plus 14° inward. A head-on approach gives 104° and a glancing one 40-50°.
- **AVOID's trigger is time to contact.** The fly turns 0.54 s before contact, so its clearance
  grows with its speed. That is the rule Tammero and Dickinson rejected.
- **AVOID's direction is deterministic.** It always turns away from the wall.
- **DEPART.** A perimeter timer, not an expansion response. Its amplitude is uniform on 40-85° and
  independent of the approach angle.

## 3. Gaps

| Feature | Model | Real fly | Class |
|---|---|---|---|
| W1 Amplitude of wall-evoked saccades | AVOID: 104° − \|approach\|, r² 1.00 | about ±90°, independent of approach, r² < 0.01 | **gap** |
| W2 Direction | always away from the wall | away with a probability that rises with the approach angle | partial |
| W3 Trigger | time to contact 0.55 s; clearance grows with speed | large-field expansion threshold; slower flies turn farther away | **gap**, limited by the world |
| W4 Between saccades | straight, with drift | drift away from the side with more motion (centering) | not represented |

**What limits a fix.**
- **W3.** The real trigger depends on the wall's contrast, which the game world does not have.
  - **The integrated expansion.** For a straight approach, the expansion summed over time since the
    wall came into range is ln(d₀/d). That does not depend on speed, so the trigger nearest to the
    real fly's in a contrast-free world would be a fixed clearance.
  - **The real distances.** They are not transferable. The real arena is about 400 BL across at the
    model's 2.5 mm per BL, against ROOM's 160 × 90 BL, and the real fly here flies about 16 times
    faster (30 cm/s, about 120 BL/s, against 7.6 BL/s).
- **W1.** This is a rule, not a scale. Real saccades are a fixed motor program, so the amplitude
  could follow the real distribution in any arena.

## 4. Candidate next step (not authorized here)

A preregistered M3.9 could change only class-B AVOID parameters and their rule, leaving every
frozen system unchanged.
- **Amplitude.** AVOID's amplitude would be drawn from the accepted saccade distribution (60-120°),
  independent of the approach angle, turning away from the wall.
  - **The basis.** W1, Tammero and Dickinson 2002.
  - **The risk.** A head-on approach with a 60° turn still closes on the wall, at half the speed.
    The fly would turn again after the refractory period, as real flies do in a sequence, but
    containment events and wall dwelling could rise.
- **Peak rate.** AVOID would use the saccade peak rate (1,200-1,500°/s) instead of 700-1,300°/s.
  - **The basis.** Wall-evoked and spontaneous saccades are one stereotyped program.
- **Trigger.** Either keep time to contact as a declared world convention (W3), or test a fixed
  clearance.
  - **The second option.** It follows the integrated-expansion argument, but it changes when every
    wall turn happens, so it would be a separate arm.
- **Direction.** Keep "away".
  - **Why.** The real probability curve is available only as a figure, so W2 stays partial.
- **Checks it would need.**
  - wall-turn amplitude against the approach angle (W1);
  - the pathology screen, with containment events and near-wall share;
  - paired no-player escapes (as P4 of M3.8);
  - fixed-fly escapes (as P5);
  - the ODOR_TRACK upwind share (as P6);
  - a human playtest.
- **What it changes visibly.** The fly would leave walls with sharp turns instead of sliding along
  them. That reverses the edge-following that M1.4 chose as a presentation rule (game/FLIGHT.md,
  "local perimeter-following"), and it is the real fly's behaviour in flight. The choice is the
  user's.

## 5. Follow-up after M3.9: why the upwind share fell (read-only)

M3.9 failed check P6 (results/game/M3_9_WALL_SACCADES.md): the ODOR_TRACK upwind share fell from
0.564 to 0.481. `tools/m3_9_odor_diagnosis.py` repeated the P6 runs (seeds 974401-974440, v32 at
`925427c` against v33 at `7727397`) with more per-tick fields, and it reproduces P6 exactly.

**The steering that matters** (game/ecology.py). In ODOR_TRACK the heading turns toward upwind
through the ecology's smoothed steering command, capped at `ecology.steering_cap_rad_s` = 0.9 rad/s
(about 52°/s; class C in the M1.8-R0 lock). A 90° turn therefore takes at least 1.7 s and a 180°
turn 3.5 s.

**The hypothesis that fails.** The drop is not a composition effect of a candidate that reaches
the food more often.
- **The test.** Re-weighting the candidate's upwind share to the baseline's distribution of
  distance to the food gives 0.488 (raw 0.481).
- **What that shows.** The share is lower at every distance, for example 0.63 against 0.48 at
  400-800 units.

**What the data show.**

| | v32 | v33 |
|---|---|---|
| Airborne bout entries | 348 | 340 |
| Heading within 45° of upwind at entry | 0.30 | 0.23 |
| Heading of EXPLORE and TRANSIT flight, shares 0-45° / 45-90° / 90-135° / 135-180° from upwind | 0.22 / 0.20 / 0.26 / 0.32 | 0.22 / 0.20 / 0.27 / 0.31 |
| Upwind share 0-0.5 s / 0.5-1 s / 1-2 s / 2-4 s / > 4 s after the bout starts | 0.31 / 0.35 / 0.46 / 0.74 / 0.80 | 0.24 / 0.29 / 0.43 / 0.69 / 0.73 |
| Share of tracking ticks more than 4 s into a bout | 0.206 | 0.129 |
| Bouts ending in ALERT | 45 | 57 |
| Entries more than 45° off upwind that reach 45° before the bout ends | 108 of 244 | 97 of 262 |
| Time to reach 45°, median (p25-p75) | 1.57 s (0.80-2.20) | 1.56 s (0.84-2.26) |

- **The model turns upwind slowly.** After an off-wind entry, the median fly needs about 1.6 s to
  come within 45° of upwind, and most bouts end before it does.
  - **The real fly** (E16, van Breugel and Dickinson 2014, abstract): "190 ± 75 ms after
    encountering a plume, flies increase their flight speed and turn upwind".
  - **Not checked.** The full text was not accessible, so the duration of the real turn is not
    sourced here.
- **So the upwind share mostly measures the entry heading.** With a slow turn, the share depends on
  where the fly points when it meets the plume and on how long the bout lasts.
  - **In v33.** Fewer entries already point upwind (0.23 against 0.30), and fewer bouts last
    beyond 4 s. The cruise heading distribution is the same in both arms.
  - **What it reflects.** How the wall turns change the paths that cross the plume, not worse
    tracking once a heading is upwind.
- **Why P6 failed.** M3.9 changed the encounter geometry. The model's slow upwind turn turned that
  change into a lower upwind share.

**A gap the scorecard did not list.**

| Feature | Model | Real fly | Class |
|---|---|---|---|
| O1 Upwind turn after odor entry | steering-rate-limited (52°/s cap); median 1.6 s to 45° from upwind | response 190 ± 75 ms after entry (E16) | **gap** |

**Candidate next step, not authorized here.** The candidate is an upwind turn on odor entry at the
real fly's timescale. Two forms are possible:
- a saccade-like upwind turn about 190 ms after entry;
- a higher steering cap during ODOR_TRACK.

**What it would need.**
- **The user's explicit request.** The ODOR_TRACK steering belongs to the M1.8 ecology, and
  `AGENTS.md` asks for an explicit user request for any further M1.8-B change.
- **A preregistration** with the checks used for M3.8 and M3.9.

**What it would make possible.** It would make the upwind share far less sensitive to the entry
heading, so the M3.9 wall-turn rule could be tested again in a later, separate milestone.

## 6. Reproduction

```
NUMBA_NUM_THREADS=1 python tools/m3_9_wall_saccades.py run --lane K --lanes 4    (K = 0-3)
python tools/m3_9_wall_saccades.py summary
NUMBA_NUM_THREADS=1 python tools/m3_9_odor_diagnosis.py run --arm baseline --lane K --lanes 2   (K = 0, 1; also --arm candidate)
python tools/m3_9_odor_diagnosis.py summary
```
