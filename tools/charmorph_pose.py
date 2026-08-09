#!/usr/bin/env python3
"""Evaluate whether an avatar uses a symmetric, garment-inspection pose."""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np


SCHEMA_VERSION = "patterna.avatar-pose/1.0"
ENDPOINT_MIRROR_ERROR_RATIO_LIMIT = 0.03
ARM_ANGLE_DIFFERENCE_LIMIT_DEGREES = 8.0
ARM_REACH_DIFFERENCE_RATIO_LIMIT = 0.015
ARM_ELEVATION_RANGE_DEGREES = (-55.0, -10.0)
ARM_FORWARD_SWEEP_LIMIT_DEGREES = 25.0


def _required_landmark(
    landmarks: dict[str, np.ndarray],
    name: str,
) -> np.ndarray:
    point = landmarks.get(name)
    if point is None:
        raise ValueError(f"Avatar pose requires landmark {name}")
    return np.asarray(point, dtype=np.float64)


def _region_vertices(
    vertices: np.ndarray,
    vertex_regions: Iterable[str],
    region: str,
) -> np.ndarray:
    mask = np.fromiter((value == region for value in vertex_regions), dtype=bool, count=len(vertices))
    selected = vertices[mask]
    if len(selected) == 0:
        raise ValueError(f"Avatar pose has no vertices for region {region}")
    return selected


def _degrees(value: float) -> float:
    return math.degrees(value)


