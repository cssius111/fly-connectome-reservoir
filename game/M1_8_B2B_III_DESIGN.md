# M1.8-B2b-iii design: the next speed context, and why it is not TRANSIT

Status: **design only. Nothing is implemented and nothing is authorized.** No runtime
code, configuration, calibration record or recorder schema was changed. Implementation
needs the user's explicit approval of section 5.

Baseline: the accepted runtime `363a1a9` (M1.8-N4B5R, ROOM `config_version` 17). It
contains B2b-ii (`0d8c254`, EXPLORE speed sampling) plus the N4B1C decoder and the N4B5R
paddle geometry. Binding decisions from [M1_8_B_PLAN.md](M1_8_B_PLAN.md) section 13
(2026-10-20): the arena stays 160 x 90 BL, the recorder moves to schema 5 only if a
stage must record new fields, M1.8-B stays phenomenological, and
`room_kinematic_scale` stays exactly 1.0.

The plan's natural next step after EXPLORE was TRANSIT, which shares the 9-13 BL/s band
with ODOR_TRACK. A measurement of where flight time actually goes shows that TRANSIT
almost never occurs, and why.

## 1. Where no-player flight time goes

`tools/ecology_occupancy_audit.py` runs the accepted runtime with no player, the
pointer parked far away (the B2b-ii diagnostic setup), for 180 simulated seconds on the
B2b-ii diagnostic seeds. It changes nothing and computes no difficulty metric. Output:
`artifacts/m1_8_b2b_iii/occupancy.json` (git-ignored).

Share of alive time in each ecological state:

| Seed | EXPLORE | ODOR_TRACK | RECOVER | ALERT | ODOR_SEARCH | TRANSIT |
|---|---:|---:|---:|---:|---:|---:|
| 101 | 0.410 | 0.312 | 0.161 | 0.095 | 0.022 | 0.000 |
| 255 | 0.498 | 0.253 | 0.143 | 0.083 | 0.022 | 0.001 |
| 4242 | 0.460 | 0.210 | 0.190 | 0.119 | 0.014 | 0.006 |

Completed episodes, mean duration:

| Seed | EXPLORE | ODOR_TRACK | RECOVER | ALERT | TRANSIT |
|---|---|---|---|---|---|
| 101 | 76 x 0.97 s | 50 x 1.12 s | 140 x 0.21 s | 141 x 0.12 s | none |
| 255 | 80 x 1.12 s | 28 x 1.61 s | 123 x 0.21 s | 123 x 0.12 s | 1 x 0.24 s |
| 4242 | 93 x 0.89 s | 49 x 0.76 s | 169 x 0.20 s | 169 x 0.13 s | 1 x 1.04 s |

The configured EXPLORE dwell is a uniform 3-7 s draw (`ecology.explore_duration_seconds`),
after which EXPLORE hands over to TRANSIT. Real EXPLORE episodes last about 1 s because
**the ecology enters ALERT 41-56 times per minute**:

| Seed | ALERT entries | per minute | no looming expansion in the preceding 120 ms | no LC4/LPLC2 drive in the preceding 120 ms |
|---|---:|---:|---:|---:|
| 101 | 141 | 47.0 | 83 (59 %) | 61 (43 %) |
| 255 | 123 | 41.0 | 73 (59 %) | 56 (46 %) |
| 4242 | 169 | 56.3 | 74 (44 %) | 61 (36 %) |

Every ALERT ends in RECOVER, which leads to a fresh EXPLORE or ODOR_TRACK episode unless
another ALERT arrives first (transition counts are in the JSON). The EXPLORE timer is therefore reset before it can
expire, and TRANSIT is entered at most once per three minutes.

### 1.1 Mechanism

All of this is accepted, frozen behaviour; nothing here is a new defect in a single
component.

