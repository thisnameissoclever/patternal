from __future__ import annotations

import unittest

import numpy as np

from tools.fit_mhr_local_profile import mesh_quality, upper_arm_weights


class FitMhrLocalProfileTests(unittest.TestCase):
    def test_mesh_quality_accepts_topology_preserving_scale(self) -> None:
        vertices = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            dtype=np.float64,
        )
        faces = np.asarray([[0, 1, 2]], dtype=np.int64)
        result = mesh_quality(vertices, vertices * [1.2, 0.8, 1.0], faces)
        self.assertTrue(result["accepted"])
        self.assertEqual(0, result["orientationFlipCount"])

    def test_mesh_quality_rejects_orientation_flip(self) -> None:
        vertices = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            dtype=np.float64,
        )
        faces = np.asarray([[0, 1, 2]], dtype=np.int64)
        flipped = vertices.copy()
        flipped[:, 0] *= -1.0
        result = mesh_quality(vertices, flipped, faces)
        self.assertFalse(result["accepted"])
        self.assertEqual(1, result["orientationFlipCount"])

    def test_upper_arm_weights_exclude_wide_lower_body_vertices(self) -> None:
        vertices = np.asarray(
            [
                [30.0, 125.0, 0.0],
                [-30.0, 125.0, 0.0],
                [30.0, 90.0, 0.0],
                [-30.0, 90.0, 0.0],
                [20.0, 125.0, 0.0],
            ],
            dtype=np.float64,
        )
        right = upper_arm_weights(
            vertices,
            side=1,
            plane_x=30.0,
            sigma=9.0,
            minimum_abs_x=17.5,
            shoulder_root_abs_x=20.0,
            minimum_y=103.0,
            stature=167.0,
        )
        self.assertGreater(right[0], 0.99)
        self.assertEqual(0.0, right[1])
        self.assertEqual(0.0, right[2])
        self.assertEqual(0.0, right[3])
        self.assertEqual(0.0, right[4])


if __name__ == "__main__":
    unittest.main()
