from __future__ import annotations

import unittest

import numpy as np

from tools.fit_mhr_local_profile import (
    mesh_quality,
    normalize_arm_forward_sweep,
    normalize_upper_arm_length,
    scaled_skeleton_state,
    upper_arm_weights,
)


class FitMhrLocalProfileTests(unittest.TestCase):
    def test_skeleton_translations_scale_to_fitted_stature(self) -> None:
        state = np.asarray(
            [
                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0],
                [10.0, 50.0, -5.0, 0.0, 0.0, 0.0, 1.0, 1.0],
            ],
            dtype=np.float64,
        )
        vertices = np.asarray([[0.0, 0.0, 0.0], [0.0, 200.0, 0.0]])
        result = scaled_skeleton_state(state, vertices, 160.0)
        np.testing.assert_allclose(result[1, :3], [8.0, 40.0, -4.0])
        np.testing.assert_allclose(result[:, 3:], state[:, 3:])

    def test_upper_arm_normalization_moves_surface_and_descendant_joints_together(self) -> None:
        vertices = np.asarray(
            [
                [20.0, 80.0, 0.0],
                [40.0, 70.0, 0.0],
                [-20.0, 80.0, 0.0],
                [-40.0, 70.0, 0.0],
                [0.0, 0.0, 0.0],
                [0.0, 100.0, 0.0],
            ],
            dtype=np.float64,
        )
        state = np.zeros((127, 8), dtype=np.float64)
        state[:, 6:] = 1.0
        state[39, :3] = [-15.0, 80.0, 0.0]
        state[40, :3] = [-25.0, 70.0, 0.0]
        state[75, :3] = [15.0, 80.0, 0.0]
        state[76, :3] = [25.0, 70.0, 0.0]
        result_vertices, result_state, evidence = normalize_upper_arm_length(
            vertices,
            state,
            target_ratio=0.17,
        )
        self.assertTrue(evidence["accepted"])
        self.assertGreater(result_vertices[1, 0], vertices[1, 0])
        self.assertLess(result_vertices[3, 0], vertices[3, 0])
        self.assertGreater(
            np.linalg.norm(result_state[76, :3] - result_state[75, :3]),
            np.linalg.norm(state[76, :3] - state[75, :3]),
        )

    def test_arm_sweep_normalization_rotates_both_sides_toward_inspection_plane(self) -> None:
        vertices = np.asarray(
            [
                [20.0, 80.0, 12.0],
                [50.0, 70.0, 30.0],
                [-20.0, 80.0, 12.0],
                [-50.0, 70.0, 30.0],
                [0.0, 0.0, 0.0],
                [0.0, 100.0, 0.0],
            ]
            + [[30.0, 70.0, 20.0], [-30.0, 70.0, 20.0]] * 120,
            dtype=np.float64,
        )
        state = np.zeros((127, 8), dtype=np.float64)
        state[:, 6:] = 1.0
        state[39, :3] = [-15.0, 80.0, 0.0]
        state[40, :3] = [-30.0, 70.0, 12.0]
        state[75, :3] = [15.0, 80.0, 0.0]
        state[76, :3] = [30.0, 70.0, 12.0]
        result_vertices, result_state, evidence = normalize_arm_forward_sweep(
            vertices,
            state,
            target_degrees=20.0,
        )
        self.assertTrue(evidence["accepted"])
        self.assertLess(result_vertices[1, 2], vertices[1, 2])
        self.assertLess(result_vertices[3, 2], vertices[3, 2])
        self.assertLess(result_state[76, 2], state[76, 2])
        self.assertLess(result_state[40, 2], state[40, 2])

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
