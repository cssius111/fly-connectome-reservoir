# M1.8-N4B4: interpretation of the accepted N4B1C free-flight escapes

Status: **research only; complete; decision in section 9.** No runtime, configuration,
calibration, provenance, policy-whitelist, Retina, encoder, brain, noise, lifecycle, physics
or recorder change. N4B1C is not retuned, and DNp04 work is not continued. The accepted
runtime (`feature/m1-8-n4b1c-runtime`, `e3c55b3`) was run unchanged from a clean detached
worktree.

Question: N4B3 found that N4B1C escapes about 0.083 times per minute in no-player free
flight. Are these escapes (A) reasonable collision or looming avoidance, (B) harmless but
acceptable sensitivity, or (C) pathological false alarms?

Short answer:

- **None of the 21 escapes resembles a spontaneous neural false trigger.** Every one
  follows real retinal expansion and LC4/LPLC2 volleys above the fixed-fly N0 envelope.
- The escapes fall into two geometric regimes of about equal size:
  - **Self-approach (9):** the fly flies toward the parked paddle. The escape comes 0.3-3.1 s
    before the closest approach, on weak-to-glancing drive. This is anticipatory avoidance
    of a large object: classes A and B.
  - **Overhead foreshortening (8):** the fly passes directly beneath the paddle at nearly
    constant range. 60-100 % of the expansion comes from the Retina's apparent-size term,
    whose tilt foreshortening depends on the horizontal bearing only. That bearing sweeps
    rapidly when the paddle is nearly overhead. This regime produces the strongest drive,
    and it is **very likely a simplification in the visual geometry, not a decoder fault**.
- By the preregistered rule, 2 of 21 are inappropriate (class C): 0.008/min, 95 % upper
  0.025/min.
- **Decision: 2. Keep N4B1C frozen and document a limitation.** Separately, the
  overhead-foreshortening effect is recorded evidence of a possible visual-geometry defect.
  It also generated the episode-5 "slow-close" signal that motivated N4B2 and N4B3. Any
  change there is a Retina/World modelling decision that needs explicit approval.

## 0. Data and reproducibility

No new scenario data were generated. All 83 stored no-player free-flight runs of the
accepted runtime were used (249 simulated minutes, 21 escapes):

| Source | Seeds | Minutes | Escapes | Numba threads |
|---|---|---|---|---|
| N4B2 development | 7101-7104 | 12 | 1 | 2 |
| N4B2 holdout | 7201-7212 | 36 | 3 | 2 |
| N4B3 development | 7301-7324 | 72 | 4 | 1 |
| N4B3 holdout | 7401-7440 | 120 | 12 | 1 |
| N4B1C runtime validation, scenario D | 101, 255, 4242 | 9 | 1 | 4 |
| **Total** (no duplicate seed / thread pairs) | | **249** | **21** | |

Every run with an escape, plus all three validation runs (whose record is a summary only),
was **re-simulated deterministically** with `tools/n4b4_replay.py` under its recorded
thread count. Verification against the original records:

- all 22 reconstructions are exact: identical escape ticks, and identical DNp01 left and
  right traces on every stepped tick;
- fly position error is 0.0 wherever positions were recorded;
- the validation reconstruction reproduces the recorded escape at seed 4242, tick 7400,
  and no escape for seeds 101 and 255.

**Counterfactual replays** were also run: 21 runs, one per escape, each with that escape
withheld for 2 s. The wrapper keeps the runtime policy unchanged:

- it passes the world a non-escape action carrying only the policy's smoothed turn (no
  impulse, no escape saccade);
- it shows the policy's ESCAPE state as ALERT to ecology and lifecycle;
- every counterfactual is exact up to the event tick.

This is **simulator counterfactual evidence, not biological truth.**

A timing note: the Retina of tick t is projected from the world state stored at tick t-1.
Geometry at the escape is therefore taken from the pre-escape state. Theta rebuilt from that
state matches the recorded theta to 1e-16.

