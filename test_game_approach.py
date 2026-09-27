"""M1.7.1 ordinary tracking, burst preservation and unambiguous session populations."""
from collections import Counter
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numba
import numpy as np
from game.action import Action
from game.world import World, StrikePhase
from game.session import Session, load_config
from game.perception import RetinaProjector
from game.session_recording import HumanSessionRecorder
from game.replay import replay_session
from test_game import shared_brain
ROOT=Path(__file__).parent
CFG=load_config(ROOT/'game_room_config.json')


def moving(speed):
    w=World(CFG,101);w.collisions_enabled=False;values=[]
    for i in range(80):
        w.set_pointer(1920+speed*min(max(i-30,0),35)*.02,388.8)
        w.tick(.02)
        if 30<=i<65:values.append(math.hypot(w.swatter.vx,w.swatter.vy))
    return w,values


class TestApproachDynamics(unittest.TestCase):
    def test_slow_tracking_remains_slow(self):
        _,v=moving(100)
        self.assertLess(max(v),150);self.assertAlmostEqual(np.mean(v),100,delta=15)

    def test_moderate_tracking_does_not_saturate(self):
        _,v=moving(600)
        self.assertLess(max(v),900);self.assertAlmostEqual(np.mean(v),600,delta=80)

    def test_sudden_burst_remains_fast(self):
        _,v=moving(2000)
        self.assertGreater(max(v),1750)

    def test_large_initial_error_has_bounded_catchup(self):
        w=World(CFG,101);w.collisions_enabled=False
        for _ in range(240):
            w.set_pointer(500,1500);w.tick(.02)
            self.assertLessEqual(math.hypot(w.swatter.vx,w.swatter.vy),900+1e-7)
        self.assertLess(math.dist((w.swatter.x,w.swatter.y),(500,1500)),2)

    def test_small_corrections_are_proportional(self):
        traces=[]
        for step in (2,4):
            w=World(CFG,101);w.collisions_enabled=False;w.tick(.02);xs=[]
            for _ in range(40):
                w.set_pointer(1920+step,388.8);w.tick(.02);xs.append(w.swatter.x-1920)
            traces.append(xs)
        np.testing.assert_allclose(traces[1],np.asarray(traces[0])*2,atol=1e-9)

    def test_pointer_changes_do_not_teleport_or_jump_velocity(self):
        w=World(CFG,101);w.tick(.02);before=(w.swatter.x,w.swatter.y,w.swatter.vx,w.swatter.vy)
        w.set_pointer(3840,2160)
        self.assertEqual(before,(w.swatter.x,w.swatter.y,w.swatter.vx,w.swatter.vy))
        for _ in range(100):
            old=(w.swatter.vx,w.swatter.vy);p=(w.swatter.x,w.swatter.y);w.tick(.02)
            self.assertLessEqual(math.dist(old,(w.swatter.vx,w.swatter.vy)),18000*.02+1e-7)
            self.assertLessEqual(math.dist(p,(w.swatter.x,w.swatter.y)),3200*.02+1e-7)

    def test_command_is_filtered_at_substeps(self):
        w=World(CFG,101);w.tick(.02);w.set_pointer(3840,388.8)
        w.tick(.002)
        cmd=math.hypot(*w.physical_swatter.approach_command)
        self.assertGreater(cmd,0);self.assertLess(cmd,65)
        self.assertLess(math.hypot(w.swatter.vx,w.swatter.vy),10)

    def test_committed_fast_swing_remains_fast(self):
        w=World(CFG,101);w.collisions_enabled=False
        for i in range(30):w.set_pointer(1500+40*i,1000);w.tick(.02)
        self.assertTrue(w.request_strike());self.assertGreater(w.swatter.swing_speed,1800)
        speeds=[]
        for _ in range(30):
            w.tick(.02)
            if w.swatter.phase in (StrikePhase.FAST_SWING,StrikePhase.ACTIVE_CONTACT):speeds.append(math.hypot(w.swatter.vx,w.swatter.vy))
        self.assertGreater(max(speeds),1700)

    def test_fixed_inputs_and_reset_are_deterministic(self):
        def run(w):
            data=[]
            for i in range(120):
                w.set_pointer(1000+i*8,1000)
                if i==60:w.request_strike()
                w.tick(.02);data.append((w.swatter.x,w.swatter.y,w.swatter.vx,w.swatter.vy,*w.physical_swatter.approach_command))
            return data
        w=World(CFG,101);a=run(w);w.reset(101);self.assertEqual(a,run(w))

    def test_retina_uses_actual_geometry_not_pointer_velocity(self):
        w=World(CFG,101)
        before=RetinaProjector(.02).project(w)
        w.set_pointer(w.fly.x,w.fly.y)
        unchanged=RetinaProjector(.02).project(w)
        self.assertEqual(before,unchanged)
        for _ in range(30):w.tick(.02)
        after=RetinaProjector(.02).project(w)
        self.assertNotEqual(before.theta,after.theta)

    def test_real_neural_alert_can_precede_click(self):
        s=Session(CFG,brain=shared_brain(),seed=101)
        s.world.fly_motion_enabled=False
        seen=[]
        for _ in range(180):
            s.tick(pointer=(s.world.fly.x,s.world.fly.y));seen.append(s.policy_diagnostics['behavior_state'])
        self.assertTrue(any(state in ('ALERT','ESCAPE') for state in seen));self.assertEqual(s.stats.strikes,0)
        s.close()


