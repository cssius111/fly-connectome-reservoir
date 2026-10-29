# M3.10: an upwind surge turn on odor entry (preregistration)

Status: **preregistered 2026-10-29, before any M3.10 candidate data.**

**Authorization.** On 2026-10-29 the user wrote: "A：同意修改 M1.8 生态的 ODOR_TRACK 转向" (option
A: I agree to modify the ODOR_TRACK steering of the M1.8 ecology). This is the explicit request that
`AGENTS.md` requires for a further M1.8-B change.
- **What it covers.** The ODOR_TRACK turn toward upwind.
- **What it leaves frozen.**
  - every frozen M1.8-B block and value: speeds, hazards, odor history, odor cues, wind
    reliability, casting;
  - the steering cap;
  - the recorder schema;
  - every other system.

**Background** (game/M3_9_WALL_SACCADE_RESEARCH.md, section 5).
- **The model (v32).**
  - **Speed of the turn.** ODOR_TRACK turns toward upwind only through the ecology's steering,
    capped at 0.9 rad/s (about 52°/s).
  - **The consequence.** After an entry more than 45° off upwind, the median fly needs 1.6 s to
    come within 45° of upwind, and 136 of 244 such bouts end before it does.
- **The real fly** (E16; van Breugel and Dickinson 2014, abstract): "190 ± 75 ms after encountering
  a plume, flies increase their flight speed and turn upwind". Its body turns are saccades (E10,
  Frye and Dickinson 2004).

## 1. The change

The ROOM configuration goes from v32 to v34; v33 is the failed M3.9 candidate. The baseline is v32,
read from commit `e113583`.

| Key | v32 | v34 | Basis |
|---|---|---|---|
| `ecology.upwind_surge.delay_seconds` (new) | absent | 0.07 | E16's 190 ms from plume entry, less the 0.12 s encounter debounce (`encounter_dwell_seconds`) |
| `ecology.upwind_surge.peak_rate_deg_per_second` (new) | absent | [1200, 1500] | the accepted saccade peak rates (M3.8) |

**The rule**, gated by the new block.
- **The request.** Once per ODOR_TRACK bout, `delay_seconds` after entry, the ecology requests a
  turn of the sensed upwind bearing. The bearing is the body-frame upwind angle the ecology
  already computes from its wind cue.
- **When it does not request.** When there is a threat input, or when the sensed wind is
  unreliable.
- **The peak rate.** Drawn from the interval with a dedicated random stream.
- **How the world executes it.** As an actuator pulse of a new kind, SURGE, with the priority of a
  spontaneous saccade: AVOID, ALERT and ESCAPE outrank it.
  - **The angle.** Limited to the actuator's existing 120° bound.
  - **When it is skipped.** While the policy steers, or when a pulse of equal or higher priority is
    active. A skipped surge is not retried.
- **The continuous steering** keeps working as before, so it completes turns larger than 120°.
- **The interface.** The request goes from the session to the world as a separate attribute. The
  recorded `EcologicalCommand` and every recorder schema are unchanged.
- **Without the block.** Nothing changes: LAB, GAME and every older configuration run as before.

**Bookkeeping keys.** `config_version` (34), `policy._comment` and `policy.calibration_paths`.

**The record.** `tools/m3_10_record.py` writes `results/game/calibration_room_m3_10.json`, carrying
the v32 decoder and threshold over as M3.8 and M3.9 did. It refuses any other configuration change.

**Not modelled.** E17 attenuates later upwind responses through the encounter history, and the
frozen continuous steering keeps that attenuation. The surge is not attenuated.

## 2. Checks

The baseline arm is v32 at `e113583`. Every seed is fresh. The tools are:
- `tools/m3_10_checks.py` for P1, P2, P5, P6, P7, D1 and D3, which runs the M3.9 tools with
  M3.10's seeds, output directory and arms;
- `tools/kinematics_sanity.py` for P3 and D2;
- `tools/paired_free_flight_check.py` for P4.

| Check | What | Pass |
|---|---|---|
| **P1** (primary) | `tools/m3_9_odor_diagnosis.py` runs on seeds 975401-975440 (40 × 180 s, no player, pointer parked): over airborne ODOR_TRACK entries more than 45° off upwind, the median time to come within 45° of upwind, counting a bout that never does as never | ≤ 0.5 s for the candidate |
| **P2** | The same runs: share of ODOR_TRACK airborne ticks heading within 45° of upwind | candidate ≥ baseline − 0.05 |
| **P3** | `tools/kinematics_sanity.py` pathology screen, candidate against baseline, on its six seeds | no failure |
| **P4** | `tools/paired_free_flight_check.py`, seeds 975201-975280 (80 × 180 s) | the candidate's total escapes are not larger than the baseline's |
| **P5** | M3.0 protocol E, seeds 975301-975324, all 16 conditions | identical escapes in every trial |
| **P6** | M3.9's wall runs, seeds 975101-975124 (24 × 180 s): wall-contact onsets per airborne minute and near-wall share | contact onsets ≤ max(2 × baseline, 0.5 per min); near-wall share ≤ 1.25 × baseline |
| **P7** | M3.0 protocol S, seeds 975501-975520 | clock-driven saccades 0.30-0.50 per s; S3 median 60-120° and ≤ 100 ms |

**Descriptive.**
- **D1.** From P1's runs:
  - surge requests and executed surges per ODOR_TRACK entry;
  - the upwind share by time since entry;
  - bout outcomes.
- **D2.** The `kinematics_sanity` comparison, including food touchdowns.
- **D3.** From P1's runs: the upwind share at entry and after 4 s.

**Risks stated beforehand.**
- **P1.** A bout that ends within about 0.3 s counts as never, and a skipped surge is not retried.
- **P4.** Any change of where the fly flies can move its encounters with the hovering paddle.
- **The food approach.** A faster upwind turn also changes how the fly approaches the food and how
  often it lands.

## 3. Decision rule

As in M3.7-M3.9.
- **If P1-P7 all pass.**
  - **The candidate stays.** v34 and its record become the working ROOM configuration as a
    candidate.
  - **Acceptance.** It goes to the user for a playtest; acceptance is the user's.
- **If any check fails.**
  - **Restore.** The working configuration returns to v32.
  - **Keep the record.** The candidate stays in git history, and the failure is reported.
  - **No adjustment.** Nothing is tuned or rerun with other values.
- **Afterwards.** No parameter is adjusted toward hit rate, escape rate or any difficulty measure.
