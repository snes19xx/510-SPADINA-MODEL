"""Regenerate the webapp's data from the model.

Runs the full scenario set and writes the geometry plus a sample of runs per scenario
into assets/.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import load_corridor, load_or_calibrate, run_scenarios, export_all


def main() -> None:
    corridor = load_corridor()
    cal = load_or_calibrate(corridor)
    ensembles = run_scenarios(corridor, cal.params, n_reps=400)
    info = export_all(corridor, ensembles)
    print("exported", info)


if __name__ == "__main__":
    main()
