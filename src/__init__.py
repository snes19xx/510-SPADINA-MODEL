"""The 510 Spadina model.

This package holds everything the notebook needs.

    config        the constants to tune
    data          loading and cleaning the real delay records and the GTFS schedule
    geometry      the measured corridor built from the GTFS feed
    demand        per-stop boarding and alighting rates
    simulation    the streetcar simulation where bunching emerges
    interventions the three operating changes, applied to the mechanism only
    calibrate     fitting the baseline to observed reality
    monte_carlo   running ensembles and summarising them
    metrics       the numbers I report
    viz           the figures
    export        the JSON the webapp replays
"""

from __future__ import annotations

from . import (
    calibrate,
    config,
    data,
    demand,
    export,
    geometry,
    interventions,
    metrics,
    monte_carlo,
    simulation,
    viz,
)
from .calibrate import calibrate as run_calibration
from .calibrate import load_or_calibrate
from .config import PALETTE, PARAMS_DEFAULT, SCENARIOS
from .export import export_all
from .geometry import Corridor, Stop, load_corridor, stop_spacing
from .interventions import INTERVENTIONS, scenarios, spacing_summary
from .monte_carlo import comparison_table, run_ensemble, run_scenarios, sensitivity
from .simulation import Scenario, simulate

__all__ = [
    # submodules
    "config", "data", "geometry", "demand", "simulation", "interventions",
    "calibrate", "monte_carlo", "metrics", "viz", "export",
    # constants
    "PALETTE", "PARAMS_DEFAULT", "SCENARIOS",
    # corridor
    "Corridor", "Stop", "load_corridor", "stop_spacing",
    # interventions
    "INTERVENTIONS", "scenarios", "spacing_summary",
    # simulation and analysis
    "Scenario", "simulate", "run_calibration", "load_or_calibrate",
    "run_ensemble", "run_scenarios", "comparison_table", "sensitivity",
    "export_all",
]
