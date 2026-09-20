"""WORLD-side analytic environment and local sensory projection; no CFD.

Coordinates remain here. The separate ecological controller imports only the
frozen EcologicalSense type, never RoomEnvironment, World or this projector.
"""
import copy
import math
import numpy as np
from .ecological_sense import EcologicalSense


class RoomEnvironment:
    def __init__(self, config, seed):
        self.config = copy.deepcopy(config)
        self.wind_config = self.config['wind']
        self.food = self.config['food']
        self.objects = self.config['objects']
        if self.wind_config['physical_force_enabled']:
            raise ValueError('physical wind forces are not implemented in M1.6')
        if self.wind_config['speed'] <= 0 or not 0 <= self.wind_config['speed_fraction'] < 1:
            raise ValueError('wind must retain positive transport speed')
        for name in ('base_width','decay_length','upwind_softness','meander_period_seconds','intermittency_period_seconds'):
            if self.food[name] <= 0: raise ValueError('invalid odor field scale: '+name)
        if self.food['emission_strength'] < 0 or not 0 <= self.food['intermittency_fraction'] < 1:
            raise ValueError('invalid odor emission')
        self.phases = np.random.default_rng(seed+6011).uniform(0,2*math.pi,4)

    def wind(self, t):
        w = self.wind_config
        angle = math.radians(w['direction_degrees'] + w['direction_amplitude_degrees'] *
                             math.sin(2*math.pi*t/w['direction_period_seconds']+self.phases[0]))
        speed = w['speed']*(1+w['speed_fraction']*math.sin(2*math.pi*t/w['speed_period_seconds']+self.phases[1]))
        return speed*math.cos(angle), speed*math.sin(angle)

    def concentration(self, x, y, t):
        f = self.food
        wx, wy = self.wind(t); speed = math.hypot(wx,wy)
        ux, uy = wx/speed, wy/speed
        dx, dy = x-f['x'], y-f['y']
        along, cross = dx*ux+dy*uy, -dx*uy+dy*ux
        soft = f['upwind_softness']
        downstream = soft*float(np.logaddexp(0.0,along/soft))
        age = downstream/speed
        delayed = t-age
        width = f['base_width'] + f['spread']*downstream
        meander = f['meander_amplitude']*(downstream/(downstream+f['base_width']))*math.sin(2*math.pi*delayed/f['meander_period_seconds']+self.phases[2])
        gate = 0.5*(1+math.tanh(along/soft))
        emission = 1+f['intermittency_fraction']*math.sin(2*math.pi*delayed/f['intermittency_period_seconds']+self.phases[3])
        return f['emission_strength']*gate*(f['base_width']/width)*math.exp(-downstream/f['decay_length']-0.5*((cross-meander)/width)**2)*emission

    def surfaces(self):
        return [dict(self.food, contrast=1.0, solid=False, name='fermentation source'), *self.objects]

    def valid_spawn(self, x, y, radius):
        return all(not o['solid'] or math.hypot(x-o['x'],y-o['y']) > radius+o['radius']+24
                   for o in self.objects)

    def constrain_motion(self, fly, previous, radius):
        """Swept disk contact stops at first impact, with no snap to a target.

        Returns contact; removes only inward velocity. Boundary contacts remain
        the existing Enclosure's responsibility. No stimulus is fabricated.
        """
        x0,y0 = previous; dx,dy = fly.x-x0,fly.y-y0
        first = 1.0; normal = None
        for o in self.objects:
            if not o['solid']: continue
            qx,qy = x0-o['x'],y0-o['y']; r = radius+o['radius']
            a = dx*dx+dy*dy; b = 2*(qx*dx+qy*dy); c = qx*qx+qy*qy-r*r
            if a <= 1e-18: continue
            disc = b*b-4*a*c
            if disc < 0: continue
            hit = (-b-math.sqrt(disc))/(2*a)
            if -1e-10 <= hit <= first:
                first = max(0.0,hit-1e-9)
                nx,ny = qx+first*dx,qy+first*dy
                mag = math.hypot(nx,ny)
                normal = (nx/mag,ny/mag) if mag else (1.0,0.0)
        if normal is None: return False
        fly.x,fly.y = x0+first*dx,y0+first*dy
        dot = fly.vx*normal[0]+fly.vy*normal[1]
        if dot < 0:
            fly.vx -= dot*normal[0];fly.vy -= dot*normal[1]
        return True

    def debug(self, fly, t):
        f = self.food
        return {'food':dict(f),'objects':self.objects,'wind_world':self.wind(t),
                'food_surface_overlap':math.hypot(fly.x-f['x'],fly.y-f['y']) <= f['radius']}


class EcologicalProjector:
    def __init__(self, config):
        self.config = config
        self.reset()

    def reset(self):
        self.last_odor = self.last_surface = None
        self.odor_rate = self.expansion = 0.0

    def project(self, room, fly, t, dt):
        c = self.config; ch,sh = math.cos(fly.heading),math.sin(fly.heading)
        odor = room.concentration(fly.x,fly.y,t)
        a = c['antenna_half_spacing']
        right = room.concentration(fly.x-sh*a,fly.y+ch*a,t)
        left = room.concentration(fly.x+sh*a,fly.y-ch*a,t)
        wx,wy = room.wind(t)
        vl=vr=vf=surface=contrast=0.0
        for o in room.surfaces():
            dx,dy = o['x']-fly.x,o['y']-fly.y
            distance = math.hypot(dx,dy)
            bearing = math.atan2(dy,dx)-fly.heading
            angular = 2*math.atan2(o['radius'],max(distance,1e-9))/math.pi
            visible = o['contrast']*math.exp(-distance/c['visual_range'])
            facing = max(0.0,math.cos(bearing))
            occupancy = angular*visible
            contrast = max(contrast,visible)
            if o['solid']:
                vl += occupancy*(1-math.sin(bearing))*.5
                vr += occupancy*(1+math.sin(bearing))*.5
                vf += occupancy*facing**4
            if o['landing_surface']:
                surface = max(surface,occupancy*facing**2)
        alpha = 1-math.exp(-dt/c['derivative_tau_seconds'])
        raw = 0.0 if self.last_odor is None else (odor-self.last_odor)/dt
        growth = 0.0 if self.last_surface is None else (surface-self.last_surface)/dt
        self.odor_rate += alpha*(raw-self.odor_rate)
        self.expansion += alpha*(growth-self.expansion)
        self.last_odor,self.last_surface = odor,surface
        cap = c['derivative_cap']
        return EcologicalSense(odor, max(-cap,min(cap,self.odor_rate)), right-left,
            wx*ch+wy*sh, -wx*sh+wy*ch, min(1,vl),min(1,vr),min(1,vf),
            min(1,max(c['background_contrast'],contrast)),min(1,surface),max(-cap,min(cap,self.expansion)))
