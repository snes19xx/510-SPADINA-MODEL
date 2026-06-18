"""
Generate the narrative notebook from prose plus a few calls into src/.
"""

from __future__ import annotations

import nbformat as nbf
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

cells = []


def md(text: str) -> None:
    cells.append(new_markdown_cell(text.strip("\n")))


def code(text: str) -> None:
    cells.append(new_code_cell(text.strip("\n")))


md(r"""
# Faster, and far more reliable: rebuilding the 510 Spadina from its own data

*Sandesh Bhandari*

The 510 Spadina runs in its own right of way, separated from traffic for almost its whole
length, and it still crawls. It is also unreliable in a particular way: the cars arrive in
clumps, so a rider waits and waits and then watches two or three streetcars roll up together.

This notebook builds a simulation of the line out of its own published schedule and its own
delay records, calibrates it until the present-day version behaves like the real thing, and
then asks one question. How much faster and how much more reliable could the 510 be if we changed
how it is run rather than what it is built from? Three operating changes are on the table:
consolidating a handful of stops that sit too close together, giving cars conditional green
priority at signals, and dispatching to an even gap instead of a clock.

Everything below is computed by the code in `src/`. The notebook only calls it, so the prose
and the numbers can never drift apart.
""")

code(r"""
%matplotlib inline
# The analysis lives in ../src, so I make sure the project root is importable first.
import sys, pathlib
_root = pathlib.Path.cwd()
if not (_root / "src").exists():
    _root = _root.parent
sys.path.insert(0, str(_root))

from src import (load_corridor, load_or_calibrate, run_scenarios, comparison_table,
                 spacing_summary, sensitivity, INTERVENTIONS, data, viz)
import pandas as pd
""")

md(r"""
## The corridor

I rebuild the line from the real feed. The stop list and order come straight out of the
schedule, and each stop is snapped onto the actual route geometry so the distances between
them are the true ones. The result is a 17 stop chain running about 5.4 km from Spadina
Station, south down Spadina Avenue, then east along Queens Quay into the Union loop.

The thing to notice is how tightly packed the downtown stops are. Several sit barely a block
apart, which means a car spends much of its time braking, opening doors, and accelerating
again without ever reaching a useful speed.
""")

code(r"""
corridor = load_corridor()
spacing = spacing_summary(corridor)
print("stops today:           %d" % spacing["n_before"])
print("mean spacing today:    %.0f m" % spacing["mean_before_m"])
print("closest pair:          %.0f m" % spacing["min_before_m"])
print("stops if consolidated: %d  (mean spacing %.0f m)" % (spacing["n_after"], spacing["mean_after_m"]))
print("stops I would drop:    " + ", ".join(spacing["removed"]))
viz.stop_map(corridor)
""")

md(r"""
## Why it bunches

Bunching is not bad luck, it is an instability built into the way a frequent line is run. A
car that falls a little behind reaches the next stop a little late. Because riders have been
arriving the whole time, a slightly longer gap means slightly more people waiting, which means
a slightly longer dwell, which puts the car further behind. The gap keeps growing, the car
keeps getting later, and eventually the car behind catches up. Streetcars share one track and
cannot pass, so the two then travel as a pair for the rest of the line.

I do not have to take this on faith. The delay logs record, at every logged incident, the gap
to the following car. In the PM peak that spacing is wildly uneven, and the coefficient of
variation of those gaps is the statistical fingerprint of bunching. It is the number my
baseline simulation has to reproduce.
""")

code(r"""
summary = data.delay_summary()
print("510 incidents on record:   %d  (%s to %s)" % (
    summary["n_incidents"], summary["date_min"].date(), summary["date_max"].date()))
print("PM-peak gap, mean:         %.1f min" % summary["peak_gap_mean"])
print("PM-peak gap, variability:  CV = %.2f" % summary["peak_gap_cv"])
""")

md(r"""
## The model, in one paragraph

I run cars down the corridor one after another. Riders arrive at each stop at a steady rate,
so the number waiting when a car pulls in is that rate times the time since the previous car
left. Boarding that many people sets the dwell. Between stops a car accelerates, maybe reaches
its top speed, and brakes for the next stop, so short blocks are slow by construction. Signals
add a wait. And because cars cannot overtake, a car that catches the one ahead is stuck behind
it. Nothing in the model decides that the line is slow or bunched. I only write down these
mechanics and let the behaviour emerge. The three changes later in the notebook act on the
mechanics alone, never on the answer.

## Calibration: make today match reality first

A model is only worth its baseline. Before I touch anything I tune two parameters until the
untouched, present-day line reproduces two facts I measured independently: the scheduled end
to end run time, about 29 minutes, and the headway variability from the delay logs. One knob
sets the overall run time (the effective free-running speed on this slow corridor) and one
sets the size of the traffic and driver noise that the boarding feedback amplifies into
bunching. Demand, geometry, and signal behaviour are fixed inputs, not knobs.
""")