## 1. Neural cause (what the policy saw)

| Quantity | Result |
|---|---|
| Trigger path (first on the escape sample) | FAST 13, LATERAL 4, SUSTAINED 4 |
| Previous escape | none within the run, except one event 2508 samples (50 s) after the previous one; no refractory-expiry re-escapes |
| Behaviour state before the escape | ALERT 15, CALM 6; the saccade state was NONE in 17 and ALERT in 4 |
| Encoder drive, peak in the 200 ms before (summed) | committed-like (>= 0.4) 4; weak/glancing-like (0.05-0.4) 15; low-drive (< 0.05) 2; **noise-like (0) 0** |
| Sensory volley above the fixed-fly N0 envelope (> 22 cells on one side) | **21 / 21** |
| Summed DNp01 at the escape | 1.49-2.47 |

References (same 200 ms measure):

- **N1 committed:** strong drive peak 1.60, medium 0.86-1.35.
- **N1 weak / glancing / aborted:** medians 0.26 / 0.31 / 0.34, range 0.10-1.00.
- **Fixed-fly N0 false triggers of N4B1C (3 in development N0):** all FAST, drive 0,
  sensory peak 5-6 cells: bilateral spontaneous coincidences (N4A mechanism).

**The free-flight escapes are stimulus-driven**, most of them at weak/glancing N1 levels.
They share nothing with the spontaneous fixed-fly false triggers. The four committed-like
events are all in the overhead regime (section 3).

## 2. Geometry (offline only)

Common to all 21:

- the fly is airborne;
- the paddle is parked, with speed 0.0, height 320 units and the non-lethal approach
  phase;
- **physical contact is impossible without the escape**: the counterfactual shows no hit
  and never a lethal paddle state;
- the fly is cruising at 179-244 units/s.

The paddle radius is 144 units; fly radius 11; footprint 155 units; 1 body length is 24
units.

| Regime (post-hoc descriptor, see below) | n | elevation of paddle (deg) | 3D range rate (units/s) | theta (rad) | theta_dot (rad/s) | share of expansion from apparent size | drive peak | time to closest approach (s) | counterfactual closest horizontal distance (units) | paths |
|---|---|---|---|---|---|---|---|---|---|---|
| **overhead foreshortening** | 8 | 80 [67-85] | +7 [-34 to +16] | 0.51 [0.48-0.55] | 0.39 [0.17-0.61] | 0.95 [0.60-1.00] | 0.36 [0.17-0.52] | -0.13 to +0.27 (at closest approach) | 59 [33-134] (already beneath) | LATERAL 4, FAST 3, SUSTAINED 1 |
| **self-approach** | 9 | 45 [23-79] | -115 [-224 to -42] | 0.38 [0.17-0.44] | 0.09 [0.05-0.14] | 0.03 [0.00-0.26] | 0.07 [0.02-0.11] | +0.30 to +3.13 (ahead) | 229 [1-438] | FAST 7, SUSTAINED 2 |
| mixed | 4 | 57 [45-79] | -17 [-53 to -8] | 0.43 | 0.11 | 0.54 [0.45-0.78] | 0.10 | +0.10 to +0.47 | 205 [51-320] | FAST 3, SUSTAINED 1 |

Values are median [range].

- **Self-approach:** the fly is flying toward the parked paddle, and the 3D range is closing
  at 42-224 units/s. Almost all of the theta growth comes from the range change: the fly's
  own translation. The escape precedes the closest approach by 0.3-3.1 s.
- **Overhead foreshortening:** the fly is already beneath the paddle (elevation
  67-85 deg), with the range nearly constant. 60-100 % of the theta growth comes from the
  apparent paddle half-size (`World.visual_half_size`), not from range. The escape happens
  at the closest approach, not before it.

The regime labels were defined **after** inspecting the events, as a descriptor. They are
not the preregistered classes, which are in section 4.

