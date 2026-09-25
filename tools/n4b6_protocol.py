"""M1.8-N4B6 research: preregistered controlled slow-approach protocol.

Research only. Nothing here is imported by the runtime. This module fixes, before any neural
simulation is run, the trajectory matrix, the brain-noise seeds, the response metrics and the
classification and decision rules of M1.8-N4B6. `tools/n4b6_controlled_approach.py freeze`
records this module's sha256 and refuses to simulate if the module changes afterwards.

Stimulus design is geometry-first:

* The fly is held fixed (fixed-fly-v2 conditions: escape disabled, fly motion disabled,
  collisions disabled, ecology off) at the room centre, heading 0 (+x). Body right is +y.
* The paddle is moved only through the accepted physical swatter controller, by a scripted
  pointer, at hover height (320 units, face 0, edge-on). No click is issued, so no strike
  phase exists anywhere in N4B6.
* Every trial is [pre-hold][motion][post-hold]. The paddle is stationary during both holds.
* Before the pre-hold the paddle is placed at the start point and its orientation is set to
  the direction of its first movement, so the motion onset does not rotate the paddle. The
  tilt term then only changes where the accepted geometry itself changes it (glancing passes,
  the reversal of an aborted approach).

Speeds are anchored to the paddle closing-speed distribution of the two recorded human
sessions (approach phase, horizontal distance <= 1000 units, closing speed > 5 units/s):
p10 28-45, p25 133-136, median 284-451, p75 745-870 units/s. N4B6 uses 50 (about p10),
130 (about p25), 300 (about the median) and 800 (about p75) units/s. No trajectory was
chosen or changed after viewing a neural result.

All distances are world units (24 units = 1 body length); all times are 20 ms ticks.
"""
from __future__ import annotations

import math

DT = 0.02
HOVER_HEIGHT = 320.0
FLY_POSE = (1920.0, 1080.0, 0.0)          # x, y, heading; room centre, facing +x
PRE_HOLD_TICKS = 100                      # 2.0 s stationary paddle before motion onset
POST_HOLD_TICKS = 75                      # 1.5 s stationary paddle after the motion ends
PLACEMENT_SETTLE_TICKS = 50               # world-only ticks after placement, before the brain runs

# Brain-noise seeds: Session.reset(seed) resets the brain with seed + 977. The same seeds are
# used for every trajectory (paired design). 500001-500048 is a new range: all used seeds are
# below 440150 (N0) or in 4000-10059 (N0 / N1) and 7101-7440 (ROOM).
SEEDS = tuple(range(500001, 500049))

# Speed ladder (units/s), anchored to the human closing-speed distribution above.
V_VERY_SLOW, V_SLOW, V_MEDIUM, V_FAST = 50.0, 130.0, 300.0, 800.0


def radial(az_deg, d0, d1, v):
    """Straight radial motion at azimuth az_deg (fly frame, + = right) from horizontal
    distance d0 to d1 at speed v."""
    return {'kind': 'radial', 'az_deg': az_deg, 'd0': d0, 'd1': d1, 'v': v}


def glancing(miss, s0, s1, v):
    """Straight pass parallel to the fly's heading, at horizontal miss distance `miss` on the
    fly's right (+y). s is the forward coordinate: s0 -> s1; closest approach at s = 0."""
    return {'kind': 'glancing', 'miss': miss, 's0': s0, 's1': s1, 'v': v}


def abort(az_deg, d0, d_turn, v):
    """Radial approach d0 -> d_turn, then immediate radial recession d_turn -> d0, speed v."""
    return {'kind': 'abort', 'az_deg': az_deg, 'd0': d0, 'd_turn': d_turn, 'v': v}


def stationary(az_deg, d, seconds):
    return {'kind': 'stationary', 'az_deg': az_deg, 'd': d, 'seconds': seconds}


def orbit(radius, az0_deg, v, seconds):
    """Constant horizontal distance: clockwise (toward +azimuth) circle around the fly."""
    return {'kind': 'orbit', 'radius': radius, 'az0_deg': az0_deg, 'v': v, 'seconds': seconds}


