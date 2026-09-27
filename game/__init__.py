"""Interactive fly-swatter game driven by the MaleCNS connectome.

Layered so the perceptual bottleneck is structural rather than a convention:

    world.py       mouse + physics + collision       (may see the mouse)
    perception.py  world -> frozen Retina -> LC4/LPLC2 drive
    fly.py         FlyLoop: connectome + DN trace     (sees only a Retina)
    action.py      MotorState -> Action               (swap-in point for M2)
    session.py     fixed-timestep engine, headless
    app.py         pygame front end

Play with:  python -m game.app
"""
from .action import Action, FixedEscapePolicy, MotorState, Policy
from .fly import FlyLoop, build_brain
from .perception import Retina, RetinaProjector, RetinalEncoder
from .session import Session, build_policy, load_config, resolve_escape_threshold
from .world import Fly, Stats, StrikePhase, Swatter, TickEvents, World

__all__ = ["Action", "FixedEscapePolicy", "MotorState", "Policy",
           "FlyLoop", "build_brain", "Retina", "RetinaProjector", "RetinalEncoder",
           "Session", "build_policy", "load_config", "resolve_escape_threshold",
           "Fly", "Stats", "StrikePhase", "Swatter", "TickEvents", "World"]
