"""Bounded world-side paddle dynamics and continuous relative swept contact.

These are game interaction parameters, not measured human biomechanics.
No state from this module is supplied directly to a neural policy.
"""
import math
import numpy as np

PHASES = ('commit','fast_swing','active_contact','follow_through','recovery')


def smoothstep(x):
    x=max(0.0,min(1.0,x));return x*x*(3-2*x)


def swept_disk_hit(head0, head1, fly0, fly1, radius):
    """Minimum separation of two linearly moving disks over the same interval."""
    rx,ry=head0[0]-fly0[0],head0[1]-fly0[1]
    dx,dy=(head1[0]-head0[0])-(fly1[0]-fly0[0]),(head1[1]-head0[1])-(fly1[1]-fly0[1])
    length=dx*dx+dy*dy
    u=0.0 if length<=1e-24 else max(0.0,min(1.0,-(rx*dx+ry*dy)/length))
    return (rx+u*dx)**2+(ry+u*dy)**2<=radius*radius


class PhysicalSwatter:
    def __init__(self, config, width, height, padding):
        self.config=config;self.width=width;self.height=height;self.padding=padding
        for key in ('speed_limit','acceleration_limit','approach_speed_limit','velocity_tau_seconds','integration_step_seconds'):
            if not math.isfinite(config[key]) or config[key]<=0:raise ValueError('invalid physical swatter '+key)
        if any(config['phases_seconds'][name]<=0 for name in PHASES):raise ValueError('strike durations must be positive')
        self.segments=[]
        self.reset()

    def reset(self):
        self.previous_target = None
        self.previous_pointer_velocity = None
        self.pointer_velocity = (0.0, 0.0)
        self.pointer_acceleration = None
        self.pointer_sample_valid = False
        self.approach_command = (0.0, 0.0)
        self.target_error = 0.0

    @staticmethod
    def _limit_vector(x, y, cap):
        length = math.hypot(x, y)
        scale = min(1.0, cap/length) if length else 1.0
        return x*scale, y*scale

    def _observe_pointer(self, sw, dt):
        target = (sw.target_x, sw.target_y)
        self.target_error = math.dist(target, (sw.x, sw.y))
        self.pointer_sample_valid = self.previous_target is not None
        if self.pointer_sample_valid:
            velocity = tuple((target[i]-self.previous_target[i])/dt for i in (0,1))
            self.pointer_acceleration = (math.dist(velocity, self.previous_pointer_velocity)/dt
                                         if self.previous_pointer_velocity is not None else None)
            self.pointer_velocity = velocity
            self.previous_pointer_velocity = velocity
        else:
            # Initial placement is not an observed movement or a hand burst.
            self.pointer_velocity = (0.0, 0.0)
            self.pointer_acceleration = None
        self.previous_target = target

    def _update_approach_command(self, sw, h):
        tracking = self.config.get('approach_tracking')
        if tracking is None:
            return
        tx = max(self.padding, min(self.width-self.padding, sw.target_x))
        ty = max(self.padding, min(self.height-self.padding, sw.target_y))
        cx,cy = self._limit_vector((tx-sw.x)*tracking['position_gain'],
                                  (ty-sw.y)*tracking['position_gain'],
                                  tracking['correction_speed_limit'])
        vx,vy = self._limit_vector(*self.pointer_velocity, self.config['approach_speed_limit'])
        desired = self._limit_vector(vx+cx, vy+cy, self.config['approach_speed_limit'])
        alpha = -math.expm1(-h/tracking['command_tau_seconds'])
        self.approach_command = tuple(old+alpha*(new-old) for old,new in zip(self.approach_command,desired))

    def diagnostics(self):
        return {'pointer_sample_valid':self.pointer_sample_valid,
                'pointer_vx':self.pointer_velocity[0], 'pointer_vy':self.pointer_velocity[1],
                'pointer_speed':math.hypot(*self.pointer_velocity),
                'pointer_acceleration':self.pointer_acceleration,
                'target_error_before_step':self.target_error,
                'approach_command_vx':self.approach_command[0],
                'approach_command_vy':self.approach_command[1]}

    def commit(self, sw, history):
        samples=np.asarray(history,dtype=float)
        vx=vy=trend=0.0
        def slope(a):
            if len(a)<2:return np.zeros(2)
            t=a[:,0]-a[:,0].mean();den=float(t@t)
            return t@a[:,1:]/den if den>1e-15 else np.zeros(2)
        if len(samples)>=2:
            vx,vy=slope(samples)
            if len(samples)>=4:
                mid=len(samples)//2
                first,last=slope(samples[:mid+1]),slope(samples[mid:])
                span=float(samples[mid:,0].mean()-samples[:mid+1,0].mean())
                trend=(np.linalg.norm(last)-np.linalg.norm(first))/max(span,1e-9)
        speed=min(math.hypot(vx,vy),self.config['approach_speed_limit'])
        if speed>=20:sw.attack_orientation=math.atan2(vy,vx)
        else:sw.attack_orientation=sw.orientation;speed=0.0
        sw.attack_speed=speed
        sw.attack_acceleration=max(-self.config['acceleration_limit'],min(self.config['acceleration_limit'],float(trend)))
        sw.swing_speed=min(self.config['speed_limit'],self.config['base_swing_speed']+
            self.config['approach_speed_gain']*speed+self.config['acceleration_trend_gain_seconds']*max(0,sw.attack_acceleration))
        sw.phase=type(sw.phase)('commit');sw.phase_elapsed=0.0

    def _desired_velocity(self, sw):
        c=self.config;phase=sw.phase.value
        tx=max(self.padding,min(self.width-self.padding,sw.target_x))
        ty=max(self.padding,min(self.height-self.padding,sw.target_y))
        vx,vy=(tx-sw.x)*c['position_gain'],(ty-sw.y)*c['position_gain']
        m=math.hypot(vx,vy)
        if m>c['approach_speed_limit']:vx*=c['approach_speed_limit']/m;vy*=c['approach_speed_limit']/m
        if c.get('approach_tracking') is not None:
            vx,vy=self.approach_command
        sx,sy=math.cos(sw.attack_orientation)*sw.swing_speed,math.sin(sw.attack_orientation)*sw.swing_speed
        if phase=='commit':return .7*sw.vx,.7*sw.vy
        if phase in ('fast_swing','active_contact'):return sx,sy
        if phase=='follow_through':
            fraction=1-.65*smoothstep(sw.phase_elapsed/c['phases_seconds'][phase])
            return sx*fraction,sy*fraction
        if phase=='recovery':
            blend=smoothstep(sw.phase_elapsed/c['phases_seconds'][phase])
            return (1-blend)*.35*sx+blend*vx,(1-blend)*.35*sy+blend*vy
        return vx,vy

    def _geometry(self, sw):
        if sw.phase.value=='approach':sw.height=self.config['heights'][0];sw.face=self.config['faces'][0];return
        i=PHASES.index(sw.phase.value)
        q=smoothstep(sw.phase_elapsed/self.config['phases_seconds'][sw.phase.value])
        sw.height=(1-q)*self.config['heights'][i]+q*self.config['heights'][i+1]
        sw.face=(1-q)*self.config['faces'][i]+q*self.config['faces'][i+1]

    def advance(self, sw, dt):
        """Substeps resolve geometry/contact windows; brain stays on its 20 ms tick."""
        self._observe_pointer(sw, dt)
        c=self.config;self.segments=[];remaining=dt;elapsed=0.0;resolved=False
        while remaining>1e-12:
            phase=sw.phase.value
            until=remaining if phase=='approach' else c['phases_seconds'][phase]-sw.phase_elapsed
            h=min(remaining,c['integration_step_seconds'],until)
            if h<=1e-12:
                i=PHASES.index(phase)
                if phase=='active_contact':resolved=True
                sw.phase=type(sw.phase)('approach' if i==len(PHASES)-1 else PHASES[i+1]);sw.phase_elapsed=0.0
                self._geometry(sw);continue
            start=(sw.x,sw.y);old_v=(sw.vx,sw.vy)
            self._update_approach_command(sw, h)
            target=self._desired_velocity(sw)
            # Bound the physical CENTER, not the rendered head extent. Partial
            # offscreen heads retain their complete collision geometry. The
            # 0.5-unit braking deadband changes no fly containment bounds.
            axis_cap=c['acceleration_limit']/math.sqrt(2)
            acceleration=[]
            for position,velocity,wanted,limit in [(sw.x,sw.vx,target[0],self.width),(sw.y,sw.vy,target[1],self.height)]:
                if position<=self.padding+.5:wanted=max(0.0,wanted)
                if position>=limit-self.padding-.5:wanted=min(0.0,wanted)
                acc=max(-axis_cap,min(axis_cap,(wanted-velocity)/c['velocity_tau_seconds']))
                distance=(limit-self.padding-position) if velocity>0 else (position-self.padding)
                stop=velocity*velocity/(2*axis_cap)+2*abs(velocity)*h+axis_cap*h*h
                if abs(velocity)>1e-8 and distance<=stop:
                    acc=-math.copysign(min(axis_cap,abs(velocity)/h),velocity)
                acceleration.append(acc)
            sw.vx+=acceleration[0]*h;sw.vy+=acceleration[1]*h
            speed=math.hypot(sw.vx,sw.vy)
            if speed>c['speed_limit']:sw.vx*=c['speed_limit']/speed;sw.vy*=c['speed_limit']/speed
            sw.ax=(sw.vx-old_v[0])/h;sw.ay=(sw.vy-old_v[1])/h
            sw.x+=sw.vx*h;sw.y+=sw.vy*h
            wanted_angle=sw.attack_orientation if phase!='approach' else (math.atan2(sw.vy,sw.vx) if speed>20 else sw.orientation)
            error=(wanted_angle-sw.orientation+math.pi)%(2*math.pi)-math.pi
            wanted_omega=max(-c['angular_speed_limit'],min(c['angular_speed_limit'],8*error))
            delta=max(-c['angular_acceleration_limit']*h,min(c['angular_acceleration_limit']*h,wanted_omega-sw.angular_velocity))
            sw.angular_velocity+=delta;sw.orientation+=sw.angular_velocity*h
            self.segments.append((elapsed/dt,(elapsed+h)/dt,start,(sw.x,sw.y),phase=='active_contact'))
            elapsed+=h;remaining-=h;sw.phase_elapsed+=h
            self._geometry(sw)
            if phase!='approach' and sw.phase_elapsed>=c['phases_seconds'][phase]-1e-12:
                i=PHASES.index(phase)
                if phase=='active_contact':resolved=True
                sw.phase=type(sw.phase)('approach' if i==len(PHASES)-1 else PHASES[i+1]);sw.phase_elapsed=0.0
                self._geometry(sw)
        return resolved

    def collision(self, fly0, fly1, radius):
        for a,b,start,end,active in self.segments:
            if not active:continue
            f0=tuple(fly0[i]+a*(fly1[i]-fly0[i]) for i in (0,1))
            f1=tuple(fly0[i]+b*(fly1[i]-fly0[i]) for i in (0,1))
            if swept_disk_hit(start,end,f0,f1,radius):return True
        return False
