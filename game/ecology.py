"""Phenomenological ecological strategy. Only local sense crosses this API.

State names are simulation abstractions, not anatomical neural modules. This
module cannot import or inspect World, source coordinates, Retina or the brain.
"""
from dataclasses import dataclass
from enum import Enum
import copy
import math
import numpy as np
from .ecological_sense import EcologicalSense


class ThreatState(Enum):
    CALM = 'CALM'
    ALERT = 'ALERT'
    ESCAPE = 'ESCAPE'


STATES = ('EXPLORE','TRANSIT','ODOR_SEARCH','ODOR_TRACK','LAND_OR_PERCH','ALERT','ESCAPE','RECOVER')


@dataclass(frozen=True, slots=True)
class EcologicalCommand:
    state: str
    target_speed_bl_s: float
    steering_rad_s: float
    spontaneous_clock_rate: float
    landing_attempt: bool = False

    def __post_init__(self):
        if self.state not in STATES: raise ValueError('unknown ecological state')
        if not all(math.isfinite(v) for v in (self.target_speed_bl_s,self.steering_rad_s,self.spontaneous_clock_rate)):
            raise ValueError('ecological command must be finite')
        if self.target_speed_bl_s < 0 or not 0 <= self.spontaneous_clock_rate <= 2:
            raise ValueError('invalid ecological flight command')
        if abs(self.steering_rad_s)>2: raise ValueError('ecological steering exceeds safety bound')


