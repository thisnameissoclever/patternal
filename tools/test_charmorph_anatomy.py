#!/usr/bin/env python3
"""Exercise the backend-neutral avatar anatomy gate."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charmorph_anatomy import evaluate_avatar_anatomy, landmark_symmetry, load_charmorph_landmarks


def plausible_fixture() -> tuple[np.ndarray, list[str], dict[str, np.ndarray]]:
    vertices = np.asarray([
        (-0.867, 0.00, 1.40), (0.867, 0.00, 1.40),
        (-0.68, 0.00, 1.40), (0.68, 0.00, 1.40),
        (-0.22, -0.10, 1.38), (0.22, -0.10, 1.38),
        (-0.22, 0.10, 1.38), (0.22, 0.10, 1.38),
        (-0.20, -0.05, 1.38), (0.20, -0.05, 1.38),
        (-0.20, 0.05, 1.38), (0.20, 0.05, 1.38),
        (-0.09, -0.08, 1.48), (0.09, -0.08, 1.48),
        (-0.08, 0.08, 1.70), (0.08, 0.08, 1.70),
        (-0.12, -0.13, 0.00), (-0.12, 0.13, 0.00),
        (-0.08, -0.13, 0.06), (-0.08, 0.13, 0.06),
        (0.08, -0.13, 0.06), (0.08, 0.13, 0.06),
        (0.12, -0.13, 0.00), (0.12, 0.13, 0.00),
    ], dtype=np.float64)
    regions = [
        "arms", "arms", "arms", "arms",
        "torso", "torso", "torso", "torso", "torso", "torso", "torso", "torso",
        "head", "head", "head", "head",
        "legs", "legs", "legs", "legs", "legs", "legs", "legs", "legs",
    ]
    landmarks = {
        "joint_spine_head": np.asarray((0.0, 0.0, 0.90)),
        "joint_chin_tail": np.asarray((0.0, -0.08, 1.48)),
        "joint_shoulder.L_tail": np.asarray((0.18, 0.0, 1.38)),
        "joint_shoulder.R_tail": np.asarray((-0.18, 0.0, 1.38)),
        "joint_upper_arm.L_tail": np.asarray((0.47, 0.0, 1.38)),
        "joint_upper_arm.R_tail": np.asarray((-0.47, 0.0, 1.38)),
        "joint_forearm.L_tail": np.asarray((0.68, 0.0, 1.40)),
        "joint_forearm.R_tail": np.asarray((-0.68, 0.0, 1.40)),
        "joint_shin.L_tail": np.asarray((0.10, 0.0, 0.08)),
        "joint_shin.R_tail": np.asarray((-0.10, 0.0, 0.08)),
        "joint_thigh.L_head": np.asarray((0.10, 0.0, 0.90)),
        "joint_thigh.R_head": np.asarray((-0.10, 0.0, 0.90)),
    }
    return vertices, regions, landmarks


class AvatarAnatomyTests(unittest.TestCase):
    def test_sparse_charmorph_landmark_weights_are_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "joints.npz"
            np.savez(
                path,
                names=np.frombuffer(b"joint_example\0", dtype=np.uint8),
                cnt=np.asarray((2,), dtype=np.uint8),
                idx=np.asarray((0, 1), dtype=np.uint16),
                weights=np.asarray((0.25, 0.75), dtype=np.float64),
            )
            landmarks = load_charmorph_landmarks(
                path,
                np.asarray(((0.0, 0.0, 0.0), (1.0, 2.0, 3.0))),
            )
            np.testing.assert_allclose((0.75, 1.5, 2.25), landmarks["joint_example"])

    def test_plausible_symmetric_fixture_is_accepted(self) -> None:
        vertices, regions, landmarks = plausible_fixture()
        report = evaluate_avatar_anatomy(vertices, regions, landmarks)
        self.assertTrue(report["accepted"])
        self.assertTrue(report["symmetry"]["accepted"])
        self.assertEqual(5, report["symmetry"]["pairCount"])
        self.assertAlmostEqual(1.021118, report["measurements"]["armSpan"]["ratioToStature"], places=6)

    def test_short_arm_span_is_rejected(self) -> None:
        vertices, regions, landmarks = plausible_fixture()
        vertices[0, 0] = -0.70
        vertices[1, 0] = 0.70
        report = evaluate_avatar_anatomy(vertices, regions, landmarks)
        self.assertFalse(report["accepted"])
        self.assertFalse(report["measurements"]["armSpan"]["accepted"])
        self.assertTrue(any("armSpan" in issue for issue in report["issues"]))

    def test_asymmetric_landmark_is_rejected(self) -> None:
        _, _, landmarks = plausible_fixture()
        landmarks["joint_upper_arm.R_tail"] = np.asarray((-0.47, 0.012, 1.38))
        report = landmark_symmetry(landmarks)
        self.assertFalse(report["accepted"])
        self.assertGreater(report["maximumMirrorErrorM"], report["limitM"])

    def test_non_finite_geometry_is_rejected(self) -> None:
        vertices, regions, landmarks = plausible_fixture()
        vertices[0, 0] = float("nan")
        with self.assertRaisesRegex(ValueError, "non-finite"):
            evaluate_avatar_anatomy(vertices, regions, landmarks)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
