"""Phenomenological local lifecycle, separate from the frozen neural policy.

Geometry and attachment belong to WORLD. See LIFECYCLE.md for evidence classes.
Sub-timestep takeoff dynamics are not explicitly resolved.
"""
from dataclasses import asdict, dataclass
import math
import numpy as np
from .action import MotionState
from .ecology import ThreatState


@dataclass(frozen=True, slots=True)
class LandingSense:
    affordance: float = 0.0
    bearing: float = 0.0                 # local retinal bearing, radians
    angular_extent: float = 0.0          # disk silhouette diameter, radians
    angular_expansion: float = 0.0       # analytic retinal expansion, rad/s
    odor: float = 0.0
    contact: bool = False
    food_contact: bool = False

    def __post_init__(self):
        if not all(math.isfinite(v) for v in asdict(self).values()):
            raise ValueError('landing observations must be finite')
        if not 0 <= self.affordance <= 1 or not 0 <= self.angular_extent <= math.pi:
            raise ValueError('invalid visual landing observation')
        if abs(self.bearing) > math.pi or self.odor < 0:
            raise ValueError('invalid local landing cue')


class LifecycleController:
    """Local history -> approach modules -> contact -> motivated departure.

    Only a nonzero Action.escape authorizes an escape launch. A threat state
    can abort an approach but cannot fabricate escape direction or magnitude.
    MotionState speeds supplied here are in body lengths/s (not neural units).
    """
    def __init__(self, config, seed):
        self.config = dict(config)
        for name, value in config.items():
            if name == 'enabled':
                continue
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError('positive finite lifecycle parameter required: ' + name)
        self.reset(seed)

    def reset(self, seed):
        self.rng = np.random.default_rng(seed + 18001)
        self.mode, self.phase = 'AIRBORNE', 'NONE'
        self.elapsed = self.eligible = self.lost = self.cooldown = self.motivation = 0.0
        self.departure_level = float(self.rng.exponential())
        self.failed_approaches = 0
        self.committed = self.feeding = False
        self.events = []
        self.reason = 'initial_airborne'
        self.target_speed = self.turn = 0.0
        self.last_sense = LandingSense()
        self.profile = 'ordinary_flight'
        self.applied_profile = {'name': 'ordinary_flight'}

    @property
    def stationary(self):
        return self.mode in ('TOUCHDOWN', 'PERCHED')

    def event(self, name, reason):
        self.reason = reason
        self.events.append({'type': name, 'reason': reason})

    def abort(self, reason):
        self.event('approach_abort', reason)
        self.failed_approaches += 1
        self.mode, self.phase = 'AIRBORNE', 'NONE'
        self.committed = False
        self.cooldown = self.config['retry_seconds']
        self.eligible = self.elapsed = 0.0

    def step(self, sense, motion, threat, dt, escape_authorized=False):
        if type(sense) is not LandingSense or type(motion) is not MotionState or type(threat) is not ThreatState:
            raise TypeError('lifecycle requires restricted local sense, motion and threat types')
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError('positive finite lifecycle timestep required')
        self.events = []
        self.last_sense = sense
        c = self.config
        self.elapsed += dt
        self.cooldown = max(0.0, self.cooldown - dt)
        speed = math.hypot(motion.forward_speed, motion.lateral_speed)
        self.profile = 'ordinary_flight'
        if self.mode.startswith('TAKEOFF_'):
            self.mode, self.phase = 'AIRBORNE', 'NONE'
            self.elapsed = 0.0
        if self.stationary:
            if not sense.contact:
                raise RuntimeError('stationary fly has no physical surface contact')
            if self.mode == 'TOUCHDOWN':
                self.mode = 'PERCHED'
            feeding = sense.food_contact and sense.odor >= c['feeding_odor_on']
            if feeding != self.feeding:
                self.event('feed_start' if feeding else 'feed_end', 'local_food_contact')
            self.feeding = feeding
            if escape_authorized:
                self.launch(True)
            else:
                # Integrated seeded hazard, not a preset departure countdown.
                rate = c['departure_rate_per_second'] * (1 + self.elapsed / c['dwell_history_seconds'])
                rate /= 1 + c['odor_persistence_gain'] * sense.odor
                if self.feeding:
                    rate *= c['feeding_departure_fraction']
                if self.elapsed >= c['minimum_perch_seconds'] and threat is ThreatState.CALM:
                    self.motivation += rate * dt
                    if self.motivation >= self.departure_level:
                        self.launch(False)
            self.profile = 'stationary_contact' if self.stationary else self.mode.lower()
            return
        if self.mode == 'LAND_APPROACH' and threat is ThreatState.ESCAPE:
            self.abort('neural_' + threat.value.lower())
            return
        visible = sense.affordance >= c['affordance_on'] and abs(sense.bearing) <= math.radians(c['orientation_limit_degrees'])
        if self.mode == 'AIRBORNE':
            eligible = visible and sense.angular_expansion > 0 and threat is ThreatState.CALM and self.cooldown == 0
            self.eligible = self.eligible + dt if eligible else 0.0
            if self.eligible >= c['orientation_dwell_seconds']:
                self.mode, self.phase = 'LAND_APPROACH', 'ORIENT'
                self.elapsed = self.lost = 0.0
                self.committed = False
                self.event('approach_onset', 'sustained_local_visual_approach')
        if self.mode != 'LAND_APPROACH':
            return
        self.lost = self.lost + dt if not visible or sense.angular_expansion < 0 else 0.0
        if self.lost >= c['cue_loss_seconds'] or self.elapsed > c['approach_timeout_seconds']:
            self.abort('fly_by_or_cue_loss' if self.lost >= c['cue_loss_seconds'] else 'approach_safety_timeout')
            return
        angle = math.radians(c['commit_extent_degrees'])
        load = sense.angular_extent / angle + max(0.0, sense.angular_expansion) * c['expansion_braking_seconds']
        self.target_speed = max(c['contact_speed_bl_s'], speed / (1 + load * load))
        self.turn = max(-c['orientation_cap_rad_s'], min(c['orientation_cap_rad_s'], c['orientation_gain'] * sense.bearing))
        self.phase = 'DECELERATE' if load >= 1 else 'ORIENT'
        if (sense.angular_extent >= angle and abs(sense.bearing) <= math.radians(c['commit_bearing_degrees'])
                and speed <= c['commit_speed_bl_s']):
            if not self.committed:
                self.event('approach_commit', 'visual_extent_alignment_and_speed')
            self.committed = True
        if self.committed:
            self.phase = 'LEG_COMMIT'
        self.profile = 'visual_approach'

    def touchdown(self):
        if self.mode != 'LAND_APPROACH' or not self.committed:
            raise RuntimeError('touchdown requires a committed visual approach')
        self.mode, self.phase = 'TOUCHDOWN', 'CONTACT'
        self.elapsed = self.motivation = 0.0
        self.departure_level = float(self.rng.exponential())
        self.event('touchdown', 'swept_surface_contact')
        self.event('perch_start', 'stable_surface_attachment')
        self.profile = 'stationary_contact'

    def launch(self, escape):
        if self.feeding:
            self.event('feed_end', 'departure')
        self.feeding = self.committed = False
        self.mode = 'TAKEOFF_ESCAPE' if escape else 'TAKEOFF_VOLUNTARY'
        self.phase = 'LAUNCH'
        self.event('perch_end', 'neural_escape' if escape else 'local_history_motivation')
        self.event('escape_takeoff' if escape else 'voluntary_takeoff', self.reason)
        self.cooldown = self.config['retry_seconds']
        self.eligible = self.elapsed = 0.0

    def diagnostics(self):
        return {'mode': self.mode, 'phase': self.phase, 'committed': self.committed,
                'feeding': self.feeding, 'reason': self.reason, 'mode_seconds': self.elapsed,
                'departure_motivation': self.motivation, 'departure_level': self.departure_level,
                'failed_approaches': self.failed_approaches, 'sense': asdict(self.last_sense),
                'requested_profile': self.profile, 'applied_profile': dict(self.applied_profile),
                'events': list(self.events)}


