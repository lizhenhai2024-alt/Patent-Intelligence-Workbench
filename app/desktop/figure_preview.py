"""Helpers for lightweight Tk patent-figure previews."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FigureScale:
    subsample: int = 1
    zoom: int = 1


def figure_scale(
    image_width: int,
    image_height: int,
    viewport_width: int,
    viewport_height: int,
    zoom_level: int = 0,
) -> FigureScale:
    """Return integer Tk scaling factors around a fit-to-window baseline."""
    width = max(viewport_width, 1)
    height = max(viewport_height, 1)
    fit = max(
        1,
        math.ceil(image_width / width),
        math.ceil(image_height / height),
    )
    if zoom_level < 0:
        return FigureScale(subsample=fit + abs(zoom_level))
    if zoom_level == 0:
        return FigureScale(subsample=fit)
    if fit > 1:
        return FigureScale(subsample=max(1, fit - zoom_level))
    return FigureScale(zoom=min(4, 1 + zoom_level))