## 3. Why the overhead regime exists: bearing-only foreshortening

`World.visual_half_size` multiplies the paddle radius by an edge-on factor, and by
`1 - tilt_anisotropy * (1 - face) * abs(sin(bearing - orientation))`, where `bearing` is the
**horizontal** direction from the paddle to the fly and `tilt_anisotropy` is 0.25. The term
does not depend on elevation.

When the fly passes nearly beneath the hovering paddle:

- the horizontal bearing sweeps through a large angle within a few ticks;
- the apparent half-size therefore changes by up to 25 % at almost constant 3D range;
- directly overhead, the bearing can flip, and the apparent size jumps in a single tick.

Geometrically, the projected extent of a plate seen from nearly straight below should
become almost independent of horizontal bearing. **The rapid bearing-driven size changes
at high elevation are very likely a simplification artifact of the visual model (Class C),
not a real looming stimulus.** This is an interpretation of the geometry code. It was not
tested against a rendered 3D projection.

The same effect produced the episode-5 **slow-close signal** in the human session (N2b
session). Theta rebuilt from the recorded world state matches the recorded theta to 1e-16:

| Ticks | theta change from range | theta change from apparent size | paddle elevation |
|---|---|---|---|
| 610-613 (DNp04 pair at 613, N4B2/N4B3) | -0.0077 rad (receding) | **+0.0296 rad** | 76-81 deg |
| 624 (144-cell saturated right volley, theta_dot +4.38) | +0.0009 | **+0.0866 in one tick** | 88 deg |

So the "slow approach" that N4B2 and N4B3 tried to detect earlier was, in that recorded
case, **entirely apparent-size change from the bearing-only foreshortening term**, while the
paddle hovered overhead. N4B3 already corrected "approaching" to "hovering". This analysis
identifies the mechanism.

## 4. Preregistered behaviour classes and counterfactual

The rules were fixed in `tools/n4b4_analysis.py` before the events were inspected:

- **A, collision-like approach:** stimulus-driven, and without the escape the fly passes
  under the paddle footprint (< 155 units) within 1.5 s;
- **B, near pass:** stimulus-driven, and within 310 units, not under the footprint;
- **C, inappropriate:** noise-like, or never within 310 units in 1.5 s.

| Class | Events | per min (249 min) | 95 % upper | Regimes |
|---|---|---|---|---|
| A | 12 | 0.048 | - | overhead 8, self-approach 2, mixed 2 |
| B | 7 | 0.028 | - | self-approach 6, mixed 1 |
| C | **2** | **0.008** | **0.025** | self-approach 1, mixed 1 |
| all | 21 | 0.084 | 0.121 | |

Counterfactual outcomes without the escape (1.5 s horizon):

- under the paddle footprint 12, near pass 7, safely separated 2;
- collision 0: impossible with a parked paddle at 320 units.

The two class C events are mild:

- **Validation seed 4242, tick 7400:** the fly is flying straight toward the paddle from
  760 units (range closing at 224 units/s). The extrapolated miss distance is 95 units, but
  the closest approach is 3.1 s away, beyond the 1.5 s horizon. This is early, low-drive
  avoidance (drive 0.02) rather than a pathology.
- **N4B3 dev seed 7316, tick 6802:** a mixed event whose counterfactual closest distance
  is 320 units, 10 units outside the class B boundary; weak drive 0.05.

How the preregistered class A needs reading: 8 of the 12 are overhead-regime events in
which the fly is **already** beneath the paddle when the escape fires. For them "would pass
under the footprint" describes where the fly already is, not an approaching collision. They
are escapes from beneath a hovering paddle, triggered mainly by foreshortening.

## 5. Human-visual review set

Figures are written by `tools/n4b4_figures.py` to `artifacts/m1_8_n4b4/figures/`
(git-ignored). Each shows:

- a top-down view with the paddle footprint, the factual path and the counterfactual path;
- theta and theta_dot;
- encoder drive and the peak volley;
- the DNp01 traces with inferred spikes.

