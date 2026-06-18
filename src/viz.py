"""The figures, in a quiet editorial style.

I want these to read like a printed page: a serif face, ink on warm paper, hairline axes,
one restrained accent, and no chartjunk. Every function takes the model output and returns a
finished figure, so the notebook only has to call it. The most important one is the Marey
diagram, because it shows the bunching happening rather than just asserting it.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from . import config, data
from .geometry import Corridor
from .monte_carlo import Ensemble
from .simulation import SimResult

P = config.PALETTE


def _setup() -> None:
    """Set the house style once."""
    plt.rcParams.update({
        "figure.facecolor": P["paper"],
        "axes.facecolor": P["paper"],
        "savefig.facecolor": P["paper"],
        "font.family": "serif",
        "font.serif": ["Georgia", "Iowan Old Style", "Times New Roman", "DejaVu Serif"],
        "font.size": 11,
        "axes.edgecolor": P["muted"],
        "axes.linewidth": 0.6,
        "axes.titlesize": 13,
        "axes.titleweight": "normal",
        "axes.labelcolor": P["ink"],
        "text.color": P["ink"],
        "xtick.color": P["muted"],
        "ytick.color": P["muted"],
        "axes.grid": True,
        "axes.axisbelow": True,        # keep gridlines behind the bars and lines, never in front
        "grid.color": P["grid"],
        "grid.linewidth": 0.6,
        "figure.dpi": 120,
    })


_setup()


def _despine(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _save(fig, name: str | None):
    # I save the figure and then hand it back through `_show`, which displays it exactly once.
    # Returning the figure as the cell value as well would make the notebook draw every figure
    # twice (once from the inline backend, once from the repr), so the public functions below
    # deliberately do not return it.
    if name:
        config.FIGURE_DIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(config.FIGURE_DIR / f"{name}.png", dpi=200, bbox_inches="tight")
    return fig


def _cdf(values: np.ndarray):
    v = np.sort(values)
    return v, np.arange(1, len(v) + 1) / len(v)


def marey(today: SimResult, proposed: SimResult, window_min: float = 45.0,
          save: str | None = "marey") -> plt.Figure:
    """Space-time diagram: distance up the page, time across it. A car's line bends flat
    while it dwells and climbs while it runs. When two lines merge and travel together, that
    is a bunch. Today's lines collapse into pairs; the proposed lines stay parallel."""
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.6), sharey=True)
    for ax, res, color, title in [
        (axes[0], today, P["baseline"], "Today: schedule-based, passive signals"),
        (axes[1], proposed, P["proposed"], "Proposed: consolidation, priority, holding"),
    ]:
        s_km = res.stop_s / 1000.0
        t0 = res.warmup_s
        t1 = t0 + window_min * 60.0
        for v in range(len(res.dispatch)):
            if not (t0 <= res.dispatch[v] <= t1):
                continue
            xs, ys = [], []
            for k in range(len(res.stops)):
                xs += [res.arr[v, k], res.dep[v, k]]
                ys += [s_km[k], s_km[k]]
            ax.plot((np.array(xs) - t0) / 60.0, ys, lw=0.9, color=color, alpha=0.75,
                    solid_capstyle="round")
        for k in range(len(res.stops)):
            ax.axhline(s_km[k], color=P["rule"], lw=0.4, zorder=0)
        ax.set_title(title, loc="left", fontsize=11.5)
        ax.set_xlabel("Minutes")
        ax.set_xlim(0, window_min)
        ax.grid(False)
        _despine(ax)
    axes[0].set_ylabel("Distance from Spadina Station (km)")
    fig.suptitle("Every car's journey down the line", x=0.5, y=1.0,
                 fontsize=14, ha="center")
    fig.tight_layout()
    _save(fig, save)


def travel_time_cdf(ensembles: dict[str, Ensemble], save: str | None = "travel_time_cdf") -> plt.Figure:
    """How long the trip takes, as a cumulative distribution. A line to the left is faster;
    a steeper line is more predictable."""
    fig, ax = plt.subplots(figsize=(8, 5))
    order = [("baseline", P["baseline"], 2.4), ("consolidation", P["muted"], 1.2),
             ("tsp", P["accent"], 1.2), ("proposed", P["proposed"], 2.4)]
    for name, color, lw in order:
        if name not in ensembles:
            continue
        x, y = _cdf(ensembles[name].run_times)
        ax.plot(x, y, color=color, lw=lw, label=ensembles[name].scenario.label)
    ax.set_xlabel("End-to-end travel time (minutes)")
    ax.set_ylabel("Share of trips at or below")
    ax.set_title("Travel time, today versus proposed", loc="left")
    ax.legend(frameon=False, loc="lower right")
    _despine(ax)
    fig.tight_layout()
    _save(fig, save)


def headway_distribution(ensembles: dict[str, Ensemble], params: config.Params,
                         save: str | None = "headway_distribution") -> plt.Figure:
    """The spacing between cars. The proposed curve clusters tightly around the target; the
    baseline curve spreads from near zero (bunched) to far too long (the gap behind a bunch)."""
    fig, ax = plt.subplots(figsize=(8, 5))
    for name, color in [("baseline", P["baseline"]), ("proposed", P["proposed"])]:
        x, y = _cdf(ensembles[name].headways)
        ax.plot(x, y, color=color, lw=2.4, label=ensembles[name].scenario.label)
    ax.axvline(params.target_headway_min, color=P["ink"], lw=1.0, ls=(0, (3, 3)))
    ax.text(params.target_headway_min, 0.04, "  target", color=P["ink"], fontsize=9)
    ax.set_xlim(0, params.target_headway_min * 3)
    ax.set_xlabel("Headway between cars (minutes)")
    ax.set_ylabel("Share of gaps at or below")
    ax.set_title("Headway regularity at Front St", loc="left")
    ax.legend(frameon=False, loc="lower right")
    _despine(ax)
    fig.tight_layout()
    _save(fig, save)


