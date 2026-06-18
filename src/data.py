"""Load the real records used for calibration.

Two sources:
  1. TTC streetcar delay logs (2024 xlsx, 2025-2026 csv). Each row is a logged incident
     with a Min Delay and a Min Gap (spacing to the next car). The PM-peak Min Gap
     distribution is the direct evidence of bunching that the simulated headways must match.
  2. GTFS schedule. Provides the scheduled end-to-end run time and planned peak headway.

Both files use slightly different column names; _normalize brings them into one schema.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config

PEAK_HOURS = (16, 17, 18)

# stop_times_510.csv caches the 510 slice of the 364 MB stop_times.txt.
CACHE_DIR = config.ROOT / ".cache"


def gtfs_minutes(series: pd.Series) -> pd.Series:
    """Convert GTFS clock strings to minutes after midnight.

    GTFS allows times past midnight (e.g. 25:30:00), so hours are parsed manually
    rather than relying on a time type that would reject hour 25.
    """
    parts = series.astype(str).str.split(":", expand=True).astype(float)
    return parts[0] * 60.0 + parts[1] + parts[2] / 60.0


def load_delay_codes() -> pd.DataFrame:
    """The lookup that turns a terse delay code (SFDP, MFTO) into a readable cause."""
    codes = pd.read_csv(config.DELAY_CODES_CSV, encoding="latin-1")
    codes = codes.rename(columns={"CODE": "code", "DESCRIPTION": "description"})
    return codes[["code", "description"]]


def _normalize(df: pd.DataFrame, year_source: str) -> pd.DataFrame:
    """Bring either file into one schema and keep only the 510."""
    df = df.rename(
        columns={
            "Station": "location",
            "Location": "location",
            "Code": "code",
            "Incident": "incident",
            "Min Delay": "min_delay",
            "Min Gap": "min_gap",
            "Line": "line",
            "Date": "date",
            "Time": "time",
            "Day": "day",
            "Bound": "bound",
            "Vehicle": "vehicle",
        }
    )

    df["line"] = df["line"].astype(str).str.strip()
    df = df[df["line"].str.contains("510", na=False)].copy()

    # One timestamp per incident, from the date and the HH:MM clock.
    date_txt = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    time_txt = df["time"].astype(str).str.strip().str.slice(0, 5)
    df["datetime"] = pd.to_datetime(date_txt + " " + time_txt, errors="coerce")
    df["hour"] = df["datetime"].dt.hour
    df["is_peak"] = df["hour"].isin(PEAK_HOURS)

    df["min_delay"] = pd.to_numeric(df["min_delay"], errors="coerce")
    df["min_gap"] = pd.to_numeric(df["min_gap"], errors="coerce")
    df["source"] = year_source

    keep = ["datetime", "hour", "is_peak", "day", "location", "min_delay",
            "min_gap", "bound", "vehicle", "source"]
    for col in ("code", "incident"):
        if col in df.columns:
            keep.append(col)
    return df[keep]


def load_delay() -> pd.DataFrame:
    """Every 510 incident from both files, cleaned and stacked, newest schema wins."""
    csv = pd.read_csv(config.DELAY_CSV_2025, encoding="latin-1")
    frames = [_normalize(csv, "2025-2026")]

    if config.DELAY_XLSX_2024.exists():
        xlsx = pd.read_excel(config.DELAY_XLSX_2024, sheet_name="Data")
        frames.append(_normalize(xlsx, "2024"))

    delay = pd.concat(frames, ignore_index=True)
    delay = delay.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
    return delay


def peak_gap_distribution(delay: pd.DataFrame | None = None) -> np.ndarray:
    """Observed spacing to the following car during the PM peak, in minutes.

    Filtered to a sane band so a single multi-hour outage does not masquerade as a headway.
    """
    if delay is None:
        delay = load_delay()
    gaps = delay.loc[delay["is_peak"], "min_gap"].dropna()
    gaps = gaps[(gaps > 0.5) & (gaps < 40)]
    return gaps.to_numpy(dtype=float)


def delay_summary(delay: pd.DataFrame | None = None) -> dict:
    """Headline summary stats for today's operation."""
    if delay is None:
        delay = load_delay()
    gaps = peak_gap_distribution(delay)
    return {
        "n_incidents": int(len(delay)),
        "date_min": delay["datetime"].min(),
        "date_max": delay["datetime"].max(),
        "peak_gap_mean": float(np.mean(gaps)),
        "peak_gap_median": float(np.median(gaps)),
        "peak_gap_cv": float(np.std(gaps) / np.mean(gaps)),
        "peak_gap_p85": float(np.percentile(gaps, 85)),
        "peak_gap_max": float(np.max(gaps)),
        "mean_min_delay": float(delay["min_delay"].dropna().mean()),
    }


