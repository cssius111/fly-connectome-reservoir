# M3.7: spontaneous flight saccades (read-only research)

Status: **research note, 2026-10-25.** No runtime code, configuration, record or frozen system
changed.

**Why.** On 2026-10-25 the user paused the escape-timing line (game/M3_5_STRIKE_ESCAPE_RESEARCH.md,
section 18) and chose the next M3.0 gap: spontaneous flight saccades. M3.0 found
(results/game/M3_0_FIDELITY_SCORECARD.md, protocol S):

| Metric | Model | Real fly | Class |
|---|---|---|---|
| S1 rate | 0.34 per s | 1.37 per s (E12) | gap |
| S2 interval, mean | 2.65 s | 0.82 s (E11) | gap |
| S3 amplitude, duration | median 57° in 80 ms | about 90° in under 100 ms (E10) | partial |

These saccades come from the hand-written flight generator (category B), not from the
connectome.

## 1. Where the model's events come from

`tools/m3_7_saccade_breakdown.py` re-reads the M3.0 protocol-S data (seeds 9501-9520, 2,951 usable
airborne seconds). It uses the M3.0 detector unchanged and splits the detected events by the
actuator kind that produced them:

| Kind | Source | Events | Per s | Amplitude, median (IQR) | Duration, median |
|---|---|---|---|---|---|
| SACCADE | free-flight clock | 568 | 0.192 | 59° (40-75°) | 60 ms |
| AVOID | wall cue (time to contact) | 336 | 0.114 | 61° (41-76°) | 80 ms |
| DEPART | wall cue (time near a wall) | 95 | 0.032 | 48° (36-57°) | 60 ms |
| CORRECTION | free-flight clock | 3 | 0.001 | 10° | 20 ms |
| **All** | | 1,002 | 0.340 | | |

**The generator** (`game/flight.py`, ROOM configuration):
- **Clock.** Each event waits an interval drawn from a three-part mixture:
  - 0.3-0.7 s with probability 0.28;
  - 0.8-1.9 s with probability 0.54;
  - 2.6-6.0 s with probability 0.18.
  The mean is 1.64 s of clock time.
- **What stops the clock.** It stops while the actuator turns and while the neural policy
  steers.
- **Clock rate by ecology state.** EXPLORE 1.0, TRANSIT 0.45, ODOR_SEARCH 1.35, ODOR_TRACK 0.35,
  RECOVER 0.7, otherwise 0.
- **Kind of event.**
  - In open space an event is a CORRECTION with probability 0.42: 5-18° at a peak of
    250-600°/s, mostly below the 450°/s detector.
  - Otherwise it is a SACCADE: 25-105° uniform, at a peak of 700-1,400°/s.
  - Near a wall every event is a CORRECTION.
- **Pulse shape.** Half-sine yaw rate, duration π A / (2 P) for angle A and peak P. The bounds
  are: at least 60 ms, at most 300 ms, and a peak of at most 1,500°/s.
- **Status of the parameters.**
  - **Class B.** The M1.8-R0 evidence lock classes every `flight.*` parameter as B,
    phenomenological and unfitted. It says that E10-E12 "do not identify these endpoints".
  - **Class C.** It classes the actuator bounds as C.
  - **Not in the freeze list.** None of these parameters is in the AGENTS.md freeze list.

**What the detector sees of a pulse** (`pulse_geometry`, continuous time):

| Peak | 65° pulse | 90° pulse |
|---|---|---|
| 700°/s | 146 ms; seen as 50° in 81 ms | 202 ms; seen as 69° in 112 ms |
| 1,000°/s | 102 ms; seen as 58° in 72 ms | 141 ms; seen as 80° in 99 ms |
| 1,400°/s | 73 ms; seen as 62° in 58 ms | 101 ms; seen as 85° in 80 ms |
| 1,500°/s (cap) | 68 ms; seen as 62° in 55 ms | 94 ms; seen as 86° in 76 ms |

The measured median of 59° is therefore the generator's 25-105° range (median 65°), truncated by
the detector.

## 2. What the real-fly numbers contain