# role: 'approach' (range closes during the intended interval), 'abort' (closes, then
# recedes), 'control' (range never closes: stationary, receding or constant).
MATRIX = {
    # A. frontal slow
    'A1_frontal_very_slow':   {'family': 'A frontal slow', 'role': 'approach', 'geometry': radial(10, 900, 200, V_VERY_SLOW)},
    'A2_frontal_slow':        {'family': 'A frontal slow', 'role': 'approach', 'geometry': radial(10, 900, 200, V_SLOW)},
    # B. frontal medium (plus a fast hover reference, still no strike)
    'B1_frontal_medium':      {'family': 'B frontal medium', 'role': 'approach', 'geometry': radial(10, 900, 200, V_MEDIUM)},
    'B2_frontal_fast_ref':    {'family': 'B frontal medium', 'role': 'approach', 'geometry': radial(10, 900, 200, V_FAST)},
    # C. lateral-oblique slow (both sides; the encoder uses azimuth only for its sign)
    'C1_oblique_slow_right':  {'family': 'C lateral-oblique slow', 'role': 'approach', 'geometry': radial(60, 900, 200, V_SLOW)},
    'C2_oblique_slow_left':   {'family': 'C lateral-oblique slow', 'role': 'approach', 'geometry': radial(-60, 900, 200, V_SLOW)},
    'C3_lateral_slow_close':  {'family': 'C lateral-oblique slow', 'role': 'approach', 'geometry': radial(90, 900, 100, V_SLOW)},
    # D. shallow glancing (closest approach at s = 0; the approach interval is s0 -> 0)
    'D1_glancing_slow':       {'family': 'D shallow glancing', 'role': 'approach', 'geometry': glancing(300, 900, -600, V_SLOW)},
    'D2_glancing_medium':     {'family': 'D shallow glancing', 'role': 'approach', 'geometry': glancing(300, 900, -600, V_MEDIUM)},
    'D3_glancing_slow_near':  {'family': 'D shallow glancing', 'role': 'approach', 'geometry': glancing(150, 900, -600, V_SLOW)},
    # E. approach then abort / recede
    'E1_abort_slow':          {'family': 'E approach then abort', 'role': 'abort', 'geometry': abort(10, 900, 400, V_SLOW)},
    'E2_abort_medium':        {'family': 'E approach then abort', 'role': 'abort', 'geometry': abort(10, 900, 300, V_MEDIUM)},
    # F. controls (range never closes)
    'F1_stationary_near':     {'family': 'F controls', 'role': 'control', 'geometry': stationary(10, 200, 10.0)},
    'F2_recede_slow':         {'family': 'F controls', 'role': 'control', 'geometry': radial(10, 200, 900, V_SLOW)},
    'F3_orbit_constant_range': {'family': 'F controls', 'role': 'control', 'geometry': orbit(300, 10, V_SLOW, 7.0)},
}


def _polar(az_deg, d):
    a = math.radians(az_deg)
    return d * math.cos(a), d * math.sin(a)


def script(geometry):
    """Pointer path relative to the fly: returns (offsets, motion_ticks, landmarks).

    offsets[k] is the pointer offset (dx, dy) at motion tick k (k = 0 .. motion_ticks - 1);
    the pointer stays at offsets[-1] during the post-hold and at offsets[0] during the pre-hold.
    landmarks give the intended closest-approach and reversal ticks (motion-tick index, or None).
    """
    g = geometry
    k = g['kind']
    if k == 'radial':
        n = int(math.ceil(abs(g['d1'] - g['d0']) / g['v'] / DT))
        if g['d1'] < g['d0']:
            ds = [max(g['d1'], g['d0'] - g['v'] * DT * i) for i in range(n + 1)]
        else:
            ds = [min(g['d1'], g['d0'] + g['v'] * DT * i) for i in range(n + 1)]
        offs = [_polar(g['az_deg'], d) for d in ds]
        closest = len(offs) - 1 if g['d1'] < g['d0'] else 0
        return offs, len(offs), {'closest_intended': closest, 'reversal_intended': None}
    if k == 'glancing':
        n = int(math.ceil(abs(g['s1'] - g['s0']) / g['v'] / DT))
        step = math.copysign(g['v'] * DT, g['s1'] - g['s0'])
        ss = [g['s0']] + [g['s0'] + step * (i + 1) for i in range(n)]
        ss = [max(s, g['s1']) if step < 0 else min(s, g['s1']) for s in ss]
        offs = [(s, g['miss']) for s in ss]
        closest = min(range(len(ss)), key=lambda i: abs(ss[i]))
        return offs, len(offs), {'closest_intended': closest, 'reversal_intended': None}
    if k == 'abort':
        n = int(math.ceil((g['d0'] - g['d_turn']) / g['v'] / DT))
        down = [max(g['d_turn'], g['d0'] - g['v'] * DT * i) for i in range(n + 1)]
        up = [min(g['d0'], g['d_turn'] + g['v'] * DT * (i + 1)) for i in range(n)]
        offs = [_polar(g['az_deg'], d) for d in down + up]
        return offs, len(offs), {'closest_intended': n, 'reversal_intended': n}
    if k == 'stationary':
        n = int(round(g['seconds'] / DT))
        return [_polar(g['az_deg'], g['d'])] * n, n, {'closest_intended': None, 'reversal_intended': None}
    if k == 'orbit':
        n = int(round(g['seconds'] / DT))
        w = g['v'] / g['radius']
        offs = [_polar(g['az0_deg'] + math.degrees(w * DT * i), g['radius']) for i in range(n)]
        return offs, n, {'closest_intended': None, 'reversal_intended': None}
    raise ValueError(k)


