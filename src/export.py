"""Write the JSON the webpage replays.

The simulation is the single source of truth. Geometry and a representative run for each
scenario are exported as time-and-distance keypoints. The page interpolates between them to
move the cars, so the browser replays exactly what the model produced.
"""

from __future__ import annotations

import json

import numpy as np

from . import config
from .geometry import Corridor
from .monte_carlo import Ensemble, comparison_table
from .simulation import SimResult


def _normalize(xy: np.ndarray):
    """Scale the projected route into a tidy box while keeping its true proportions, so the
    dog-leg at the bottom looks like the real thing on screen."""
    mn = xy.min(axis=0)
    span = float((xy.max(axis=0) - mn).max())
    return (xy - mn) / span, mn, span


def _route(corridor: Corridor) -> dict:
    nxy, mn, span = _normalize(corridor.shape_xy)
    length = corridor.length_m
    stops = []
    for st in corridor.stops:
        stops.append({
            "name": st.name,
            "key": st.key,
            "s": round(st.s / length, 6),
            "x": round(float((st.x - mn[0]) / span), 5),
            "y": round(float((st.y - mn[1]) / span), 5),
            "signal": st.signal,
            "remove": st.remove,
            "control": st.key in config.CONTROL_POINTS,
        })
    return {
        "length_m": round(length, 1),
        "path": [[round(float(x), 5), round(float(y), 5)] for x, y in nxy],
        "path_s": [round(float(s / length), 6) for s in corridor.shape_s],
        "stops": stops,
    }


def _vehicles(res: SimResult, window_min: float) -> list[dict]:
    """Keypoints for every car that is somewhere on the line during the playback window.

    Each car becomes a list of [time, distance-fraction] points: an arrival and a departure
    at each stop it serves. The flat step between the two is the dwell; the climb to the next
    pair is the run. Times are relative to the start of the window and may be negative for a
    car that was already rolling when the window opened.
    """
    t0 = res.warmup_s
    t1 = t0 + window_min * 60.0
    length = res.stop_s[-1]
    out = []
    for v in range(len(res.dispatch)):
        if res.arr[v, 0] > t1 or res.arr[v, -1] < t0:
            continue
        keys = []
        for k in range(len(res.stops)):
            sfrac = round(float(res.stop_s[k] / length), 5)
            keys.append([round(float(res.arr[v, k] - t0), 1), sfrac])
            keys.append([round(float(res.dep[v, k] - t0), 1), sfrac])
        out.append({"keys": keys})
    return out


def _runs(results: list[SimResult], window_min: float) -> list[dict]:
    """A list of runs the page can cycle through, each a set of vehicle keypoint tracks."""
    return [{"vehicles": _vehicles(res, window_min)} for res in results]


def _metric_blob(ens: Ensemble) -> dict:
    s = ens.summary
    return {
        "run_median": round(s["run_median"]["mean"], 2),
        "run_p85": round(s["run_p85"]["mean"], 2),
        "speed_kmh": round(s["speed_kmh"]["mean"], 2),
        "headway_cv": round(s["headway_cv"]["mean"], 3),
        "bunching_rate": round(s["bunching_rate"]["mean"], 3),
    }


def _cdf_points(values: np.ndarray, n: int = 80) -> list[list[float]]:
    v = np.sort(values)
    q = np.linspace(0, 1, n)
    xs = np.quantile(v, q)
    return [[round(float(x), 2), round(float(p), 3)] for x, p in zip(xs, q)]


def export_all(corridor: Corridor, ensembles: dict[str, Ensemble],
               window_min: float = 45.0) -> dict:
    """Write route.json and sim.json into the site's assets folder."""
    config.WEBAPP_ASSETS.mkdir(parents=True, exist_ok=True)

    route = _route(corridor)
    today = ensembles["baseline"]
    proposed = ensembles["proposed"]

    sim = {
        "window_s": round(window_min * 60.0, 1),
        "target_headway_min": config.PARAMS_DEFAULT.target_headway_min,
        "n_reps": int(len(today.per_run)),    # Monte Carlo runs behind each scenario's numbers
        "scenarios": {
            "today": {"runs": _runs(today.runs, window_min), "metrics": _metric_blob(today)},
            "proposed": {"runs": _runs(proposed.runs, window_min), "metrics": _metric_blob(proposed)},
        },
        "summary": comparison_table(ensembles),
        "charts": {
            "travel_time": {k: _cdf_points(ensembles[k].run_times)
                            for k in ("baseline", "proposed") if k in ensembles},
            "headway": {k: _cdf_points(ensembles[k].headways)
                        for k in ("baseline", "proposed") if k in ensembles},
        },
    }

    (config.WEBAPP_ASSETS / "route.json").write_text(json.dumps(route))
    (config.WEBAPP_ASSETS / "sim.json").write_text(json.dumps(sim))

    return {"route_stops": len(route["stops"]),
            "today_runs": len(sim["scenarios"]["today"]["runs"]),
            "proposed_runs": len(sim["scenarios"]["proposed"]["runs"])}
