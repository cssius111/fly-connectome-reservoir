"""M1.5 environment, perception boundaries and recording regressions."""
import copy
from dataclasses import fields
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
import numpy as np
from game.action import Action, MotionState, MotorState
from game.modes import MODES
from game.perception import RetinaProjector
from game.recording import InteractionRecorder, policy_observation
from game.session import Session, load_config, resolve_escape_threshold
from game.world import World, StrikePhase
from test_game import CONFIG, shared_brain

GAME=load_config(Path(__file__).parent/'game_play_config.json')
DT=.02


def slip(w):
    return (math.atan2(w.fly.vy,w.fly.vx)-w.fly.heading+math.pi)%(2*math.pi)-math.pi


class TestSpawnAndArena(unittest.TestCase):
    def test_seed_reproduces_full_spawn_and_different_seeds_vary(self):
        self.assertEqual(World(GAME,101).spawn_state,World(GAME,101).spawn_state)
        self.assertNotEqual(World(GAME,101).spawn_state,World(GAME,102).spawn_state)

    def test_spawn_clearance_heading_and_quadrant_coverage(self):
        quadrants=set();headings=set()
        for seed in range(128):
            w=World(GAME,seed);f=w.fly
            clearance=w.margin+w.fly_radius+6*w.body_length
            self.assertTrue(clearance<=f.x<=w.width-clearance)
            self.assertTrue(clearance<=f.y<=w.height-clearance)
            self.assertGreater(math.hypot(f.x-w.swatter.x,f.y-w.swatter.y),w.paddle_radius+w.fly_radius+3*w.body_length)
            self.assertFalse(w.lethal)
            self.assertLessEqual(abs(slip(w)),math.radians(12)+1e-9)
            quadrants.add((f.x>w.width/2,f.y>w.height/2))
            headings.add(int((f.heading+math.pi)/(math.pi/4)))
        self.assertEqual(len(quadrants),4);self.assertEqual(len(headings),8)

    def test_lab_and_calibration_remain_controlled(self):
        a,b=World(CONFIG,101),World(CONFIG,102)
        self.assertEqual((a.fly.x,a.fly.y,a.fly.heading),(b.fly.x,b.fly.y,b.fly.heading))
        w=World(GAME,101);w.fly_motion_enabled=False;w.reset(102)
        self.assertEqual((w.fly.x,w.fly.y,w.fly.heading,w.fly.vx,w.fly.vy),(1920,1339.2,0,0,0))

    def test_game_dimensions_are_larger_and_body_relative(self):
        w=World(GAME,101)
        self.assertEqual((w.width/w.body_length,w.height/w.body_length),(160,90))
        self.assertEqual(2*w.paddle_radius/w.body_length,12)
        self.assertGreater(w.width*w.height,8*CONFIG['world']['width']*CONFIG['world']['height'])
        self.assertLess(w.body_length/w.width,.01)

    def test_render_scale_keeps_relative_geometry_and_pointer_mapping(self):
        import pygame
        from game.app import App
        self.addCleanup(pygame.quit)
        session=Session(GAME,brain=shared_brain())
        with patch('game.app.Session',return_value=session):app=App(GAME)
        for size in ((1280,720),(1920,1080),(1600,1000)):
            app.screen=pygame.Surface(size)
            scale,ox,oy=app._letterbox()
            self.assertAlmostEqual((24*scale)/(3840*scale),1/160)
            self.assertEqual(app._screen_to_world((ox+1920*scale,oy+1080*scale)),(1920,1080))
            app._draw()
        self.assertEqual(app.canvas.get_size(),(1280,720))

    def test_modes_never_enable_learning(self):
        self.assertTrue(MODES['training'].future_updates_allowed)
        self.assertTrue(all(not m.updates_enabled for m in MODES.values()))
        self.assertTrue(MODES['evaluation'].deterministic_default_seed)

    def test_both_calibration_records_match_their_presets(self):
        self.assertEqual(resolve_escape_threshold(CONFIG).threshold,1.45)
        self.assertGreater(resolve_escape_threshold(GAME).threshold,0)


