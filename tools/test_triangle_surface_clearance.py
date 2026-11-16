from __future__ import annotations

import unittest

import numpy as np

from tools.triangle_surface_clearance import (
    conservative_center_candidates,
    point_triangle_distance,
    prove_surface_clearance,
    segment_segment_distance,
    triangle_triangle_distance,
)


class TriangleSurfaceClearanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.faces = np.asarray([[0, 1, 2]], dtype=np.int32)
        self.base = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            dtype=np.float64,
        )

    def test_point_triangle_interior_distance(self) -> None:
        distance = point_triangle_distance(
            np.asarray([0.25, 0.25, 0.2]),
            self.base,
        )
        self.assertAlmostEqual(0.2, distance, places=10)

    def test_skew_segments_use_interior_points(self) -> None:
        distance = segment_segment_distance(
            np.asarray([-1.0, 0.0, 0.0]),
            np.asarray([1.0, 0.0, 0.0]),
            np.asarray([0.0, -1.0, 0.3]),
            np.asarray([0.0, 1.0, 0.3]),
        )
        self.assertAlmostEqual(0.3, distance, places=10)

    def test_parallel_triangle_distance(self) -> None:
        raised = self.base + np.asarray([0.0, 0.0, 0.2])
        self.assertAlmostEqual(
            0.2,
            triangle_triangle_distance(self.base, raised),
            places=10,
        )

    def test_clearance_rejects_surface_below_threshold(self) -> None:
        raised = self.base + np.asarray([0.0, 0.0, 0.2])
        result = prove_surface_clearance(
            self.base,
            self.faces,
            raised,
            self.faces,
            0.25,
        )
        self.assertFalse(result["passed"])
        self.assertAlmostEqual(0.2, result["measuredDistance"], places=10)

    def test_clearance_proves_lower_bound_without_inventing_minimum(self) -> None:
        raised = self.base + np.asarray([0.0, 0.0, 0.3])
        result = prove_surface_clearance(
            self.base,
            self.faces,
            raised,
            self.faces,
            0.25,
        )
        self.assertTrue(result["passed"])
        self.assertIsNone(result["measuredDistance"])
        self.assertEqual(0.25, result["provenLowerBound"])

    def test_far_surface_needs_no_exact_pair_evaluation(self) -> None:
        far = self.base + np.asarray([100.0, 0.0, 0.0])
        result = prove_surface_clearance(
            self.base,
            self.faces,
            far,
            self.faces,
            0.25,
        )
        self.assertTrue(result["passed"])
        self.assertEqual(0, result["testedCandidatePairs"])

    def test_spatial_hash_keeps_boundary_candidate(self) -> None:
        candidates = conservative_center_candidates(
            np.asarray([[0.99, 0.0, 0.0]], dtype=np.float64),
            np.asarray([0.01], dtype=np.float64),
            np.asarray([[1.01, 0.0, 0.0]], dtype=np.float64),
            maximum_second_radius=0.01,
            threshold=0.01,
        )
        self.assertEqual([[0]], candidates)


if __name__ == "__main__":
    unittest.main()