- The fixed policy reports ALERT when the summed DNp01 trace reaches
  `alert_threshold_fraction` x threshold = 0.55 x 1.45 = **0.80**
  (`game/action.py`, M1.2). One DNp01 spike adds 1.0 to the trace, so **a single spike
  crosses the ALERT gate**. ALERT also persists while the smoothed turn exceeds 0.03:
  one spike gives a target turn of up to 0.8 x (1.0 / 2.9) = 0.28, and the first smoothed
  step of up to 0.042 already exceeds 0.03.
- The session maps the policy's ALERT state to `ThreatState.ALERT`
  (`game/session.py`), and the ecology enters ALERT, then RECOVER for
  `alert_recover_seconds` = 0.2 s, then EXPLORE with a newly drawn dwell
  (`game/ecology.py`).
- The N4B1C escape decoder removed single- and two-spike *escapes*; the ALERT gate was
  never part of that work. Roughly half of the ALERT entries above occur with no looming
  expansion at all, consistent with spontaneous DNp01 spikes (the N0 / N4A finding that
  most spontaneous DNp01 spikes are noise kicks). The rest coincide with some visual
  drive, which under the N4B8 mirror result cannot be separated from the fly's own motion
  toward the parked paddle.

The fly's alert turn, the ALERT gate and the session's threat mapping are frozen parts of
the accepted runtime. M1.8-B must not change them. Section 5 asks for a decision.

### 1.2 Consequences for M1.8-B

- **TRANSIT** (0.0-0.6 % of alive time, at most one episode per run): sampling its speed
  now would change almost nothing observable. Deferred.
- **RECOVER** (14-19 %): its episodes last about 0.2 s, shorter than the 0.33 s time
  constant of the WORLD damping (3.0/s) that realizes any target, so a per-episode RECOVER
  sample could barely act. Low value.
- **ODOR_TRACK** (21-31 %, episodes 0.8-1.6 s, band 9-13 BL/s): the largest context that
  still uses the shared 8 s sinusoid. **Proposed for B2b-iii.**
- **B3** (bout structure and timer removal, plan section 7): premature. The EXPLORE and
  TRANSIT dwell timers it would replace rarely expire, so its effect cannot be attributed
  until the ALERT interruption is decided.

## 2. Proposed B2b-iii: ODOR_TRACK speed distribution

Same method as B2b-ii, applied to one more context.

| Item | Proposal | Class |
|---|---|---|
| Config block | `kinematics.odor_track_speed_bl_s` | - |
| Distribution | `triangular_symmetric`, the only shape the sampler accepts | C |
| Support | 9.0 to 13.0 BL/s, the accepted ODOR_TRACK envelope | B (inherited) |
| Mode | 11.0 BL/s, the midpoint, so the mean equals the accepted sinusoid mean | C |
| Resample boundary | each ecological entry into ODOR_TRACK | C (reuses the state machine) |
| Persistence | the ODOR_TRACK episode itself; it ends on odor loss, the 8 s `odor_bout_seconds` expiry, a landing attempt or a threat | unchanged |

Why the same shape: no reviewed source gives a usable central tendency, spread or shape
for odor-tracking groundspeed in ROOM terms. E05's 0.55-0.59 m/s is a horizontal airspeed
before and after plume contact in a wind tunnel with 0.4 m/s wind (its ground-relative
upwind component is only 0.09-0.15 m/s), a different quantity in a different context, and its 220-236 BL/s
could only enter through `room_kinematic_scale`, which stays 1.0. Mean and support are
preserved; the standard deviation falls from 1.414 (U-shaped sinusoid time density) to
0.816 BL/s. As in B2b-ii this is a phenomenological change of sampling model, not a
correction.

Implementation outline:

- `game/kinematics.py`: `KinematicSampler` accepts a spec per sampled context and keeps
  episode tracking per context. ODOR_TRACK draws from its **own** stream at a new seed
  offset, asserted pairwise unique with the existing offsets (world 0, flight 3907,
  ecology 7013, spawn 8191, lifecycle 18001, kinematics 24593). The EXPLORE draw
  sequence is then unchanged by construction.
