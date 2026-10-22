"""Offline edge diagnostics only; never a policy observation or steering input."""
import math


def edge_diagnostics(world, hit=False, miss=False):
    f, sw = world.fly, world.swatter
    center_wall = min(f.x-world.margin, world.width-world.margin-f.x,
                      f.y-world.margin, world.height-world.margin-f.y)
    horizontal_gap = min(f.x, world.width-f.x)-world.margin-world.fly_radius
    vertical_gap = min(f.y, world.height-f.y)-world.margin-world.fly_radius
    near = min(horizontal_gap, vertical_gap) <= world.body_length
    physical = world.physical_swatter
    inset = physical.padding if physical is not None else 0.0
    dx = max(inset-f.x, 0.0, f.x-(world.width-inset))
    dy = max(inset-f.y, 0.0, f.y-(world.height-inset))
    radius = world.paddle_radius+world.fly_radius
    overlap = radius-math.hypot(dx, dy)
    return {
        "fly_distance_to_nearest_wall": center_wall,
        "fly_body_clearance_to_wall": center_wall-world.fly_radius,
        "fly_near_wall": near,
        "fly_near_corner": horizontal_gap <= world.body_length and vertical_gap <= world.body_length,
        "swatter_reachable_overlap": overlap,
        "fly_geometrically_reachable": overlap >= 0.0,
        "swatter_current_overlap": radius-math.hypot(sw.x-f.x, sw.y-f.y),
        "swatter_head_outside_viewport": min(sw.x, world.width-sw.x, sw.y, world.height-sw.y) < world.paddle_radius,
        "hit_near_wall": bool(hit and near),
        "miss_near_wall": bool(miss and near),
    }
