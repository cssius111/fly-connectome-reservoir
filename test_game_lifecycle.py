"""M1.8-A local lifecycle and real frozen-neural integration regressions."""
import copy
from dataclasses import asdict, fields, replace
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
import numpy as np
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
from game.action import Action, MotionState
from game.ecology import ThreatState
from game.lifecycle import LandingSense, LifecycleController, LifecycleMetrics
from game.room import RoomEnvironment
from game.session import Session, load_config, resolve_escape_threshold
from game.session_recording import HumanSessionRecorder
from game.replay import replay_session
from game.world import World, Fly
from test_game import shared_brain

ROOT = Path(__file__).parent
ROOM = load_config(ROOT/'game_room_config.json')
DT = .02


def controller(seed=101):
    return LifecycleController(ROOM['lifecycle'], seed)


def approach_world(seed=101):
    w = World(ROOM, seed)
    w.fly = Fly(1290, 1120, -216, 0, math.pi)
    return w


def local_tick(w, action=Action(), threat=ThreatState.CALM):
    m = w.motion_state()
    sense = w.room.landing_sense(w.fly, w.time_seconds, w.contact_surface_id)
    w.lifecycle.step(sense, MotionState(m.forward_speed/w.body_length, m.lateral_speed/w.body_length,
                                       m.yaw_rate, m.saccade_remaining), threat, DT,
                     action.escape and action.strength > 0 and math.hypot(action.forward, action.lateral) > 0)
    w.tick(DT, action)


def land(w):
    for i in range(500):
        local_tick(w)
        if w.lifecycle.stationary:
            return i
    raise AssertionError('local visual approach did not land')


