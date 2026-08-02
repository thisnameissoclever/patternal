from __future__ import annotations

import math
import unittest

import numpy as np
import torch

from tools.mhr_anthropometry import (
    build_section_topology,
    section_extent_cm,
    section_perimeter_cm,
)


class MhrAnthropometryTests(unittest.TestCase):
    def test_section_tracks_scaled_prism(self) -> None:
        vertices = np.asarray(
            [
                [-1.0, 0.0, -2.0], [1.0, 0.0, -2.0],
                [1.0, 0.0, 2.0], [-1.0, 0.0, 2.0],
                [-1.0, 10.0, -2.0], [1.0, 10.0, -2.0],
                [1.0, 10.0, 2.0], [-1.0, 10.0, 2.0],
            ],
            dtype=np.float64,
        )
        faces = np.asarray(
            [
                [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
                [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
                [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
            ],
            dtype=np.int64,
        )
        topology = build_section_topology(
            vertices, faces, name="prism", height_ratio=0.53, torso_half_width_cm=5.0
        )
        self.assertTrue(math.isclose(12.0, topology.reference_perimeter_cm, abs_tol=1.0e-8))
        batch = torch.from_numpy(np.stack([vertices, vertices * [2.0, 1.0, 0.5]])).double()
        measured = section_perimeter_cm(batch, topology)
        np.testing.assert_allclose(measured.numpy(), [12.0, 12.0], atol=1.0e-8)
        np.testing.assert_allclose(
            section_extent_cm(batch, topology, axis=0).numpy(), [2.0, 4.0], atol=1.0e-8
        )
        np.testing.assert_allclose(
            section_extent_cm(batch, topology, axis=2).numpy(), [4.0, 2.0], atol=1.0e-8
        )

    def test_section_can_be_perpendicular_to_arm_axis(self) -> None:
        vertices = np.asarray(
            [
                [-1.0, 0.0, -2.0], [1.0, 0.0, -2.0],
                [1.0, 0.0, 2.0], [-1.0, 0.0, 2.0],
                [-1.0, 10.0, -2.0], [1.0, 10.0, -2.0],
                [1.0, 10.0, 2.0], [-1.0, 10.0, 2.0],
            ],
            dtype=np.float64,
        )
        faces = np.asarray(
            [
                [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
                [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
                [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
            ],
            dtype=np.int64,
        )
        topology = build_section_topology(
            vertices,
            faces,
            name="axis-x",
            height_ratio=0.6,
            section_axis=0,
            require_centered=False,
        )
        measured = section_perimeter_cm(torch.from_numpy(vertices[None]).double(), topology)
        self.assertAlmostEqual(28.0, float(measured.item()), places=8)


if __name__ == "__main__":
    unittest.main()