- **Censi et al. 2013** (E12's source; PLOS Comput Biol, doi:10.1371/journal.pcbi.1002891):
  - **The assay.** A "2 meter diameter, 80 cm high cylinder" with a checkerboard of 10 cm
    squares. Only flight above 5 cm/s was kept. There were 6,613 saccades in 4,814 s, or
    1.37 per s.
  - **Most saccades are stimulus-driven.**
    - "roughly 90% of the saccades are stimulus-driven in the regions of maximum stimulus".
    - The rate depends strongly on the fly's distance and orientation relative to the wall.
  - **The baseline.** "we can bound the contributions of these two terms in a baseline saccade
    rate that we estimate at 0.4 saccades/sec", "roughly a tenth of the maximum rate". The two
    terms are random or internal processes and unmodelled features.
  - **Direction.** In the arena's centre, left and right saccades are equally likely.
- **Frye and Dickinson 2004** (Curr Opin Neurobiol 14; doi:10.1016/j.conb.2004.10.004):
  - **Kinematics.** "During each saccade, the animal changes heading by 90° over a period of
    ~50 ms, corresponding to peak angular velocity exceeding 1000 degrees per second".
  - **Trigger.** "saccades are elicited by visual expansion". An expansion on one side triggers a
    saccade away. Frontal expansion triggers landing instead.
  - **Between saccades.** "Between saccades, Drosophila tends to fly in a straight line."
- **Tammero and Dickinson 2002** (E10): about 90° in under 100 ms (abstract, as locked by R0).

## 3. The pooled rate does not transfer to ROOM in time units

ROOM's speed is the frozen gameplay scale (C1).

| | Real fly (Censi et al. 2013) | ROOM |
|---|---|---|
| Speed | about 107 BL/s (E02) | 7.6 BL/s |
| Arena | 2 m across, 800 BL at 2.5 mm per BL | 160 × 90 BL |
| Time to cross the arena | about 7.5 s | 12-21 s |
| Distance per saccade at 1.37 per s | about 78 BL | 5.5 BL |

- **Why the pooled rate does not transfer.**
  - **It is mostly geometry.** About 90 % of the pooled rate is driven by the walls of a large
    arena crossed at high speed.
  - **The cost of matching it.** Matching 1.37 per s in ROOM time would put a saccade every
    5.5 BL, a path about 14 times more tortuous per distance than a real fly's.
- **What does transfer in time units.** Censi et al.'s baseline of about 0.4 per s. It is the
  part not explained by the visual stimulus, and they bound it there.
- **The model's two parts.**
  - **The clock part.** 0.19 per s, about half that bound.
  - **The wall part.** AVOID and DEPART, 0.15 per s. It is the model's counterpart of the
    stimulus-driven saccades. In a 14-times slower world its per-second rate has no direct
    comparator.

## 4. Candidate designs

Each needs the user's decision, a preregistration and explicit authorization. All stay inside
the class-B `flight` block; the actuator bounds, the ecology clock rates and every frozen system
are unchanged.

1. **Straight flight between saccades.**
   - **The change.** In open space, every clock event becomes a saccade: `flight.correction.probability`
     from 0.42 to 0.
   - **What stays.** Near a wall every event remains a CORRECTION (wall following, boundary
     behaviour).
   - **Basis.** "Between saccades, Drosophila tends to fly in a straight line."
   - **Expected.** The same clock gives about 0.192 / 0.58 ≈ 0.33 saccades per s, within the
     0.4 per s baseline.
2. **Saccades of about 90°.**
   - **The change.** Centre `flight.saccade.degrees` on 90° and raise the peak rates within the
     existing 1,500°/s cap. One example: 60-120° at 1,200-1,500°/s.
   - **Expected.** A 90° saccade at 1,400°/s lasts 101 ms and is seen as 85° in 80 ms, an S3
     match.
   - **What the rules prevent.** The ~50 ms of Frye and Dickinson is not reachable without
     raising the class-C actuator cap and the 60 ms minimum, which is set by the 20 ms tick.
   - **The spread.** No source gives the amplitude distribution (E10 is "a characteristic
     description"), so the spread is a design choice. A spread is kept so that turns are not
     identical.
3. **Wall-driven turns.**
   - **No change now.** AVOID and DEPART stay as they are.
   - **What a comparator would need.** One that does not depend on the frozen speed scale, for
     example the share of wall approaches resolved by a turn, or the time to contact at the turn.
     That would need literature on expansion-triggered saccades: Tammero and Dickinson 2002's full
     text was not accessible to R0.
4. **A comparator that fits.**
   - **The new metric.** A preregistered metric for the clock part, scored against Censi et al.'s
     baseline bound (at most 0.4 per s), with S3 unchanged.
   - **M3.0 unchanged.** M3.0's S1 and S2 stay as recorded. The expected total of about 0.48
     per s would remain an S1 gap by construction, because that comparator is mostly
     stimulus-driven.

**What a change would touch.**
- **Paths.** More, larger turns change flight paths, wall approaches, perching and odor tracking.
  The ODOR_TRACK clock runs at 0.35.
- **Checks.** A preregistration would therefore need the paired free-flight check, the ecology
  checks and a playtest.
- **Difficulty.** A fly that turns more often and further is likely harder to hit. That is a
  consequence to report, not a target.