class TestDirectionalSwatter(unittest.TestCase):
    def approach(self,angle,speed=600):
        w=World(GAME,101);w.fly_motion_enabled=False
        for t in range(20):
            w.set_pointer(1500+speed*t*DT*math.cos(angle),900+speed*t*DT*math.sin(angle))
            w.tick(DT)
        w.set_pointer(1500+speed*20*DT*math.cos(angle),900+speed*20*DT*math.sin(angle))
        return w

    def test_attack_follows_multiple_pointer_orientations(self):
        for angle in (0,math.pi/2,math.pi,-math.pi/2,math.pi/4,-math.pi/4):
            w=self.approach(angle);w.request_strike()
            delta=(w.swatter.orientation-angle+math.pi)%(2*math.pi)-math.pi
            self.assertAlmostEqual(delta,0,places=8)
            self.assertAlmostEqual(w.swatter.attack_speed,600,places=7)
            before=(w.swatter.x,w.swatter.y)
            for _ in range(8):w.tick(DT)
            displacement=np.array((w.swatter.x-before[0],w.swatter.y-before[1]))
            self.assertGreater(displacement@np.array((math.cos(angle),math.sin(angle))),1)

    def test_acceleration_changes_attack_speed_and_recent_stop_removes_sweep(self):
        slow=self.approach(0,100);fast=self.approach(0,1000)
        slow.request_strike();fast.request_strike()
        self.assertGreater(fast.swatter.attack_speed,slow.swatter.attack_speed)
        stopped=self.approach(0)
        for _ in range(20):stopped.tick(DT)
        stopped.request_strike();self.assertEqual(stopped.swatter.attack_speed,0)

    def test_committed_stroke_cannot_be_retargeted_by_click_followup(self):
        a=self.approach(0);b=self.approach(0)
        a.request_strike();b.request_strike()
        for _ in range(10):
            a.set_pointer(0,0);b.set_pointer(3840,2160)
            a.tick(DT);b.tick(DT)
            self.assertEqual((a.swatter.x,a.swatter.y),(b.swatter.x,b.swatter.y))

    def test_click_itself_does_not_change_retina_without_geometry(self):
        w=self.approach(math.pi/4)
        # Match visible orientation before and after a click to isolate phase.
        w._sample_pointer()
        vx,vy=w.pointer_velocity();w.swatter.orientation=math.atan2(vy,vx)
        a=RetinaProjector(DT).project(w)
        w.request_strike();b=RetinaProjector(DT).project(w)
        self.assertEqual(a,b)

    def test_hidden_world_fields_cannot_change_retina(self):
        w=self.approach(0);a=RetinaProjector(DT).project(w)
        w.swatter.attack_speed=12345;w.swatter.target_x=1;w.swatter.phase=StrikePhase.ACTIVE
        b=RetinaProjector(DT).project(w)
        self.assertEqual(a,b)

    def test_direction_changes_retinal_geometry_over_time(self):
        sequences=[]
        for angle in (0,math.pi/2,math.pi/4):
            w=self.approach(angle);w.fly.x,w.fly.y=1800,1000
            p=RetinaProjector(DT);w.request_strike()
            sequence=[]
            for _ in range(15):
                r=p.project(w);sequence.append((r.theta,r.theta_dot,r.azimuth));w.tick(DT)
            sequences.append(sequence)
        self.assertFalse(np.array_equal(sequences[0],sequences[1]))
        self.assertFalse(np.array_equal(sequences[0],sequences[2]))


class TestNaturalFlight(unittest.TestCase):
    def test_calibration_freezes_curvature_and_flight_clocks(self):
        w=World(GAME,101);w.fly_motion_enabled=False;w.reset(102)
        wait=w.flight.wait;phases=w._curve_phases.copy()
        for _ in range(100):w.tick(DT)
        self.assertEqual(w._flight_time,0)
        self.assertEqual(w.flight.wait,wait)
        np.testing.assert_array_equal(w._curve_phases,phases)

    def test_curvature_is_smooth_persistent_and_bounded(self):
        cfg=copy.deepcopy(GAME);cfg['saccades']['enabled']=False
        w=World(cfg,101);w.fly.x,w.fly.y=1920,1080
        values=[]
        for _ in range(250):w.tick(DT);values.append(w.yaw_rate)
        self.assertGreater(max(values)-min(values),.1)
        self.assertLessEqual(max(map(abs,values)),.22)
        self.assertLess(max(abs(a-b) for a,b in zip(values,values[1:])),.005)

    def test_major_course_changes_use_discrete_pulses(self):
        w=World(GAME,101);rapid=0
        for _ in range(2000):
            w.tick(DT)
            if abs(w.yaw_rate)>1:
                rapid+=1;self.assertNotEqual(w.saccades.last_delta,0)
        self.assertGreater(rapid,0)

    def test_sideslip_is_bounded_in_turns_and_escape(self):
        w=World(GAME,101);seen=0
        for t in range(1000):
            action=Action(escape=True,lateral=1,forward=.35,saccade=1) if t in (0,100,200) else Action()
            before=(w.fly.x,w.fly.y)
            w.tick(DT,action)
            self.assertLessEqual(math.dist(before,(w.fly.x,w.fly.y)),w.max_speed*DT+1e-8)
            self.assertLessEqual(abs(w.yaw_rate),w.max_yaw_rate)
            seen=max(seen,abs(slip(w)))
            self.assertLessEqual(abs(slip(w)),math.radians(80)+1e-8)
        self.assertGreater(seen,math.radians(20))

    def test_sideslip_realigns_smoothly_without_heading_assignment(self):
        cfg=copy.deepcopy(GAME);cfg['saccades']['enabled']=False
        cfg['fly']['curvature']['amplitudes_rad_s']=[0,0]
        w=World(cfg,101);w.fly.x,w.fly.y,w.fly.heading=1920,1080,0
        w.fly.vx,w.fly.vy=150,100
        old=abs(slip(w));values=[]
        for _ in range(60):
            w.tick(DT);values.append(abs(slip(w)))
            self.assertEqual(w.fly.heading,0)
        self.assertTrue(all(b<=a+1e-9 for a,b in zip([old]+values,values)))
        self.assertLess(values[-1],.002)

    def test_seeded_trajectory_replays(self):
        def run():
            w=World(GAME,123);rows=[]
            for _ in range(1000):w.tick(DT);rows.append(w.state_vector())
            return rows
        np.testing.assert_array_equal(run(),run())

    def test_game_walls_are_less_dominant_than_lab_for_predeclared_seeds(self):
        fractions=[]
        for cfg in (CONFIG,GAME):
            near=0
            for seed in (17,101,102,103,104):
                w=World(cfg,seed)
                for _ in range(6000):
                    w.tick(DT);near+=w.wall_cue.proximity>=.45
            fractions.append(near/30000)
        self.assertLess(fractions[1],fractions[0])
        self.assertLess(fractions[1],.3)


