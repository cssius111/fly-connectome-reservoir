"""M1.7 fixed-tick recording, deterministic replay and physical paddle regressions."""
import copy
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
import numpy as np
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
from game.session import Session, load_config
from game.session_recording import HumanSessionRecorder, canonical_hash
from game.replay import replay_session
from game.world import World, StrikePhase
from game.physical_swatter import swept_disk_hit
from game.perception import RetinaProjector
from test_game import shared_brain, CONFIG
ROOM=load_config(Path(__file__).parent/'game_room_config.json')
DT=.02


def read_rows(path):return [json.loads(s) for s in Path(path).read_text(encoding='utf-8').splitlines()]


def synthetic(directory):
    rec=HumanSessionRecorder(directory,config_file=Path(__file__).parent/'game_room_config.json',archive_source=False)
    s=Session(ROOM,brain=shared_brain(),seed=101,mode='evaluation',recorder=rec)
    for i in range(90):s.tick(pointer=(1200+7*i,850+2*i),strike=i==25)
    s.record_control('pause',paused=True)
    s.record_control('pause',paused=False)
    s.request_strike()  # between ticks, including acceptance/rejection
    for i in range(60):s.tick(pointer=(1900-5*i,1100-2*i))
    s.reset(1101)
    for i in range(100):s.tick(pointer=(1300+3*i,900),strike=i==30)
    s.close();return rec