`summary_events.png` plots all 21 events: counterfactual closest distance against
theta_dot, by class.

| Event | Why selected | Regime / class |
|---|---|---|
| N4B2 holdout 7201 @ 3563 | strongest drive (theta_dot spike to about 1.8 rad/s as the fly crosses beneath) | overhead / A |
| N4B2 holdout 7211 @ 3755 | strongest drive | overhead / A |
| N4B3 dev 7317 @ 1549 | strongest drive | overhead / A |
| N4B3 holdout 7432 @ 6505 | strongest drive | overhead / A |
| N4B3 holdout 7432 @ 3997 | weakest drive | self-approach / B |
| N4B3 holdout 7440 @ 2681 | weakest drive | self-approach / B |
| validation 4242 @ 7400 | weakest drive; class C | self-approach / C |
| N4B3 dev 7316 @ 6802 | weakest drive; class C; boundary case | mixed / C |
| N4B2 holdout 7207 @ 8885, N4B3 holdout 7406 @ 7419 | ambiguous (near the footprint boundary) | mixed / A, overhead / A |
| remaining class B: N4B2 dev 7102, N4B3 dev 7308, 7321, N4B3 holdout 7417, 7431 | class B | self-approach or mixed / B |

Deterministic replay of any event (set `NUMBA_NUM_THREADS` to the source's thread count: 2
for N4B2, 1 for N4B3, 4 for validation):

    python tools/n4b4_replay.py replay --source n4b3_holdout --seed 7432
    python tools/n4b4_replay.py replay --source n4b3_holdout --seed 7432 --suppress 6505

User review is not required for the decision below. The offline classification is decisive
on the main question: stimulus-driven versus spontaneous, and no decoder pathology. The
figures are provided for the visual-geometry question in section 3.

## 6. Metric domains

N4B1C was accepted on the **fixed-fly no-loom** metric. Free flight is a different domain,
and the fixed-fly threshold should not be applied to it mechanically.

| Metric | Definition | N4B1C now |
|---|---|---|
| **M1. No-loom neural false escapes / min** (existing target < 0.1 at 95 %) | fixed fly, static paddle, encoder drive 0; purely spontaneous | 4 in 1190 min (all development and holdout N0 sets): 0.0034, upper **0.0077** |
| **M2. Inappropriate free-flight escapes / min** (proposed; same < 0.1 target) | stimulus-free, or no near pass within the horizon (preregistered class C) | 2 in 249 min: 0.008, upper **0.025** |
| M3. Visual-model-artifact escapes / min (proposed; tracked, no target yet) | expansion dominated (>= 60 %) by apparent-size change at high elevation (>= 60 deg) | 8 in 249 min: 0.032, upper 0.058 |
| M4. Legitimate self-approach looming escapes / min (informational) | range closing, expansion from range change | 9 in 249 min: 0.036, upper 0.063 |
| All free-flight escapes / min (informational) | M2 + M3 + M4 + mixed | 21 in 249 min: 0.084, upper 0.121 |

Recommendations for future milestones:

- Report M1 and M2 as acceptance metrics, and M3 and M4 descriptively.
- M2 needs a preregistered behavioural classifier like section 4, with a horizon long
  enough (at least 3 s) for fast direct approaches.
- **No threshold is changed here.** N4B1C passes M1 and M2 with wide margins.

## 7. Biology and interpretation

A. **Published evidence** (checked for N4B3; see its section 12):

- In free flight, expansion from the fly's own forward motion triggers saccades (Tammero &
  Dickinson 2002a).
- Frontal expansion drives landing and lateral expansion drives collision avoidance
  (Tammero & Dickinson 2002b; van Breugel & Dickinson 2012).
- No efference-copy suppression of looming pathways is known.

B. **Literature-inspired interpretation:** an evasive response to a large object the fly is
flying toward is plausible fly behaviour, so the self-approach escapes are not
biologically unreasonable. A real fly would more likely saccade or land than make an
escape-strength evasive burst. The game's single escape action does not distinguish these.