class TestLocalLifecycle(unittest.TestCase):
    def test_local_sensory_whitelist(self):
        self.assertEqual({f.name for f in fields(LandingSense)},
                         {'affordance','bearing','angular_extent','angular_expansion','odor','contact','food_contact'})
        c = controller()
        for value in ({'x': 100}, World(ROOM, 1), (1, 2)):
            with self.assertRaises(TypeError):c.step(value, MotionState(), ThreatState.CALM, DT)

    def test_true_expansion_matches_angular_finite_difference(self):
        w = approach_world();f=w.fly
        a = w.room.landing_sense(f, 0)
        moved = replace(f, x=f.x+f.vx*1e-6, y=f.y+f.vy*1e-6)
        b = w.room.landing_sense(moved, 0)
        self.assertAlmostEqual((b.angular_extent-a.angular_extent)/1e-6, a.angular_expansion, places=5)
        rotated = replace(f, heading=f.heading+.1)
        self.assertAlmostEqual(w.room.landing_sense(rotated, 0).angular_expansion, a.angular_expansion)

    def test_entry_needs_sustained_local_approach(self):
        c = controller();cue = LandingSense(.2, 0, .7, .3)
        c.step(cue, MotionState(8), ThreatState.CALM, DT)
        self.assertEqual(c.mode, 'AIRBORNE')
        for _ in range(6):c.step(cue, MotionState(8), ThreatState.CALM, DT)
        self.assertEqual(c.mode, 'LAND_APPROACH')

    def test_affordance_alone_does_not_force_a_landing(self):
        c = controller()
        for _ in range(100):c.step(LandingSense(.9, 0, 2, 0), MotionState(8), ThreatState.CALM, DT)
        self.assertEqual(c.mode, 'AIRBORNE')

    def test_visual_extent_expansion_and_speed_affect_deceleration(self):
        def target(extent, expansion, speed):
            c=controller();c.mode='LAND_APPROACH'
            c.step(LandingSense(.4, 0, extent, expansion), MotionState(speed), ThreatState.CALM, DT)
            return c.target_speed
        self.assertLess(target(1.4,.3,8),target(.5,.3,8))
        self.assertLess(target(.5,1.5,8),target(.5,.1,8))
        self.assertGreater(target(.5,.3,10),target(.5,.3,5))

    def test_leg_commit_requires_size_speed_and_alignment(self):
        for speed,bearing,expected in ((9,0,False),(3,.5,False),(3,0,True)):
            c=controller();c.mode='LAND_APPROACH'
            c.step(LandingSense(.5,bearing,1.2,.2),MotionState(speed),ThreatState.CALM,DT)
            self.assertEqual(c.committed,expected)
            self.assertEqual(c.mode,'LAND_APPROACH')

    def test_lost_surface_causes_flyby_abort(self):
        c=controller();c.mode='LAND_APPROACH'
        for _ in range(9):c.step(LandingSense(.2,0,.7,-.4),MotionState(8),ThreatState.CALM,DT)
        self.assertEqual(c.mode,'AIRBORNE');self.assertEqual(c.failed_approaches,1)
        self.assertEqual(c.reason,'fly_by_or_cue_loss')

    def test_neural_escape_aborts_approach(self):
        c=controller();c.mode='LAND_APPROACH';c.committed=True
        c.step(LandingSense(),MotionState(4),ThreatState.ESCAPE,DT,True)
        self.assertEqual(c.mode,'AIRBORNE');self.assertFalse(c.committed)
        self.assertEqual(c.events[0]['reason'],'neural_escape')

    def test_touchdown_requires_physical_callback(self):
        c=controller();c.mode='LAND_APPROACH'
        c.step(LandingSense(.8,0,2,.3),MotionState(2),ThreatState.CALM,DT)
        self.assertTrue(c.committed);self.assertFalse(c.stationary)
        c.touchdown();self.assertEqual(c.mode,'TOUCHDOWN')

    def test_swept_contact_does_not_tunnel_or_snap(self):
        w=approach_world();f=Fly(800,1120,-500,0,math.pi)
        contact=w.room.landing_contact(f,(1400,1120),w.fly_radius)
        self.assertEqual(contact,'surface-0');self.assertAlmostEqual(f.x,1126)
        f=Fly(1030,1120,-100,0,math.pi)
        self.assertIsNone(w.room.landing_contact(f,(1040,1120),w.fly_radius))
        self.assertEqual(f.x,1030)

    def test_physical_touchdown_and_stationary_pose(self):
        w=approach_world();land(w)
        pose=(w.fly.x,w.fly.y,w.fly.heading);flight_clock=w._flight_time
        wait=w.flight.wait
        for _ in range(75):
            local_tick(w)
            self.assertEqual((w.fly.x,w.fly.y,w.fly.heading),pose)
            self.assertEqual((w.fly.vx,w.fly.vy,w.yaw_rate),(0,0,0))
            self.assertEqual(w.saccades.kind,'NONE')
        self.assertEqual(w._flight_time,flight_clock);self.assertEqual(w.flight.wait,wait)
        self.assertTrue(w.fly.alive);self.assertTrue(w.lifecycle.feeding)
        self.assertEqual(w.contact_surface_id,'surface-0')

    def test_nonfood_surface_perches_without_feeding(self):
        w=approach_world();w.fly=Fly(3090,1610,-216,0,math.pi)
        land(w)
        for _ in range(20):local_tick(w)
        self.assertEqual(w.contact_surface_id,'surface-2')
        self.assertTrue(w.lifecycle.stationary);self.assertFalse(w.lifecycle.feeding)

    def test_reset_clears_attachment_and_lifecycle_history(self):
        w=approach_world();land(w);w.reset(101)
        self.assertIsNone(w.contact_pose);self.assertIsNone(w.contact_surface_id)
        self.assertEqual(w.lifecycle.mode,'AIRBORNE');self.assertFalse(w.lifecycle.feeding)

    def test_stale_ignored_calibration_cannot_override_matching_record(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            valid=load_config(ROOT/'results/game/calibration_room_m1_8_b2a.json')
            stale=copy.deepcopy(valid);stale['provenance']['encoder_seed']+=1
            stale['escape_threshold']=99
            for path,record in zip(ROOM['policy']['calibration_paths'],(stale,valid)):
                p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(record))
            source=resolve_escape_threshold(ROOM,root)
            self.assertEqual(source.threshold,1.45)
            self.assertEqual(source.origin,ROOM['policy']['calibration_paths'][1])

    def test_stationary_alert_does_not_execute_airborne_turns(self):
        w=approach_world();land(w);heading=w.fly.heading
        local_tick(w,Action(turn=1,saccade=1),ThreatState.ALERT)
        self.assertEqual(w.fly.heading,heading);self.assertEqual(w.body_lengths_per_second,0)

    def test_voluntary_departure_deterministic_and_sensory_dependent(self):
        def departure(seed, food, odor):
            c=controller(seed);c.mode='LAND_APPROACH';c.committed=True;c.touchdown()
            for i in range(5000):
                c.step(LandingSense(odor=odor,contact=True,food_contact=food),MotionState(),ThreatState.CALM,DT)
                if c.mode=='TAKEOFF_VOLUNTARY':return i
            self.fail('no motivated departure')
        a=departure(101,False,0)
        self.assertEqual(a,departure(101,False,0))
        self.assertGreater(departure(101,True,2),a)
        self.assertNotEqual(a,departure(102,False,0))
        self.assertGreaterEqual(a*DT,ROOM['lifecycle']['minimum_perch_seconds']-DT)

    def test_launch_clears_contact_and_preserves_separate_profiles(self):
        w=approach_world();land(w)
        local_tick(w,Action(escape=True,lateral=1,strength=.5),ThreatState.ESCAPE)
        self.assertEqual(w.lifecycle.mode,'TAKEOFF_ESCAPE')
        self.assertIsNone(w.contact_surface_id);self.assertGreater(w.body_lengths_per_second,0)
        self.assertEqual(w.lifecycle.applied_profile['impulse_bl_s'],880*.5/24)
        local_tick(w);self.assertEqual(w.lifecycle.mode,'AIRBORNE')

    def test_zero_strength_escape_cannot_launch(self):
        w=approach_world();land(w)
        local_tick(w,Action(escape=True,lateral=1,strength=0),ThreatState.ESCAPE)
        self.assertTrue(w.lifecycle.stationary)

    def test_voluntary_kinematic_initial_condition(self):
        w=approach_world();land(w)
        for _ in range(2000):
            local_tick(w)
            if w.lifecycle.mode=='TAKEOFF_VOLUNTARY':break
        self.assertEqual(w.lifecycle.mode,'TAKEOFF_VOLUNTARY')
        self.assertAlmostEqual(w.body_lengths_per_second,6)
        self.assertIsNone(w.contact_pose);self.assertFalse(w.lifecycle.committed)

    def test_alive_only_metrics_and_censoring(self):
        m=LifecycleMetrics();c=controller()
        m.capture(c,True,DT)
        c.mode='PERCHED';c.feeding=True
        for _ in range(10):m.capture(c,True,DT)
        c.mode='TAKEOFF_VOLUNTARY';c.feeding=False;m.capture(c,True,DT)
        m.capture(c,False,DT)
        r=m.report();self.assertEqual(r['alive_ticks'],12)
        self.assertAlmostEqual(r['fractions']['perched'],10/12)
        self.assertAlmostEqual(r['median_perch_seconds'],.2)
        self.assertIsNone(r['median_flight_bout_seconds'])
        self.assertEqual(len(r['censored_bouts']),2)

    def test_legacy_arenas_have_no_lifecycle(self):
        for path in ('game_config.json','game_play_config.json'):
            self.assertIsNone(World(load_config(ROOT/path),1).lifecycle)

    def test_calibration_transfer_only_changes_inactive_protocol_fields(self):
        import subprocess
        before=json.loads(subprocess.check_output(['git','show','f8f440b:game_room_config.json'],cwd=ROOT,text=True))
        after=copy.deepcopy(ROOM)
        after.pop('lifecycle');after.pop('kinematics');after['config_version']=before['config_version']
        after['policy']['calibration_paths']=before['policy']['calibration_paths']
        self.assertEqual(after,before)
        # The active record chains M1.8-B2a -> M1.8-A -> the M1.7.1 measurement, and every
        # link must name the exact bytes it transfers from.
        original=ROOT/'results/game/calibration_room_m1_7_1.json'
        previous=ROOT/'results/game/calibration_room_m1_8_a.json'
        self.assertEqual(load_config(previous)['measurement_reuse']['source_sha256'],
                         hashlib.sha256(original.read_bytes()).hexdigest())
        record=load_config(ROOT/'results/game/calibration_room_m1_8_b2a.json')
        reuse=record['measurement_reuse']
        self.assertEqual(reuse['source_record'],'results/game/calibration_room_m1_8_a.json')
        self.assertEqual(reuse['source_sha256'],hashlib.sha256(previous.read_bytes()).hexdigest())
        self.assertEqual(reuse['original_measurement'],'results/game/calibration_room_m1_7_1.json')
        self.assertEqual(reuse['original_measurement_sha256'],
                         hashlib.sha256(original.read_bytes()).hexdigest())
        self.assertEqual(sorted(reuse['changed_config_paths']),
                         ['config_version','kinematics','policy.calibration_paths'])
        self.assertEqual(resolve_escape_threshold(ROOM).threshold,1.45)
        self.assertEqual(resolve_escape_threshold(ROOM).origin,
                         'results/game/calibration_room_m1_8_b2a.json')
        for section,key in (('brain','gain'),('encoder','encoder_seed'),
                            ('lifecycle','contact_speed_bl_s'),
                            ('kinematics','room_kinematic_scale')):
            changed=copy.deepcopy(ROOM);changed[section][key]+=1
            with self.assertRaisesRegex(ValueError,'No matching'):resolve_escape_threshold(changed)


