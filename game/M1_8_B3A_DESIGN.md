# M1.8-B3a design: the ecology reacts to executed responses, not to the policy's ALERT state

Status: **preregistered design. Requested by the user on 2026-10-21** ("continue M1.8-B,
do the ALERT stage"), as option 2 of
[M1_8_ALERT_INTERRUPTION.md](M1_8_ALERT_INTERRUPTION.md) section 5. This note fixes the
scope and the acceptance checks before any implementation; nothing is implemented in the
commit that adds it.

Baseline: the accepted runtime `feature/m1-8-b2b-iii` @ `c4f9b8f` (M1.8-B2b-iii, ROOM
`config_version` 18). B3a is the first B3 stage: it does not remove a timer, it lets the
existing ecological timers act so that later bout-structure work is attributable.

## 1. Problem

The ecology enters ALERT 43-48 times per minute in no-player flight, and 80-88 % of those
entries carry no requested or executing saccade. They come from the fixed policy's ALERT
state alone, which one spontaneous DNp01 spike sets (gate 0.80, spike 1.0) and its
smoothed turn then holds for about 0.1 s. Each entry passes through a 0.2 s RECOVER into a
fresh episode, so EXPLORE lasts about 1 s against its 3-7 s dwell and TRANSIT takes about
1 % of alive time. The research counterfactual showed that an executed-response mapping
removes the interruption without touching the policy.

## 2. Change

`Session.tick` (`game/session.py`) computes one ThreatState and hands it to both the
ecology and the lifecycle. B3a splits the ecology's input from the lifecycle's:

| Situation on a tick | Lifecycle receives | Ecology receives (B3a) |
| --- | --- | --- |
| escape action, policy ESCAPE state or an ESCAPE saccade executing | ESCAPE | ESCAPE |
| an alert saccade requested this tick, or an ALERT saccade executing | ALERT | ALERT |
| the policy reports ALERT, but no saccade is requested or executing | ALERT | **CALM** |
| otherwise | CALM | CALM |

Only the third row changes. It is selected by a new ROOM block:

```json
"ecology_threat_input": {"mode": "executed_response_v1"}
```

The default when the block is absent is `policy_state_v0`, the accepted mapping, so LAB,
GAME and any older configuration behave exactly as before. An unknown mode is rejected.

Unchanged, by construction:

- the fixed policy: its ALERT gate, its alert turn (still executed by the world), alert
  and escape saccades, and its reported behaviour state;
- the N4B1C decoder, the N4B5R geometry, the M1.7.1 swatter;
- the M1.8-A lifecycle **and its threat input**: landing eligibility and the voluntary
  takeoff hazard still pause on the accepted ALERT;
- the B1-B2b-iii kinematics: EXPLORE and ODOR_TRACK sampling, caps, scale 1.0;
- the policy observation whitelist; the recorder schema (4).

Two things change in meaning and are documented, not hidden:

- the ecology diagnostic `neural_threat_state` (recorded in session logs) reports the
  threat the ecology received, which can now be CALM while the policy's own
  `behavior_state` is ALERT;
- TRANSIT and ODOR_SEARCH, rare until now, become common (about 22-24 % and 11-15 % of
  alive time in the research study). TRANSIT speed is still the legacy shared 8 s
  sinusoid over 9-13 BL/s; converting it is a candidate later stage, not part of B3a.

Parameter class: the mapping is **C** (an interface choice). No biological claim is made
that a fly's ongoing behaviour ignores sub-threshold descending activity.

## 3. Provenance

`config_version` 18 -> 19 and `policy.calibration_paths` -> a new transfer record
`results/game/calibration_room_m1_8_b3a.json` (tool `tools/b3a_record.py`), chaining from
the accepted `calibration_room_m1_8_b2b_iii.json` with the unchanged decoder and geometry,
naming the M1.7.1 measurement, and listing exactly the changed config paths. The tool
refuses any other difference from the B2b-iii configuration. No recalibration: fixed-fly-v2
disables ecology.

## 4. Acceptance checks (fixed before implementation)

1. **Code alone is bit-identical.** With the new code and `config_version` 18, all seven
   `tools/kinematics_trace.py` scenarios and every random stream equal a baseline capture at
   `c4f9b8f`.
2. **The first divergence is the intended one.** With `config_version` 19, each scenario that
   diverges does so exactly at its first tick on which the accepted mapping would hand the
   ecology ALERT from the policy state alone. `room_no_ecology`, `game_preset` and
   `lab_preset` stay bit-identical.
3. **Unit tests.** The mapping truth table above (lifecycle and ecology inputs separately),
   the default mode, rejection of an unknown mode, the mode bound into calibration
   provenance, and LAB / GAME / no-ecology untouched.
4. **The interruption is gone.** `tools/ecology_occupancy_audit.py` on seeds 101 / 255 / 4242:
   no ecology ALERT entry without a requested or executing saccade (hard check). Occupancy,
   ALERT entries per minute and episode durations are reported, not targeted.
5. **Paired free flight.** A new tool, `tools/paired_free_flight_check.py`, reusing the B2b-iii
   method: 80 fresh seeds **9201-9280** (absent from every report, tool and holdout list on
   every branch), 180 s each, no player, the pointer parked, one Numba thread, under
   `config_version` 18 (`c4f9b8f`) and 19. Escapes classified A-D with the N4B4
   counterfactual. **Criterion: category B below 0.1/min at 95 % under the candidate.** A,
   C and D are reported; category D (self-approach) is the expected risk, because more
   TRANSIT means more fast flight toward the parked paddle.
6. **Frozen systems.** Full test suite; lifecycle scenarios replay exactly (event sets
   reported, since ecology states may differ); recorder exact replay at schema 4; escape /
   cruise study identical; swatter controlled fixtures identical; calibration resolves 1.45
   through the new record; locally: protected files, `verify_results.py`, the swatter on the
   M1.7.1 recording and the suite on Windows.
7. **Human playtest, recommended for acceptance.** The fly's behaviour visibly changes, so the
   acceptance checklist includes a short playtest; whether to require it is the user's call.
8. **No difficulty optimization.** Hit rate and survival are not computed; if one appears it is
   an outcome, and nothing is tuned because of it.

## 5. Not part of B3a

TRANSIT or other new speed sampling; timer removal or new bout models; any change to the
policy, the decoder, the lifecycle or its threat input, the recorder schema, the caps or the
scale; any learning.