class TestPhysicalSwatter(unittest.TestCase):
    def test_bounded_speed_and_acceleration_during_approach_and_strike(self):
        w=World(ROOM,101);cap=ROOM['swatter']['physical']
        for i in range(500):
            w.set_pointer(0 if i%140<70 else w.width,0 if i%180<90 else w.height)
            if i%75==20:w.request_strike()
            before=(w.swatter.vx,w.swatter.vy);w.tick(DT)
            sw=w.swatter
            self.assertLessEqual(math.hypot(sw.vx,sw.vy),cap['speed_limit']+1e-8)
            self.assertLessEqual(math.dist(before,(sw.vx,sw.vy))/DT,cap['acceleration_limit']+1e-7)
            self.assertLessEqual(math.hypot(sw.ax,sw.ay),cap['acceleration_limit']+1e-7)
            self.assertLessEqual(abs(sw.angular_velocity),cap['angular_speed_limit']+1e-8)

    def test_no_pointer_teleport(self):
        w=World(ROOM,101);before=(w.swatter.x,w.swatter.y)
        w.set_pointer(3500,2000)
        self.assertEqual(before,(w.swatter.x,w.swatter.y))
        w.tick(DT)
        self.assertLess(math.dist(before,(w.swatter.x,w.swatter.y)),3200*DT)
        self.assertGreater(math.dist((3500,2000),(w.swatter.x,w.swatter.y)),500)

    def test_center_stays_bounded_with_partial_offscreen_head_in_corner_stress(self):
        w=World(ROOM,101);w.collisions_enabled=False
        for i in range(1500):
            w.set_pointer(0 if i%220<110 else w.width,0 if i%300<150 else w.height)
            if i%60==20:w.request_strike()
            w.tick(DT)
            self.assertGreater(w.swatter.x,-2)
            self.assertLess(w.swatter.x,w.width+2)
            self.assertGreater(w.swatter.y,-2)
            self.assertLess(w.swatter.y,w.height+2)

    def approach(self,angle,speed):
        w=World(ROOM,101)
        for i in range(15):
            w.set_pointer(1800+speed*i*DT*math.cos(angle),1000+speed*i*DT*math.sin(angle));w.tick(DT)
        w.request_strike();return w

    def test_slow_fast_stationary_and_directions_differ(self):
        slow=self.approach(0,100);fast=self.approach(0,1400);still=self.approach(0,0)
        self.assertLess(still.swatter.swing_speed,slow.swatter.swing_speed)
        self.assertLess(slow.swatter.swing_speed,fast.swatter.swing_speed)
        for angle in (0,math.pi,-math.pi/2,math.pi/4):
            w=self.approach(angle,700)
            error=(w.swatter.attack_orientation-angle+math.pi)%(2*math.pi)-math.pi
            self.assertAlmostEqual(error,0,places=9)

    def test_recent_acceleration_trend_changes_committed_swing(self):
        w=World(ROOM,101)
        for i in range(20):w.set_pointer(1700+500*(i*DT)**2,1000);w.tick(DT)
        w.request_strike();self.assertGreater(w.swatter.attack_acceleration,0)

    def test_all_phases_follow_through_and_recovery_restore_control(self):
        w=self.approach(0,1000);w.collisions_enabled=False;phases={w.swatter.phase};follow=[]
        for _ in range(80):
            w.tick(DT);phases.add(w.swatter.phase)
            if w.swatter.phase is StrikePhase.FOLLOW_THROUGH:follow.append(w.swatter.x)
        self.assertEqual(phases,{StrikePhase.COMMIT,StrikePhase.FAST_SWING,StrikePhase.ACTIVE_CONTACT,
                                 StrikePhase.FOLLOW_THROUGH,StrikePhase.RECOVERY,StrikePhase.APPROACH})
        self.assertGreater(follow[-1],follow[0])
        before=w.swatter.x;w.set_pointer(500,w.swatter.y)
        for _ in range(50):w.tick(DT)
        self.assertLess(w.swatter.x,before)

    def test_click_does_not_instantly_change_retina_geometry(self):
        w=self.approach(.3,700)
        # A commit changes state/intent, not position, face or height.
        w=World(ROOM,101);p=RetinaProjector(DT)
        a=p.project(w);w.request_strike();b=p.project(w)
        self.assertEqual((a.theta,a.azimuth),(b.theta,b.azimuth))
        self.assertAlmostEqual(b.theta_dot,0)

    def test_legacy_lab_has_no_physical_swatter(self):
        self.assertIsNone(World(CONFIG,101).physical_swatter)

    def test_swept_crossing_and_moving_fly_are_detected(self):
        self.assertTrue(swept_disk_hit((-100,0),(100,0),(0,0),(0,0),5))
        self.assertTrue(swept_disk_hit((-100,0),(100,0),(100,0),(-100,0),5))
        self.assertFalse(swept_disk_hit((-100,10),(100,10),(0,0),(0,0),5))

    def test_world_uses_active_swept_interval_not_only_endpoint(self):
        w=World(ROOM,101);w.fly.x=w.fly.y=1000
        w._fly_before=(1000,1000)
        w.physical_swatter.segments=[(0,1,(700,1000),(1300,1000),True)]
        w.swatter.x=1300;w.swatter.y=1000;w.swatter.phase=StrikePhase.FOLLOW_THROUGH
        self.assertTrue(w._resolve_collision())
        w.physical_swatter.segments=[(0,1,(700,1200),(1300,1200),True)]
        self.assertFalse(w._resolve_collision())
        w.physical_swatter.segments=[(0,1,(700,1000),(1300,1000),False)]
        self.assertFalse(w._resolve_collision())

    def test_collision_trajectory_is_independent_of_render_reads(self):
        def run(reads):
            w=World(ROOM,101);rows=[]
            for i in range(100):
                w.set_pointer(1800+i*4,1250)
                if i==25:w.request_strike()
                events=w.tick(DT)
                for _ in range(reads):_=(w.visual_half_size,w.state_vector(),w.lethal)
                rows.append((w.state_vector(),events.hit))
            return rows
        a,b=run(0),run(5)
        for x,y in zip(a,b):np.testing.assert_array_equal(x[0],y[0]);self.assertEqual(x[1],y[1])


