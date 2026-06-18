"""The numbers I report from the simulations.
"""

from __future__ import annotations

import numpy as np

from . import config
from .simulation import SimResult


def trip_metrics(res: SimResult, params: config.Params) -> dict:
    """Everything I measure from one run of the corridor."""
    rt = res.run_times_min()
    hw = res.headways_min()
    target = params.target_headway_min

    cv = float(hw.std() / hw.mean())
    paired = float(np.mean(hw < 0.5 * target))           # cars arriving in a bunch (gap under half the target)
    on_even = float(np.mean(np.abs(hw - target) <= 0.5 * target))  # close to the planned gap
    length_km = res.stop_s[-1] / 1000.0

    return {
        "run_median": float(np.median(rt)),
        "run_mean": float(np.mean(rt)),
        "run_p85": float(np.percentile(rt, 85)),
        "headway_cv": cv,
        "bunching_rate": paired,
        "on_even_rate": on_even,
        "speed_kmh": float(length_km / (np.median(rt) / 60.0)),
    }


def mean_ci(values: np.ndarray, confidence: float = 0.95) -> tuple[float, float, float]:
    """Mean and a normal confidence interval. With hundreds of replications the normal
    approximation is more than good enough, and it keeps the story simple."""
    values = np.asarray(values, dtype=float)
    mean = float(values.mean())
    if len(values) < 2:
        return mean, mean, mean
    z = 1.959963984540054 if confidence == 0.95 else 1.6448536269514722
    half = z * float(values.std(ddof=1)) / np.sqrt(len(values))
    return mean, mean - half, mean + half


def aggregate(per_run: list[dict]) -> dict:
    """Collapse a list of per-run metric dicts into mean and CI per metric."""
    keys = per_run[0].keys()
    out = {}
    for k in keys:
        col = np.array([d[k] for d in per_run])
        mean, lo, hi = mean_ci(col)
        out[k] = {"mean": mean, "lo": lo, "hi": hi, "std": float(col.std(ddof=1)) if len(col) > 1 else 0.0}
    return out


def improvement(baseline: dict, scenario: dict, key: str) -> float:
    """Percent change of a metric against the baseline, signed so that a drop is negative."""
    b = baseline[key]["mean"]
    s = scenario[key]["mean"]
    return (s - b) / b * 100.0 if b else 0.0