C. **Simulator engineering:**

- The self-approach escapes follow correctly from the frozen Retina, encoder, MaleCNS and
  decoder chain.
- The overhead escapes follow correctly from the Retina input too. That input contains a
  likely geometric artifact.
- Nothing here validates biology through game behaviour.

## 8. DNp04 status

DNp04 stays **not approved** for flight runtime use (N4B3). Section 3 finds a more general
modelling issue: bearing-only foreshortening in the visual size. That issue affects the
DNp04 motivation too: the episode-5 slow-close signal was produced by it. It is a
Retina/World question, not a DNp04 question, so it does not reopen DNp04.

## 9. Decision

**2. KEEP N4B1C FROZEN, BUT DOCUMENT A LIMITATION.**

- No escape resembles a spontaneous neural false trigger: 0 of 21 are noise-like, and all
  21 follow real volleys.
- Inappropriate escapes by the preregistered rule are rare (2 in 249 min, upper
  0.025/min), and both are mild.
- **No meaningful fraction is a pathological decoder false alarm, so reopening N4B1C
  safety research (option 3) is not warranted.**
- About 9 escapes are reasonable anticipatory responses to genuine self-generated looming
  (option 1 territory).
- About 8 are driven mainly by a likely visual-geometry artifact. N4B1C should not be
  "fixed" for those: the decoder responds correctly to its input.

The documented limitation: in no-player free flight, N4B1C escapes about 0.08 times per
minute. About half of these are anticipatory responses to the fly's own approach to a
large parked paddle. About half are escapes while passing beneath it, where the Retina's
bearing-only tilt foreshortening creates apparent expansion at constant range.

**Separate item for your decision (not implemented):** whether the bearing-only
foreshortening term in `World.visual_half_size` (`swatter.directional.tilt_anisotropy`
0.25, introduced in `58ffd60`) is a real defect.

- It affects the Retina input for every policy.
- It generated the slow-close signal behind N4B2 and N4B3.
- Changing it would be a Retina/World modelling change, and it may touch M1.7-era swatter
  geometry. It therefore needs explicit approval and its own milestone with before/after
  validation.

## 10. Reproduction and validation

    python tools/n4b4_replay.py all        (inventory, 22 reconstructions and 21 counterfactuals; about 40 min on 8 lanes)
    python tools/n4b4_analysis.py
    python tools/n4b4_figures.py

The tools need the detached runtime worktree `artifacts/worktrees/n4b1c-runtime-detached`
(`e3c55b3`, with a `data` junction), and the N4B2 and N4B3 ROOM artifacts.

Artifacts (`artifacts/m1_8_n4b4/`, git-ignored):

- `inventory.json` sha256 `e5b7a82e569a4b42`;
- `analysis.json` sha256 `fd36af8c677717ee`;
- per-run `*_seed*.json/.npz` and `*_cf*.json/.npz`;
- `figures/`.

Validation:

- 330 / 330 tests pass on the research branch.
- The 20 protected files match `artifacts/m1-2/protected-before.json`, and none differs from
  `76806f0`.
- `verify_results.py` passes.
- No runtime file (`game/action.py`, `session.py`, `world.py`, `perception.py`, `fly.py`,
  `game_room_config.json`, `results/`) differs from `d09dac4`.
- `feature/m1-8-n4b1c-runtime` is still at `e3c55b3`, and both runtime worktrees are clean.
- The N4B2 and N4B3 frozen criteria modules are unchanged.

Limitations:

- the free-flight background is a parked paddle only;
- the counterfactual withholds one escape for 2 s and keeps the rest of the policy state;
- the regime labels are post-hoc;
- the foreshortening interpretation rests on the geometry code, not on a rendered
  projection;
- the classification horizon (1.5 s) is short for fast long-range approaches (the 4242
  case).