class TestHumanSessionRecording(unittest.TestCase):
    def test_fixed_tick_schema_and_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            rec=synthetic(Path(d));rows=read_rows(rec.path/'ticks.jsonl')
            self.assertEqual(len(rows),250)
            for i,row in enumerate(rows):
                self.assertEqual(row['global_tick'],i)
                self.assertAlmostEqual(row['simulation_time'],row['tick']*.02)
                for key in ('fly','retina','visual_input','sensory_spikes','neural','action','saccade','ecology','wall','swatter','event_flags','presentation'):
                    self.assertIn(key,row)
            fly=rows[0]['fly'];self.assertTrue({'vx','vy','speed_bl_s','velocity_heading','heading_velocity_mismatch','ax','ay'}<=set(fly))
            neural=rows[0]['neural'];self.assertTrue({'dnp01_total','dna02_left','threshold','refractory_seconds'}<=set(neural))
            manifest=json.loads((rec.path/'manifest.json').read_text())
            self.assertEqual(manifest['sampling_hz'],50);self.assertEqual(manifest['tick_count'],250)
            self.assertTrue(manifest['closed_cleanly']);self.assertFalse(manifest['full_brain_recording'])
            for key in ('git_commit','git_branch','config_sha256','config_file','arena','initial_seed','logical_arena','body_length','source_sha256'):self.assertIn(key,manifest)
            self.assertTrue(all(f.closed for f in rec.files.values()))

    def test_unique_directories_and_zero_tick_close(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=HumanSessionRecorder(d,archive_source=False),HumanSessionRecorder(d,archive_source=False)
            self.assertNotEqual(a.path,b.path)
            for rec in (a,b):
                s=Session(ROOM,brain=shared_brain(),seed=101,recorder=rec);s.close();s.close()
                summary=json.loads((rec.path/'summary.json').read_text())
                self.assertEqual(summary['ticks'],0);self.assertIsNone(summary['hit_rate'])

    def test_summary_matches_tick_and_episode_records(self):
        with tempfile.TemporaryDirectory() as d:
            rec=synthetic(d);rows=read_rows(rec.path/'ticks.jsonl');ep=read_rows(rec.path/'episodes.jsonl')
            summary=json.loads((rec.path/'summary.json').read_text())
            self.assertEqual(summary['episodes'],2);self.assertEqual(summary['duration_simulation_seconds'],5)
            self.assertEqual(summary['strikes'],sum(e['stats']['strikes'] for e in ep))
            self.assertEqual(summary['alert_count'],sum(r['event_flags']['alert_onset'] for r in rows))
            self.assertEqual(summary['escape_count'],sum(r['event_flags']['escape_onset'] for r in rows))
            self.assertEqual(summary['dnp01_threshold_crossings'],sum(r['event_flags']['threshold_crossing'] for r in rows))
            self.assertAlmostEqual(sum(summary['threat_state_fraction'].values()),1)
            self.assertTrue((rec.path/'REPORT.md').exists())

    def test_strike_event_window_indices_and_input_timing(self):
        with tempfile.TemporaryDirectory() as d:
            rec=synthetic(d);strikes=json.loads((rec.path/'strikes.json').read_text())
            inputs=read_rows(rec.path/'inputs.jsonl');ticks=read_rows(rec.path/'ticks.jsonl')
            self.assertGreaterEqual(len(strikes),2)
            self.assertEqual(strikes[0]['start_tick'],25)
            for st in strikes:
                lo,hi=st['window_global_ticks'];window=ticks[lo:hi+1]
                self.assertTrue(all(r['episode']==st['episode'] for r in window))
                self.assertEqual(st['requested_window_ticks'][1],st['start_tick']+100)
            clicks=[r for r in inputs if r['kind']=='tick' and r['strike']]
            self.assertEqual([r['next_tick'] for r in clicks],[25,30])
            self.assertEqual([r['next_tick'] for r in inputs if r['kind']=='request_strike'],[90])
            self.assertEqual(sum(r['kind']=='control' for r in inputs),2)

    def test_policy_whitelist_remains_separate_from_world(self):
        with tempfile.TemporaryDirectory() as d:
            rec=synthetic(d)
            for row in read_rows(rec.path/'policy_observations.jsonl'):
                obs=row['observation'];self.assertEqual(set(obs),{'neural','motion','behavior_state','history'})
                for token in ('pointer','swatter','food','room_world','world_position','wind'):
                    self.assertNotIn(token,json.dumps(obs))
            self.assertIn('room_world',read_rows(rec.path/'ticks.jsonl')[0])

    def test_recorder_does_not_change_trajectory(self):
        def run(rec):
            s=Session(ROOM,brain=shared_brain(),seed=101,recorder=rec);rows=[]
            for i in range(80):s.tick(pointer=(1500+5*i,1100),strike=i==20);rows.append(s.state_vector())
            s.close();return rows
        reference=run(None)
        with tempfile.TemporaryDirectory() as d:np.testing.assert_array_equal(reference,run(HumanSessionRecorder(d,archive_source=False)))

    def test_exact_replay_including_restarts_pauses_and_between_tick_click(self):
        with tempfile.TemporaryDirectory() as d:
            rec=synthetic(d);result=replay_session(rec.path,write_report=False)
            self.assertTrue(result['exact']);self.assertEqual(result['ticks_verified'],250)
            self.assertEqual(result['episodes'],2)

    def test_replay_detects_modified_tick_state(self):
        with tempfile.TemporaryDirectory() as d:
            rec=synthetic(d);rows=read_rows(rec.path/'ticks.jsonl');rows[10]['deterministic_sha256']='bad'
            (rec.path/'ticks.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n',encoding='utf-8')
            with self.assertRaisesRegex(AssertionError,'diverged'):replay_session(rec.path,write_report=False)

    def test_replay_detects_modified_state_even_if_hash_is_not_edited(self):
        with tempfile.TemporaryDirectory() as d:
            rec=synthetic(d);rows=read_rows(rec.path/'ticks.jsonl');rows[10]['fly']['x']+=1
            (rec.path/'ticks.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n',encoding='utf-8')
            with self.assertRaisesRegex(AssertionError,'integrity diverged'):replay_session(rec.path,write_report=False)

    def test_between_tick_click_then_immediate_restart_is_indexed(self):
        with tempfile.TemporaryDirectory() as d:
            rec=HumanSessionRecorder(d,archive_source=False)
            session=Session(ROOM,brain=shared_brain(),seed=101,recorder=rec)
            self.assertTrue(session.request_strike())
            session.reset(1101);session.tick(pointer=(500,500));session.close()
            strikes=json.loads((rec.path/'strikes.json').read_text())
            self.assertEqual(len(strikes),1);self.assertTrue(strikes[0]['no_tick_sample'])
            self.assertEqual(strikes[0]['window_global_ticks'],[0,-1])
            summary=json.loads((rec.path/'summary.json').read_text())
            self.assertEqual(summary['strikes'],1);self.assertEqual(summary['incomplete_strikes'],1)
            self.assertTrue(replay_session(rec.path,write_report=False)['exact'])

    def test_profile_counts_persist_without_overwriting_sessions(self):
        with tempfile.TemporaryDirectory() as d:
            a=synthetic(d);original=(a.path/'summary.json').read_bytes();synthetic(d)
            profile=json.loads((Path(d)/'profile.json').read_text())
            self.assertEqual(profile['episodes_played'],4);self.assertEqual(profile['learning_updates'],0)
            self.assertEqual((a.path/'summary.json').read_bytes(),original)

    def test_physical_head_draws_in_all_phases(self):
        from game.app import App,pygame
        app=App(ROOM,seed=101,mode='evaluation')
        try:
            for phase in (StrikePhase.APPROACH,StrikePhase.COMMIT,StrikePhase.FAST_SWING,StrikePhase.ACTIVE_CONTACT,StrikePhase.FOLLOW_THROUGH,StrikePhase.RECOVERY):
                app.session.world.swatter.phase=phase
                surface=pygame.Surface((1280,720));surface.fill((0,0,0))
                app._draw_swatter(surface,(500,400),60,.5)
                pixels=pygame.surfarray.array3d(surface)
                self.assertGreater(np.count_nonzero(pixels[450:550,300:450]),500)
        finally:app.session.close();pygame.quit()


if __name__=='__main__':unittest.main()