class TestNeuralLifecycle(unittest.TestCase):
    def test_natural_spawn_lands_and_perched_sensing_continues(self):
        s=Session(ROOM,brain=shared_brain(),seed=255)
        seen=set();odor=[];motor=[]
        for _ in range(240):
            s.tick(pointer=(1920,388.8))
            seen.update(e['type'] for e in s.world.lifecycle.events)
            if s.world.lifecycle.stationary:
                odor.append(s.last_ecological_sense.odor)
                motor.append(s.fly_loop.last_motor.dnp01_total)
        self.assertTrue({'approach_onset','approach_commit','touchdown','feed_start'} <= seen)
        self.assertGreater(len(odor),50);self.assertGreater(np.ptp(odor),0)
        self.assertGreater(np.ptp(motor),0)
        self.assertEqual(s.ecology.diagnostics()['landing_mechanics'],'external_local_lifecycle')

    def test_real_approaching_swatter_launches_perched_fly_without_click(self):
        s=Session(ROOM,brain=shared_brain(),seed=255)
        for _ in range(170):s.tick(pointer=(1920,388.8))
        self.assertTrue(s.world.lifecycle.stationary)
        seen=False;max_expansion=0
        for _ in range(220):
            s.tick(pointer=(s.world.fly.x,s.world.fly.y))
            max_expansion=max(max_expansion,s.last_retina.theta_dot)
            if s.world.lifecycle.mode=='TAKEOFF_ESCAPE':
                self.assertTrue(s.fly_loop.last_action.escape)
                self.assertGreaterEqual(s.fly_loop.last_motor.dnp01_total,1.45)
                self.assertIsNone(s.world.contact_surface_id)
                seen=True;break
        self.assertTrue(seen);self.assertGreater(max_expansion,0)
        self.assertEqual(s.stats.strikes,0);self.assertTrue(s.world.fly.alive)

    def test_real_loom_aborts_approach(self):
        s=Session(ROOM,brain=shared_brain(),seed=255)
        for _ in range(10):s.tick(pointer=(1920,388.8))
        self.assertEqual(s.world.lifecycle.mode,'LAND_APPROACH')
        # WORLD fixture: start the physical paddle near the approaching fly.
        # The controller still sees only Retina -> frozen brain -> Action.
        sw=s.world.swatter;f=s.world.fly
        sw.x,sw.y=f.x+450,f.y
        sw.target_x,sw.target_y=sw.x,sw.y
        found=False
        for _ in range(100):
            s.tick(pointer=(f.x,f.y))
            if any(e['type']=='approach_abort' and e['reason']=='neural_escape' for e in s.world.lifecycle.events):
                found=True;break
        self.assertTrue(found)

    def test_room_lifecycle_recording_exact_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            rec=HumanSessionRecorder(folder,archive_source=False)
            s=Session(ROOM,brain=shared_brain(),seed=255,recorder=rec)
            for _ in range(240):s.tick(pointer=(1920,388.8))
            for _ in range(100):s.tick(pointer=(s.world.fly.x,s.world.fly.y))
            s.close()
            manifest=load_config(rec.path/'manifest.json')
            self.assertEqual(manifest['recording_schema_version'],4)
            summary=load_config(rec.path/'summary.json')
            self.assertGreater(summary['lifecycle']['fractions']['perched'],0)
            self.assertEqual(summary['lifecycle']['events']['escape_takeoff'],1)
            rows=[json.loads(line) for line in (rec.path/'ticks.jsonl').read_text().splitlines()]
            self.assertTrue(any(row['lifecycle']['contact_surface_id']=='surface-0' for row in rows))
            self.assertTrue(replay_session(rec.path,write_report=False)['exact'])

    def test_lifecycle_never_reaches_policy_observations(self):
        forbidden=('lifecycle','contact','surface','landing','affordance','odor','food','perch',
                   'angular_extent','angular_expansion','swatter','pointer')
        with tempfile.TemporaryDirectory() as folder:
            rec=HumanSessionRecorder(folder,archive_source=False)
            s=Session(ROOM,brain=shared_brain(),seed=255,recorder=rec)
            for _ in range(160):s.tick(pointer=(1920,388.8))
            self.assertTrue(s.world.lifecycle.stationary)
            s.close()
            rows=[json.loads(line) for line in (rec.path/'policy_observations.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),160)
            for row in rows:
                self.assertEqual(set(row['observation']),{'neural','motion','behavior_state','history'})
            blob=json.dumps(rows)
            for key in forbidden:self.assertNotIn(key,blob)
            # The same privileged state is retained for offline WORLD analysis.
            ticks=[json.loads(line) for line in (rec.path/'ticks.jsonl').read_text().splitlines()]
            self.assertTrue(any(row['lifecycle']['contact_surface_id']=='surface-0' for row in ticks))
            self.assertTrue(all(row['room_world']['contact_pose'] is not None
                                for row in ticks if row['lifecycle']['attached']))

    def test_perch_death_events_do_not_repeat_and_metrics_exclude_dead(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            rec=HumanSessionRecorder(folder,archive_source=False)
            s=Session(ROOM,brain=shared_brain(),seed=255,recorder=rec)
            for _ in range(150):s.tick(pointer=(1920,388.8))
            self.assertTrue(s.world.lifecycle.stationary)
            with patch.object(s.world,'_resolve_collision',return_value=True):s.tick()
            for _ in range(5):s.tick()
            s.close()
            events=[json.loads(line) for line in (rec.path/'events.jsonl').read_text().splitlines()]
            ended=[e for e in events if e['type']=='perch_end']
            self.assertEqual(len(ended),1);self.assertEqual(ended[0]['reason'],'death')
            summary=load_config(rec.path/'summary.json')
            self.assertEqual(summary['lifecycle']['alive_ticks'],150)

    def test_disabled_ecology_keeps_lifecycle_inactive(self):
        s=Session(ROOM,brain=shared_brain(),seed=255,ecology_enabled=False)
        self.assertFalse(s.world.lifecycle_active)
        s.tick();self.assertFalse(s.world.lifecycle_active)

    def test_fixed_fly_protocol_neural_outputs_are_identical(self):
        import subprocess
        from tools.calibrate_escape import RecordingPolicy, _trial
        before=json.loads(subprocess.check_output(['git','show','f8f440b:game_room_config.json'],cwd=ROOT,text=True))
        outputs=[]
        for config in (before,ROOM):
            p=RecordingPolicy();s=Session(config,brain=shared_brain(),policy=p)
            s.world.fly_motion_enabled=False;s.world.collisions_enabled=False
            a=_trial(s,p,5000,(15,10),90,20)
            outputs.append(a['total'])
            self.assertEqual((s.world.fly.vx,s.world.fly.vy),(0,0))
        np.testing.assert_array_equal(*outputs)


class TestLifecyclePresentation(unittest.TestCase):
    """Presentation only; no lifecycle, ecology, swatter or threshold behavior changes."""

    def app_at_perch(self, ticks=240):
        from game.app import App
        app=App(ROOM,seed=255,mode='evaluation')
        app.pointer_world=(1920,388.8)
        for _ in range(ticks):app._advance(DT,False)
        return app

    def test_hud_shows_feeding_while_ecology_still_reports_odor_track(self):
        app=self.app_at_perch()
        try:
            w=app.session.world
            self.assertTrue(w.lifecycle.stationary);self.assertTrue(w.lifecycle.feeding)
            # The background ecological intent is exactly what confused the human tester.
            self.assertEqual(app.session.ecology.state,'ODOR_TRACK')
            self.assertGreater(app.session.ecology.speed,0)
            rows=app.behavior_lines()
            lifecycle_line,motion_line,intent_line,note_line=rows
            self.assertTrue(lifecycle_line.startswith('LIFECYCLE'))
            self.assertIn('PERCHED',lifecycle_line);self.assertIn('FEEDING',lifecycle_line)
            self.assertTrue(intent_line.startswith('ECO INTENT'))
            self.assertIn('ODOR_TRACK',intent_line)
            self.assertNotIn('not executed',intent_line)
            self.assertIn('not executed: suppressed while perched',note_line)
            # Effective behavior must be readable before the unexecuted intent.
            self.assertLess(rows.index(lifecycle_line),rows.index(intent_line))
            self.assertNotIn('ODOR_TRACK',lifecycle_line+motion_line)
        finally:app.session.close()

    def test_hud_motion_and_applied_drive_are_zero_while_perched(self):
        app=self.app_at_perch()
        try:
            w=app.session.world
            motion_line=app.behavior_lines()[1]
            self.assertTrue(motion_line.startswith('MOTION'))
            self.assertIn('0.0 BL/s  applied drive 0.0 BL/s',motion_line)
            self.assertEqual(w.body_lengths_per_second,0);self.assertEqual(w.applied_target_speed,0)
            app._draw()  # The perch ring and FEEDING marker must render without error.
        finally:app.session.close()

    def test_behavior_rows_fit_inside_the_neural_panel(self):
        from game.app import NEURAL_PANEL_WIDTH
        app=self.app_at_perch()
        try:
            self.assertIn('not executed: suppressed while perched',app.behavior_lines()[3])
            for row in app.behavior_lines():
                width=app.font_small.size(row)[0]
                self.assertLess(width,NEURAL_PANEL_WIDTH-24,'HUD row overflows the panel: '+row)
        finally:app.session.close()

    def test_airborne_intent_is_not_labelled_suppressed(self):
        app=self.app_at_perch(ticks=1)
        try:
            self.assertFalse(app.session.world.lifecycle.stationary)
            self.assertEqual(len(app.behavior_lines()),3)
            self.assertNotIn('not executed',' '.join(app.behavior_lines()))
        finally:app.session.close()

    def test_legacy_arena_hud_keeps_its_original_rows(self):
        from game.app import App
        app=App(load_config(ROOT/'game_play_config.json'),seed=1,mode='evaluation')
        try:
            self.assertFalse(any(row.startswith('LIFECYCLE') for row in app.behavior_lines()))
        finally:app.session.close()

    def test_report_does_not_present_legacy_counter_as_lifecycle_landings(self):
        with tempfile.TemporaryDirectory() as folder:
            rec=HumanSessionRecorder(folder,archive_source=False)
            s=Session(ROOM,brain=shared_brain(),seed=255,recorder=rec)
            for _ in range(240):s.tick(pointer=(1920,388.8))
            s.close()
            summary=load_config(rec.path/'summary.json')
            self.assertEqual(summary['landing_attempts'],0)
            self.assertEqual(summary['lifecycle']['events']['touchdown'],1)
            self.assertIn('not the M1.8 landing count',summary['landing_attempts_status'])
            report=(rec.path/'REPORT.md').read_text(encoding='utf-8')
            self.assertNotIn('; landing attempts: 0.',report)
            self.assertIn('legacy ecology landing attempts: 0',report)
            self.assertIn('authoritative for M1.8-A landing behavior',report)
            self.assertIn('touchdowns 1',report)
            # The authoritative summary must precede the superseded legacy counter.
            self.assertLess(report.index('authoritative for M1.8-A'),report.index('legacy ecology landing'))


if __name__=='__main__':unittest.main(verbosity=2)
