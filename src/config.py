"""Constants and parameters for the 510 Spadina simulation.

Every number with a physical meaning lives here so calibration only touches one object.
Values are real operating characteristics (door times, speed, signals, demand) taken from
data, the transit operations literature, or adjusted during calibration.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path


# Paths are relative to the repo root so the code runs from any entry point.
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
GTFS_DIR = DATA_DIR / "Complete GTFS"
STOPS_TXT = GTFS_DIR / "stops.txt"
SHAPES_TXT = GTFS_DIR / "shapes.txt"
DELAY_CSV_2025 = DATA_DIR / "TTC Streetcar Delay Data since 2025.csv"
DELAY_XLSX_2024 = DATA_DIR / "ttc-streetcar-delay-data-2024.xlsx"
DELAY_CODES_CSV = DATA_DIR / "delay_data_Code Descriptions.csv"

# Assets at ROOT so GitHub Pages serves index.html directly.
FIGURE_DIR = ROOT / "notebooks" / "figures"
WEBAPP_ASSETS = ROOT / "assets"
SHAPE_ID = "shp-510-56"
SEED = 20260613


# Ordered stop list, north terminal first.
#
# Fields:
#   key      short machine name used everywhere downstream
#   name     human label for charts and the webapp
#   stop_id  real GTFS stop_id, ties geometry to the actual feed
#   signal   True if the stop is at a signalised intersection (eligible for TSP)
#   nearside True if the stop is on the near side of its signal (green can time out mid-dwell)
#   board    relative boarding weight
#   alight   relative alighting weight
#   remove   True if stop consolidation drops it
#
# stop_ids and order are read straight from stop_times.txt for a southbound shp-510-56 trip.
# The scheduled run time on that trip is 29 minutes — the first calibration target.
STOPS: list[dict] = [
    dict(key="spadina_stn", name="Spadina Station", stop_id=3895,  signal=True,  nearside=False, board=1.00, alight=0.30, remove=False),
    dict(key="sussex",      name="Sussex Ave",      stop_id=10453, signal=False, nearside=False, board=0.18, alight=0.10, remove=True),
    dict(key="harbord",     name="Harbord St",      stop_id=8632,  signal=True,  nearside=True,  board=0.45, alight=0.35, remove=False),
    dict(key="willcocks",   name="Willcocks St",    stop_id=7409,  signal=False, nearside=False, board=0.16, alight=0.10, remove=True),
    dict(key="college",     name="College St",      stop_id=7039,  signal=True,  nearside=False, board=0.95, alight=0.85, remove=False),
    dict(key="nassau",      name="Nassau St",       stop_id=6892,  signal=False, nearside=False, board=0.14, alight=0.10, remove=True),
    dict(key="dundas",      name="Dundas St West",  stop_id=2444,  signal=True,  nearside=False, board=0.90, alight=0.80, remove=False),
    dict(key="sullivan",    name="Sullivan St",     stop_id=5928,  signal=False, nearside=False, board=0.15, alight=0.10, remove=True),
    dict(key="queen",       name="Queen St West",   stop_id=1634,  signal=True,  nearside=False, board=0.95, alight=0.90, remove=False),
    dict(key="king",        name="King St West",    stop_id=2485,  signal=True,  nearside=False, board=0.90, alight=0.95, remove=False),
    dict(key="front",       name="Front St West",   stop_id=10277, signal=True,  nearside=True,  board=0.50, alight=0.60, remove=False),
    dict(key="bremner",     name="Bremner Blvd",    stop_id=9990,  signal=True,  nearside=False, board=0.20, alight=0.20, remove=True),
    dict(key="queens_quay", name="Queens Quay Blvd", stop_id=5956,  signal=True,  nearside=False, board=0.35, alight=0.40, remove=False),
    dict(key="rees",        name="Rees St",         stop_id=4157,  signal=False, nearside=False, board=0.25, alight=0.30, remove=False),
    dict(key="harbourfront",name="Harbourfront Centre", stop_id=4158, signal=True, nearside=False, board=0.30, alight=0.35, remove=False),
    dict(key="ferry_docks", name="Queens Quay Station", stop_id=5443,  signal=False, nearside=False, board=0.25, alight=0.35, remove=False),
    dict(key="union",       name="Union Station",   stop_id=1656,  signal=True,  nearside=False, board=0.30, alight=1.00, remove=False),
]

# The two big transfer intersections in the middle of the line; a held car still does useful
# spacing work here without stranding anyone for long.
CONTROL_POINTS = ("college", "king")


@dataclass
class Params:
    """Every operating parameter the simulation reads, with sensible starting values.

    calibrate.py produces a tuned copy; defaults are physically honest so the baseline
    is in the right ballpark even before calibration.
    """

    door_cycle_s: float = 6.0          # fixed overhead to open, hold, and close doors
    board_time_s: float = 0.55         # seconds added per boarding passenger
    alight_time_s: float = 0.35        # seconds added per alighting passenger
    crowd_dwell_factor: float = 0.6    # extra dwell as the car approaches crush load

    # Speed profile: accelerate, maybe reach cruise, brake. On short downtown links the car
    # rarely reaches cruise speed -- the core reason closely spaced stops are costly.
    # cruise_speed_kmh is the top operating speed, not the average achieved on a short block.
    cruise_speed_kmh: float = 42.0     # top operating speed in the right of way
    accel_mps2: float = 0.9            # acceleration of a loaded Flexity car
    decel_mps2: float = 1.2            # service braking
    link_noise_cv: float = 0.20        # lognormal spread on link running time (traffic, drivers)

    # Near-side stops lose the green while the car is still dwelling hence the extra penalty.
    signal_cycle_s: float = 90.0       # representative signal cycle length
    signal_stop_prob: float = 0.70     # chance an unaided car meets a red on this badly coordinated corridor
    nearside_penalty_s: float = 14.0   # extra wait when a near-side green times out

    capacity: int = 250                # Flexity Outlook seated plus standing
    min_following_s: float = 25.0      # a car cannot sit right on top of the one ahead

    # Representative weekday PM peak hour ~35k riders/day
    peak_boardings_per_hour: float = 3200.0

    target_headway_min: float = 5.0    # scheduled peak frequency
    sim_period_min: float = 180.0      # length of the simulated peak window
    warmup_min: float = 25.0           # discard the fill-up period before measuring
    dt_s: float = 1.0                  # simulation time step

    # Terminal departure jitter is the seed that bunching amplifies.
    dispatch_jitter_s: float = 35.0

    # Headway-based control
    holding_cap_s: float = 60.0        # most a car may be held at a control point
    holding_deadband_s: float = 25.0   # only hold when the gap is meaningfully short
    headway_dispatch_jitter_s: float = 8.0   # terminals hit a target gap far more tightly

    # Conditional TSP (used only when the TSP intervention is on): withheld when bunched or
    # early, aggressive when lagging. 
    tsp_stop_prob_helped: float = 0.18     # red-meeting chance once a lagging car gets priority
    tsp_nearside_fix: float = 0.85         # share of the near-side penalty removed by motion-triggered calls
    tsp_bunched_ratio: float = 0.75        # below this share of target headway a car is "bunched", priority withheld
    tsp_lagging_ratio: float = 1.25        # above this share a car is "lagging" and gets aggressive priority

    def with_overrides(self, **kw) -> "Params":
        """Return a tuned copy. calibrate.py and the sensitivity sweep lean on this."""
        return replace(self, **kw)


PARAMS_DEFAULT = Params()


SCENARIOS: dict[str, dict] = {
    "baseline":      dict(label="Today",                 consolidate=False, tsp=False, headway=False),
    "consolidation": dict(label="+ Stop consolidation",  consolidate=True,  tsp=False, headway=False),
    "tsp":           dict(label="+ Conditional priority", consolidate=True, tsp=True,  headway=False),
    "proposed":      dict(label="Proposed (all three)",  consolidate=True,  tsp=True,  headway=True),
}


PALETTE = dict(
    paper="#faf8f3",
    ink="#1a1a1a",
    muted="#8a8377",
    rule="#d9d2c5",
    baseline="#b03a2e",   
    proposed="#2c6e63",   
    accent="#c98a1a",
    grid="#e7e1d6",
)
