"""M1.4 local enclosure, bounded pulses and event-based exploration regressions."""
import copy
from dataclasses import fields
import math
import unittest
from unittest.mock import patch

import numpy as np
from game.enclosure import Enclosure, Opening, WallCue
from game.flight import FreeFlightController
from game.saccade import SaccadeActuator
from game.world import World, Fly
from test_game import CONFIG

DT = CONFIG['sim']['tick_seconds']


class TestPulseBounds(unittest.TestCase):
    def test_integral_and_peak_bounds_across_directions_and_tick_sizes(self):
        for degrees in (-120, -25, 5, 55, 110, 120):
            for dt in (.003, .02, .027):
                a = SaccadeActuator(CONFIG['saccades'])
                requested = math.radians(degrees)
                peak = math.radians(1400)
                a.request('SACCADE', requested, peak)
                self.assertLessEqual(abs(a.angle) * math.pi / (2*a.duration), peak + 1e-10)
                increments = []
                while a.active:
                    increments.append(a.step(dt))
                self.assertAlmostEqual(sum(increments), requested, places=12)
                self.assertLessEqual(max(map(abs, increments))/dt, peak + 1e-10)

    def test_duration_scales_with_angle_and_minimum_is_respected(self):
        a = SaccadeActuator(CONFIG['saccades'])
        self.assertEqual(a.duration_for(.01, 20), a.min_duration)
        self.assertAlmostEqual(a.duration_for(2, 20), 2*a.duration_for(1, 20))

    def test_impossible_rate_duration_request_fails_without_mutation(self):
        a = SaccadeActuator(CONFIG['saccades'])
        a.request('CORRECTION', .1, 10)
        before = a.kind, a.angle, a.duration, a.elapsed
        with self.assertRaisesRegex(ValueError, 'cannot fit'):
            a.request('ESCAPE', 2, .01)
        self.assertEqual(before, (a.kind, a.angle, a.duration, a.elapsed))

    def test_cap_and_angle_limit_apply_even_to_extreme_request(self):
        a = SaccadeActuator(CONFIG['saccades'])
        a.request('ESCAPE', 100, 1e6)
        self.assertEqual(a.angle, math.radians(120))
        self.assertLessEqual(abs(a.angle)*math.pi/(2*a.duration), a.peak_rate_cap+1e-10)

    def test_invalid_rate_and_step_are_rejected(self):
        for v in (0, -1, float('nan'), float('inf')):
            a = SaccadeActuator(CONFIG['saccades'])
            with self.assertRaises(ValueError): a.request('SACCADE', .3, v)
            with self.assertRaises(ValueError): a.step(v)

    def test_lower_or_equal_priority_cannot_interrupt_or_flip_an_escape(self):
        a = SaccadeActuator(CONFIG['saccades'])
        a.request('ESCAPE', 1, 20)
        angle = 0
        while a.active:
            for kind in ('CORRECTION', 'SACCADE', 'DEPART', 'AVOID', 'ALERT', 'ESCAPE'):
                self.assertFalse(a.request(kind, -1, 20))
            angle += a.step(DT)
        self.assertAlmostEqual(angle, 1)


