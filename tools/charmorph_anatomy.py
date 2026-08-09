#!/usr/bin/env python3
"""Evaluate avatar proportions and landmark symmetry from fitted geometry."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np


SCHEMA_VERSION = "patterna.avatar-anatomy/1.0"
LANDMARK_SYMMETRY_LIMIT_M = 0.001

# These are deliberately broad rejection envelopes, not sizing percentiles.
# Arm span and upper-arm length use widened outer four-standard-deviation
# limits across the sex and race groups in Baum and Man, Scientific Reports
# 14, 6551 (2024), Table 2. Hand, foot, arm, and bideltoid limits conservatively
# enclose the female and male applicant data in NASA RP-1304, Tables 5 through
# 8. Head and leg limits are project-owned gross-anatomy guards pending a
# larger dataset with definitions that match the available surface and rig
# landmarks.
RATIO_LIMITS = {
    "armSpan": (0.90, 1.17),
    "armLength": (0.37, 0.64),
    "upperArmLength": (0.16, 0.23),
    "handLength": (0.079, 0.145),
    "footLength": (0.11, 0.20),
    "shoulderBreadth": (0.18, 0.355),
    "headHeight": (0.10, 0.16),
    "functionalLegLength": (0.45, 0.62),
}

REFERENCE_EVIDENCE = [
    {
        "title": "Race and geography impact validity of maximum allowable standing height equations for para-athletes",
        "publication": "Scientific Reports 14, 6551 (2024), Table 2",
        "url": "https://doi.org/10.1038/s41598-024-56597-y",
        "scope": "arm-span and upper-arm length ratios from ANSUR II",
    },
    {
        "title": "Anthropometric Survey of the Astronaut Applicants and Astronauts From 1985 to 1991",
        "publication": "NASA RP-1304 (1993), Tables 5 through 8",
        "url": "https://ntrs.nasa.gov/citations/19930020135",
        "scope": "arm, upper-arm, hand, foot, and bideltoid dimensions",
    },
]


def load_charmorph_landmarks(
    path: Path,
    vertices: np.ndarray,
) -> dict[str, np.ndarray]:
    """Resolve CharMorph's sparse weighted joint definitions on fitted vertices."""
    with np.load(path, allow_pickle=False) as archive:
        required = {"names", "cnt", "idx", "weights"}
        missing = required.difference(archive.files)
        if missing:
            raise ValueError(f"CharMorph joint pack is missing: {', '.join(sorted(missing))}")
        names = [
            name.decode("utf-8")
            for name in bytes(archive["names"]).split(b"\0")
            if name
        ]
        counts = archive["cnt"]
        indices = archive["idx"]
        weights = archive["weights"]
        if len(names) != len(counts) or int(np.sum(counts)) != len(indices):
            raise ValueError("CharMorph joint pack has inconsistent sparse-array lengths")
        if len(indices) != len(weights):
            raise ValueError("CharMorph joint indices and weights have different lengths")
        landmarks: dict[str, np.ndarray] = {}
        offset = 0
        for name, raw_count in zip(names, counts, strict=True):
            count = int(raw_count)
            selected_indices = indices[offset : offset + count].astype(np.int64)
            selected_weights = weights[offset : offset + count].astype(np.float64)
            offset += count
            if count == 0 or np.any(selected_indices < 0) or np.any(selected_indices >= len(vertices)):
                raise ValueError(f"CharMorph landmark {name} has invalid vertex indices")
            total_weight = float(np.sum(selected_weights))
            if not math.isfinite(total_weight) or total_weight <= 1e-12:
                raise ValueError(f"CharMorph landmark {name} has invalid weights")
            landmarks[name] = np.sum(
                vertices[selected_indices] * selected_weights[:, None],
                axis=0,
            ) / total_weight
    return landmarks


def _required_landmark(
    landmarks: dict[str, np.ndarray],
    name: str,
) -> np.ndarray:
    point = landmarks.get(name)
    if point is None:
        raise ValueError(f"Avatar anatomy requires landmark {name}")
    return point


def _region_vertices(
    vertices: np.ndarray,
    vertex_regions: Iterable[str],
    region: str,
) -> np.ndarray:
    mask = np.fromiter((value == region for value in vertex_regions), dtype=bool, count=len(vertices))
    selected = vertices[mask]
    if len(selected) == 0:
        raise ValueError(f"Avatar anatomy has no vertices for region {region}")
    return selected


