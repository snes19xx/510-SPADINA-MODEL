# 510 Spadina Improvement Model: Baseline Methodology

## Overview
This module establishes the baseline performance metrics (**"Current State"**) for the 510 Spadina streetcar. [cite_start]It ingests raw TTC data to empirically derive travel time distributions and headway variability, forming the control group for the intervention simulations[cite: 142].

## 1. Baseline Travel Time Calculation
- **Source:** TTC GTFS static data [Link](https://open.toronto.ca/dataset/merged-gtfs-ttc-routes-and-schedules/)
- **Function:** `calculate_baseline_travel_times()`

This function extracts end-to-end travel times for the 510 route by processing scheduled trip sequences.

### Key Processes:
* **Time Normalization:** Converts GTFS timestamps (which often extend past 24:00:00 for late-night service) into absolute minute values for calculation.
* **Trip Filtering:**
  * Filters for valid `trip_id` sequences associated with the 510 route.
  * **Heuristic Validation:** Applies a domain-knowledge filter to exclude data artifacts. Only trips with durations between **15 and 45 minutes** are retained. [cite_start]This threshold removes depot moves or partial trips while capturing the variance of real-world operations (typical run time is ~29 mins)[cite: 145].
* **Output:** Returns a NumPy array of valid travel times ($t$) for the simulation engine.

## 2. Baseline Headway Analysis
- **Source:** TTC Delay Data (CSV format)[LINK](https://open.toronto.ca/dataset/ttc-streetcar-delay-data/).
- **Function:** `calculate_baseline_headways()`

This function reconstructs the actual spacing between vehicles to quantify the "bunching" phenomenon described in the literature review[cite: 5, 30].

### Key Processes:
* **Time-Difference Calculation:** Sorts historical delay incidents by `DateTime` and calculates the delta ($\Delta t$) between consecutive log entries.
* **Noise Filtering:**
  * **Lower Bound (0.5 min):** Removes duplicate entries or simultaneous reports.
  * **Upper Bound (15 min):** Excludes major service gaps or prolonged disruptions that do not represent standard headway variance.
* **Data Fallback Logic (Waterfall):**
  1. **Primary:** Calculated time differences from raw timestamps.
  2. **Secondary:** If sample size $n < 50$, supplements with the `Min Gap` field provided in the delay logs.
  3. **Tertiary (Fail-safe):** If empirical data is insufficient, generates a synthetic Gamma distribution ($\alpha=2, \beta=1.5$) to model high-frequency bunching behavior.

## Dependencies
* `pandas`: Data manipulation and time-series handling.
* `numpy`: Array operations for stochastic simulation.
* `datetime`: Parsing GTFS time strings.