class TestInteractionRecording(unittest.TestCase):
    def test_observation_whitelist_rejects_world_and_untrusted_history(self):
        motor=MotorState(1,2,3,4,np.zeros(10),MotionState(1,2,.3,.1))
        obs=policy_observation(motor,'CALM')
        self.assertEqual(set(obs),{'neural','motion','behavior_state','history'})
        self.assertEqual(set(obs['neural']),{'dnp01_left','dnp01_right','dna02_left','dna02_right'})
        self.assertEqual(set(obs['motion']),{f.name for f in fields(MotionState)})
        with self.assertRaises(TypeError):policy_observation(World(GAME,101),'CALM')
        with self.assertRaises(ValueError):policy_observation(motor,'CALM',[{'pointer':(1,2)}])

    def test_recording_does_not_change_neural_or_physical_trajectory(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder=InteractionRecorder(Path(directory))
            def run(rec):
                s=Session(GAME,brain=shared_brain(),seed=101,mode='evaluation',recorder=rec)
                rows=[]
                for tick in range(100):
                    f=s.world.fly
                    s.tick((f.x+300-tick*5,f.y-100),strike=tick==65)
                    rows.append(s.state_vector().copy())
                s.close();return rows
            np.testing.assert_array_equal(run(None),run(recorder))

    def test_record_schema_metadata_actual_spikes_and_profile_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            r=InteractionRecorder(Path(directory))
            s=Session(GAME,brain=shared_brain(),seed=101,mode='evaluation',recorder=r)
            for tick in range(110):
                f=s.world.fly;s.tick((f.x+250-tick*3,f.y),strike=tick==65)
            s.close()
            read=lambda name:[json.loads(line) for line in (r.path/(name+'.jsonl')).read_text().splitlines()]
            episodes=read('episodes');samples=read('policy_samples');debug=read('world_debug');strikes=read('strikes')
            self.assertEqual(episodes[0]['episode_seed'],101)
            self.assertIn('spawn',episodes[0]);self.assertIn('provenance',episodes[0])
            self.assertEqual(len(strikes),1)
            for name in ('approach_angle','approach_speed','retina','neural','sensory_spikes','initial_heading','survival_after_threat_seconds','right_censored'):
                self.assertIn(name,strikes[0])
            self.assertIn('pointer',debug[0]);self.assertIn('injection_drive',debug[0]);self.assertIn('sensory_spikes',debug[0])
            self.assertEqual(samples[0]['observation']['behavior_state'],'CALM')
            self.assertIn('actuator',samples[0])
            manifest=json.loads((r.path/'manifest.json').read_text())
            self.assertEqual(manifest['config'],GAME)
            for sample in samples:
                text=json.dumps(sample['observation'])
                for bad in ('pointer','swatter','azimuth','theta','position','click','episode_seed'):
                    self.assertNotIn(bad,text)
                self.assertLessEqual(len(sample['observation']['history']),4)
            profile=json.loads((Path(directory)/'profile.json').read_text())
            self.assertEqual(profile['episodes_played'],1);self.assertEqual(profile['learning_updates'],0)
            self.assertIsNone(profile['policy_checkpoint'])

    def test_restart_flushes_episode_and_clears_internal_history(self):
        with tempfile.TemporaryDirectory() as directory:
            r=InteractionRecorder(Path(directory));s=Session(GAME,brain=shared_brain(),recorder=r)
            for _ in range(8):s.tick()
            s.reset(102);self.assertEqual(len(r.history),0)
            s.tick();s.close()
            episodes=(r.path/'episodes.jsonl').read_text().splitlines()
            self.assertEqual(len(episodes),2)


if __name__=='__main__':unittest.main(verbosity=2)
