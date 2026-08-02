#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_charmorph_profile import enforce_closed_circuits, scaled_vertices, triangulate_quads
from charmorph_profile_controls import clamp_controls, measurement_targets


class FitCharMorphProfileTests(unittest.TestCase):
    def test_triangulates_quads_without_reordering_vertices(self) -> None:
        faces = triangulate_quads(np.array([[0, 1, 2, 3]], dtype=np.uint16))
        np.testing.assert_array_equal(faces, [[0, 1, 2], [0, 2, 3]])

    def test_scales_height_exactly(self) -> None:
        vertices = np.array([[0.0, 0.0, -0.1], [0.0, 0.0, 1.4]])
        result = scaled_vertices(vertices, 165.0)
        self.assertAlmostEqual(1.65, float(np.ptp(result[:, 2])), places=9)

    def test_clamps_controls(self) -> None:
        self.assertEqual({"a": 1.0, "b": -1.0}, clamp_controls({"a": 2.0, "b": -3.0}))

    def test_extracts_measurement_targets(self) -> None:
        profile = {
            "body": {"hips": 100, "waist": 70, "bust": 90, "bust_points": 17},
            "measurements": {
                "hip": 101,
                "abdomenCirc": 80,
                "waist": 71,
                "underBust": 75,
                "chest": 91,
                "highChestCirc": 85,
            },
        }
        self.assertEqual(75.0, measurement_targets(profile)["underbust"])


if __name__ == "__main__":
    unittest.main()
