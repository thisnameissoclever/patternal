from __future__ import annotations

import unittest

from tools.pose_mpfb_body import pose_relaxed_arms


class PoseMpfbBodyTests(unittest.TestCase):
    def test_relaxed_pose_is_symmetric_and_floor_preserving(self) -> None:
        vertices = [
            [0.0, 0.0, 0.0],
            [0.12, 0.0, 1.35],
            [0.18, 0.0, 1.30],
            [0.52, 0.0, 0.98],
            [-0.12, 0.0, 1.35],
            [-0.18, 0.0, 1.30],
            [-0.52, 0.0, 0.98],
        ]
        weights = {
            "weights": {
                "upperarm01.L": [[1, 0.2], [2, 0.4], [3, 1.0]],
                "upperarm01.R": [[4, 0.2], [5, 0.4], [6, 1.0]],
            }
        }

        posed, evidence = pose_relaxed_arms(vertices, weights, 22.0)

        self.assertEqual(vertices[0], posed[0])
        self.assertAlmostEqual(posed[3][0], -posed[6][0], places=12)
        self.assertAlmostEqual(posed[3][2], posed[6][2], places=12)
        self.assertLess(posed[3][2], vertices[3][2])
        self.assertLess(abs(posed[3][0]), abs(vertices[3][0]))
        self.assertEqual(3, evidence["positive_x_arm"]["affected_vertex_count"])
        self.assertEqual(3, evidence["negative_x_arm"]["affected_vertex_count"])

    def test_pose_rejects_implausible_angle(self) -> None:
        with self.assertRaises(ValueError):
            pose_relaxed_arms(
                [[0.0, 0.0, 0.0]],
                {"weights": {}},
                41.0,
            )

    def test_negative_rotation_raises_arms_for_dressing(self) -> None:
        vertices = [
            [0.12, 0.0, 1.35],
            [0.18, 0.0, 1.30],
            [0.52, 0.0, 0.98],
            [-0.12, 0.0, 1.35],
            [-0.18, 0.0, 1.30],
            [-0.52, 0.0, 0.98],
        ]
        weights = {
            "weights": {
                "upperarm01.L": [[0, 0.2], [1, 0.4], [2, 1.0]],
                "upperarm01.R": [[3, 0.2], [4, 0.4], [5, 1.0]],
            }
        }

        posed, _ = pose_relaxed_arms(vertices, weights, -35.0)

        self.assertGreater(posed[2][2], vertices[2][2])
        self.assertGreater(posed[5][2], vertices[5][2])
        self.assertAlmostEqual(posed[2][0], -posed[5][0], places=12)


if __name__ == "__main__":
    unittest.main()
