"""Body-relative acceptance checks for product garment presentation."""

from __future__ import annotations

import math
from typing import Sequence


Bounds = dict[str, Sequence[float]]


def _coordinate(bounds: Bounds, boundary: str, axis: int) -> float:
    values = bounds.get(boundary)
    if values is None or len(values) != 3:
        raise ValueError(f"Bounds must contain a three-value {boundary} coordinate.")
    value = float(values[axis])
    if not math.isfinite(value):
        raise ValueError("Bounds contain a non-finite coordinate.")
    return value


def evaluate_upper_body_registration(
    body_bounds: Bounds,
    garment_bounds: Bounds,
) -> dict[str, object]:
    """Evaluate whether a shirt-like garment occupies the body's torso region."""
    body_minimum = [_coordinate(body_bounds, "minimum", axis) for axis in range(3)]
    body_maximum = [_coordinate(body_bounds, "maximum", axis) for axis in range(3)]
    garment_minimum = [
        _coordinate(garment_bounds, "minimum", axis) for axis in range(3)
    ]
    garment_maximum = [
        _coordinate(garment_bounds, "maximum", axis) for axis in range(3)
    ]

    body_size = [
        body_maximum[axis] - body_minimum[axis] for axis in range(3)
    ]
    garment_size = [
        garment_maximum[axis] - garment_minimum[axis] for axis in range(3)
    ]
    if any(size <= 0.0 for size in body_size + garment_size):
        raise ValueError("Body and garment bounds must have positive size on every axis.")

    body_center = [
        (body_minimum[axis] + body_maximum[axis]) * 0.5 for axis in range(3)
    ]
    garment_center = [
        (garment_minimum[axis] + garment_maximum[axis]) * 0.5
        for axis in range(3)
    ]
    center_offset = [
        garment_center[axis] - body_center[axis] for axis in range(3)
    ]
    overlap_z = min(body_maximum[2], garment_maximum[2]) - max(
        body_minimum[2], garment_minimum[2]
    )
    minimum_height_fraction = (
        garment_minimum[2] - body_minimum[2]
    ) / body_size[2]
    maximum_height_fraction = (
        garment_maximum[2] - body_minimum[2]
    ) / body_size[2]
    vertical_span_fraction = garment_size[2] / body_size[2]

    issues: list[str] = []
    if not 1.45 <= body_size[2] <= 2.15 or abs(body_minimum[2]) > 0.015:
        issues.append("The display avatar is not upright on the studio floor.")
    if not 0.44 <= minimum_height_fraction <= 0.62:
        issues.append("The garment hem is outside the body's upper-torso region.")
    if not 0.76 <= maximum_height_fraction <= 0.93:
        issues.append("The garment neckline is outside the body's upper-torso region.")
    if vertical_span_fraction < 0.25:
        issues.append("The garment has insufficient vertical torso coverage.")
    if overlap_z < 0.45:
        issues.append("The garment and body lack sufficient vertical overlap.")
    if abs(center_offset[0]) > 0.04:
        issues.append("The garment is not centered on the body's left-right axis.")
    if abs(center_offset[1]) > 0.25:
        issues.append("The garment is not centered on the body's front-back axis.")

    return {
        "schema_version": "patterna.product-registration/2.0",
        "accepted": not issues,
        "issues": issues,
        "body_bounds_m": {
            "minimum": body_minimum,
            "maximum": body_maximum,
        },
        "garment_bounds_m": {
            "minimum": garment_minimum,
            "maximum": garment_maximum,
        },
        "vertical_overlap_m": overlap_z,
        "center_offset_m": center_offset,
        "anatomical_vertical_coverage": {
            "garment_minimum_body_height_fraction": minimum_height_fraction,
            "garment_maximum_body_height_fraction": maximum_height_fraction,
            "garment_span_body_height_fraction": vertical_span_fraction,
        },
    }
