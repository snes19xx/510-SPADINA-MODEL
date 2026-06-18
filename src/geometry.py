"""Turn the raw TTC feed into a measured corridor.

Stop coordinates from stops.txt and the route polyline from shapes.txt are projected into
metres; each stop is then snapped onto the line. This recovers true stop spacing (including
the short downtown gaps that consolidation targets) and the real route shape the webapp draws.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pyproj import Transformer

from . import config


# UTM zone 17N: all distances in metres, not degrees.
_TO_METRES = Transformer.from_crs("EPSG:4326", "EPSG:32617", always_xy=True)


@dataclass
class Stop:
    key: str
    name: str
    stop_id: int
    lat: float
    lon: float
    x: float          # easting in metres
    y: float          # northing in metres
    s: float          # distance along the route from the north terminal, in metres
    signal: bool
    nearside: bool
    board: float
    alight: float
    remove: bool

    @property
    def short(self) -> str:
        return self.name.split(" ")[0]


@dataclass
class Corridor:
    """The 510 as the model sees it: an ordered chain of stops on a measured line."""

    stops: list[Stop]
    shape_lonlat: np.ndarray   # (N, 2) raw longitude/latitude of the route
    shape_xy: np.ndarray       # (N, 2) projected metres
    shape_s: np.ndarray        # (N,) cumulative distance along the route in metres

    @property
    def length_m(self) -> float:
        return float(self.shape_s[-1])

    def active_stops(self, consolidate: bool) -> list[Stop]:
        """The stops a car actually serves. Consolidation drops the flagged minor stops."""
        if not consolidate:
            return list(self.stops)
        return [s for s in self.stops if not s.remove]

    def nearest_active(self, stop: Stop, consolidate: bool) -> Stop:
        """Where a dropped stop's riders walk to: the closest stop still in service."""
        actives = self.active_stops(consolidate)
        return min(actives, key=lambda a: abs(a.s - stop.s))


def _load_shape() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Read the chosen 510 polyline and return its lon/lat, projected metres, and the
    running distance along it."""
    cols = ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"]
    shapes = pd.read_csv(config.SHAPES_TXT, usecols=cols)
    line = shapes[shapes["shape_id"] == config.SHAPE_ID].sort_values("shape_pt_sequence")
    if line.empty:
        raise ValueError(f"shape {config.SHAPE_ID} not found in {config.SHAPES_TXT}")

    lonlat = line[["shape_pt_lon", "shape_pt_lat"]].to_numpy(dtype=float)
    x, y = _TO_METRES.transform(lonlat[:, 0], lonlat[:, 1])
    xy = np.column_stack([x, y])

    # Cumulative straight-line distance between consecutive shape points.
    seg = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    return lonlat, xy, s


def _snap_to_line(px: float, py: float, xy: np.ndarray, s: np.ndarray) -> float:
    """Project a point onto the polyline and return its along-track distance.

    For every segment, finds the closest point (clamped to segment ends), keeps the nearest
    segment, and returns the running distance to that segment's start plus the perpendicular
    foot offset.
    """
    a = xy[:-1]
    b = xy[1:]
    ab = b - a
    ab_len2 = np.einsum("ij,ij->i", ab, ab)
    ab_len2 = np.where(ab_len2 == 0.0, 1e-9, ab_len2)

    ap = np.array([px, py]) - a
    t = np.clip(np.einsum("ij,ij->i", ap, ab) / ab_len2, 0.0, 1.0)
    foot = a + t[:, None] * ab
    d = np.linalg.norm(foot - np.array([px, py]), axis=1)

    i = int(np.argmin(d))
    return float(s[i] + t[i] * np.linalg.norm(ab[i]))


def load_corridor() -> Corridor:
    """Build the corridor once: real stops, snapped onto the real line, ordered north to
    south with true along-track distances."""
    lonlat, xy, s = _load_shape()

    stops_df = pd.read_csv(config.STOPS_TXT, usecols=["stop_id", "stop_name", "stop_lat", "stop_lon"])
    by_id = stops_df.set_index("stop_id")

    stops: list[Stop] = []
    for meta in config.STOPS:
        row = by_id.loc[meta["stop_id"]]
        lon, lat = float(row["stop_lon"]), float(row["stop_lat"])
        px, py = _TO_METRES.transform(lon, lat)
        along = _snap_to_line(px, py, xy, s)
        stops.append(
            Stop(
                key=meta["key"],
                name=meta["name"],
                stop_id=meta["stop_id"],
                lat=lat,
                lon=lon,
                x=float(px),
                y=float(py),
                s=along,
                signal=meta["signal"],
                nearside=meta["nearside"],
                board=meta["board"],
                alight=meta["alight"],
                remove=meta["remove"],
            )
        )

    # Sort by snapped distance as a guard: a mislabelled stop can't silently scramble the chain.
    stops.sort(key=lambda st: st.s)
    return Corridor(stops=stops, shape_lonlat=lonlat, shape_xy=xy, shape_s=s)


def stop_spacing(corridor: Corridor, consolidate: bool) -> np.ndarray:
    """Gaps between consecutive served stops, in metres. Handy for showing how
    consolidation widens the average spacing."""
    actives = corridor.active_stops(consolidate)
    s = np.array([st.s for st in actives])
    return np.diff(s)
