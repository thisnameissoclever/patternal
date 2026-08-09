#!/usr/bin/env python3
"""Exercise the backend-neutral avatar inspection-pose gate."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charmorph_pose import evaluate_avatar_pose


def pose_fixture() -> tuple[np.ndarray, list[str], dict[str, np.ndarray]]:
    vertices = np.asarray([
        (-0.80, 0.00, 1.20), (-0.78, 0.02, 1.21), (-0.25, 0.00, 1.38), (-0.30, 0.02, 1.34),
        (0.80, 0.00, 1.20), (0.78, 0.02, 1.21), (0.25, 0.00, 1.38), (0.30, 0.02, 1.34),
        (-0.20, -0.10, 1.38), (0.20, -0.10, 1.38), (-0.20, 0.10, 1.38), (0.20, 0.10, 1.38),
        (-0.08, 0.00, 0.00), (0.08, 0.00, 0.00), (-0.08, 0.00, 1.70), (0.08, 0.00, 1.70),
    ], dtype=np.float64)
    regions = ["arms"] * 8 + ["torso"] * 4 + ["legs"] * 2 + ["head"] * 2
    landmarks = {
        "joint_spine_head": np.asarray((0.0, 0.0, 0.90)),
        "joint_shoulder.L_tail": np.asarray((0.20, 0.0, 1.38)),
        "joint_shoulder.R_tail": np.asarray((-0.20, 0.0, 1.38)),
        "joint_forearm.L_tail": np.asarray((0.60, 0.0, 1.32)),
        "joint_forearm.R_tail": np.asarray((-0.60, 0.0, 1.32)),
    }
    return vertices, regions, landmarks


class AvatarPoseTests(unittest.TestCase):
    def test_symmetric_shallow_a_pose_is_accepted(self) -> None:
        vertices, regions, landmarks = pose_fixture()
        report = evaluate_avatar_pose(vertices, regions, landmarks)
        self.assertTrue(report["accepted"])
        self.assertAlmostEqual(0.0, report["metrics"]["armEndpointMirrorError"]["valueM"])

    def test_one_raised_arm_is_rejected(self) -> None:
        vertices, regions, landmarks = pose_fixture()
        vertices[4] = np.asarray((0.62, 0.00, 1.68))
        vertices[5] = np.asarray((0.61, 0.02, 1.66))
        report = evaluate_avatar_pose(vertices, regions, landmarks)
        self.assertFalse(report["accepted"])
        self.assertFalse(report["metrics"]["armEndpointMirrorError"]["accepted"])
        self.assertFalse(report["metrics"]["armElevationDifference"]["accepted"])

    def test_symmetric_overhead_pose_is_rejected(self) -> None:
        vertices, regions, landmarks = pose_fixture()
        vertices[0] = np.asarray((-0.35, 0.00, 1.80))
        vertices[1] = np.asarray((-0.34, 0.02, 1.78))
        vertices[4] = np.asarray((0.35, 0.00, 1.80))
        vertices[5] = np.asarray((0.34, 0.02, 1.78))
        report = evaluate_avatar_pose(vertices, regions, landmarks)
        self.assertFalse(report["accepted"])
        self.assertFalse(report["metrics"]["meanArmElevation"]["accepted"])

    def test_large_forward_sweep_is_rejected(self) -> None:
        vertices, regions, landmarks = pose_fixture()
        vertices[0] = np.asarray((-0.65, 0.55, 1.30))
        vertices[1] = np.asarray((-0.64, 0.54, 1.31))
        vertices[4] = np.asarray((0.65, 0.55, 1.30))
        vertices[5] = np.asarray((0.64, 0.54, 1.31))
        report = evaluate_avatar_pose(vertices, regions, landmarks)
        self.assertFalse(report["accepted"])
        self.assertFalse(report["metrics"]["meanArmForwardSweep"]["accepted"])

    def test_non_finite_geometry_is_rejected(self) -> None:
        vertices, regions, landmarks = pose_fixture()
        vertices[0, 2] = float("nan")
        with self.assertRaisesRegex(ValueError, "non-finite"):
            evaluate_avatar_pose(vertices, regions, landmarks)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