def evaluate_avatar_pose(
    vertices: np.ndarray,
    vertex_regions: list[str],
    landmarks: dict[str, np.ndarray],
) -> dict[str, Any]:
    """Return symmetric inspection-pose evidence from the fitted surface."""
    vertices = np.asarray(vertices, dtype=np.float64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) != len(vertex_regions):
        raise ValueError("Avatar pose vertices and regions have incompatible shapes")
    if len(vertices) < 4 or not np.isfinite(vertices).all():
        raise ValueError("Avatar pose vertices are empty or non-finite")
    if any(not np.isfinite(point).all() for point in landmarks.values()):
        raise ValueError("Avatar pose landmarks contain non-finite values")

    height_m = float(np.ptp(vertices[:, 2]))
    if height_m <= 0.25:
        raise ValueError("Avatar pose stature is not usable")
    arms = _region_vertices(vertices, vertex_regions, "arms")
    central_x = [
        float(point[0])
        for name, point in landmarks.items()
        if ".L" not in name and ".R" not in name
    ]
    if not central_x:
        raise ValueError("Avatar pose has no central landmarks for a sagittal plane")
    midline_x = float(np.median(np.asarray(central_x)))
    floor_z = float(np.min(vertices[:, 2]))
    minimum_arm_surface_z = floor_z + 0.35 * height_m

    vectors: dict[str, np.ndarray] = {}
    endpoints: dict[str, np.ndarray] = {}
    for side, direction in (("L", 1.0), ("R", -1.0)):
        shoulder = _required_landmark(landmarks, f"joint_shoulder.{side}_tail")
        side_arms = arms[
            ((arms[:, 0] - midline_x) * direction > 0.0)
            & (arms[:, 2] > minimum_arm_surface_z)
        ]
        if len(side_arms) == 0:
            raise ValueError(f"Avatar pose has no usable {side} arm surface above the lower-body exclusion band")
        distances = np.linalg.norm(side_arms - shoulder, axis=1)
        endpoint = side_arms[int(np.argmax(distances))]
        endpoints[side] = endpoint
        vectors[side] = endpoint - shoulder

    left_vector = vectors["L"]
    reflected_right_vector = vectors["R"].copy()
    reflected_right_vector[0] *= -1.0
    endpoint_mirror_error_m = float(np.linalg.norm(left_vector - reflected_right_vector))
    endpoint_mirror_error_ratio = endpoint_mirror_error_m / height_m

    reaches = {side: float(np.linalg.norm(vector)) for side, vector in vectors.items()}
    reach_difference_ratio = abs(reaches["L"] - reaches["R"]) / height_m
    elevations = {
        side: _degrees(math.atan2(vector[2], math.hypot(vector[0], vector[1])))
        for side, vector in vectors.items()
    }
    forward_sweeps = {
        side: _degrees(math.atan2(vector[1], abs(vector[0])))
        for side, vector in vectors.items()
    }
    elevation_difference = abs(elevations["L"] - elevations["R"])
    forward_sweep_difference = abs(forward_sweeps["L"] - forward_sweeps["R"])
    mean_elevation = (elevations["L"] + elevations["R"]) / 2.0
    mean_forward_sweep = (forward_sweeps["L"] + forward_sweeps["R"]) / 2.0

    metrics = {
        "armEndpointMirrorError": {
            "accepted": endpoint_mirror_error_ratio <= ENDPOINT_MIRROR_ERROR_RATIO_LIMIT,
            "valueM": endpoint_mirror_error_m,
            "ratioToStature": endpoint_mirror_error_ratio,
            "maximumRatio": ENDPOINT_MIRROR_ERROR_RATIO_LIMIT,
        },
        "armReachDifference": {
            "accepted": reach_difference_ratio <= ARM_REACH_DIFFERENCE_RATIO_LIMIT,
            "leftM": reaches["L"],
            "rightM": reaches["R"],
            "ratioToStature": reach_difference_ratio,
            "maximumRatio": ARM_REACH_DIFFERENCE_RATIO_LIMIT,
        },
        "armElevationDifference": {
            "accepted": elevation_difference <= ARM_ANGLE_DIFFERENCE_LIMIT_DEGREES,
            "leftDegrees": elevations["L"],
            "rightDegrees": elevations["R"],
            "differenceDegrees": elevation_difference,
            "maximumDifferenceDegrees": ARM_ANGLE_DIFFERENCE_LIMIT_DEGREES,
        },
        "armForwardSweepDifference": {
            "accepted": forward_sweep_difference <= ARM_ANGLE_DIFFERENCE_LIMIT_DEGREES,
            "leftDegrees": forward_sweeps["L"],
            "rightDegrees": forward_sweeps["R"],
            "differenceDegrees": forward_sweep_difference,
            "maximumDifferenceDegrees": ARM_ANGLE_DIFFERENCE_LIMIT_DEGREES,
        },
        "meanArmElevation": {
            "accepted": ARM_ELEVATION_RANGE_DEGREES[0] <= mean_elevation <= ARM_ELEVATION_RANGE_DEGREES[1],
            "valueDegrees": mean_elevation,
            "minimumDegrees": ARM_ELEVATION_RANGE_DEGREES[0],
            "maximumDegrees": ARM_ELEVATION_RANGE_DEGREES[1],
        },
        "meanArmForwardSweep": {
            "accepted": abs(mean_forward_sweep) <= ARM_FORWARD_SWEEP_LIMIT_DEGREES,
            "valueDegrees": mean_forward_sweep,
            "maximumAbsoluteDegrees": ARM_FORWARD_SWEEP_LIMIT_DEGREES,
        },
    }
    issues = [name for name, metric in metrics.items() if not metric["accepted"]]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "accepted": not issues,
        "acceptanceScope": "symmetric garment-inspection pose surface sanity only",
        "symmetricPresetRequired": True,
        "statureM": height_m,
        "midlineXM": midline_x,
        "surfaceEndpointsM": {
            side: [float(value) for value in endpoint]
            for side, endpoint in endpoints.items()
        },
        "metrics": metrics,
        "issues": issues,
        "limitations": [
            "this project-owned gate rejects gross inspection-pose defects and is not a motion-quality score",
            "passing does not prove joint deformation, skinning, balance, expression, or garment clearance",
            "authored asymmetric presets require a separate target-pose contract and must not reuse this symmetric gate",
        ],
    }
