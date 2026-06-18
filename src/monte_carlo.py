"""Run the simulation many times.

The simulation is stochastic (link times, signals, dispatch all carry noise), so any one run
is a single sample. Each scenario is run hundreds of times with different seeds; per-run
metrics are gathered and one representative run per scenario is kept for the animation.
Pooling runs yields smooth travel-time and headway distributions for the charts.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config, metrics
from .geometry import Corridor
from .simulation import Scenario, SimResult, simulate

# Runs kept for the webapp to cycle through; freak tails trimmed, spread across the outcome range.
_WEBAPP_SAMPLE = 24


@dataclass
class Ensemble:
    scenario: Scenario
    per_run: list[dict]            # trip_metrics for every replication
    summary: dict                  # mean and confidence interval per metric
    representative: SimResult      # one typical run, used for the Marey chart
    run_times: np.ndarray          # every settled trip time across all runs, minutes
    headways: np.ndarray           # every settled headway across all runs, minutes
    runs: list[SimResult]          # a varied sample of runs the webapp cycles through


def run_ensemble(corridor: Corridor, params: config.Params, scenario: Scenario,
                 n_reps: int = 400, base_seed: int = config.SEED) -> Ensemble:
    """Run one scenario n_reps times and summarise it."""
    results: list[SimResult] = []
    per_run: list[dict] = []
    run_times, headways = [], []

    for r in range(n_reps):
        res = simulate(corridor, params, scenario, np.random.default_rng(base_seed + r))
        results.append(res)
        per_run.append(metrics.trip_metrics(res, params))
        run_times.append(res.run_times_min())
        headways.append(res.headways_min())

    # The representative run is the one whose headway spread is closest to the typical run,
    # so the Marey chart shows a fair day rather than a freak one.
    cvs = np.array([m["headway_cv"] for m in per_run])
    rep = results[int(np.argmin(np.abs(cvs - np.median(cvs))))]

    # Spread of real runs ordered calm to clumpy, extreme tails trimmed; the page picks at random.
    order = np.argsort(cvs)
    trim = int(0.05 * n_reps)
    band = order[trim:n_reps - trim] if n_reps > 2 * trim + _WEBAPP_SAMPLE else order
    take = np.unique(np.linspace(0, len(band) - 1, min(_WEBAPP_SAMPLE, len(band))).round().astype(int))
    sample = [results[int(band[j])] for j in take]

    return Ensemble(
        scenario=scenario,
        per_run=per_run,
        summary=metrics.aggregate(per_run),
        representative=rep,
        run_times=np.concatenate(run_times),
        headways=np.concatenate(headways),
        runs=sample,
    )


def run_scenarios(corridor: Corridor, params: config.Params,
                  names: list[str] | None = None, n_reps: int = 400) -> dict[str, Ensemble]:
    """Run the full comparison set and return it keyed by scenario name."""
    names = names or list(config.SCENARIOS)
    return {name: run_ensemble(corridor, params, Scenario.from_name(name), n_reps=n_reps)
            for name in names}


def sensitivity(corridor: Corridor, params: config.Params, param_name: str,
                values, scenario: str = "baseline", n_reps: int = 120) -> list[dict]:
    """Sweep one parameter and observe the baseline response.

    Shows the model is not balanced on a knife edge: run time and headway spread move smoothly
    with demand, noise, or signal behaviour, as expected from an honest mechanism rather than
    a fitted curve.
    """
    sc = Scenario.from_name(scenario)
    rows = []
    for v in values:
        ens = run_ensemble(corridor, params.with_overrides(**{param_name: v}), sc, n_reps=n_reps)
        rows.append({
            "value": float(v),
            "run_median": ens.summary["run_median"]["mean"],
            "headway_cv": ens.summary["headway_cv"]["mean"],
        })
    return rows


def comparison_table(ensembles: dict[str, Ensemble]) -> list[dict]:
    """A tidy row per scenario for the notebook and the webapp, with improvements measured
    against the baseline."""
    base = ensembles["baseline"].summary
    rows = []
    for name, ens in ensembles.items():
        s = ens.summary
        rows.append({
            "scenario": name,
            "label": ens.scenario.label,
            "run_median": s["run_median"]["mean"],
            "run_median_lo": s["run_median"]["lo"],
            "run_median_hi": s["run_median"]["hi"],
            "run_p85": s["run_p85"]["mean"],
            "speed_kmh": s["speed_kmh"]["mean"],
            "headway_cv": s["headway_cv"]["mean"],
            "headway_cv_lo": s["headway_cv"]["lo"],
            "headway_cv_hi": s["headway_cv"]["hi"],
            "bunching_rate": s["bunching_rate"]["mean"],
            "run_change_pct": metrics.improvement(base, s, "run_median"),
            "cv_change_pct": metrics.improvement(base, s, "headway_cv"),
        })
    return rows
