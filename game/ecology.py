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
        'spontaneous_clock_rate'}

    def __init__(self, config, seed):
        if set(config)-self.CONFIG_KEYS: raise ValueError('only ecological controller parameters are allowed')
        self.config = copy.deepcopy(config)
        if not 0 <= config['odor_off'] < config['odor_on']: raise ValueError('odor hysteresis must be ordered')
        if not 0 < config['steering_cap_rad_s'] <= 2: raise ValueError('invalid ecological steering cap')
        for state in STATES:
            low,high = config['speed_bl_s'][state]
            if not 0 < low <= high: raise ValueError('speed ranges must be positive and ordered')
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
        eligible=(sense.landing_affordance>=c['landing_affordance_threshold'] and sense.surface_expansion>0 and self.has_odor)
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
            elif self.state=='ODOR_TRACK' and self.elapsed>=c['odor_bout_seconds']:
                self.ignore_odor=c['relocation_seconds'];self._enter('TRANSIT')
            else:self._enter('ODOR_TRACK')
        elif self.state=='ODOR_TRACK':self._enter('ODOR_SEARCH')
        elif self.state=='ODOR_SEARCH':
            if self.elapsed>=c['search_seconds']:self._enter('EXPLORE')
        elif self.state=='RECOVER':self._enter('EXPLORE')
        elif self.elapsed>=self.state_duration:
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
        if self.state in ('ODOR_TRACK','ODOR_SEARCH') and wind_speed>1e-6:
            error=upwind
            if self.state=='ODOR_SEARCH':
                error+=c['search_amplitude_radians']*math.sin(2*math.pi*self.elapsed/c['search_period_seconds']+self.phase)
                error=(error+math.pi)%(2*math.pi)-math.pi
            # atan2 has a sign ambiguity exactly downwind; retain a seeded side.
            if abs(abs(error)-math.pi)<1e-8:error=self.tie_side*math.pi
            steer=c['upwind_gain']*error*visual_gain
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

    def diagnostics(self):
        return {'state':self.state,'state_seconds':self.elapsed,'target_speed_bl_s':self.speed,
                'steering_rad_s':self.steering,'odor_detected':self.has_odor,'transitions':self.transitions,
                'landing_attempts':self.landing_attempts,'neural_threat_state':self.last_threat.value,
                'landing_mechanics':'approach_only; perching deferred'}