class LifecycleMetrics:
    """Alive-post-step simulator metrics; complete and censored bouts separated."""
    def __init__(self):
        from collections import Counter
        self.counts = Counter()
        self.events = Counter()
        self.perches, self.flights, self.censored = [], [], []
        self.kind = None
        self.seconds = 0.0
        self.left_censored = True

    def end_episode(self):
        if self.kind is not None:
            self.censored.append({'kind': self.kind, 'seconds': self.seconds,
                                  'left_censored': self.left_censored, 'right_censored': True})
        self.kind, self.seconds, self.left_censored = None, 0.0, True

    def capture(self, life, alive, dt):
        if not alive:
            self.end_episode()
            return
        # TOUCHDOWN is attached; both launch modes are airborne.
        kind = 'perched' if life.stationary else 'airborne'
        self.counts['alive'] += 1
        self.counts[kind] += 1
        self.counts['feeding'] += int(life.feeding)
        self.events.update(event['type'] for event in life.events)
        if self.kind is not None and self.kind != kind:
            if self.left_censored:
                self.censored.append({'kind': self.kind, 'seconds': self.seconds,
                                      'left_censored': True, 'right_censored': False})
            else:
                (self.perches if self.kind == 'perched' else self.flights).append(self.seconds)
            self.seconds, self.left_censored = 0.0, False
        self.kind = kind
        self.seconds += dt

    def report(self):
        import statistics
        n = self.counts['alive']
        return {'label': 'simulator metrics; not real activity-budget estimates',
                'denominator': 'alive post-step ticks; fatal ticks excluded', 'alive_ticks': n,
                'fractions': {k: self.counts[k]/n if n else None for k in ('airborne','perched','feeding')},
                'events': {k: self.events[k] for k in ('approach_onset','approach_commit','approach_abort',
                           'touchdown','voluntary_takeoff','escape_takeoff')},
                'median_perch_seconds': statistics.median(self.perches) if self.perches else None,
                'median_flight_bout_seconds': statistics.median(self.flights) if self.flights else None,
                'complete_perches': len(self.perches), 'complete_flights': len(self.flights),
                'censored_bouts': list(self.censored)}