def scenario_dotplot(ensembles: dict[str, Ensemble], save: str | None = "scenarios") -> plt.Figure:
    """Run time and headway variability for each scenario, with confidence intervals, so the
    size and the certainty of each gain are both visible."""
    names = list(ensembles)
    labels = [ensembles[n].scenario.label for n in names]
    ypos = np.arange(len(names))[::-1]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))

    for ax, key, title, unit in [
        (ax1, "run_median", "Median travel time", "minutes"),
        (ax2, "headway_cv", "Headway variability (CV)", ""),
    ]:
        means = [ensembles[n].summary[key]["mean"] for n in names]
        lo = [ensembles[n].summary[key]["lo"] for n in names]
        hi = [ensembles[n].summary[key]["hi"] for n in names]
        colors = [P["baseline"] if n == "baseline" else (P["proposed"] if n == "proposed" else P["muted"])
                  for n in names]
        ax.hlines(ypos, lo, hi, color=colors, lw=2.0, alpha=0.5)
        ax.scatter(means, ypos, color=colors, s=42, zorder=3)
        for y, m in zip(ypos, means):
            ax.text(m, y + 0.18, f"{m:.2f}".rstrip("0").rstrip(".") if key == "headway_cv" else f"{m:.1f}",
                    ha="center", fontsize=9, color=P["ink"])
        ax.set_yticks(ypos)
        ax.set_yticklabels(labels if ax is ax1 else [])
        ax.set_title(title, loc="left", fontsize=12)
        ax.set_xlabel(unit)
        ax.grid(axis="y", visible=False)
        _despine(ax)
    fig.tight_layout()
    _save(fig, save)


def stop_map(corridor: Corridor, save: str | None = "stop_map") -> plt.Figure:
    """The corridor with its stops. Filled dots stay; open dots are the five stops
    consolidation removes."""
    fig, ax = plt.subplots(figsize=(4.6, 8))
    xy = corridor.shape_xy
    x0, y0 = xy[:, 0].min(), xy[:, 1].min()
    ax.plot((xy[:, 0] - x0), (xy[:, 1] - y0), color=P["rule"], lw=3.0, solid_capstyle="round")
    for st in corridor.stops:
        kept = not st.remove
        ax.scatter(st.x - x0, st.y - y0, s=46,
                   facecolor=(P["ink"] if kept else P["paper"]),
                   edgecolor=(P["ink"] if kept else P["baseline"]),
                   linewidth=1.4, zorder=3)
        ax.text(st.x - x0 + 70, st.y - y0, st.name, va="center", fontsize=8.5,
                color=(P["ink"] if kept else P["baseline"]))
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("510 Spadina corridor", loc="left", fontsize=12)
    fig.tight_layout()
    _save(fig, save)


def calibration_fit(baseline: Ensemble, save: str | None = "calibration") -> plt.Figure:
    """Show that the untouched baseline matches reality. On the left, the simulated run-time
    distribution against the published schedule. On the right, the simulated headway spread
    against the spacing seen in the delay logs."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.4))

    sched = data.scheduled_run_times()
    x, y = _cdf(sched)
    ax1.plot(x, y, color=P["muted"], lw=2.0, label="Scheduled (GTFS)")
    x, y = _cdf(baseline.run_times)
    ax1.plot(x, y, color=P["baseline"], lw=2.0, label="Simulated baseline")
    ax1.set_xlabel("Run time (minutes)")
    ax1.set_ylabel("Cumulative share")
    ax1.set_title("Run time vs the schedule", loc="left", fontsize=12)
    ax1.legend(frameon=False, loc="lower right")
    _despine(ax1)

    gaps = data.peak_gap_distribution()
    obs_cv = gaps.std() / gaps.mean()
    sim_cv = baseline.headways.std() / baseline.headways.mean()
    ax2.bar(["Delay logs\n(PM peak gaps)", "Simulated\nbaseline"], [obs_cv, sim_cv],
            color=[P["muted"], P["baseline"]], width=0.55)
    for i, val in enumerate([obs_cv, sim_cv]):
        ax2.text(i, val + 0.01, f"{val:.2f}", ha="center", fontsize=10, color=P["ink"])
    ax2.set_ylabel("Coefficient of variation")
    ax2.set_title("Headway irregularity vs the delay data", loc="left", fontsize=12)
    ax2.grid(axis="x", visible=False)
    _despine(ax2)

    fig.tight_layout()
    _save(fig, save)


def sensitivity_plot(rows: list[dict], param_label: str, save: str | None = "sensitivity") -> plt.Figure:
    """Run time and headway CV as one parameter is swept, to show the model responds
    smoothly rather than balancing on a fitted point."""
    v = [r["value"] for r in rows]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    ax.plot(v, [r["run_median"] for r in rows], color=P["baseline"], lw=2.0, marker="o", ms=4,
            label="Median travel time (min)")
    ax.set_xlabel(param_label)
    ax.set_ylabel("Median travel time (min)", color=P["baseline"])
    _despine(ax)
    ax2 = ax.twinx()
    ax2.plot(v, [r["headway_cv"] for r in rows], color=P["proposed"], lw=2.0, marker="s", ms=4,
             label="Headway CV")
    ax2.set_ylabel("Headway CV", color=P["proposed"])
    ax2.grid(False)
    for s in ("top",):
        ax2.spines[s].set_visible(False)
    ax.set_title("Baseline sensitivity", loc="left")
    fig.tight_layout()
    _save(fig, save)