- `game/world.py`: pass the new spec to the sampler.
- `game_room_config.json`: the new block; `config_version` 17 -> 18.
- `results/game/calibration_room_m1_8_b2b_iii.json`: a new transfer record chaining
  from the active `calibration_room_m1_8_n4b5r.json`, copying its decoder block,
  reusing the M1.7.1 measurement and listing exactly the changed config paths. No
  recalibration: fixed-fly-v2 disables ecology, so ODOR_TRACK sampling cannot reach the
  calibration input.
- `test_game_kinematics.py`: sampler, stream-isolation and config tests.
- `results/game/M1_8_B2B_III.md`: the validation report.

Recorder schema stays 4: no new recorded field is needed, because
`applied_target_speed_bl_s` already records the requested target.

## 3. Acceptance checks (fixed before implementation)

1. **Bit-identity where nothing should change.** LAB and GAME presets and the
   `room_no_ecology` scenario stay bit-identical. Every ROOM scenario is identical up to
   its first ODOR_TRACK sample; the first divergence (scenario, tick, column, sampler
   draw index) is recorded with `tools/kinematics_diff.py` as positive evidence.
2. **Stream isolation.** A regression test makes 2,000 alternating sampler calls and
   shows that only the new stream advances: world, spawn, flight, ecology, lifecycle and
   the EXPLORE stream stay byte-identical.
3. **Offline distribution.** 200,000 seeded draws: support inside [9, 13], mean within
   0.01 of 11.0, sd within 0.01 of 0.816, and a histogram against the legacy sinusoid.
4. **Closed-loop diagnostics.** The same three no-player 180 s runs: requested and actual
   ODOR_TRACK speed, state occupancy, saccade intervals and lifecycle events, plus a
   re-run of `tools/ecology_occupancy_audit.py`.
5. **Free-flight escapes (paired).** 240 minutes of no-player ROOM free flight on fresh
   seeds outside every listed holdout, each run under both `config_version` 17 and the
   candidate. Report escapes per minute with exact Poisson 95 % bounds for each, and
   classify every escape that occurs only under the candidate with the A-D categories.
   Category B must stay below 0.1/min at 95 % (the provisional criterion); C and D are
   tracked.
6. **Frozen systems.** Full test suite; M1.7.1 fixtures byte-identical; the escape study
   reproduces its 54 cases; M1.8-A lifecycle scenarios replay exactly; recorder exact
   replay at schema 4; policy observation whitelist unchanged; calibration resolves 1.45
   through the new record; the 20 protected files and `verify_results.py` on the local
   Windows checkout.
7. **No difficulty optimization.** Hit rate, survival and time-to-first-hit are not
   computed. If one appears in a report it is labelled as an outcome, and no parameter
   changes because of it.

## 4. Explicitly not part of B2b-iii

TRANSIT, ODOR_SEARCH or RECOVER sampling; acceleration or deceleration models; timer
removal (B3); any change to `room_kinematic_scale`, the three caps, `escape_impulse` or
the escape clamp; the ALERT gate, the alert turn or the session's threat mapping; the
N4B1C decoder, the N4B5R geometry, the M1.7.1 swatter or the M1.8-A lifecycle; a recorder
schema change; any learning.

## 5. Decisions for the user

1. **Scope.** Approve B2b-iii as the ODOR_TRACK speed distribution in section 2, or
   choose otherwise (for example TRANSIT despite section 1.2).
2. **The ALERT interruption** (section 1). Options:
   - (a) accept it as documented behaviour of the accepted runtime and continue;
   - (b) open a research-only investigation of how the ecology consumes ALERT, for
     example whether ecological state should react only to executed saccades and escapes
     rather than to the policy's ALERT state. Any resulting runtime change would need its
     own approval and must leave the fixed policy, the N4B1C decoder and the lifecycle
     untouched;
   - (c) defer the question until B3.
3. **Check 5.** Whether the paired 240-minute free-flight check is required for this
   stage. It is the most expensive check, and B2b-ii did not run one.
