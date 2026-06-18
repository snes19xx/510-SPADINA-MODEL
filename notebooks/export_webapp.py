"""Regenerate the webapp's data from the model.

Run the full scenario set here and write the
geometry plus a sample of genuine runs per scenario into the webapp, which the page then cycles
through. 
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