class TestSessionPopulationReporting(unittest.TestCase):
    def test_dead_ticks_are_separated_for_state_ecology_and_speed(self):
        class Policy:
            def reset(self):self.n=0
            def decide(self,motor):self.n+=1;return Action()
            def diagnostics(self):return {'behavior_state':'ESCAPE' if self.n>=5 else 'CALM'}
        with tempfile.TemporaryDirectory() as d:
            rec=HumanSessionRecorder(d,archive_source=False)
            s=Session(CFG,brain=shared_brain(),policy=Policy(),seed=101,recorder=rec)
            for _ in range(8):s.tick()
            s.world.fly.alive=False;s.world.fly.vx=s.world.fly.vy=0
            for _ in range(12):s.tick()
            s.close();summary=json.loads((rec.path/'summary.json').read_text())
            rows=[json.loads(line) for line in (rec.path/'ticks.jsonl').read_text().splitlines()]
            for label,eligible in [('all',rows),('alive',[r for r in rows if r['fly']['alive']])]:
                for prefix,group,key in [('threat','neural','state'),('ecological','ecology','state')]:
                    counts=Counter(r[group][key] for r in eligible)
                    self.assertEqual(summary[f'{prefix}_state_fraction_{label}'],{k:v/len(eligible) for k,v in counts.items()})
                self.assertAlmostEqual(summary[f'speed_bl_s_{label}']['mean'],np.mean([r['fly']['speed_bl_s'] for r in eligible]))
            self.assertEqual(summary['tick_populations']['alive_post_step'],8)
            self.assertGreater(summary['threat_state_fraction_all']['ESCAPE'],summary['threat_state_fraction_alive']['ESCAPE'])
            self.assertLess(summary['speed_bl_s_all']['mean'],summary['speed_bl_s_alive']['mean'])

    def test_control_diagnostics_are_not_policy_observations(self):
        with tempfile.TemporaryDirectory() as d:
            rec=HumanSessionRecorder(d,archive_source=False);s=Session(CFG,brain=shared_brain(),recorder=rec,seed=101)
            for i in range(4):s.tick(pointer=(1000+10*i,900))
            s.close();rows=[json.loads(line) for line in (rec.path/'ticks.jsonl').read_text().splitlines()]
            self.assertFalse(rows[0]['swatter_control']['pointer_sample_valid'])
            self.assertEqual(rows[1]['swatter_control']['pointer_speed'],500)
            for line in (rec.path/'policy_observations.jsonl').read_text().splitlines():
                obs=json.loads(line)['observation']
                self.assertEqual(set(obs),{'neural','motion','behavior_state','history'})
                for key in rows[1]['swatter_control']:self.assertNotIn(key,json.dumps(obs))

    def test_replay_restores_recorded_thread_count_and_then_callers_count(self):
        previous=numba.get_num_threads()
        try:
            numba.set_num_threads(2)
            with tempfile.TemporaryDirectory() as d:
                rec=HumanSessionRecorder(d,archive_source=False);s=Session(CFG,brain=shared_brain(),recorder=rec,seed=101)
                for i in range(60):s.tick(pointer=(1000+8*i,900),strike=i==35)
                s.reset(1101)
                for _ in range(10):s.tick(pointer=(500,900))
                s.close();numba.set_num_threads(1)
                # Late environment defaults may reload config without resizing
                # the initialized pool. The actual set_num_threads API decides.
                with patch.object(numba.config,'NUMBA_NUM_THREADS',1):
                    result=replay_session(rec.path,write_report=False)
                self.assertTrue(result['exact']);self.assertEqual(result['runtime_verified']['numba_threads'],2)
                self.assertEqual(numba.get_num_threads(),1)
        finally:numba.set_num_threads(previous)

    def test_zero_alive_population_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            rec=HumanSessionRecorder(d,archive_source=False);s=Session(CFG,brain=shared_brain(),recorder=rec,seed=101)
            s.close();summary=json.loads((rec.path/'summary.json').read_text())
            self.assertEqual(summary['threat_state_fraction_alive'],{})
            self.assertEqual(summary['speed_bl_s_alive']['n'],0);self.assertIsNone(summary['speed_bl_s_alive']['mean'])


if __name__=='__main__':unittest.main()