class EcologicalController:
    CONFIG_KEYS = {'enabled','_comment','odor_on','odor_off','encounter_dwell_seconds','loss_dwell_seconds',
        'search_seconds','odor_bout_seconds','relocation_seconds','recover_seconds','alert_recover_seconds','explore_duration_seconds',
        'transit_duration_seconds','speed_bl_s','speed_tau_seconds','steering_tau_seconds','steering_cap_rad_s',
        'upwind_gain','search_period_seconds','search_amplitude_radians','visual_gain_floor',
        'landing_affordance_threshold','landing_dwell_seconds','landing_attempt_seconds','landing_cooldown_seconds',
        'spontaneous_clock_rate','odor_history','intent_hazards','search_half_period_seconds',
        'odor_cues','wind_reliability'}
    # M1.8-B3b: encounter history replacing the odor timers (game/M1_8_B_COMPLETION_DESIGN.md).
    ODOR_HISTORY_KEYS = {'_comment','build_seconds','recovery_seconds','upwind_attenuation','abandon_seconds',
                         'refractory_seconds','search_min_seconds','search_give_up_seconds'}
    ODOR_HISTORY_SEED_OFFSET = 53113
    # M1.8-B3c: EXPLORE/TRANSIT dwell timers replaced by evidence-gated hazards.
    INTENT_KEYS = {'_comment','min_dwell_seconds','explore_hazard_seconds','transit_hazard_seconds',
                   'structure_reference','structure_gain'}
    INTENT_SEED_OFFSET = 59011
    # M1.8-B3d: the ODOR_SEARCH casting half-period is redrawn every half-cycle.
    CASTING_SEED_OFFSET = 64747
    # M1.8-B4a: ODOR_TRACK consumes the odor derivative and the bilateral difference.
    ODOR_CUE_KEYS = {'_comment','bilateral_gain','bilateral_scale','rate_gain','rate_scale'}
    # M1.8-B4b: reliability of the sensed wind and a still-air search strategy.
    WIND_KEYS = {'_comment','unreliable_below','reliable_above'}

    def __init__(self, config, seed, landing_enabled=True):
        if set(config)-self.CONFIG_KEYS: raise ValueError('only ecological controller parameters are allowed')
        self.landing_enabled = landing_enabled
        self.config = copy.deepcopy(config)
        if not 0 <= config['odor_off'] < config['odor_on']: raise ValueError('odor hysteresis must be ordered')
        if not 0 < config['steering_cap_rad_s'] <= 2: raise ValueError('invalid ecological steering cap')
        for state in STATES:
            low,high = config['speed_bl_s'][state]
            if not 0 < low <= high: raise ValueError('speed ranges must be positive and ordered')
        self.odor_history = config.get('odor_history')
        if self.odor_history is not None:
            h = self.odor_history
            if set(h) != self.ODOR_HISTORY_KEYS: raise ValueError('odor_history requires exactly its documented keys')
            for name in self.ODOR_HISTORY_KEYS - {'_comment','upwind_attenuation'}:
                if not math.isfinite(h[name]) or h[name] <= 0: raise ValueError('odor_history.'+name+' must be positive')
            if not 0 <= h['upwind_attenuation'] <= 1: raise ValueError('odor_history.upwind_attenuation must be in [0,1]')
        self.intent = config.get('intent_hazards')
        if self.intent is not None:
            i = self.intent
            if set(i) != self.INTENT_KEYS: raise ValueError('intent_hazards requires exactly its documented keys')
            for name in self.INTENT_KEYS - {'_comment','structure_gain'}:
                if not math.isfinite(i[name]) or i[name] <= 0: raise ValueError('intent_hazards.'+name+' must be positive')
            if not 0 <= i['structure_gain'] <= 1: raise ValueError('intent_hazards.structure_gain must be in [0,1]')
        self.casting = config.get('search_half_period_seconds')
        if self.casting is not None:
            s = self.casting
            if s.get('distribution') != 'triangular_symmetric':
                raise ValueError('search_half_period_seconds must be triangular_symmetric')
            low, mode, high = (float(s[k]) for k in ('min_seconds','mode_seconds','max_seconds'))
            if not 0 < low < high or abs((low+high)/2-mode) > 1e-9:
                raise ValueError('search half-period support must be positive, ordered and symmetric')
            self._casting_support = (low, mode, high)
        self.odor_cues = config.get('odor_cues')
        if self.odor_cues is not None:
            o = self.odor_cues
            if set(o) != self.ODOR_CUE_KEYS: raise ValueError('odor_cues requires exactly its documented keys')
            for name in ('bilateral_scale','rate_scale'):
                if not math.isfinite(o[name]) or o[name] <= 0: raise ValueError('odor_cues.'+name+' must be positive')
            if not 0 <= o['bilateral_gain'] <= config['steering_cap_rad_s']: raise ValueError('odor_cues.bilateral_gain must be within the steering cap')
            if not 0 <= o['rate_gain'] < 1: raise ValueError('odor_cues.rate_gain must be in [0,1)')
        self.wind_reliability = config.get('wind_reliability')
        if self.wind_reliability is not None:
            w = self.wind_reliability
            if set(w) != self.WIND_KEYS: raise ValueError('wind_reliability requires exactly its documented keys')
            if not 0 <= w['unreliable_below'] < w['reliable_above']:
                raise ValueError('wind_reliability thresholds must be ordered and nonnegative')
        self.reset(seed)

    def reset(self, seed):
        self.rng = np.random.default_rng(seed+7013)
        self.phase = float(self.rng.uniform(0,2*math.pi))
        self.tie_side = 1.0 if self.rng.random()<.5 else -1.0
        self.state = 'EXPLORE';self.elapsed=self.time=0.0
        self.on_time=self.off_time=self.surface_time=0.0
        self.has_odor=False;self.ignore_odor=self.landing_cooldown=0.0
        self.transitions=0;self.landing_attempts=0
        self.recovery_duration=self.config['alert_recover_seconds']
        self.state_duration=float(self.rng.uniform(*self.config['explore_duration_seconds']))
        self.speed=sum(self.config['speed_bl_s']['EXPLORE'])/2
        # Encounter history H in [0,1] and its hazard stream; inert without odor_history.
        self.history=0.0
        self.history_rng=np.random.default_rng(seed+self.ODOR_HISTORY_SEED_OFFSET)
        # Local visual structure and the EXPLORE/TRANSIT hazard stream; inert without intent_hazards.
        self.structure=0.0
        self.intent_rng=np.random.default_rng(seed+self.INTENT_SEED_OFFSET)
        # Casting oscillator phase, its next half-cycle boundary and current half-period.
        self.cast_rng=np.random.default_rng(seed+self.CASTING_SEED_OFFSET)
        self.cast_phase=0.0;self.cast_boundary=math.pi;self.cast_half=None
        self.reliability=1.0
        self.steering=0.0;self.last_threat=ThreatState.CALM
        self.last_command=EcologicalCommand(self.state,self.speed,0.0,1.0)

    def _enter(self, state):
        if state==self.state:return False
        self.state=state;self.elapsed=0.0;self.transitions+=1
        if state in ('EXPLORE','TRANSIT'):
            self.state_duration=float(self.rng.uniform(*self.config[state.lower()+'_duration_seconds']))
        if state=='LAND_OR_PERCH':self.landing_attempts+=1
        return True

    def step(self, sense, threat, dt):
        if type(sense) is not EcologicalSense: raise TypeError('ecology accepts only exact EcologicalSense')
        if type(threat) is not ThreatState: raise TypeError('threat must be the separate ThreatState enum')
        if not math.isfinite(dt) or dt<=0:raise ValueError('dt must be finite and positive')
        c=self.config;self.time+=dt;self.elapsed+=dt
        self.ignore_odor=max(0.0,self.ignore_odor-dt)
        self.landing_cooldown=max(0.0,self.landing_cooldown-dt)
        self.on_time=self.on_time+dt if sense.odor>=c['odor_on'] else 0.0
        self.off_time=self.off_time+dt if sense.odor<=c['odor_off'] else 0.0
        if self.on_time>=c['encounter_dwell_seconds']:self.has_odor=True
        if self.off_time>=c['loss_dwell_seconds']:self.has_odor=False
        h=self.odor_history
        if h is not None:
            if self.has_odor:self.history+=(1-self.history)*(1-math.exp(-dt/h['build_seconds']))
            else:self.history-=self.history*(1-math.exp(-dt/h['recovery_seconds']))
        eligible=(self.landing_enabled and sense.landing_affordance>=c['landing_affordance_threshold'] and sense.surface_expansion>0 and self.has_odor)
        self.surface_time=self.surface_time+dt if eligible else 0.0
        attempt=False
        if threat is not ThreatState.CALM:
            if threat is ThreatState.ESCAPE:
                self.recovery_duration=c['recover_seconds']
            elif self.state not in ('ALERT','ESCAPE','RECOVER'):
                self.recovery_duration=c['alert_recover_seconds']
            self._enter(threat.value)
            self.surface_time=0.0
        elif self.state in ('ALERT','ESCAPE'):
            self._enter('RECOVER')
        elif self.state=='RECOVER' and self.elapsed<self.recovery_duration:
            pass
        elif self.state=='LAND_OR_PERCH':
            if self.elapsed>=c['landing_attempt_seconds'] or not self.has_odor:
                self.landing_cooldown=c['landing_cooldown_seconds']
                self.ignore_odor=c['relocation_seconds'];self._enter('TRANSIT')
        elif self.ignore_odor>0:
            self._enter('TRANSIT')
        elif self.has_odor:
            if self.surface_time>=c['landing_dwell_seconds'] and self.landing_cooldown<=0:
                attempt=self._enter('LAND_OR_PERCH')
            elif h is None and self.state=='ODOR_TRACK' and self.elapsed>=c['odor_bout_seconds']:
                self.ignore_odor=c['relocation_seconds'];self._enter('TRANSIT')
            elif h is not None and self.state=='ODOR_TRACK' and self._hazard(self.history/h['abandon_seconds'],dt):
                # Leaving the plume: only a short refractory, not a relocation timer.
                self.ignore_odor=h['refractory_seconds'];self._enter('TRANSIT')
            else:self._enter('ODOR_TRACK')
        elif self.state=='ODOR_TRACK':self._enter('ODOR_SEARCH')
        elif self.state=='ODOR_SEARCH':
            if h is None:
                if self.elapsed>=c['search_seconds']:self._enter('EXPLORE')
            elif self.elapsed>=h['search_min_seconds'] and self._hazard(1/h['search_give_up_seconds'],dt):
                self._enter('EXPLORE')
        elif self.state=='RECOVER':self._enter('EXPLORE')
        elif self.intent is None:
            if self.elapsed>=self.state_duration:
                self._enter('TRANSIT' if self.state=='EXPLORE' else 'EXPLORE')
        elif self.elapsed>=self.intent['min_dwell_seconds'] and self._intent_switch(sense,dt):
            # The accepted uniform dwell is still drawn on entry, so the ecology stream keeps
            # its call order; its value is not used under intent_hazards.
            self._enter('TRANSIT' if self.state=='EXPLORE' else 'EXPLORE')

        lo,hi=c['speed_bl_s'][self.state]
        target=lo+(hi-lo)*(.5+.5*math.sin(2*math.pi*self.time/8+self.phase))
        self.speed+=(target-self.speed)*(1-math.exp(-dt/c['speed_tau_seconds']))
        # The local body-axis flow cue supplies upwind bearing, not source bearing.
        # It stands for ideal local wind estimation, not a mechanoreceptor model.
        wind_speed=math.hypot(sense.wind_forward,sense.wind_lateral)
        upwind=math.atan2(-sense.wind_lateral,-sense.wind_forward) if wind_speed>1e-6 else 0.0
        steer=0.0
        visual_gain=c['visual_gain_floor']+(1-c['visual_gain_floor'])*sense.visual_contrast
        w=self.wind_reliability
        if w is not None:
            self.reliability=min(1.0,max(0.0,(wind_speed-w['unreliable_below'])/(w['reliable_above']-w['unreliable_below'])))
        still_air=w is not None and self.reliability<0.5
        if self.state in ('ODOR_TRACK','ODOR_SEARCH') and (wind_speed>1e-6 or w is not None):
            error=upwind
            if still_air and self.state=='ODOR_SEARCH':
                # E19: without reliable wind, cast around the current course, not around upwind.
                error=0.0
            if self.state=='ODOR_SEARCH' and self.casting is not None:
                error+=c['search_amplitude_radians']*math.sin(self._cast_phase(dt)+self.phase)
                error=(error+math.pi)%(2*math.pi)-math.pi
            elif self.state=='ODOR_SEARCH':
                error+=c['search_amplitude_radians']*math.sin(2*math.pi*self.elapsed/c['search_period_seconds']+self.phase)
                error=(error+math.pi)%(2*math.pi)-math.pi
            # atan2 has a sign ambiguity exactly downwind; retain a seeded side.
            if abs(abs(error)-math.pi)<1e-8:error=self.tie_side*math.pi
            steer=c['upwind_gain']*error*visual_gain
            if w is not None and not (still_air and self.state=='ODOR_SEARCH'):
                steer*=self.reliability
            if h is not None and self.state=='ODOR_TRACK':
                # E17: later encounters elicit weaker upwind responses.
                steer*=1-h['upwind_attenuation']*self.history
            if self.odor_cues is not None and self.state=='ODOR_TRACK':
                # E16: a stronger upwind response while the concentration rises, weaker while it falls.
                o=self.odor_cues
                steer*=1+o['rate_gain']*math.tanh(sense.odor_rate/max(sense.odor,c['odor_on'])/o['rate_scale'])
        if self.odor_cues is not None and self.state=='ODOR_TRACK':
            # E18: turn toward the antenna sensing the stronger concentration (positive is right).
            o=self.odor_cues
            steer+=o['bilateral_gain']*math.tanh(sense.odor_bilateral/max(sense.odor,c['odor_on'])/o['bilateral_scale'])
        obstacle_turn=2*(sense.visual_left-sense.visual_right)
        if abs(obstacle_turn)<.01 and sense.visual_front>.08:
            obstacle_turn=self.tie_side*sense.visual_front*2
        steer+=obstacle_turn
        cap=c['steering_cap_rad_s'];steer=max(-cap,min(cap,steer))
        self.steering+=(steer-self.steering)*(1-math.exp(-dt/c['steering_tau_seconds']))
        if threat is not ThreatState.CALM:self.steering=0.0
        self.last_threat=threat
        self.last_command=EcologicalCommand(self.state,self.speed,self.steering,c['spontaneous_clock_rate'][self.state],attempt)
        return self.last_command

    def _intent_switch(self, sense, dt):
        """EXPLORE -> TRANSIT slows and TRANSIT -> EXPLORE quickens with local visual structure."""
        i = self.intent
        self.structure = min(1.0,(sense.visual_left+sense.visual_right+sense.landing_affordance)/i['structure_reference'])
        if self.state=='EXPLORE':rate=(1-i['structure_gain']*self.structure)/i['explore_hazard_seconds']
        else:rate=(1+i['structure_gain']*self.structure)/i['transit_hazard_seconds']
        return float(self.intent_rng.random()) < 1-math.exp(-rate*dt)

    def _cast_phase(self, dt):
        """A phase oscillator whose half-period is redrawn at every half-cycle boundary.

        The phase restarts at zero on the tick ODOR_SEARCH is entered, as the accepted sine
        did through `elapsed`.
        """
        if self.elapsed == 0.0 or self.cast_half is None:
            self.cast_phase, self.cast_boundary = 0.0, math.pi
            self.cast_half = float(self.cast_rng.triangular(*self._casting_support))
            return self.cast_phase
        self.cast_phase += math.pi*dt/self.cast_half
        while self.cast_phase >= self.cast_boundary:
            self.cast_boundary += math.pi
            self.cast_half = float(self.cast_rng.triangular(*self._casting_support))
        return self.cast_phase

    def _hazard(self, rate, dt):
        """One seeded Bernoulli draw for a constant-rate event over this tick."""
        return float(self.history_rng.random()) < 1-math.exp(-rate*dt)

    def diagnostics(self):
        extra = {} if self.odor_history is None else {'odor_history':self.history}
        if self.intent is not None:extra['visual_structure']=self.structure
        if self.casting is not None:extra['cast_half_period_seconds']=self.cast_half
        if self.wind_reliability is not None:extra['wind_reliability']=self.reliability
        return {**self._diagnostics(), **extra}

    def _diagnostics(self):
        return {'state':self.state,'state_seconds':self.elapsed,'target_speed_bl_s':self.speed,
                'steering_rad_s':self.steering,'odor_detected':self.has_odor,'transitions':self.transitions,
                'landing_attempts':self.landing_attempts,'neural_threat_state':self.last_threat.value,
                'landing_mechanics':'legacy_approach_only' if self.landing_enabled else 'external_local_lifecycle'}
