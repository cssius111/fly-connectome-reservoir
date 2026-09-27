"""M1.8-N4B5 research: paddle apparent-size formulas (offline only).

Research only. Nothing here is imported by the runtime. Every function is a pure function of
recorded WORLD state (fly and paddle positions, paddle height, face and orientation), so it
can be evaluated on recorded runs or monkeypatched into a research re-simulation. It is
never a policy input.

The runtime formula (game/world.py, World.visual_half_size) is reproduced exactly as G0. The
alternatives were chosen from geometry before the full event dataset was evaluated, and are
frozen by `tools/n4b5_analysis.py freeze` (sha256 of this module).

Coordinate conventions (from game/world.py and game/physical_swatter.py):
* the play plane is (x, y) in world units, y growing downward on screen; the fly lives in
  the plane (z = 0) and the paddle centre is at height `height` above it;
* `orientation` is a world-plane angle: the paddle's physical approach / handle axis,
  steered toward the paddle's velocity direction during approach and latched to the attack
  direction during a strike;
* `face` runs from 0 (edge-on, hovering) to 1 (face-on, striking);
* `bearing` in the runtime formula is the HORIZONTAL direction from the paddle to the fly.

The Retina uses theta = 2 atan(half / R), with R the 3D fly-paddle distance.

Candidates:
* G0  current: r (e + (1 - e) face) (1 - a (1 - face) |sin(bearing - orientation)|),
  with e = 0.65 and a = 0.25.
* G1  isotropic control: a = 0.
* G2  reduced anisotropy: a = 0.10.
* G3  elevation-aware attenuation: the anisotropy term is multiplied by cos(elevation) =
  horizontal distance / R. Rationale: bearing-dependent foreshortening of a plate comes
  from the horizontal component of the viewing direction; seen from straight below, the
  horizontal bearing cannot change the projection. This keeps G0 unchanged at low
  elevation and removes the bearing term overhead.
* G4  explicit projected disk (reference geometry, not a fitted heuristic): a thin circular
  disk of radius r, whose unit normal is horizontal along `orientation` at face 0 and
  tilts to vertical (facing the fly plane) at face 1, tilt angle face * 90 deg. The
  perspective projection of a small disk is an ellipse with semi-major axis r and
  semi-minor axis r |n . v| (v the unit view direction). The reported half-size is the
  mean projected semi-axis, r (1 + |n . v|) / 2. That spans [0.5 r, r], the same range as
  G0's [0.49 r, r], so no parameter is fitted.
"""
from __future__ import annotations

import math

EDGE_ON = 0.65
ANISOTROPY = 0.25
PADDLE_RADIUS = 144.0

CANDIDATES = ('G0_current', 'G1_isotropic', 'G2_reduced_0p10', 'G3_elevation_aware', 'G4_projected_disk')


def _bearing(fx, fy, px, py):
    return math.atan2(fy - py, fx - px)


def half_size(name, fx, fy, px, py, height, face, orientation, r=PADDLE_RADIUS, e=EDGE_ON, a=ANISOTROPY):
    """Apparent half-size (world units) of the paddle for one candidate."""
    base = e + (1.0 - e) * face
    if name == 'G0_current':
        return r * base * (1.0 - a * (1.0 - face) * abs(math.sin(_bearing(fx, fy, px, py) - orientation)))
    if name == 'G1_isotropic':
        return r * base
    if name == 'G2_reduced_0p10':
        return r * base * (1.0 - 0.10 * (1.0 - face) * abs(math.sin(_bearing(fx, fy, px, py) - orientation)))
    if name == 'G3_elevation_aware':
        dh = math.hypot(fx - px, fy - py)
        rng = math.sqrt(dh * dh + height * height)
        cos_elev = dh / rng if rng > 0 else 0.0
        return r * base * (1.0 - a * cos_elev * (1.0 - face) * abs(math.sin(_bearing(fx, fy, px, py) - orientation)))
    if name == 'G4_projected_disk':
        tilt = face * math.pi / 2.0
        n = (math.cos(orientation) * math.cos(tilt), math.sin(orientation) * math.cos(tilt), -math.sin(tilt))
        vx, vy, vz = px - fx, py - fy, height            # fly -> paddle
        norm = math.sqrt(vx * vx + vy * vy + vz * vz)
        c = abs(n[0] * vx + n[1] * vy + n[2] * vz) / norm if norm > 0 else 1.0
        return r * (1.0 + c) / 2.0
    raise ValueError(name)


def theta(name, fx, fy, px, py, height, face, orientation, **kw):
    """Retina theta for one candidate, from the world state the Retina is projected from."""
    dx, dy = px - fx, py - fy
    rng = math.sqrt(dx * dx + dy * dy + height * height)
    return 2.0 * math.atan(half_size(name, fx, fy, px, py, height, face, orientation, **kw) / max(rng, 1e-6))


def decompose(prev, cur, name='G0_current'):
    """Split the theta change between two consecutive world states into range, bearing,
    orientation and face contributions (evaluated sequentially). States are dicts with
    fx, fy, px, py, height, face, orientation."""
    def th(s):
        return theta(name, s['fx'], s['fy'], s['px'], s['py'], s['height'], s['face'], s['orientation'])

    def rng(s):
        return math.sqrt((s['px'] - s['fx']) ** 2 + (s['py'] - s['fy']) ** 2 + s['height'] ** 2)

    def hs(s):
        return half_size(name, s['fx'], s['fy'], s['px'], s['py'], s['height'], s['face'], s['orientation'])
    t0 = th(prev)
    h0 = hs(prev)
    d_range = 2 * math.atan(h0 / rng(cur)) - t0
    # bearing: move the fly-paddle relative position, keep face and orientation
    s_b = dict(cur, face=prev['face'], orientation=prev['orientation'])
    d_bearing = 2 * math.atan(hs(s_b) / rng(cur)) - 2 * math.atan(h0 / rng(cur))
    s_o = dict(cur, face=prev['face'])
    d_orient = 2 * math.atan(hs(s_o) / rng(cur)) - 2 * math.atan(hs(s_b) / rng(cur))
    d_face = th(cur) - 2 * math.atan(hs(s_o) / rng(cur))
    return {'range': d_range, 'bearing': d_bearing, 'orientation': d_orient, 'face': d_face,
            'total': th(cur) - t0}


def elevation_deg(fx, fy, px, py, height):
    return math.degrees(math.atan2(height, math.hypot(fx - px, fy - py)))
