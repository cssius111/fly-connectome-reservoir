"""Deterministic ROOM environment, sensory-boundary and integration regressions."""
import copy
from dataclasses import asdict, fields, FrozenInstanceError
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
import numpy as np
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
from game.action import Action, MotorState, MotionState
from game.ecological_sense import EcologicalSense
from game.ecology import EcologicalController, EcologicalCommand, ThreatState, STATES
from game.room import RoomEnvironment, EcologicalProjector
from game.world import World, Fly
from game.session import Session, load_config, calibration_provenance, resolve_escape_threshold
from game.recording import InteractionRecorder, policy_observation
from test_game import shared_brain, CONFIG
ROOM=load_config(Path(__file__).parent/'game_room_config.json')
GAME=load_config(Path(__file__).parent/'game_play_config.json')
DT=.02


def environment(seed=101,config=None):
    return RoomEnvironment((config or ROOM)['room'],seed)


def controller(seed=101):
    return EcologicalController(ROOM['ecology'],seed)


def run_cue(c,cue,seconds,threat=ThreatState.CALM):
    commands=[]
    for _ in range(round(seconds/DT)):commands.append(c.step(cue,threat,DT))
    return commands


class TestRoomFields(unittest.TestCase):
    def test_field_seed_reproduces_and_varies(self):
        points=[(1500+i*50,1100+i*8,i*.3) for i in range(12)]
        a,b,d=environment(),environment(),environment(102)
        av=[a.concentration(*p) for p in points]
        self.assertEqual(av,[b.concentration(*p) for p in points])
        self.assertNotEqual(av,[d.concentration(*p) for p in points])

    def test_concentration_is_spatially_and_temporally_continuous(self):
        r=environment()
        for x,y in [(1050,1120),(1050,1300),(1700,1200),(3000,1400)]:
            a=r.concentration(x,y,2)
            for dx,dy,dt in [(1e-4,0,0),(0,1e-4,0),(0,0,1e-4)]:
                self.assertLess(abs(a-r.concentration(x+dx,y+dy,2+dt)),1e-3)
            self.assertGreaterEqual(a,0)

    def test_wind_rotates_the_plume_not_a_radial_food_gradient(self):
        c=copy.deepcopy(ROOM);c['room']['wind']['direction_amplitude_degrees']=0
        a=environment(config=c)
        c['room']['wind']['direction_degrees']=180
        b=environment(config=c)
        self.assertGreater(a.concentration(1550,1120,0),a.concentration(550,1120,0)*100)
        self.assertGreater(b.concentration(550,1120,0),b.concentration(1550,1120,0)*100)
        self.assertLess(a.concentration(1050,1620,0),a.concentration(1550,1120,0))

    def test_emission_modulation_advects_downwind(self):
        c=copy.deepcopy(ROOM);w=c['room']['wind'];w.update(direction_amplitude_degrees=0,speed_fraction=0)
        c['room']['food']['meander_amplitude']=0
        r=environment(config=c);f=r.food
        def age(x):return f['upwind_softness']*float(np.logaddexp(0,(x-f['x'])/f['upwind_softness']))/w['speed']
        x1,x2=1450,1750;delta=age(x2)-age(x1)
        ratios=[r.concentration(x1,1120,t)/r.concentration(x2,1120,t+delta) for t in [0,1,2,3]]
        np.testing.assert_allclose(ratios,ratios[0],rtol=1e-12)

    def test_wind_is_seeded_and_smooth(self):
        a,b=environment(),environment()
        for t in np.arange(0,60,.1):
            self.assertEqual(a.wind(t),b.wind(t))
            self.assertLess(math.dist(a.wind(t),a.wind(t+DT)),.2)

    def test_wind_cue_rotates_into_body_axes(self):
        room=environment();p=EcologicalProjector(ROOM['room']['sensing'])
        f=Fly(1800,1100,heading=0);a=p.project(room,f,3,DT)
        f.heading=math.pi/2;b=p.project(room,f,3,DT)
        self.assertAlmostEqual(b.wind_forward,a.wind_lateral)
        self.assertAlmostEqual(b.wind_lateral,-a.wind_forward)

    def test_wind_has_no_body_force(self):
        a=World(ROOM,101);c=copy.deepcopy(ROOM);c['room']['wind']['speed']=200
        b=World(c,101)
        for _ in range(200):
            a.tick(DT);b.tick(DT)
            np.testing.assert_array_equal(a.state_vector(),b.state_vector())

    def test_projector_reset_clears_odor_derivative(self):
        p=EcologicalProjector(ROOM['room']['sensing']);r=environment();f=Fly(1500,1120)
        p.project(r,f,0,DT);f.y+=500;p.project(r,f,DT,DT)
        p.reset();v=p.project(r,f,DT,DT)
        self.assertEqual(v.odor_rate,0)
        self.assertEqual(v.surface_expansion,0)

    def test_objects_produce_local_visual_cues(self):
        p=EcologicalProjector(ROOM['room']['sensing']);r=environment()
        a=p.project(r,Fly(2230,780,heading=0),0,DT)
        b=p.project(r,Fly(2230,780,heading=math.pi),0,DT)
        self.assertGreater(a.visual_front,b.visual_front)
        self.assertFalse(hasattr(a,'object_x'))

    def test_spawn_excludes_solid_obstacles(self):
        for seed in range(100):
            w=World(ROOM,seed)
            self.assertTrue(w.room.valid_spawn(w.fly.x,w.fly.y,w.fly_radius))


