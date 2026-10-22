# M1.8 research note: the ALERT interruption of the ecology

Status: **research only. Nothing in the runtime was changed and no fix is selected.** No
runtime file, configuration, calibration record, policy, decoder, lifecycle or recorder
schema was modified. Authorized by the user on 2026-10-20 as option (b) of
[M1_8_B2B_III_DESIGN.md](M1_8_B2B_III_DESIGN.md) section 5.

## 1. The finding

The B2b-iii design audit (`tools/ecology_occupancy_audit.py`, accepted runtime `363a1a9`,
no player, seeds 101 / 255 / 4242, 180 s each) found that the ecology enters ALERT
**41-56 times per minute**, that EXPLORE episodes last about 1 s against their configured
3-7 s dwell, and that TRANSIT takes at most 0.6 % of alive time.

Mechanism, all in accepted code:

1. The fixed policy reports the behaviour state ALERT when the summed DNp01 trace reaches
   `alert_threshold_fraction` x threshold = 0.55 x 1.45 = 0.80, or while its smoothed turn
   exceeds 0.03 (`game/action.py`). One DNp01 spike adds 1.0 to the trace, so a single
   spike is enough, and the smoothed turn then holds ALERT for about 0.1 s.
2. The session maps that state to `ThreatState.ALERT` for both the ecology and the
   lifecycle (`game/session.py`), even when no alert saccade is requested or executing.
   One spike decays below 0.80 within two ticks, so it never reaches the policy's own
   3-tick alert-saccade dwell: the fly turns slightly but executes no saccade.
3. The ecology enters ALERT, then RECOVER for `alert_recover_seconds` = 0.2 s, then a fresh
   EXPLORE or ODOR_TRACK episode with a newly drawn dwell (`game/ecology.py`).

The N4B1C escape decoder removed single- and two-spike *escapes*; the ALERT gate was never
part of that work.

## 2. Method

`tools/alert_interruption_study.py` wraps `session.ecology.step` on a live session and
changes only the ThreatState handed to the ecology. The policy, decoder, lifecycle (which
keeps receiving the accepted threat) and world run unchanged; ESCAPE is never altered.
Three mappings were compared on the runtime with B2b-iii (`config_version` 18), no player,
the pointer parked far away, seeds 101 / 255 / 4242, 180 s each:

- **accepted**: the session's mapping;
- **executed_response**: the ecology sees ALERT only while an alert or escape saccade is
  requested or executing; the policy's ALERT state alone is shown to it as CALM;
- **sustained_alert**: as executed_response, but the ecology also sees ALERT once the
  policy's ALERT state has lasted the policy's own alert-saccade dwell
  (`policy.alert_saccade_dwell_seconds` = 0.06 s, 3 ticks).

Output: `artifacts/m1_8_alert/study.json` (git-ignored). No hit rate, survival or
difficulty measure was computed.

## 3. Results

Ranges over the three seeds:

| Measure | accepted | executed_response | sustained_alert |
| --- | --- | --- | --- |
| ALERT entries per minute | 43.0-48.3 | **1.7-2.0** | 36.7-45.3 |
| ALERT entries with no saccade requested or executing | 80-88 % | 0 % | 89-94 % |
| ALERT + RECOVER share of alive time | 24-27 % | 1 % | 19-24 % |
| EXPLORE mean episode | 0.97-1.25 s | **4.17-4.52 s** | 1.11-1.46 s |
| ODOR_TRACK mean episode | 0.80-1.20 s | 4.31-5.50 s | 0.74-1.15 s |
| TRANSIT share of alive time (entries per run) | 0.3-1.5 % (1-3) | **22-24 % (13-14)** | 0-1.2 % (0-3) |
| ODOR_SEARCH share of alive time | 1-2 % | 11-15 % | 2-3 % |
| Touchdowns / voluntary takeoffs per run | 5, 2, 2 / 5, 2, 2 | 4, 2, 3 / 4, 2, 3 | 4, 2, 2 / 3, 2, 2 |
| Policy escapes per run | 0, 1, 0 | 0, 0, 0 | 0, 0, 0 |
| Perched ticks on which the lifecycle sees a non-CALM threat | 7-8 % | 7-9 % | 7-10 % |

Reading:

- Under the accepted mapping, **80-88 % of the ALERT entries carry no executed response**:
  they come from the policy's ALERT state alone, mostly single spontaneous DNp01 spikes.
- With executed_response the configured ecological timers act as written: EXPLORE episodes
  of about 4.3 s (configured 3-7 s, minus genuine interruptions), TRANSIT episodes of about
  3.0 s (configured 2-5 s) at 22-24 % of alive time, ODOR_SEARCH episodes of 4.7-5.8 s
  against the 6 s `search_seconds`, and ODOR_TRACK bouts of 4.3-5.5 s instead of about 1 s.
- sustained_alert barely helps, because the policy's ALERT state after one spike already
  outlasts the 0.06 s dwell through the smoothed turn.
- Landing, feeding and voluntary takeoff occur under every mapping. Escapes are too rare in
  9 minutes per mapping to compare.
- While perched, the lifecycle sees a non-CALM threat on 7-10 % of ticks under every
  mapping, because it was deliberately left on the accepted threat. CALM gates its landing
  eligibility and voluntary-takeoff hazard, so the same interruption also slows those
  accruals. That is frozen M1.8-A behaviour and is not altered here.

## 4. Interpretation

The ecology's dwell timers (`explore_duration_seconds`, `transit_duration_seconds`,
`search_seconds`, `odor_bout_seconds`) and the TRANSIT state, which M1.8-B set out to
replace with evidence-driven structure, are in practice overridden by about 45 neural
ALERT interruptions per minute. Most of these interruptions carry no behaviour the fly
executes. The activity budget the runtime produces is therefore set mainly by spontaneous
DNp01 activity crossing a gate that one spike can cross, not by the ecological model.

This is neither a decoder defect nor a lifecycle defect. It is an interface choice: the
ecology reacts to the policy's internal ALERT state rather than to what the fly does.
Under the N4B8 mirror result, the remaining ALERT entries that do coincide with visual drive
cannot be separated from the fly's own approach toward the parked paddle anyway.

## 5. Options (none selected)

1. **Keep the accepted mapping** and document the activity budget as noise-dominated. B3
   (timer removal) would then be largely moot, because the timers rarely expire.
2. **Adopt the executed-response mapping for the ecology only**, as a separate,
   preregistered stage. It is a runtime change to `game/session.py` (the threat handed to
   the ecology); the fixed policy, the N4B1C decoder, the lifecycle's threat input and the
   escape paths would stay untouched. It changes the activity budget substantially: about a
   quarter of alive time moves into TRANSIT at 9-13 BL/s and ODOR_SEARCH grows, which can
   change self-approach escapes (category D) and difficulty. It would need the paired
   free-flight check of B2b-iii, a recorder exact-replay check and a human playtest.
3. **A different ecology-side rule**, for example reacting to ALERT only when DNp01
   evidence reaches the two-spike level. Not studied here; it would need its own design.

Changing the policy's ALERT gate itself, or the lifecycle's threat input, would reopen
frozen systems (the fixed baseline policy and M1.8-A) and is not proposed.

## 6. Reproduction

```text
python tools/ecology_occupancy_audit.py      # the original finding (section 1)
python tools/alert_interruption_study.py     # the three mappings (sections 2-3)
```
