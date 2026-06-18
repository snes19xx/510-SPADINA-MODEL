"""Who gets on where, and where they get off.

The simulation needs two things from demand. First, a boarding rate at every served stop,
in passengers per minute, because that rate times the gap to the car ahead is how many
people are waiting when a car pulls in. That product is the feedback that drives bunching.
Second, for everyone who boards, a destination, so I can work out how many people alight at
each stop and add that to the dwell.

Stop consolidation does not delete riders. When a stop is dropped, its boardings and its
alightings move to the nearest stop that is still served, which is exactly the short walk a
rider would make in real life.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config
from .geometry import Corridor, Stop


@dataclass
class DemandModel:
    """Everything the simulation reads about demand for one stopping pattern."""

    stops: list[Stop]              # the active stops, in order
    board_rate: np.ndarray         # passengers per minute boarding at each stop
    dest_split: list[np.ndarray]   # dest_split[j][k] = P(a boarder at j alights at k)

    @property
    def keys(self) -> list[str]:
        return [s.key for s in self.stops]


def _effective_weights(corridor: Corridor, consolidate: bool) -> tuple[list[Stop], np.ndarray, np.ndarray]:
    """Active stops with the demand of any dropped neighbour folded in.

    walk the full stop list and pour each dropped stop's boarding and alighting weight
    into whichever active stop is closest along the line. The totals are therefore
    conserved, which keeps the comparison between scenarios honest.
    """
    actives = corridor.active_stops(consolidate)
    idx = {s.key: i for i, s in enumerate(actives)}

    board = np.array([s.board for s in actives], dtype=float)
    alight = np.array([s.alight for s in actives], dtype=float)

    if consolidate:
        for s in corridor.stops:
            if s.remove:
                nearest = corridor.nearest_active(s, consolidate=True)
                board[idx[nearest.key]] += s.board
                alight[idx[nearest.key]] += s.alight

    return actives, board, alight


def build(corridor: Corridor, params: config.Params, consolidate: bool) -> DemandModel:
    """Assemble the demand model for a stopping pattern."""
    actives, board_w, alight_w = _effective_weights(corridor, consolidate)

    # Spread the hourly peak boardings across stops by weight, then convert to per minute.
    per_minute_total = params.peak_boardings_per_hour / 60.0
    board_rate = per_minute_total * board_w / board_w.sum()

    # For a boarder at stop j, draw a destination among the downstream stops in proportion
    # to how attractive each is as a destination. The final stop mops up anyone left, so
    # nobody rides off the end of the line still on board.
    n = len(actives)
    dest_split: list[np.ndarray] = []
    for j in range(n):
        p = np.zeros(n)
        downstream = alight_w.copy()
        downstream[: j + 1] = 0.0
        if downstream.sum() > 0:
            p = downstream / downstream.sum()
        else:
            p[-1] = 1.0
        dest_split.append(p)

    return DemandModel(stops=actives, board_rate=board_rate, dest_split=dest_split)
