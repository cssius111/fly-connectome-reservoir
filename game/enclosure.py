"""The box the fly is in: local boundary perception and hard containment.

Two mechanisms live here, and they are deliberately different kinds of thing.

**Category A -- local sensory geometry.** `Enclosure.sense` returns a
`WallCue`: a body-frame, local percept of the nearest surface and of the
surface the fly is currently closing on. It reports a collision-relevant
optic-flow proxy (inverse time-to-contact) and bearings relative to the fly's
own heading. It does *not* report arena size, wall coordinates, the fly's
absolute position, or where an exit might be. It is computed from geometry
rather than from a rendered image: a proxy for what expansion of the
surrounding surfaces would look like, not a retinal simulation.

**Category D -- pure physics.** `Enclosure.contain` is the last-resort
geometric constraint that keeps the fly inside the box when avoidance has
already failed. It clamps and cancels the outward velocity component (a
slide), not a reflection, so it does not read as a billiard bounce.

Neither mechanism touches the connectome. The swatter threat pathway
(world -> Retina -> LC4/LPLC2 -> MaleCNS -> descending neurons -> policy) is
category C and is not represented in this module at all. What the fly *does*
with a `WallCue` is category B and lives in `flight.py`.

`Opening` exists so a visible gap can be added later without a global planner.
An opening is a span on one wall; it changes only what `sense` perceives
locally and what `contain` physically blocks. There is no exit coordinate, no
waypoint and no "distance to the gap" signal anywhere. A fly finds a gap, if
one is ever added, by flying near the boundary and perceiving that a stretch
of it no longer looms.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

TAU = 2.0 * math.pi
_EPS = 1e-9
# Wall identifiers. A cue never carries them; they are internal geometry.
LEFT, RIGHT, TOP, BOTTOM = "left", "right", "top", "bottom"
SIDES = (LEFT, RIGHT, TOP, BOTTOM)


def wrap(angle: float) -> float:
    """Signed angle in [-pi, pi)."""
    return (angle + math.pi) % TAU - math.pi


@dataclass(frozen=True, slots=True)
class Opening:
    """A gap in one wall, spanning `center +- half_width` along that wall.

    `side` LEFT/RIGHT spans y; TOP/BOTTOM spans x. Reserved for a later
    milestone: `Enclosure.openings` is empty in this build.
    """
    side: str
    center: float
    half_width: float

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise ValueError(f"unknown wall side {self.side!r}")
        if not math.isfinite(self.center) or not math.isfinite(self.half_width) or self.half_width <= 0:
            raise ValueError("opening needs a finite center and a positive half width")

    def spans(self, coordinate: float) -> bool:
        return abs(coordinate - self.center) <= self.half_width


@dataclass(frozen=True, slots=True)
class WallCue:
    """Everything the free-flight controller may know about the boundary.

    expansion        inverse time-to-contact with the surface being closed
                     on, in 1/s; 0 when nothing is being approached. This is
                     the collision-related optic-flow proxy.
    contact_bearing  body-frame bearing of that surface (radians, + = right).
                     Meaningless when expansion is 0.
    proximity        0..1 nearness of the *nearest* surface within sensing
                     range; 1 at contact, 0 beyond range.
    surface_bearing  body-frame bearing of that nearest surface.
    open_ahead       the closing surface has a gap on the current flight
                     path, so it is not perceived as a barrier.
    """
    expansion: float = 0.0
    contact_bearing: float = 0.0
    proximity: float = 0.0
    surface_bearing: float = 0.0
    open_ahead: bool = False

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in (self.expansion, self.contact_bearing,
                                              self.proximity, self.surface_bearing)):
            raise ValueError("wall cues must be finite")
        if self.expansion < 0 or not 0 <= self.proximity <= 1:
            raise ValueError("invalid expansion/proximity")
        if not all(-math.pi <= v <= math.pi for v in (self.contact_bearing, self.surface_bearing)):
            raise ValueError("wall bearings must be in [-pi, pi]")
        if type(self.open_ahead) is not bool:
            raise TypeError("open_ahead must be bool")


class Enclosure:
    """Rectangular box, optionally with gaps in its walls."""

    def __init__(self, width: float, height: float, margin: float,
                 body_radius: float, sense_range: float,
                 openings: tuple[Opening, ...] = ()):
        self.lo_x = float(margin)
        self.hi_x = float(width) - float(margin)
        self.lo_y = float(margin)
        self.hi_y = float(height) - float(margin)
        self.body_radius = float(body_radius)
        self.sense_range = float(sense_range)
        if not all(math.isfinite(v) for v in (width, height, margin, body_radius, sense_range)):
            raise ValueError("enclosure dimensions must be finite")
        if body_radius <= 0 or margin < 0:
            raise ValueError("body radius must be positive and margin nonnegative")
        if self.hi_x - self.lo_x <= 2 * body_radius or self.hi_y - self.lo_y <= 2 * body_radius:
            raise ValueError("enclosure margin leaves no playable region")
        if not (self.sense_range > 0.0):
            raise ValueError("sense_range must be positive")
        self.openings = tuple(openings)

    # ---- geometry ---------------------------------------------------------
    def _walls(self, x: float, y: float):
        """(side, clearance, outward normal, coordinate along that wall)."""
        r = self.body_radius
        return ((LEFT, x - self.lo_x - r, (-1.0, 0.0), y),
                (RIGHT, self.hi_x - x - r, (1.0, 0.0), y),
                (TOP, y - self.lo_y - r, (0.0, -1.0), x),
                (BOTTOM, self.hi_y - y - r, (0.0, 1.0), x))

    def _is_open(self, side: str, coordinate: float) -> bool:
        return any(o.side == side and abs(coordinate - o.center) + self.body_radius <= o.half_width
                   for o in self.openings)

    # ---- category A: local sensory geometry -------------------------------
    def sense(self, x: float, y: float, vx: float, vy: float, heading: float) -> WallCue:
        best_expansion, contact_bearing = 0.0, 0.0
        best_proximity, surface_bearing = 0.0, 0.0
        gap_on_path = False
        for side, clearance, (nx, ny), along in self._walls(x, y):
            # A distant opening cannot be discovered from across the box.
            if clearance > self.sense_range:
                continue
            bearing = wrap(math.atan2(ny, nx) - heading)
            if not self._is_open(side, along):
                proximity = max(0.0, min(1.0, 1.0 - clearance / self.sense_range))
                if proximity > best_proximity:
                    best_proximity, surface_bearing = proximity, bearing
            closing = vx * nx + vy * ny
            if closing <= _EPS:
                continue
            ttc = max(0.0, clearance) / closing
            crossing = (y + vy * ttc) if nx else (x + vx * ttc)
            if (math.hypot(max(0.0, clearance), crossing - along) <= self.sense_range
                    and self._is_open(side, crossing)):
                gap_on_path = True
                continue
            expansion = 1.0 / max(ttc, _EPS)
            if expansion > best_expansion:
                best_expansion, contact_bearing = expansion, bearing
        # A gap on one surface must not suppress a solid corner collision.
        return WallCue(best_expansion, contact_bearing, best_proximity,
                       surface_bearing, gap_on_path and best_expansion == 0.0)

    # ---- category D: pure physics -----------------------------------------
    def contain(self, fly) -> bool:
        """Clamp the fly back inside and cancel the outward velocity.

        A slide rather than a rebound: hard bouncing reads as a game
        boundary, and by the time this runs, avoidance has already failed.
        Returns True when the constraint had to act. A gap is a real hole, so
        a fly crossing one is not clamped.
        """
        acted = False
        r = self.body_radius
        lx, hx, ly, hy = self.lo_x + r, self.hi_x - r, self.lo_y + r, self.hi_y - r
        if fly.x < lx or fly.x > hx:
            side = LEFT if fly.x < lx else RIGHT
            if not self._is_open(side, fly.y):
                fly.x = min(max(fly.x, lx), hx)
                fly.vx = max(0.0, fly.vx) if side == LEFT else min(0.0, fly.vx)
                acted = True
        if fly.y < ly or fly.y > hy:
            side = TOP if fly.y < ly else BOTTOM
            if not self._is_open(side, fly.x):
                fly.y = min(max(fly.y, ly), hy)
                fly.vy = max(0.0, fly.vy) if side == TOP else min(0.0, fly.vy)
                acted = True
        return acted
