#!/usr/bin/env python3
"""Measurement-driven supported-bust shaping for the CharMorph body."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

import numpy as np


@dataclass(frozen=True)
class SupportedBustEvidence:
    method: str
    support_percent: float
    root_half_width_cm: float
    requested_projection_cm: float
    affected_vertex_count: int
    maximum_displacement_cm: float
    root_curvature_before_cm: tuple[float, float]
    root_curvature_after_cm: tuple[float, float]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def breast_vertex_indices(raw_morphs: Mapping[str, object]) -> np.ndarray:
    """Return the stable MB-Lab breast topology selected by its own morphs."""

    indices: set[int] = set()
    for name, morph in raw_morphs.items():
        morph_indices = getattr(morph, "indices", None)
        if "Breast" in name and morph_indices is not None:
            indices.update(int(index) for index in morph_indices)
    if len(indices) < 250:
        raise RuntimeError("CharMorph breast morph topology is incomplete")
    return np.asarray(sorted(indices), dtype=np.int64)


def _apices(
    vertices: np.ndarray,
    breast_indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    floor = float(vertices[:, 2].min())
    height = float(np.ptp(vertices[:, 2]))
    points = vertices[breast_indices]
    result: list[np.ndarray] = []
    for side in (-1.0, 1.0):
        side_x = points[:, 0] * side
        mask = (
            (side_x >= 0.035 * height / 1.67)
            & (side_x <= 0.18 * height / 1.67)
            & (points[:, 2] >= floor + 0.69 * height)
            & (points[:, 2] <= floor + 0.77 * height)
        )
        candidates = points[mask]
        if len(candidates) < 20:
            raise RuntimeError("Could not isolate a CharMorph breast surface")
        result.append(candidates[int(np.argmin(candidates[:, 1]))])
    return result[0], result[1]


def underbust_root_curvature_cm(
    vertices: np.ndarray,
    breast_indices: np.ndarray,
    root_half_width_m: float,
) -> tuple[float, float]:
    """Measure how far the lower pole center falls below its two root edges."""

    height = float(np.ptp(vertices[:, 2]))
    points = vertices[breast_indices]
    values: list[float] = []
    for side, apex in zip((-1.0, 1.0), _apices(vertices, breast_indices), strict=True):
        normalized_x = (points[:, 0] - apex[0]) / root_half_width_m
        lower = (
            (points[:, 0] * side > 0.0)
            & (points[:, 1] < -0.045 * height / 1.67)
            & (points[:, 2] < apex[2])
            & (points[:, 2] > apex[2] - 0.14 * height / 1.67)
        )
        center = points[lower & (np.abs(normalized_x) < 0.22), 2]
        edges = points[
            lower
            & (np.abs(normalized_x) > 0.52)
            & (np.abs(normalized_x) < 0.90),
            2,
        ]
        if len(center) < 8 or len(edges) < 8:
            raise RuntimeError("Could not measure the CharMorph underbust root curve")
        values.append(float((np.percentile(edges, 20) - np.percentile(center, 20)) * 100.0))
    return values[0], values[1]


def apply_supported_bust_shape(
    vertices: np.ndarray,
    raw_morphs: Mapping[str, object],
    measurements: Mapping[str, object],
) -> tuple[np.ndarray, SupportedBustEvidence]:
    """Curve each lower breast pole independently using editable support data.

    CharMorph's large-bust morph tends toward a horizontal lower edge. This
    bounded topology-aware deformation raises the medial and lateral root while
    retaining the lower pole center, producing the U-shaped inframammary curve
    required by a supported dressmaking avatar.
    """

    source = np.asarray(vertices, dtype=np.float64)
    if source.ndim != 2 or source.shape[1] != 3 or not np.isfinite(source).all():
        raise ValueError("Supported-bust shaping requires finite 3D vertices")
    height = float(np.ptp(source[:, 2]))
    if height <= 0.0:
        raise ValueError("Supported-bust shaping requires positive body height")

    support_percent = float(measurements.get("bustSupport", 0.0))
    support_strength = float(np.clip(support_percent / 100.0, 0.0, 1.0))
    bust_cm = float(measurements.get("chest", 90.0))
    underbust_cm = float(measurements.get("underBust", bust_cm * 0.86))
    projection_cm = float(np.mean([
        float(measurements.get("bustProjectionL", 7.0)),
        float(measurements.get("bustProjectionR", 7.0)),
    ]))
    if min(bust_cm, underbust_cm, projection_cm) <= 0.0:
        raise ValueError("Supported-bust measurements must be positive")

    scale = height / 1.67
    root_half_width_m = float(np.clip((bust_cm - underbust_cm) * 0.0028, 0.065, 0.095) * scale)
    lower_radius_m = 0.115 * scale
    # A supported large bust raises the lower pole as a whole. Keeping the
    # center fixed while lifting only the two root edges creates a hanging
    # point in side view, even if the front-view fold is curved.
    center_lift_m = 0.025 * scale * support_strength
    edge_lift_m = float(np.clip(projection_cm * 0.012, 0.070, 0.120) * scale * support_strength)
    breast_indices = breast_vertex_indices(raw_morphs)
    before_curve = underbust_root_curvature_cm(source, breast_indices, root_half_width_m)

    result = source.copy()
    points = result[breast_indices].copy()
    affected = np.zeros(len(points), dtype=bool)
    for side, apex in zip((-1.0, 1.0), _apices(source, breast_indices), strict=True):
        horizontal = (points[:, 0] - apex[0]) / root_half_width_m
        vertical = (points[:, 2] - apex[2]) / lower_radius_m
        radius_squared = horizontal * horizontal + vertical * vertical
        region = (
            (points[:, 0] * side > 0.0)
            & (radius_squared < 1.35)
            & (points[:, 1] < -0.045 * scale)
        )
        front_weight = np.clip((-points[:, 1] - 0.045 * scale) / (0.18 * scale), 0.0, 1.0)
        lower_weight = np.clip((apex[2] - points[:, 2]) / lower_radius_m, 0.0, 1.0)
        lateral_weight = np.clip(np.abs(horizontal), 0.0, 1.0)
        boundary_weight = np.clip(1.0 - radius_squared / 1.35, 0.0, 1.0) ** 0.25
        lift = (
            front_weight
            * lower_weight
            * boundary_weight
            * (center_lift_m + (edge_lift_m - center_lift_m) * lateral_weight ** 1.35)
        )
        points[region, 2] += lift[region]
        affected |= region & (lift > 1.0e-10)
    result[breast_indices] = points

    displacement = np.linalg.norm(result - source, axis=1)
    after_curve = underbust_root_curvature_cm(result, breast_indices, root_half_width_m)
    evidence = SupportedBustEvidence(
        method="CharMorph morph topology plus bounded asymmetric lower-pole support",
        support_percent=support_percent,
        root_half_width_cm=root_half_width_m * 100.0,
        requested_projection_cm=projection_cm,
        affected_vertex_count=int(np.count_nonzero(affected)),
        maximum_displacement_cm=float(displacement.max() * 100.0),
        root_curvature_before_cm=before_curve,
        root_curvature_after_cm=after_curve,
    )
    return result, evidence
