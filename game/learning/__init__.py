"""M2.0 learning infrastructure (research / infrastructure only).

Nothing in this package is used by the accepted runtime: the game still builds the frozen
`FixedEscapePolicy` (M1.8-N4B1C decoder, N4B5R geometry). A learned policy plugs in through
the existing `Policy` protocol (`reset`, `decide(MotorState)`), so world physics, flight,
lifecycle, walls and brain stepping are never bypassed.

Modules:
    contracts  observation contract (whitelist encoder) and maneuver-level action contract
    policies   policy adapter, non-learning controls, exploit probes
    model      small numpy MLP proposal (no training here)
    runmode    TRAIN / EVAL separation and the seed registry
    scenarios  scripted opponents and scenario setup (environment side; may read the world)
    reward     interpretable reward terms computed from privileged world state (never observed)
    metrics    episode metrics and anti-cheating diagnostics
    runner     episode runner, benchmark suite and run manifest
"""