class TestEcologicalBoundary(unittest.TestCase):
    def test_frozen_schema_has_no_coordinates_or_ids(self):
        expected={'odor','odor_rate','odor_bilateral','wind_forward','wind_lateral','visual_left','visual_right',
                  'visual_front','visual_contrast','landing_affordance','surface_expansion'}
        self.assertEqual({f.name for f in fields(EcologicalSense)},expected)
        v=EcologicalSense()
        with self.assertRaises((FrozenInstanceError,AttributeError,TypeError)):v.food_x=1
        with self.assertRaises(TypeError):EcologicalSense(food_x=1)
        with self.assertRaises(ValueError):EcologicalSense(odor=float('nan'))

    def test_subclasses_and_world_objects_rejected(self):
        class Hidden(EcologicalSense):pass
        c=controller()
        for bad in [Hidden(),World(ROOM,1),{'odor':1,'food_x':1050}]:
            with self.assertRaises(TypeError):c.step(bad,ThreatState.CALM,DT)
        with self.assertRaises(TypeError):c.step(EcologicalSense(),'ESCAPE',DT)

    def test_controller_config_cannot_carry_world_coordinates(self):
        cfg=copy.deepcopy(ROOM['ecology']);cfg['food_x']=1050
        with self.assertRaises(ValueError):EcologicalController(cfg,1)
        self.assertFalse(hasattr(controller(),'world'))
        self.assertFalse(hasattr(controller(),'room'))

    def test_identical_local_history_produces_identical_behavior(self):
        a,b=controller(),controller()
        for i in range(500):
            cue=EcologicalSense(odor=.3 if i<150 else 0,wind_forward=30,wind_lateral=20,visual_contrast=.6)
            self.assertEqual(a.step(cue,ThreatState.CALM,DT),b.step(cue,ThreatState.CALM,DT))

    def test_future_policy_observation_remains_unchanged(self):
        m=MotorState(0,0,0,0,np.zeros(2),MotionState())
        obs=policy_observation(m,'CALM')
        self.assertEqual(set(obs),{'neural','motion','behavior_state','history'})
        self.assertNotIn('odor',json.dumps(obs))
        with self.assertRaises(ValueError):policy_observation(m,'CALM',[{'food_x':1}])