def _metric(
    name: str,
    value_m: float,
    height_m: float,
    method: str,
) -> dict[str, Any]:
    minimum, maximum = RATIO_LIMITS[name]
    ratio = value_m / height_m
    accepted = minimum <= ratio <= maximum
    return {
        "accepted": accepted,
        "valueM": value_m,
        "ratioToStature": ratio,
        "minimumRatio": minimum,
        "maximumRatio": maximum,
        "method": method,
    }


def _bilateral_metric(
    name: str,
    left_m: float,
    right_m: float,
    height_m: float,
    method: str,
) -> dict[str, Any]:
    result = _metric(name, (left_m + right_m) / 2.0, height_m, method)
    result.update({
        "leftM": left_m,
        "rightM": right_m,
        "leftRightDifferenceM": abs(left_m - right_m),
    })
    return result


def landmark_symmetry(
    landmarks: dict[str, np.ndarray],
) -> dict[str, Any]:
    central_x = [
        float(point[0])
        for name, point in landmarks.items()
        if ".L" not in name and ".R" not in name
    ]
    if not central_x:
        raise ValueError("Avatar anatomy has no central landmarks for a symmetry plane")
    midline_x = float(np.median(np.asarray(central_x)))
    pairs: list[dict[str, Any]] = []
    for left_name in sorted(name for name in landmarks if ".L" in name):
        right_name = left_name.replace(".L", ".R", 1)
        right = landmarks.get(right_name)
        if right is None:
            continue
        left = landmarks[left_name]
        reflected = np.array((2.0 * midline_x - left[0], left[1], left[2]))
        error = float(np.linalg.norm(reflected - right))
        pairs.append({
            "left": left_name,
            "right": right_name,
            "mirrorErrorM": error,
        })
    if not pairs:
        raise ValueError("Avatar anatomy has no left-right landmark pairs")
    maximum_error = max(pair["mirrorErrorM"] for pair in pairs)
    return {
        "accepted": maximum_error <= LANDMARK_SYMMETRY_LIMIT_M,
        "midlineXM": midline_x,
        "pairCount": len(pairs),
        "maximumMirrorErrorM": maximum_error,
        "limitM": LANDMARK_SYMMETRY_LIMIT_M,
        "pairs": pairs,
    }