class TestWallPerception(unittest.TestCase):
    def enclosure(self, openings=()):
        return Enclosure(1280, 720, 26, 11, 150, openings)

    def test_interface_is_frozen_local_and_rejects_world_objects(self):
        self.assertEqual({f.name for f in fields(WallCue)},
                         {'expansion','contact_bearing','proximity','surface_bearing','open_ahead'})
        cue = WallCue()
        self.assertFalse(hasattr(cue, '__dict__'))
        with self.assertRaises((AttributeError, TypeError)): cue.exit_x = 20
        class Sneaky(WallCue):
            __slots__ = ()
        controller = FreeFlightController(CONFIG['flight'], 101)
        actuator = SaccadeActuator(CONFIG['saccades'])
        for value in (World(CONFIG, 101), {'x': 20}, Sneaky()):
            with self.assertRaises(TypeError): controller.update(DT, value, actuator)

    def test_nonfinite_or_out_of_range_cues_are_rejected(self):
        for kwargs in ({'proximity':1.01}, {'expansion':-1}, {'surface_bearing':4},
                       {'expansion':float('nan')}, {'open_ahead':1}):
            with self.assertRaises((TypeError, ValueError)): WallCue(**kwargs)

    def test_translation_equivalent_local_geometry_and_body_bearings(self):
        a = self.enclosure().sense(1200, 360, 160, 0, 0)
        b = Enclosure(1480, 920, 26, 11, 150).sense(1400, 460, 160, 0, 0)
        self.assertEqual(a, b)
        turned = self.enclosure().sense(1200,360,160,0,math.pi/2)
        self.assertAlmostEqual(turned.contact_bearing, -math.pi/2)
        self.assertEqual(a.expansion, turned.expansion)

    def test_distant_gap_is_not_visible_and_no_actual_opening_is_configured(self):
        e = self.enclosure((Opening('right',360,50),))
        self.assertEqual(e.sense(640,360,160,0,0), WallCue())
        self.assertTrue(e.sense(1200,360,160,0,0).open_ahead)
        self.assertEqual(World(CONFIG,101).enclosure.openings, ())

    def test_gap_projected_far_along_wall_is_not_disclosed(self):
        e = self.enclosure((Opening('right',530,40),))
        self.assertFalse(e.sense(1200,100,1,10,0).open_ahead)

    def test_seeded_wall_trajectory_replays_exactly(self):
        def run():
            w=World(CONFIG,101)
            w.fly.x,w.fly.y=1200,640
            rows=[]
            for _ in range(1000):
                w.tick(DT)
                rows.append(w.state_vector().copy())
            return rows
        np.testing.assert_array_equal(run(),run())

    def test_gap_cannot_mask_a_solid_adjacent_wall(self):
        e = self.enclosure((Opening('right',650,80),))
        cue = e.sense(1200,650,100,100,math.pi/4)
        self.assertGreater(cue.expansion,0)
        self.assertFalse(cue.open_ahead)

    def test_top_gap_uses_screen_top_and_requires_body_clearance(self):
        e = self.enclosure((Opening('top',640,30),))
        self.assertTrue(e.sense(640,60,0,-160,-math.pi/2).open_ahead)
        self.assertFalse(e.sense(665,60,0,-160,-math.pi/2).open_ahead)
        self.assertFalse(e.sense(640,660,0,160,math.pi/2).open_ahead)

    def test_containment_matches_sensor_radius_and_does_not_reverse_velocity(self):
        e = self.enclosure()
        f = Fly(1250,360,160,12)
        self.assertTrue(e.contain(f))
        self.assertEqual((f.x,f.vx,f.vy),(1243,0,12))
        self.assertEqual(e.sense(f.x,f.y,160,0,0).proximity,1)
        f.x, f.vx = 1250, -20
        e.contain(f)
        self.assertEqual(f.vx,-20)