class TestEcologicalBehavior(unittest.TestCase):
    def test_odor_encounter_changes_state_and_target_speed(self):
        a,b=controller(),controller()
        commands=run_cue(a,EcologicalSense(odor=1,wind_forward=-45,visual_contrast=1),2)
        run_cue(b,EcologicalSense(),2)
        self.assertEqual(a.state,'ODOR_TRACK')
        self.assertGreater(commands[-1].target_speed_bl_s,b.speed)
        self.assertEqual(a.last_threat,ThreatState.CALM)

    def test_loss_enters_bounded_search_then_exploration(self):
        c=controller();run_cue(c,EcologicalSense(odor=1),1)
        run_cue(c,EcologicalSense(),.6)
        self.assertEqual(c.state,'ODOR_SEARCH')
        run_cue(c,EcologicalSense(),6.1)
        self.assertEqual(c.state,'EXPLORE')

    def test_hysteresis_rejects_single_tick_encounter(self):
        c=controller();c.step(EcologicalSense(odor=1),ThreatState.CALM,DT)
        self.assertEqual(c.state,'EXPLORE')

    def test_threat_overrides_and_recovery_follows(self):
        c=controller();cue=EcologicalSense(odor=1,wind_lateral=45,visual_contrast=1)
        run_cue(c,cue,1)
        out=c.step(cue,ThreatState.ESCAPE,DT)
        self.assertEqual(out.state,'ESCAPE');self.assertEqual(out.steering_rad_s,0)
        self.assertFalse(out.landing_attempt)
        out=c.step(cue,ThreatState.CALM,DT)
        self.assertEqual(out.state,'RECOVER')
        run_cue(c,cue,1.3);self.assertEqual(c.state,'ODOR_TRACK')

    def test_brief_alert_has_short_recovery_but_escape_retains_long_recovery(self):
        cue=EcologicalSense(odor=1)
        c=controller();run_cue(c,cue,.4,ThreatState.ALERT)
        run_cue(c,cue,.3);self.assertEqual(c.state,'ODOR_TRACK')
        c.step(cue,ThreatState.ESCAPE,DT)
        c.step(cue,ThreatState.ALERT,DT)
        run_cue(c,cue,.3);self.assertEqual(c.state,'RECOVER')
        run_cue(c,cue,1.0);self.assertEqual(c.state,'ODOR_TRACK')

    def test_ecology_cannot_fabricate_neural_escape(self):
        c=controller();seen=set()
        for i in range(2500):
            out=c.step(EcologicalSense(odor=1 if i%600<400 else 0,wind_lateral=45,visual_front=.6),ThreatState.CALM,DT)
            seen.add(out.state)
            self.assertFalse(hasattr(out,'escape'))
        self.assertFalse({'ALERT','ESCAPE'} & seen)
        self.assertGreater(len(seen),2)

    def test_upwind_response_changes_sign_with_local_wind(self):
        a,b=controller(),controller()
        run_cue(a,EcologicalSense(odor=1,wind_lateral=45,visual_contrast=1),1)
        run_cue(b,EcologicalSense(odor=1,wind_lateral=-45,visual_contrast=1),1)
        self.assertLess(a.steering,0);self.assertGreater(b.steering,0)

    def test_visual_feedback_modulates_upwind_gain(self):
        a,b=controller(),controller()
        run_cue(a,EcologicalSense(odor=1,wind_forward=-45,wind_lateral=10,visual_contrast=1),1)
        run_cue(b,EcologicalSense(odor=1,wind_forward=-45,wind_lateral=10,visual_contrast=0),1)
        self.assertGreater(abs(a.steering),abs(b.steering))

    def test_long_odor_bout_relocates_instead_of_locking_to_source(self):
        c=controller();run_cue(c,EcologicalSense(odor=1),8.5)
        self.assertEqual(c.state,'TRANSIT');self.assertGreater(c.ignore_odor,0)

    def test_landing_is_attempt_only_with_dwell_and_cooldown(self):
        c=controller();cue=EcologicalSense(odor=1,landing_affordance=.8,surface_expansion=.3)
        commands=run_cue(c,cue,.5)
        self.assertEqual(c.state,'LAND_OR_PERCH')
        self.assertEqual(sum(v.landing_attempt for v in commands),1)
        run_cue(c,cue,1)
        self.assertEqual(c.state,'TRANSIT');self.assertGreater(c.landing_cooldown,0)
        self.assertNotIn('position',asdict(c.last_command))

    def test_ordinary_states_alternate_without_player(self):
        c=controller();states={x.state for x in run_cue(c,EcologicalSense(),20)}
        self.assertEqual(states,{'EXPLORE','TRANSIT'})

    def test_steering_is_bounded_and_smooth(self):
        c=controller();commands=run_cue(c,EcologicalSense(odor=1,wind_lateral=45,visual_contrast=1),5)
        values=[x.steering_rad_s for x in commands]
        self.assertLessEqual(max(map(abs,values)),ROOM['ecology']['steering_cap_rad_s'])
        self.assertLess(max(abs(b-a) for a,b in zip(values,values[1:])),.1)