def _route_510_trips() -> pd.DataFrame:
    """Trip rows for route 510, with their shape and direction."""
    # Pin dtypes: pandas 3.0 trips on mixed types in this feed.
    trips = pd.read_csv(
        config.GTFS_DIR / "trips.txt",
        usecols=["trip_id", "route_id", "service_id", "direction_id", "shape_id", "trip_headsign"],
        dtype={"trip_id": "int64", "route_id": "str", "service_id": "str",
               "direction_id": "str", "shape_id": "str", "trip_headsign": "str"},
    )
    trips["route_id"] = trips["route_id"].str.strip()
    return trips[trips["route_id"] == "510"].copy()


def load_schedule_510(use_cache: bool = True) -> pd.DataFrame:
    """Scheduled stop times for every 510 trip, pulled from the full feed once.

    stop_times.txt is 364 MB; scanned in chunks, only 510 trips kept, result cached.
    """
    cache = CACHE_DIR / "stop_times_510.csv"
    id_cols = {"shape_id": "str", "service_id": "str", "direction_id": "str"}
    if use_cache and cache.exists():
        return pd.read_csv(cache, dtype=id_cols)

    trips = _route_510_trips()
    trip_ids = set(trips["trip_id"])

    wanted = ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]
    dtypes = {"trip_id": "int64", "arrival_time": "str", "departure_time": "str",
              "stop_id": "int64", "stop_sequence": "int64"}
    chunks = []
    for chunk in pd.read_csv(config.GTFS_DIR / "stop_times.txt", usecols=wanted,
                             dtype=dtypes, chunksize=500_000):
        chunks.append(chunk[chunk["trip_id"].isin(trip_ids)])
    sched = pd.concat(chunks, ignore_index=True)

    sched = sched.merge(trips[["trip_id", "shape_id", "direction_id", "service_id"]],
                        on="trip_id", how="left")
    sched["arr_min"] = gtfs_minutes(sched["arrival_time"])
    sched["dep_min"] = gtfs_minutes(sched["departure_time"])

    CACHE_DIR.mkdir(exist_ok=True)
    sched.to_csv(cache, index=False)
    return sched


def scheduled_run_times(shape_id: str = config.SHAPE_ID,
                        sched: pd.DataFrame | None = None) -> np.ndarray:
    """End to end scheduled run time per trip on the mainline shape, in minutes."""
    if sched is None:
        sched = load_schedule_510()
    line = sched[sched["shape_id"] == shape_id]
    span = line.groupby("trip_id")["arr_min"].agg(lambda v: v.max() - v.min())
    span = span[(span > 10) & (span < 60)]
    return span.to_numpy(dtype=float)


def scheduled_headways(shape_id: str | None = config.SHAPE_ID,
                       hours: tuple[int, ...] = PEAK_HOURS,
                       sched: pd.DataFrame | None = None) -> np.ndarray:
    """Planned headways at the north terminal during the peak, in minutes.

    Filtered to the busiest service_id (weekday) to avoid weekday and weekend trips
    sharing clock times. shape_id=None pools all southbound branches from Spadina Station.
    """
    if sched is None:
        sched = load_schedule_510()

    weekday = sched["service_id"].value_counts().idxmax()
    day = sched[sched["service_id"] == weekday]
    if shape_id is not None:
        day = day[day["shape_id"] == shape_id]
    else:
        day = day[day["direction_id"] == "1"]  # southbound towards Union / Queens Quay

    firsts = day.sort_values("stop_sequence").groupby("trip_id").first()
    dep = firsts["dep_min"].to_numpy()
    dep = np.sort(dep[(dep >= min(hours) * 60) & (dep < (max(hours) + 1) * 60)])
    return np.diff(dep)
