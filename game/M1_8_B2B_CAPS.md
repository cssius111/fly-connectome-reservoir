# M1.8-B2b cap architecture design note

Status: **design only. Not implemented, not authorized.** No distribution is sampled, no
`room_kinematic_scale` value is chosen, no cap value is chosen, and `fly.max_speed` is
unchanged.

Baseline: B2a accepted, committed and frozen at `4d9566c`. Decision taken: **do not raise
the shared `max_speed`.** The B2a audit showed that cap also binds the accepted neural
escape path, so raising it would silently widen the frozen M1.8-A escape envelope.

## A. The three cap fields

| Field | Location | Units | Applies to | Class |
| --- | --- | --- | --- | --- |
| `ecological_cap_bl_s` | `kinematics` config -> profile | BL/s | sampled ecological locomotion only | C |
| `neural_cap_units_s` | `kinematics` config -> profile | world units/s | threat-priority cruise and the escape impulse | C |
| `safety_ceiling_units_s` | `kinematics` config -> executor | world units/s | every path, applied last | C |

All three are engineering values. None is a biological claim, and the safety ceiling in
particular is a numerical guard that should never bind in normal play.

On `KinematicProfile` the existing `max_speed` / `clamp_speed` pair becomes explicit:

```python
profile_cap: float = math.inf      # world units/s, already converted from the field above
safety_ceiling: float = math.inf   # engineering guard, applied last
clamp_speed: bool = False          # unchanged: whether the executor clamps at all
```

The executor clamps once, against `min(profile_cap, safety_ceiling)`. Lifecycle profiles
keep the frozen legacy value as their `profile_cap`, so M1.8-A needs no new config field
of its own.

## B. Where each current `max_speed` usage goes

From the measured B2a audit:

| Current usage | Moves to | Note |
| --- | --- | --- |
| Ecological target truncation, `min(max_speed, ecological_units(bl))` | `ecological_cap_bl_s` | the only cap B2b intends to change |
| Baseline / threat-priority cruise clamp | `neural_cap_units_s` | frozen at today's value |
| Neural escape impulse clamp | `neural_cap_units_s` | frozen; see section C of the freeze below |
| Lifecycle voluntary takeoff, `min(max_speed, 6 BL/s * body)` | legacy value via lifecycle profile | frozen M1.8-A |
| Lifecycle landing approach target | legacy value via lifecycle profile | frozen M1.8-A, `clamp_speed` stays off |
| Recorder `speed_cap_exceeded` diagnostic | `safety_ceiling_units_s` | keep the `+1e-6` tolerance: sideslip re-derives velocity after the clamp |
| `tools/room_sanity.py` displacement assertion | `safety_ceiling_units_s` | |

## C. Preserving bit-identity at legacy values

Set `ecological_cap_bl_s = 1000/24 = 41.666...`, `neural_cap_units_s = 1000.0`,
`safety_ceiling_units_s = 1000.0`. Then every site reduces to today's arithmetic:

- `min(1000.0, x)` is unchanged wherever the legacy `max_speed` appeared.
- `min(profile_cap, safety_ceiling)` = `min(1000.0, 1000.0)` = `1000.0` exactly.
- `ecological_cap_bl_s * body_length` = `41.666... * 24`. **This is the one risk**: it is
  not guaranteed to reproduce `1000.0` bit-for-bit. Avoid it by storing the ecological cap
  in BL/s but comparing in BL/s, or by configuring the legacy stage in world units and
  converting only when the value is deliberately changed. Prove whichever form is chosen
  with `tools/kinematics_diff.py` before accepting it, exactly as B2a proved the `* 1.0`.

Recommended staging, each accepted on its own trace comparison:

1. **B2b-i** — introduce all three fields at legacy-equivalent values. Expected
   bit-identical; if not, stop and report the first divergence rather than accept drift.
2. **B2b-ii** — first sampled distribution (section G). Expected first intentional
   divergence.

## D. Keeping the ecological cap off neural escape

Already structurally guaranteed by the B1 arbitration, and verified in B2a:
`World._neural_active` returns true whenever `action.escape` is set, regardless of
strength or direction, so any tick that applies the escape impulse also has
`threat_priority == True`. The resolver therefore returns the `neural_priority` profile,
which carries `neural_cap_units_s`. The ecological cap is never in scope on an escape
tick. A regression test should pin this rather than rely on the implication holding.

**One seam to document honestly.** The cap changes mid-decay. The escape *peak* is
produced on threat-priority ticks under the frozen neural cap, but once the action and
the ESCAPE saccade end, the fly returns to an ecological profile and its post-escape
recovery runs under the ecological cap and target. So B2b preserves the accepted escape
envelope but will change the post-escape recovery trajectory. That is intended, and the
B2b metrics must be able to show it.