class TestExploration(unittest.TestCase):
    def test_timing_mixture_contains_short_ordinary_and_long_gaps(self):
        c = FreeFlightController(CONFIG['flight'],101)
        values = np.array([c._interval(False) for _ in range(10000)])
        self.assertTrue(np.all((values>=.3)&(values<=6)))
        self.assertAlmostEqual(np.mean(values<=.7),.28,delta=.02)
        self.assertAlmostEqual(np.mean(values>=2.6),.18,delta=.02)
        self.assertGreater(values.std(),1)

    def test_busy_actuator_does_not_resample_or_consume_quiet_gap(self):
        c = FreeFlightController(CONFIG['flight'],101)
        a = SaccadeActuator(CONFIG['saccades'])
        a.request('ESCAPE',1,20)
        c.wait = 0
        state = copy.deepcopy(c.rng.bit_generator.state)
        for _ in range(10): c.update(DT,WallCue(),a)
        self.assertEqual(c.rng.bit_generator.state,state)
        self.assertEqual(c.wait,0)

    def test_inertial_approach_does_not_unwind_an_already_away_heading(self):
        c=FreeFlightController(CONFIG['flight'],101)
        a=SaccadeActuator(CONFIG['saccades'])
        cue=WallCue(expansion=10,contact_bearing=math.radians(130),proximity=.7,
                    surface_bearing=math.radians(130))
        c.update(DT,cue,a)
        self.assertEqual(a.kind,'NONE')

    def test_precontact_avoidance_turns_before_constraint(self):
        w = World(CONFIG,101)
        w.fly.x, w.fly.y = 1160,360
        w.fly.vx, w.fly.vy, w.fly.heading = 160,0,0
        kinds, contacts = set(),0
        for _ in range(200):
            w.tick(DT);kinds.add(w.saccades.kind);contacts+=w.wall_contact
        self.assertIn('AVOID',kinds)
        self.assertEqual(contacts,0)
        self.assertLess(w.fly.x,1160)

    def test_wall_and_corner_starts_return_to_open_space_without_teleport(self):
        starts = ((1200,360,0),(80,360,math.pi),(640,80,-math.pi/2),
                  (640,640,math.pi/2),(1200,640,math.pi/4),
                  (80,80,-3*math.pi/4),(80,640,3*math.pi/4),(1200,80,-math.pi/4))
        for seed,(x,y,h) in enumerate(starts,101):
            with self.subTest(seed=seed):
                w=World(CONFIG,seed);f=w.fly
                f.x,f.y,f.heading=x,y,h;f.vx,f.vy=160*math.cos(h),160*math.sin(h)
                reached_open=False;contacts=0
                for _ in range(750):
                    before=(f.x,f.y);w.tick(DT)
                    self.assertLessEqual(math.dist(before,(f.x,f.y)),160*DT+1e-8)
                    reached_open |= w.wall_cue.proximity <= .2
                    contacts+=w.wall_contact
                self.assertTrue(reached_open)
                self.assertLess(contacts,30)

    def test_outward_fly_at_contact_can_recover_after_velocity_clamp(self):
        w=World(CONFIG,101);f=w.fly
        f.x,f.y,f.heading,f.vx,f.vy=1243,360,0,160,0
        for _ in range(400): w.tick(DT)
        self.assertLess(f.x,1100)

    def test_local_controller_has_no_world_brain_or_swatter_reference(self):
        w=World(CONFIG,101)
        self.assertFalse(any(key in vars(w.flight) for key in
                             ('world','brain','swatter','exit','width','height')))

    def test_long_enclosure_runs_leave_walls_without_rapid_avoid_reversals(self):
        from tools.flight_sanity import trajectory
        for seed in (17,101,102,103,104):
            with self.subTest(seed=seed):
                summary,_,_=trajectory(CONFIG,seed)
                self.assertEqual(summary['rapid_opposite_avoid_pairs'],0)
                self.assertGreater(summary['returns_to_open_space'],5)
                self.assertLess(summary['longest_near_wall_seconds'],12)
                self.assertLess(summary['constraint_ticks'],15)

    def test_wall_contact_flag_is_not_sticky_after_death(self):
        w=World(CONFIG,101)
        w.wall_contact=True;w.fly.alive=False
        w.tick(DT)
        self.assertFalse(w.wall_contact)

    def test_calibration_reset_starts_with_zero_velocity(self):
        w=World(CONFIG,101);w.fly_motion_enabled=False;w.reset(102)
        self.assertEqual((w.fly.vx,w.fly.vy),(0,0))

    def test_body_scale_agrees_with_configured_speed(self):
        w=World(CONFIG,101)
        self.assertEqual(w.body_length,24)
        self.assertAlmostEqual(w.cruise_body_lengths_per_second,160/24)
        self.assertAlmostEqual(w.body_lengths_per_second,160/24)


if __name__ == '__main__':
    unittest.main(verbosity=2)
