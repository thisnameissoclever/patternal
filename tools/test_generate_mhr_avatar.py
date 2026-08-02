#!/usr/bin/env python3
"""Focused contract tests for the MHR avatar bridge."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from tools.generate_mhr_avatar import (
    apply_identity_overrides,
    load_identity,
    scale_to_height,
    to_blender_meters,
    write_obj,
)


class GenerateMhrAvatarTests(unittest.TestCase):
    def test_coordinate_transform_uses_blender_meters(self) -> None:
        source = np.asarray([[100.0, 200.0, 300.0]], dtype=np.float64)
        result = to_blender_meters(source)
        np.testing.assert_allclose(result, [[1.0, -3.0, 2.0]])

    def test_neutral_identity_has_exact_shape(self) -> None:
        identity = load_identity(None)
        self.assertEqual((45,), identity.shape)
        np.testing.assert_array_equal(identity, np.zeros(45, dtype=np.float32))

    def test_identity_override_is_bounded_by_coefficient_count(self) -> None:
        identity = apply_identity_overrides(load_identity(None), ["0=-1.25", "19=0.5"])
        self.assertEqual(-1.25, float(identity[0]))
        self.assertEqual(0.5, float(identity[19]))
        with self.assertRaisesRegex(ValueError, "out of range"):
            apply_identity_overrides(identity, ["45=1"])

    def test_numpy_height_scaling_is_exact(self) -> None:
        vertices = np.asarray([[0.0, 2.0, 0.0], [0.0, 12.0, 0.0]])
        result = scale_to_height(vertices, 167.0)
        self.assertAlmostEqual(167.0, float(np.ptp(result[:, 1])), places=8)

    def test_obj_writer_preserves_separate_uv_indices(self) -> None:
        vertices = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            dtype=np.float64,
        )
        faces = np.asarray([[0, 1, 2]], dtype=np.int64)
        uvs = np.asarray([[0.0, 0.0], [0.5, 0.0], [0.0, 0.5]], dtype=np.float64)
        uv_faces = np.asarray([[2, 1, 0]], dtype=np.int64)
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "mesh.obj"
            write_obj(output, vertices, faces, uvs, uv_faces, reverse_winding=True)
            text = output.read_text(encoding="utf-8")
        self.assertIn("f 3/1 2/2 1/3", text)


if __name__ == "__main__":
    unittest.main()