## E. Leaving lifecycle takeoff and landing untouched

`KinematicResolver.landing_approach` and `lifecycle_direct` carry the frozen legacy cap,
keep `clamp_speed=False` for the approach, and keep the unscaled
`bl_s * body_length` conversion — B2a already established that the ROOM mapping is not
applied to landing. Voluntary launch keeps `min(cap, 6 BL/s * body)`.

Acceptance test: after the ecological cap is deliberately changed in B2b-ii, the three
M1.8-A lifecycle scenario traces (1200 / 340 / 120 ticks) must remain **bit-identical**,
because no lifecycle-owned path reads the ecological cap. That is a sharper check than
merely re-running the lifecycle event counts.

## F. Saturation under candidate scales

Sampled contexts and their current bands: EXPLORE 5-8, TRANSIT 9-13, ODOR_TRACK 9-13,
ODOR_SEARCH 4-7, RECOVER 5-8 BL/s. TRANSIT/ODOR_TRACK have the highest top, so they set
the required cap. Escape impulse is 880 units/s = 36.67 BL/s; neural cap is 41.67 BL/s.

| `room_kinematic_scale` | TRANSIT band (BL/s) | Ecological cap needed (BL/s) | = units/s | Eco top vs escape impulse |
| --- | --- | --- | --- | --- |
| 1.00 (today) | 9.0-13.0 | 13.0 | 312 | 0.35x |
| 2.00 | 18.0-26.0 | 26.0 | 624 | 0.71x |
| 3.21 | 28.9-41.7 | 41.7 | 1002 | 1.14x |
| 4.00 | 36.0-52.0 | 52.0 | 1248 | 1.42x |
| 6.15 (TRANSIT into E03's 60-80) | 55.4-80.0 | 80.0 | 1919 | 2.18x |
| 8.00 | 72.0-104.0 | 104.0 | 2496 | 2.84x |
| 12.00 | 108.0-156.0 | 156.0 | 3744 | 4.25x |

**The binding constraint is not the cap itself — it is the escape envelope.** Above scale
≈ 3.21 the ecological cap must exceed the frozen neural cap of 41.67 BL/s. At that point
a fly cruising above 41.67 BL/s that enters escape is **clamped downward** by the neural
cap: escaping would make it slower than cruising. Separately, at scale 6.15 the cruise top
is 2.18x the escape impulse, so the impulse becomes a small perturbation on top of cruise
rather than a decisive escape.

So "freeze the neural cap and raise only the ecological cap" is self-consistent only up to
roughly **scale 3.21**, which reaches about 29-42 BL/s for TRANSIT — still well short of
E03's 60-80 BL/s. Going further requires one of:

- accept a lower scale than literature parity, and say so plainly;
- treat the neural cap as a pure numerical guard raised in step, while preserving the
  escape *impulse dynamics* rather than the escape *cap number* — this needs an explicit
  argument that "equivalent to current 1000 units/s behavior" means the dynamics, not the
  literal ceiling;
- revisit `escape_impulse` jointly, which needs separate recorded evidence and re-opens
  M1.8-A acceptance.

**No selection is made here.** This is the decision that should be taken before B2b-ii,
not discovered during it.

## G. First context to receive a real distribution

**EXPLORE.** Reasons: it is the most frequently active ecological state, so a change is
immediately visible in the traces; its band (5-8 BL/s) is the furthest from every cap, so
the first distribution can be evaluated without entangling the saturation question; and it
is independent of odor state, wind reliability and the lifecycle, so a divergence has a
single cause. `TRANSIT` and `ODOR_TRACK` should follow only after the cap decision in
section F is settled, because they are the contexts that saturate first.

## H. The first intentional non-bit-identical event

The first tick on which `KinematicSampler.target_speed_bl_s` returns a float instead of
`None` — concretely, the first airborne EXPLORE tick with ecology active,
`threat_priority` false and the lifecycle not owning the actuator.

That change must be landed alone, with:

- a before/after capture from `tools/kinematics_trace.py`;
- the first-divergence scenario, tick and column recorded from
  `tools/kinematics_diff.py`, as positive evidence of the intended change;
- confirmation that `existing_rng_streams_unchanged` is still true for `world`, `spawn`,
  `flight` and `ecology`, and that only the `kinematics` stream advanced;
- the three M1.8-A lifecycle traces still bit-identical (section E);
- `game_preset` and `lab_preset` traces still bit-identical, since neither has a
  `kinematics` config block.

Everything else in B2b should be staged after that single attributable divergence.