def initial_orientation(offsets):
    """Direction of the first pointer movement (world frame); the paddle faces its motion."""
    for a, b in zip(offsets, offsets[1:]):
        if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-9:
            return math.atan2(b[1] - a[1], b[0] - a[0])
    # Stationary: the orientation the radial approaches end with (pointing at the fly).
    return math.atan2(-offsets[0][1], -offsets[0][0])


# ----------------------------------------------------------------- metric definitions ---
METRICS = {
    'onset': 'motion onset: first motion tick (pre-hold end). Latencies are seconds from onset.',
    'retina_onset': 'first tick at or after onset with Retina theta_dot > 1e-9 rad/s (N4A level A; '
                    'the N0 envelope of theta_dot is 0).',
    'encoder_drive_onset': 'first tick at or after onset with any LPLC2/LC4 drive > 0 (N4A level B, drive).',
    'encoder_onset': 'first tick at or after onset with LPLC2 + LC4 sensory spikes > 22 on one side '
                     '(N4A level B: above the N0 per-side maximum).',
    'first_dnp01_spike': 'first DNp01 spike (either side) at or after onset.',
    'n4b1c_trigger': 'first escape of the accepted N4B1C decoder (runtime FixedEscapePolicy, fresh state at '
                     'the start of the pre-hold) at or after onset, with its trigger path(s): LATERAL, FAST, '
                     'SUSTAINED.',
    'dnp04_offline': 'first event of the frozen N4B2 research readouts on DNp04 spike trains at or after '
                     'onset: "DNp04 pair 60 ms" (same side, k 2, window 3) and "DNp04 triple 200 ms" '
                     '(same side, k 3, window 10). Offline diagnostic only; DNp04 is not whitelisted.',
    'closest_approach': 'approach / abort trials: the first tick from onset to the end of the post-hold at '
                        'which the actual 3-D paddle-fly range is within 1 unit of its minimum over that '
                        'interval (the paddle lags the pointer and settles asymptotically). For aborts this is '
                        'the actual reversal. Detection must occur at or before it.',
    'pre_onset_events': 'N4B1C escapes during the 2 s pre-hold (stationary paddle): baseline false responses.',
}

# ----------------------------------------------------------------- classification ---
CLASSIFICATION = {
    'timely_detection': 'approach / abort trials: an N4B1C trigger at or after onset and at or before the '
                        'closest-approach (or reversal) tick.',
    'late_detection': 'a first N4B1C trigger after the closest-approach tick, within the post-hold.',
    'reliable': 'timely-detection probability >= 0.90 over the 48 seeds.',
    'marginal': 'timely-detection probability >= 0.10 and < 0.90.',
    'undetected': 'timely-detection probability < 0.10.',
    'control_false_response': 'control trials: any N4B1C trigger at or after onset. Reported per trial and as '
                              'a rate per stimulus minute with an exact one-sided 95 % Poisson upper bound; '
                              'category A criterion < 0.1/min.',
    'encoder_evidence_present': 'per trial: encoder onset (sensory spikes > N0 per-side maximum) occurs at least '
                                '0.25 s (12.5 ticks, i.e. <= closest - 13 ticks) before the closest-approach tick.',
    'response_margin': '0.25 s is about one strike duration (commit 0.10 s + fast swing 0.12 s to contact in the '
                       'accepted M1.7.1 dynamics): a response that leaves less than that before the paddle '
                       'arrives cannot pre-empt a strike launched on arrival. It is a product-level margin, '
                       'not a biological constant.',
}

# ----------------------------------------------------------------- decision rule ---
DECISION_RULE = (
    'Slow-approach trajectories are A1, A2, C1, C2, C3, D1 and D3 (speed <= 130 units/s). '
    '1. A slow-approach blind spot exists if at least one slow-approach trajectory that brings the paddle '
    'to <= 200 horizontal units (A1, A2, C1, C2, C3) is marginal or undetected, or if the median timely '
    'latency of a reliable one leaves < 0.25 s before closest approach. D1 / D3 (miss 300 / 150) and '
    'the controls are reported but do not by themselves define a blind spot. '
    '2. If no blind spot exists and the controls are within the category-A criterion: outcome 1 (NO '
    'MATERIAL PROBLEM). '
    '3. If a blind spot exists, the layer is attributed per blind-spot trajectory: '
    '(a) STIMULUS / RETINA LIMIT (outcome 3) if encoder evidence is present (>= 0.25 s before closest '
    'approach) in < 50 % of seeds, i.e. the Retina / encoder stage itself does not separate the approach from the N0 '
    'envelope in time; '
    '(b) REAL DNp01 SENSITIVITY LIMIT (outcome 2) if encoder evidence is present (>= 0.25 s before '
    'closest approach) in >= 90 % of seeds while N4B1C is marginal or undetected (or leaves < 0.25 s); '
    '(c) otherwise mixed, reported as such. '
    'The overall outcome is the attribution shared by the blind-spot trajectories, or "mixed" with the '
    'per-trajectory breakdown. DNp04 is compared offline only and cannot change the outcome class; its '
    'known free-flight non-specificity (N4B2 / N4B3) is reported next to it.')
