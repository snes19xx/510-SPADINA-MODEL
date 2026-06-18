"""The three operating changes:

The mechanics of each change are in simulation.py, because the honest way to model an
intervention is to alter the mechanism and let the outcome follow. What I keep here is the
human-readable side: what each change is, which stops and intersections it touches, and the
ordered list of scenarios I compare. The notebook and the webapp both read from this so the
prose, the charts, and the animation always describe the same thing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config
from .geometry import Corridor, stop_spacing
from .simulation import Scenario


@dataclass
class Intervention:
    key: str
    name: str
    summary: str


INTERVENTIONS = [
    Intervention(
        key="consolidation",
        name="Stop consolidation",
        summary="Drop five closely spaced minor stops so cars stop less often and can reach "
                "speed between stops. Riders at a dropped stop walk to the next one.",
    ),
    Intervention(
        key="tsp",
        name="Conditional transit signal priority",
        summary="Give a car green priority at signals, but only when it has fallen behind. A "
                "car that is bunched up against the one ahead gets nothing, so the signals "
                "help spacing instead of fighting it.",
    ),
    Intervention(
        key="headway",
        name="Headway-based control",
        summary="Meter cars out of the terminal to an even gap and hold an early car briefly "
                "at College or King to keep spacing even, rather than chasing a clock.",
    ),
]


def scenarios() -> list[Scenario]:
    """The comparison set, baseline first, each adding one change to the last."""
    return [Scenario.from_name(name) for name in config.SCENARIOS]


def removed_stops(corridor: Corridor) -> list:
    """The stops stop consolidation drops."""
    return [s for s in corridor.stops if s.remove]


def control_point_stops(corridor: Corridor) -> list:
    """The stops where headway holding is allowed."""
    return [s for s in corridor.stops if s.key in config.CONTROL_POINTS]


def tsp_intersections(corridor: Corridor, consolidate: bool = False) -> list:
    """The signalised stops conditional priority can act on."""
    return [s for s in corridor.active_stops(consolidate) if s.signal]


def spacing_summary(corridor: Corridor) -> dict:
    """How consolidation changes stop spacing, the lever behind the speed gain."""
    before = stop_spacing(corridor, consolidate=False)
    after = stop_spacing(corridor, consolidate=True)
    return {
        "n_before": len(corridor.active_stops(False)),
        "n_after": len(corridor.active_stops(True)),
        "mean_before_m": float(np.mean(before)),
        "mean_after_m": float(np.mean(after)),
        "min_before_m": float(np.min(before)),
        "removed": [s.name for s in removed_stops(corridor)],
    }
