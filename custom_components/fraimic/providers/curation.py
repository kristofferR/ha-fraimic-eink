"""Pure curation predicates for e-ink suitability."""

from __future__ import annotations

import math

from ..const import (
    ART_ASPECT_MAX,
    ART_ASPECT_MIN,
    FIT_CONTAIN,
    FIT_CONTAIN_BLACK,
    FIT_STRETCH,
    MIN_ART_SHORT_EDGE,
)

ASPECT_RELAXED_FITS = {FIT_CONTAIN, FIT_CONTAIN_BLACK, FIT_STRETCH}


def large_enough(width: int, height: int) -> bool:
    """Image has enough source resolution to avoid obvious upscale softness."""
    return width > 0 and height > 0 and min(width, height) >= MIN_ART_SHORT_EDGE


def acceptable(width: int, height: int, target_w: int, target_h: int) -> bool:
    """Is an image of these dimensions worth showing on this frame?

    - Short edge >= MIN_ART_SHORT_EDGE: anything smaller upscales visibly
      soft on a ~150 PPI panel.
    - Aspect ratio within [ART_ASPECT_MIN, ART_ASPECT_MAX] x the frame's
      viewed aspect: cover-cropping handles moderate mismatch, but extreme
      panoramas / tall scrolls lose most of the artwork to the crop.
    """
    if not large_enough(width, height):
        return False
    ratio = (width / height) / (target_w / target_h)
    return ART_ASPECT_MIN <= ratio <= ART_ASPECT_MAX


def acceptable_for_fit(
    width: int, height: int, target_w: int, target_h: int, fit: str
) -> bool:
    """Is this image suitable after accounting for the requested fit policy?"""
    if fit in ASPECT_RELAXED_FITS:
        return large_enough(width, height)
    return acceptable(width, height, target_w, target_h)


def aspect_score(width: int, height: int, target_w: int, target_h: int) -> float:
    """Higher = better fit; used to pick the best fallback candidate."""
    if width <= 0 or height <= 0:
        return 0.0
    ratio = (width / height) / (target_w / target_h)
    if ratio <= 0:
        return 0.0
    # 1.0 at a perfect aspect match, decaying symmetrically in log space.
    closeness = 1.0 / (1.0 + abs(math.log(ratio)))
    # Resolution factor saturates at 1.0 once the short edge covers the panel.
    resolution = min(1.0, min(width, height) / max(1, min(target_w, target_h)))
    return closeness * resolution
