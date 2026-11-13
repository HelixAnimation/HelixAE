"""Worker-safe Kitsu metadata decisions, independent of Prism and Qt."""
import math


def shot_fps(shot, project_fps=None, prism_fps=None):
    """Prefer shot data.fps, then top-level fps, project, Prism, and 25.

    Empty, malformed, non-positive and non-finite rates are not overrides.
    """
    shot = shot if isinstance(shot, dict) else {}
    data = shot.get('data') or {}
    data = data if isinstance(data, dict) else {}
    for value in (data.get('fps'), shot.get('fps'), project_fps, prism_fps, 25):
        if isinstance(value, bool):
            continue
        try:
            rate = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(rate) and rate > 0:
            return rate
