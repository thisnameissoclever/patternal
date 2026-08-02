from __future__ import annotations

import unittest

import numpy as np
import trimesh

from fit_mhclo_garment import convert_output_vertices, project_outside


class FitMhcLoGarmentTests(unittest.TestCase):
    def test_projection_moves_near_vertices_outside_watertight_body(self) -> None:
        body = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
        vertices = np.asarray(
            [
                [0.0, 0.0, 0.95],
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 1.4],
            ],
            dtype=np.float64,
        )
        fitted, metrics = project_outside(body, vertices, 0.1)
        signed = trimesh.proximity.signed_distance(body, fitted)
        self.assertEqual(2, metrics["projected_vertex_count"])
        self.assertEqual(0, metrics["final_inside_vertex_count"])
        self.assertTrue(np.all(signed <= -0.098))
        np.testing.assert_allclose(vertices[2], fitted[2])

    def test_garmentcode_conversion_swaps_up_and_depth_in_centimeters(self) -> None:
        vertices = np.asarray([[0.25, -0.12, 1.50]], dtype=np.float64)
        converted, label = convert_output_vertices(
            vertices,
            0.20,
            "garmentcode-centimeters",
        )
        np.testing.assert_allclose(converted, [[25.0, 130.0, -12.0]])
        self.assertEqual("x,y,z meters to x,z-floor,y centimeters", label)


if __name__ == "__main__":
    unittest.main()
