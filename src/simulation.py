"""Streetcar simulation where bunching emerges from the mechanics rather than being prescribed.

Nothing here decides whether the line gets faster or more reliable. The corridor mechanics
are modelled, and travel times and bunching fall out of those mechanics.

Key structural fact: streetcars share a single track and cannot pass, so dispatch order is
arrival order at every stop. Vehicles are processed one at a time: when a car reaches a
stop, the leader has already left, and the leader's departure time is the available gap.
That gap times the boarding rate gives waiting riders, which sets the dwell, which amplifies
a small delay into a bunch.

Interventions reach this code only as the three flags on Scenario: consolidation,
conditional TSP, and headway holding.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config, demand
from .geometry import Corridor, Stop


@dataclass(frozen=True)
class Scenario:
    """A named on/off combination of the three operating changes."""
    key: str
    label: str
    consolidate: bool
    tsp: bool
    headway: bool

    @classmethod
    def from_name(cls, name: str) -> "Scenario":
        s = config.SCENARIOS[name]
        return cls(key=name, label=s["label"], consolidate=s["consolidate"],
                   tsp=s["tsp"], headway=s["headway"])


@dataclass
class SimResult:
    """Everything one run produces. metrics.py reads it; export.py animates it."""
    scenario: Scenario
    stops: list[Stop]            # the stops actually served in this run
    stop_s: np.ndarray          # their distance along the route, metres
    dispatch: np.ndarray        # (V,) terminal departure time of each car, seconds
    arr: np.ndarray             # (V, K) arrival time at each stop, seconds
    dep: np.ndarray             # (V, K) departure time from each stop, seconds
    load_max: np.ndarray        # (V,) peak on-board load of each car
    detector: int               # stop index used to measure headways (mid route)
    warmup_s: float
    period_s: float

    def _settled(self) -> np.ndarray:
        """Cars dispatched after warm-up and before the end of the window; excludes the
        half-empty fill-up fleet at the start."""
        return (self.dispatch >= self.warmup_s) & (self.dispatch <= self.period_s)

    def run_times_min(self) -> np.ndarray:
        """In-service travel time, leaving Spadina Station to reaching Union, in minutes."""
        m = self._settled()
        return (self.arr[m, -1] - self.dep[m, 0]) / 60.0

    def headways_min(self) -> np.ndarray:
        """Spacing between cars as they pass the mid-route detector, in minutes."""
        passes = np.sort(self.arr[self._settled(), self.detector])
        return np.diff(passes) / 60.0


def _link_time(distance: float, vmax: float, accel: float, decel: float) -> float:
    """Time to drive one link, accelerating from rest and braking to rest.

    On a long enough link the car reaches its top speed and holds it (a trapezoidal speed
    profile). On a short downtown block it runs out of room first and brakes before ever
    reaching top speed (a triangular profile), so its average speed is far lower. This is
    exactly why a string of 140 metre stops is so slow, and why widening the spacing buys
    real time rather than just saving a dwell.
    """
    if distance <= 0:
        return 0.0
    d_acc = vmax * vmax / (2.0 * accel)
    d_dec = vmax * vmax / (2.0 * decel)
    if d_acc + d_dec <= distance:
        cruise_dist = distance - d_acc - d_dec
        return vmax / accel + vmax / decel + cruise_dist / vmax
    peak = (2.0 * distance * accel * decel / (accel + decel)) ** 0.5
    return peak / accel + peak / decel


def _signal_delay(params: config.Params, stop: Stop, tsp: bool, state: str,
                  rng: np.random.Generator) -> float:
    """Delay a car picks up at a signalised stop.

    Without priority a car meets a red some of the time and waits part of the cycle, and a
    near-side stop adds the wasted-green penalty. Conditional priority changes the odds, but
    only in the right direction: a car that has fallen behind is waved through, a car that is
    bunched up against its leader is given nothing so the signals stop helping it close the
    gap.
    """
    if not stop.signal:
        return 0.0

    stop_prob = params.signal_stop_prob
    nearside_factor = 1.0
    if tsp:
        if state == "lagging":
            stop_prob = params.tsp_stop_prob_helped
            nearside_factor = 1.0 - params.tsp_nearside_fix
        elif state == "normal":
            stop_prob = 0.5 * (params.signal_stop_prob + params.tsp_stop_prob_helped)
            nearside_factor = 1.0 - 0.5 * params.tsp_nearside_fix
        # a bunched or leading car keeps the unaided odds, priority withheld

    delay = 0.0
    if rng.random() < stop_prob:
        delay += rng.uniform(0.0, params.signal_cycle_s * 0.5)
    if stop.nearside:
        delay += params.nearside_penalty_s * nearside_factor
    return delay


def _headway_state(ratio: float, params: config.Params) -> str:
    """Label a car by how its forward gap compares with the target headway."""
    if ratio < params.tsp_bunched_ratio:
        return "bunched"
    if ratio > params.tsp_lagging_ratio:
        return "lagging"
    return "normal"


def _dispatch_times(params: config.Params, scenario: Scenario,
                    rng: np.random.Generator) -> np.ndarray:
    """When each car leaves the north terminal.

    Schedule-based terminals aim for the clock and miss it by a fair margin, and nothing
    downstream corrects the result. Headway-based dispatching meters cars out to an even gap,
    which is the first half of the headway intervention; the holding at control points is the
    second half and lives in the main loop.
    """
    target = params.target_headway_min * 60.0
    jitter = params.headway_dispatch_jitter_s if scenario.headway else params.dispatch_jitter_s
    n = int(params.sim_period_min * 60.0 / target) + 2
    times = np.arange(n) * target + rng.normal(0.0, jitter, size=n)
    return np.sort(np.clip(times, 0.0, None))


def simulate(corridor: Corridor, params: config.Params, scenario: Scenario,
             rng: np.random.Generator) -> SimResult:
    """Run the corridor once and hand back the full space-time picture."""
    dem = demand.build(corridor, params, scenario.consolidate)
    stops = dem.stops
    K = len(stops)
    s = np.array([st.s for st in stops])
    link_dist = np.diff(s, prepend=s[0])      # link_dist[0] is 0 at the terminal
    board_per_s = dem.board_rate / 60.0
    vmax = params.cruise_speed_kmh / 3.6
    target = params.target_headway_min * 60.0

    # Clean (noise-free) driving time per link from the speed profile, computed once since
    # values only depend on the stopping pattern, then jittered per car.
    base_link = np.array([_link_time(d, vmax, params.accel_mps2, params.decel_mps2)
                          for d in link_dist])

    dispatch = _dispatch_times(params, scenario, rng)
    V = len(dispatch)

    arr = np.zeros((V, K))
    dep = np.zeros((V, K))
    load_max = np.zeros(V)

    # State carried from the car ahead to the next car.
    prev_dep = np.full(K, np.nan)        # when the leader left each stop
    carryover = np.zeros(K)              # riders the leader could not fit, left waiting

    control_keys = set(config.CONTROL_POINTS)

    for v in range(V):
        onboard = 0.0
        dest = np.zeros(K)               # on-board riders by destination stop
        t = dispatch[v]

        for k in range(K):
            stop = stops[k]

            # Running time on the link into this stop. The first "link" is the terminal
            # itself, which costs nothing to reach.
            if k > 0:
                noise = rng.lognormal(mean=0.0, sigma=params.link_noise_cv)
                t = dep[v, k - 1] + base_link[k] * noise

            # No overtaking: a car cannot arrive before the leader has cleared this stop.
            leader_dep = prev_dep[k]
            if not np.isnan(leader_dep):
                t = max(t, leader_dep + params.min_following_s)

            arr[v, k] = t

            # Forward gap to the leader, the spacing this car is working with.
            gap = target if np.isnan(leader_dep) else (t - leader_dep)
            ratio = gap / target
            state = _headway_state(ratio, params)

            # Alight first, then board whoever has piled up in the gap.
            alighting = dest[k]
            onboard -= alighting
            dest[k] = 0.0

            waiting = board_per_s[k] * gap + carryover[k]
            space = max(params.capacity - onboard, 0.0)
            boarding = min(waiting, space)
            carryover[k] = waiting - boarding
            dest += boarding * dem.dest_split[k]
            onboard += boarding
            load_max[v] = max(load_max[v], onboard)

            # Dwell: the door cycle every time, plus the per-rider service, stretched a
            # little when the car is crowded.
            dwell = params.door_cycle_s + params.board_time_s * boarding + params.alight_time_s * alighting
            dwell *= 1.0 + params.crowd_dwell_factor * (onboard / params.capacity)

            # Signals.
            dwell += _signal_delay(params, stop, scenario.tsp, state, rng)

            # Headway holding: at a control point an early car is held just enough to restore
            # the target gap, capped at holding_cap_s. The deadband avoids correcting trivial
            # deviations, keeping the speed cost small while still catching real bunching.
            if scenario.headway and stop.key in control_keys and not np.isnan(leader_dep):
                hold = np.clip((target - gap) - params.holding_deadband_s, 0.0, params.holding_cap_s)
                dwell += hold

            dep[v, k] = arr[v, k] + dwell
            prev_dep[k] = dep[v, k]

    # Headway regularity measured at Front St, downstream of both holding control points
    # (College and King), so the detector sees the full effect of the intervention.
    detector = next((i for i, st in enumerate(stops) if st.key == "front"), K // 2)
    return SimResult(
        scenario=scenario, stops=stops, stop_s=s, dispatch=dispatch, arr=arr, dep=dep,
        load_max=load_max, detector=detector,
        warmup_s=params.warmup_min * 60.0, period_s=params.sim_period_min * 60.0,
    )
