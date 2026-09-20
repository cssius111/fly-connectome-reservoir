"""Edge-reachability regression: physics may extend beyond the viewport."""
import copy
import json
import math
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from game.session import load_config, Session
from game.world import World, StrikePhase
from game.edge_analysis import edge_diagnostics
from game.session_recording import HumanSessionRecorder
from test_game import shared_brain

ROOT=Path(__file__).parent
ROOM=load_config(ROOT/"game_room_config.json")


def held_fly(x,y):
    w=World(ROOM,101)
    w.fly_motion_enabled=False  # Geometry fixture only; gameplay remains unchanged.
    w.fly.x=x;w.fly.y=y;w.fly.vx=w.fly.vy=0
    return w


class TestEdgeReachability(unittest.TestCase):
    def assert_reachable_strike(self,x,y):
        w=held_fly(x,y)
        for _ in range(300):
            w.set_pointer(x,y);w.tick(.02)
        self.assertLess(math.dist((w.swatter.x,w.swatter.y),(x,y)),.01)
        self.assertTrue(w.request_strike())
        hit=False
        for _ in range(40):
            before=(w.swatter.vx,w.swatter.vy)
            events=w.tick(.02)
            self.assertLessEqual(math.dist(before,(w.swatter.vx,w.swatter.vy))/.02,18000+1e-7)
            self.assertLessEqual(math.hypot(w.swatter.vx,w.swatter.vy),3200+1e-7)
            if events.hit:
                hit=True
                self.assertTrue(edge_diagnostics(w,hit=True)['swatter_head_outside_viewport'])
                self.assertTrue(edge_diagnostics(w,hit=True)['hit_near_wall'])
        self.assertTrue(hit)
        self.assertEqual(w.stats.hits,1)

    def test_left_edge(self):self.assert_reachable_strike(59,1080)
    def test_right_edge(self):self.assert_reachable_strike(3781,1080)
    def test_top_edge(self):self.assert_reachable_strike(1920,59)
    def test_bottom_edge(self):self.assert_reachable_strike(1920,2101)
    def test_top_left_corner(self):self.assert_reachable_strike(59,59)
    def test_top_right_corner(self):self.assert_reachable_strike(3781,59)
    def test_bottom_left_corner(self):self.assert_reachable_strike(59,2101)
    def test_bottom_right_corner(self):self.assert_reachable_strike(3781,2101)

    def test_human_recorded_position_was_unreachable_and_is_now_hittable(self):
        fixture=json.loads((ROOT/'results/game/edge_regression_m1_7.json').read_text())
        f=fixture['example']['fly'];x,y=f['x'],f['y']
        self.assertGreater(math.hypot(max(240-x,0,x-3600),max(240-y,0,y-1920)),155)
        self.assert_reachable_strike(x,y)

    def fast_world(self,near_miss=False):
        # A short grazing chord: both 20-ms endpoints miss, the swept interval hits.
        w=held_fly(62,59);w.request_strike();sw=w.swatter
        sw.x=30;sw.y=214.1 if near_miss else 213.9
        sw.vx=3200;sw.vy=0;sw.attack_orientation=0;sw.swing_speed=3200
        sw.phase=StrikePhase.ACTIVE_CONTACT;sw.phase_elapsed=0
        w.stats.strikes=1
        return w

    def test_fast_partial_offscreen_sweep_hits_despite_both_endpoints_missing(self):
        w=self.fast_world();f=(w.fly.x,w.fly.y)
        self.assertGreater(math.dist((w.swatter.x,w.swatter.y),f),155)
        self.assertTrue(w.tick(.02).hit)
        self.assertGreater(math.dist((w.swatter.x,w.swatter.y),f),155)
        self.assertTrue(edge_diagnostics(w)['swatter_head_outside_viewport'])

    def test_edge_near_miss_stays_a_miss(self):
        w=self.fast_world(near_miss=True)
        for _ in range(6):self.assertFalse(w.tick(.02).hit)
        self.assertEqual(w.stats.misses,1)
        self.assertTrue(edge_diagnostics(w,miss=True)['miss_near_wall'])

    def test_render_clipping_and_render_count_do_not_change_collision(self):
        from game.app import App,pygame
        pygame.font.init()
        outcomes=[]
        for draws,clip in [(0,None),(1,(0,0,1280,720)),(7,(1000,600,10,10))]:
            w=self.fast_world()
            app=object.__new__(App);app.session=SimpleNamespace(world=w)
            app.render_scale=1/3;app.font_small=pygame.font.Font(None,18)
            surface=pygame.Surface((1280,720));surface.set_clip(clip)
            for _ in range(draws):app._draw_swatter(surface,(w.swatter.x/3,w.swatter.y/3),8,.9)
            outcomes.append((w.tick(.02).hit,w.swatter.x,w.swatter.y))
        self.assertEqual(outcomes,[outcomes[0]]*3)
        self.assertTrue(outcomes[0][0])

    def test_pointer_conversion_preserves_all_viewport_edges_with_letterbox(self):
        from game.app import App,pygame
        app=object.__new__(App);app.world_w=3840;app.world_h=2160
        for size in ((1280,720),(2560,1440),(1280,1000)):
            app.screen=pygame.Surface(size);scale,ox,oy=app._letterbox()
            for x,y in ((0,0),(3840,0),(0,2160),(3840,2160)):
                actual=app._screen_to_world((ox+x*scale,oy+y*scale))
                self.assertAlmostEqual(actual[0],x);self.assertAlmostEqual(actual[1],y)

    def test_geometry_covers_entire_fly_rectangle_without_changing_it(self):
        w=held_fly(59,59)
        for x in (59,85,130.4,1920,3700,3781):
            for y in (59,85,130.4,1080,2030,2101):
                w.fly.x=x;w.fly.y=y
                self.assertTrue(edge_diagnostics(w)['fly_geometrically_reachable'])
        w.fly.x=-100;w.fly.y=-100;w.enclosure.contain(w.fly)
        self.assertEqual((w.fly.x,w.fly.y),(59,59))
        w.fly.x=4000;w.fly.y=2300;w.enclosure.contain(w.fly)
        self.assertEqual((w.fly.x,w.fly.y),(3781,2101))

    def test_recorded_edge_diagnostics_do_not_enter_policy_observation(self):
        with tempfile.TemporaryDirectory() as d:
            rec=HumanSessionRecorder(d,archive_source=False)
            s=Session(ROOM,brain=shared_brain(),seed=101,recorder=rec)
            s.tick(pointer=(0,0));s.close()
            row=json.loads((rec.path/'ticks.jsonl').read_text())
            edge=row['edge_analysis']
            self.assertTrue({'fly_distance_to_nearest_wall','fly_near_corner','swatter_reachable_overlap','hit_near_wall','miss_near_wall'}<=set(edge))
            observation=json.loads((rec.path/'policy_observations.jsonl').read_text())['observation']
            self.assertEqual(set(observation),{'neural','motion','behavior_state','history'})
            for key in edge:self.assertNotIn(key,json.dumps(observation))
            self.assertEqual(json.loads((rec.path/'manifest.json').read_text())['recording_schema_version'],2)


if __name__=='__main__':unittest.main()