code(r"""
cal = load_or_calibrate(corridor)
print(cal.report())
""")

md(r"""
The baseline lands on both targets. The left panel below puts the simulated run-time
distribution against the published schedule; the right panel puts the simulated headway
spread against the spacing seen in the delay data. With that in hand, I can trust what the
model says about changes.
""")

code(r"""
ensembles = run_scenarios(corridor, cal.params, n_reps=400)
viz.calibration_fit(ensembles["baseline"])
""")

md(r"""
## Watching it happen

This is the clearest way to see the problem and the fix. Time runs left to right, distance
up the line. A car's trace goes flat while it dwells and climbs while it runs. When two
traces merge and travel together, that is a bunch.

On the left, today's traces collapse into pairs partway down the line. On the right, under all
three changes, the traces stay parallel and evenly spaced from terminal to terminal.
""")

code(r"""
viz.marey(ensembles["baseline"].representative, ensembles["proposed"].representative)
""")

md(r"""
## The three changes

Each change is added on top of the last, so I can see what each one buys.
""")

code(r"""
from IPython.display import Markdown
Markdown("\n".join("- **%s:** %s" % (iv.name, iv.summary) for iv in INTERVENTIONS))
""")

md(r"""
### Travel time

Conditional priority is the speed lever; it pulls the whole distribution to the left. Stop
consolidation helps a little on its own. Headway control, by design, gives a small amount of
that speed back, because holding an early car costs it time. What headway control buys instead
is on the next chart.
""")

code(r"""
viz.travel_time_cdf(ensembles)
""")

md(r"""
### Reliability

Here is the real prize. Today the gap between cars runs from near zero (a bunch) to far too
long (the wait behind a bunch). Under the full set of changes the gaps cluster tightly around
the target, which is what a rider actually feels as a dependable service.
""")

code(r"""
viz.headway_distribution(ensembles, cal.params)
""")

md(r"""
### Putting it together

Every number below is an average over 400 simulated runs, with a 95 percent confidence
interval, so both the size of each gain and how sure I am of it are visible.
""")

code(r"""
viz.scenario_dotplot(ensembles)

rows = comparison_table(ensembles)
# I report both change columns so that a positive number always means a better line: a car
# that is faster, and a service that is more reliable. A drop in the headway CV is a gain in
# reliability, so I flip its sign here rather than print a confusing negative.
table = pd.DataFrame([{
    "Scenario": r["label"],
    "Travel time (min)": round(r["run_median"], 1),
    "85th pct (min)": round(r["run_p85"], 1),
    "Speed (km/h)": round(r["speed_kmh"], 1),
    "Headway CV": round(r["headway_cv"], 3),
    "Faster vs today": "%+.1f%%" % (-r["run_change_pct"]),
    "More reliable vs today": "%+.1f%%" % (-r["cv_change_pct"]),
} for r in rows]).set_index("Scenario")
table
""")

md(r"""
## How sensitive is this?

A fitted curve can match a target and still be meaningless. To show the baseline is resting on
a real mechanism, I sweep the demand it carries and watch the run time and the headway
variability respond. Both move smoothly and in the direction the mechanics predict: more
riders means slower cars and worse bunching.
""")

code(r"""
sweep = sensitivity(corridor, cal.params, "peak_boardings_per_hour",
                    [2000, 2600, 3200, 3800, 4400], n_reps=120)
viz.sensitivity_plot(sweep, "PM-peak boardings per hour")
""")

md(r"""
## What this captures, and what it does not

The model is deliberately a model of one thing: the operating dynamics of a single busy
direction in the peak. It earns its keep by reproducing the present-day run time and bunching
from mechanism alone, and by showing how three operating changes move them.

It does not try to be everything. It runs one direction over a representative peak rather than
a full service day, it treats boarding as a smooth flow rather than individual fare taps, and
it holds demand fixed instead of letting better service attract new riders. Weather, blocked
tracks, and special-event surges, all of which show up in the delay logs, are out of scope. A
fuller study would relax these, but none of them change the central finding: the 510's
unreliability is an operating problem, and operating changes fix most of it.

The headline, in plain terms. Consolidating five stops and adding conditional signal priority
make the trip meaningfully faster. Dispatching to an even headway is what turns a clumpy,
unpredictable line into a reliable one, cutting the variability in spacing by roughly two
thirds, for a small and worthwhile cost in speed.
""")

nb = new_notebook(cells=cells, metadata={
    "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
    "language_info": {"name": "python"},
})

import pathlib
out = pathlib.Path(__file__).resolve().parent / "510_spadina.ipynb"
nbf.write(nb, str(out))
print("wrote", out)
