# M3.10 follow-up: where the clock-driven saccades went (read-only)

Status: **research only, 2026-10-30.** No runtime file changed. It does not change the M3.10 decision
(results/game/M3_10_UPWIND_SURGE.md): P7 failed and v32 stays.

**The question.** M3.10 failed check P7: clock-driven saccades fell from 0.308 to 0.282 per airborne
second on seeds 975501-975520. Its report excluded more ODOR_TRACK time and left the mechanism
open.

## 1. The mechanism on P7's seeds

`tools/m3_10_saccade_loss.py` repeats P7's protocol-S sessions for v32 (`e113583`) and v34
(`9c2b53d`), recording when the flight generator's clock can run and every accepted turn request.

**How the flight generator spends the clock** (game/flight.py).
- **When it runs.** The countdown runs only while the actuator is idle and the policy is not
  steering.
- **Near a wall.** The event becomes a CORRECTION, and the next interval is 1.7 times longer.
- **A DEPART** resets the countdown.

The saccade rate per airborne second is the product of three factors:

| Factor | v32 | v34 | Ratio |
|---|---|---|---|
| Clock seconds per airborne second | 0.630 | 0.626 | 0.994 |
| Clock events per clock second | 0.548 | 0.528 | 0.963 |
| SACCADE share of clock events | 0.891 | 0.854 | 0.958 |
| **SACCADE per airborne second** | **0.308** | **0.282** | **0.916** |
| Near-wall share of clock seconds | 0.176 | 0.230 | |
| Near-wall share of airborne time | 0.157 | 0.190 | |
| DEPART per airborne second | 0.029 | 0.035 | |

- **What drives the drop.** More time near walls. The candidate's clock runs as much as the
  baseline's, but more of it runs near a wall, where clock events become corrections and come less
  often.
- **The product matches.** The three ratios multiply to 0.916, the observed ratio.

## 2. It does not recur on other seeds

**Near-wall time, three seed sets.** On the other two, the candidate spends less time near walls,
not more:
- the P6 wall runs (975101-975124): 0.154 → 0.137;
- the P1 odor runs (975401-975440): 0.110 → 0.097. This set uses clearances under 3.4 BL, a close
  stand-in for the perimeter flag.

**A replication on 40 fresh seeds.** `--seed-set replication` ran seeds 976001-976040, which played
no part in M3.10:

| | v32 | v34 | Difference (seed bootstrap 95 %) |
|---|---|---|---|
| SACCADE per airborne second | 0.303 | 0.297 | −0.006 [−0.024, +0.012] |
| Near-wall share of airborne time | 0.153 | 0.151 | −0.003 [−0.022, +0.018] |
| The three factor ratios | | | 0.991, 0.988, 1.002 |

- **No reliable drop.** On fresh seeds the clock-driven saccade rate does not fall reliably, and
  near-wall time is unchanged.
- **What the P7 drop was.** It came from more near-wall time on that seed set, which converted
  saccades into corrections.

## 3. What this means for check P7

- **The absolute band does not discriminate near v32.**
  - **Its lower bound.** 0.30 per s.
  - **v32's own values.** 0.307, 0.300, 0.308 and now 0.303 on four seed sets.
  - **The consequence.** A candidate with no real effect fails P7 about as often as it passes. The
    replication's v34 value, 0.297, would also fail.
- **A retest that could discriminate.**
  - **The criterion.** Relative to the baseline, for example a candidate no more than 0.03 per s
    below it.
  - **The sample.** At least 40 seeds; the bootstrap interval here is about ±0.02.
- **Why it needs the user's agreement.** That would be a criterion chosen after the M3.10 failure.
  It would need a new preregistration that says so.
- **What it would leave unchanged.** The M3.10 result stands as recorded.

## 4. Reproduction

```
NUMBA_NUM_THREADS=1 python tools/m3_10_saccade_loss.py run --arm baseline --lane K --lanes 2     (K = 0, 1; also --arm candidate)
python tools/m3_10_saccade_loss.py summary
NUMBA_NUM_THREADS=1 python tools/m3_10_saccade_loss.py run --seed-set replication --arm baseline --lane K --lanes 2
python tools/m3_10_saccade_loss.py summary --seed-set replication
```