def evaluate_avatar_anatomy(
    vertices: np.ndarray,
    vertex_regions: list[str],
    landmarks: dict[str, np.ndarray],
) -> dict[str, Any]:
    """Return backend-neutral avatar proportion and symmetric-preset evidence."""
    vertices = np.asarray(vertices, dtype=np.float64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) != len(vertex_regions):
        raise ValueError("Avatar anatomy vertices and regions have incompatible shapes")
    if len(vertices) < 4 or not np.isfinite(vertices).all():
        raise ValueError("Avatar anatomy vertices are empty or non-finite")
    if any(not np.isfinite(point).all() for point in landmarks.values()):
        raise ValueError("Avatar anatomy landmarks contain non-finite values")

    floor_z = float(np.min(vertices[:, 2]))
    height_m = float(np.ptp(vertices[:, 2]))
    if height_m <= 0.25:
        raise ValueError("Avatar anatomy stature is not usable")
    arms = _region_vertices(vertices, vertex_regions, "arms")
    torso = _region_vertices(vertices, vertex_regions, "torso")
    head = _region_vertices(vertices, vertex_regions, "head")

    metrics: dict[str, dict[str, Any]] = {}
    bilateral: dict[str, list[float]] = {
        "armLength": [],
        "upperArmLength": [],
        "handLength": [],
        "footLength": [],
        "functionalLegLength": [],
    }
    for side, direction in (("L", 1.0), ("R", -1.0)):
        shoulder = _required_landmark(landmarks, f"joint_shoulder.{side}_tail")
        elbow = _required_landmark(landmarks, f"joint_upper_arm.{side}_tail")
        wrist = _required_landmark(landmarks, f"joint_forearm.{side}_tail")
        ankle = _required_landmark(landmarks, f"joint_shin.{side}_tail")
        hip = _required_landmark(landmarks, f"joint_thigh.{side}_head")
        distal = arms[arms[:, 0] * direction > wrist[0] * direction]
        if len(distal) == 0:
            raise ValueError(f"Avatar anatomy has no distal {side} hand surface")
        tip = distal[int(np.argmax(distal[:, 0] * direction))]
        side_vertices = vertices[vertices[:, 0] * direction > 0.0]
        foot = side_vertices[side_vertices[:, 2] <= ankle[2] + 0.03 * height_m]
        if len(foot) < 4:
            raise ValueError(f"Avatar anatomy has no usable {side} foot surface")
        upper_arm_length = float(np.linalg.norm(elbow - shoulder))
        forearm_length = float(np.linalg.norm(wrist - elbow))
        hand_length = float(np.linalg.norm(tip - wrist))
        bilateral["armLength"].append(upper_arm_length + forearm_length + hand_length)
        bilateral["upperArmLength"].append(upper_arm_length)
        bilateral["handLength"].append(hand_length)
        bilateral["footLength"].append(float(np.ptp(foot[:, 1])))
        bilateral["functionalLegLength"].append(float(hip[2] - floor_z))

    method_by_name = {
        "armLength": "shoulder-to-elbow, elbow-to-wrist, and wrist-to-fingertip segment chain",
        "upperArmLength": "shoulder to elbow rig landmarks",
        "handLength": "wrist rig landmark to distal fingertip surface",
        "footLength": "sagittal extent of the below-ankle foot surface",
        "functionalLegLength": "vertical hip rig landmark to floor datum",
    }
    for name, values in bilateral.items():
        metrics[name] = _bilateral_metric(
            name,
            values[0],
            values[1],
            height_m,
            method_by_name[name],
        )

    shoulder_joint_breadth_m = float(np.linalg.norm(
        _required_landmark(landmarks, "joint_shoulder.L_tail")
        - _required_landmark(landmarks, "joint_shoulder.R_tail")
    ))
    metrics["armSpan"] = _metric(
        "armSpan",
        bilateral["armLength"][0] + shoulder_joint_breadth_m + bilateral["armLength"][1],
        height_m,
        "bilateral arm segment chains plus shoulder-joint breadth, independent of authored pose",
    )

    shoulder_z = float(np.mean([
        _required_landmark(landmarks, "joint_shoulder.L_tail")[2],
        _required_landmark(landmarks, "joint_shoulder.R_tail")[2],
    ]))
    shoulder_band = torso[np.abs(torso[:, 2] - shoulder_z) <= 0.01 * height_m]
    if len(shoulder_band) < 8:
        raise ValueError("Avatar anatomy has no usable shoulder surface band")
    metrics["shoulderBreadth"] = _metric(
        "shoulderBreadth",
        float(np.ptp(shoulder_band[:, 0])),
        height_m,
        "torso-surface breadth in a two-percent-stature band centered on shoulder landmarks",
    )
    chin = _required_landmark(landmarks, "joint_chin_tail")
    metrics["headHeight"] = _metric(
        "headHeight",
        float(np.max(head[:, 2]) - chin[2]),
        height_m,
        "chin rig landmark to crown of the head surface",
    )

    symmetry = landmark_symmetry(landmarks)
    issues = [
        f"{name} ratio {metric['ratioToStature']:.6f} is outside "
        f"[{metric['minimumRatio']:.6f}, {metric['maximumRatio']:.6f}]"
        for name, metric in metrics.items()
        if not metric["accepted"]
    ]
    if not symmetry["accepted"]:
        issues.append(
            f"landmark mirror error {symmetry['maximumMirrorErrorM']:.6f} m exceeds "
            f"{symmetry['limitM']:.6f} m"
        )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "accepted": not issues,
        "acceptanceScope": "gross proportion and symmetric-preset landmark sanity only",
        "statureM": height_m,
        "floorDatumM": floor_z,
        "measurements": metrics,
        "symmetry": symmetry,
        "referenceEvidence": REFERENCE_EVIDENCE,
        "limitations": [
            "reference populations are design sanity evidence, not a universal definition of normal anatomy",
            "head-height and functional-leg limits are broad project-owned guards pending a larger definition-matched dataset",
            "passing this report does not prove silhouette, pose, texture, expression, or packaged visual quality",
        ],
        "issues": issues,
    }