class TestRoomIntegration(unittest.TestCase):
    def test_lab_has_no_ecological_layer_even_if_requested(self):
        s=Session(CONFIG,brain=shared_brain(),ecology_enabled=True)
        self.assertIsNone(s.ecology);self.assertIsNone(s.world.room)
        s.tick();self.assertIsNone(s.last_ecological_sense)

    def test_room_layer_can_be_disabled_without_config_hash_change(self):
        s=Session(ROOM,brain=shared_brain(),ecology_enabled=False)
        before=calibration_provenance(ROOM)
        s.tick();self.assertIsNone(s.ecology);self.assertIsNone(s.world.ecological_command)
        self.assertEqual(before,calibration_provenance(ROOM))

    def test_calibration_freezes_ecology_and_motion(self):
        s=Session(ROOM,brain=shared_brain());s.world.fly_motion_enabled=False;s.world.collisions_enabled=False;s.reset(101)
        before=(s.world.fly.x,s.world.fly.y,s.world.fly.heading)
        for _ in range(50):s.tick(pointer=(100,100))
        self.assertEqual(before,(s.world.fly.x,s.world.fly.y,s.world.fly.heading))
        self.assertEqual((s.world.fly.vx,s.world.fly.vy,s.ecology.time),(0,0,0))
        self.assertIsNone(s.last_ecological_sense)

    def test_all_presets_have_matching_calibration(self):
        for c in (CONFIG,GAME,ROOM):self.assertGreater(resolve_escape_threshold(c).threshold,0)
        bad=copy.deepcopy(ROOM);bad['room']['food']['emission_strength']+=1
        with self.assertRaisesRegex(ValueError,'No matching'):resolve_escape_threshold(bad)

    def test_neural_action_overrides_ecological_steering_and_drive(self):
        a,b=World(ROOM,101),World(ROOM,101)
        a.ecological_command=EcologicalCommand('ODOR_TRACK',2,-.9,0)
        action=Action(escape=True,forward=1,turn=.5,saccade=.8)
        for _ in range(5):
            a.tick(DT,action);b.tick(DT,action)
            np.testing.assert_array_equal(a.state_vector(),b.state_vector())
        self.assertEqual(a.saccades.kind,'ESCAPE')

    def test_collision_is_swept_and_cannot_teleport(self):
        w=World(ROOM,101);o=w.room.objects[0]
        w.fly.x=o['x']-o['radius']-w.fly_radius-5;w.fly.y=o['y'];w.fly.vx=1000;w.fly.vy=0;w.fly.heading=0
        before=(w.fly.x,w.fly.y);w.tick(DT)
        self.assertTrue(w.object_contact)
        self.assertLessEqual(math.dist(before,(w.fly.x,w.fly.y)),1000*DT)
        self.assertGreaterEqual(math.hypot(w.fly.x-o['x'],w.fly.y-o['y']),o['radius']+w.fly_radius-1e-6)

    def test_ecological_flight_is_seeded_bounded_and_not_teleporting(self):
        def trajectory():
            w=World(ROOM,101);c=controller();p=EcologicalProjector(ROOM['room']['sensing']);rows=[]
            for _ in range(2000):
                sense=p.project(w.room,w.fly,w.time_seconds,DT)
                w.ecological_command=c.step(sense,ThreatState.CALM,DT)
                before=(w.fly.x,w.fly.y);w.tick(DT)
                self.assertLessEqual(math.dist(before,(w.fly.x,w.fly.y)),w.max_speed*DT+1e-6)
                self.assertLessEqual(abs(w.yaw_rate),w.max_yaw_rate)
                slip=(math.atan2(w.fly.vy,w.fly.vx)-w.fly.heading+math.pi)%(2*math.pi)-math.pi
                self.assertLessEqual(abs(slip),math.radians(80)+1e-8)
                rows.append(w.state_vector())
            self.assertEqual(w.stats.escapes,0)
            return rows
        np.testing.assert_array_equal(trajectory(),trajectory())

    def test_recording_does_not_alter_neural_or_physical_state(self):
        def simulate(rec):
            s=Session(ROOM,brain=shared_brain(),seed=101,recorder=rec);rows=[]
            for _ in range(100):s.tick(pointer=(100,100));rows.append(s.state_vector())
            s.close();return rows
        reference=simulate(None)
        with tempfile.TemporaryDirectory() as d:
            rec=InteractionRecorder(Path(d));actual=simulate(rec)
            np.testing.assert_array_equal(reference,actual)
            debug=[json.loads(x) for x in (rec.path/'world_debug.jsonl').read_text().splitlines()]
            self.assertIsNotNone(debug[-1]['room_analysis']['sense'])
            self.assertIn('food',debug[-1]['room_analysis']['world'])
            samples=[json.loads(x) for x in (rec.path/'policy_samples.jsonl').read_text().splitlines()]
            for row in samples:
                obs=row['observation'];self.assertEqual(set(obs),{'neural','motion','behavior_state','history'})
                for denied in ('food','wind','room','odor','pointer','ecological'):
                    self.assertNotIn(denied,json.dumps(obs))
            meta=json.loads((rec.path/'manifest.json').read_text());self.assertTrue(meta['ecology_enabled'])

    def test_same_retina_keeps_neural_path_identical_with_or_without_ecology(self):
        from game.perception import Retina
        def collect(enabled):
            s=Session(ROOM,brain=shared_brain(),seed=101,ecology_enabled=enabled);rows=[]
            # Identical legitimate retina and motion: only world trajectories may differ in closed loop.
            for i in range(100):
                a=s.fly_loop.step(Retina(.2,.4,.3),MotionState())
                m=s.fly_loop.last_motor;rows.append((asdict(a),m.dnp01_left,m.dnp01_right))
            return rows
        self.assertEqual(collect(True),collect(False))


if __name__=='__main__':unittest.main()
