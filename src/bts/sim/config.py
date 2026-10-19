"""Tunable parameters of the match simulator.

Defaults are calibrated by ``scripts/realism_check.py`` so that means over 200 matches fall
inside the target ranges documented in ``bts.sim.realism``.
"""

from dataclasses import dataclass, field


@dataclass
class SimConfig:
    period_seconds: float = 2700.0
    stoppage_mean: float = 120.0
    stoppage_sd: float = 30.0

    base_pass_success: float = 0.87
    pass_attr_effect: float = 0.12
    pass_difficulty_effect: float = 0.18

    shot_rate_final_third: float = 0.042
    long_shot_rate: float = 0.02
    pressure_rate: float = 0.06
    foul_rate: float = 0.015
    carry_dispossess_rate: float = 0.06
    miscontrol_rate: float = 0.01

    momentum_drift: float = 0.05
    momentum_goal_jump: float = 0.35
    momentum_chance_jump: float = 0.15
    momentum_effect: float = 0.08
    momentum_decay: float = 0.97

    xg_by_zone: dict[str, float] = field(
        default_factory=lambda: {
            "box_central": 0.18,
            "box_wide": 0.07,
            "edge": 0.045,
            "long": 0.02,
        }
    )
