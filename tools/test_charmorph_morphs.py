#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charmorph_morphs import MorphDelta, apply_controls, combine_morphs, load_packed_morphs, morph_weights


class CharMorphMorphTests(unittest.TestCase):
    def test_decodes_sparse_and_full_morphs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pack.npz"
            np.savez(
                path,
                names=np.frombuffer(b"Demo_Size_max\0Demo_Size_min", dtype=np.uint8),
                cnt=np.array([2, -1], dtype=np.int16),
                idx=np.array([0, 2], dtype=np.uint16),
                delta=np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32),
                full=np.ones((1, 3, 3), dtype=np.float32),
            )
            result = load_packed_morphs(path)
            self.assertEqual([0, 2], result["Demo_Size_max"].indices.tolist())
            self.assertIsNone(result["Demo_Size_min"].indices)

    def test_simple_min_max_weights_match_signed_control(self) -> None:
        zero = MorphDelta(None, np.zeros((1, 3)))
        groups = combine_morphs({"Arms_Girth_min": zero, "Arms_Girth_max": zero})
        self.assertEqual({"Arms_Girth_max": 0.75}, morph_weights(groups, {"Arms_Girth": 0.75}))
        self.assertEqual({"Arms_Girth_min": 0.25}, morph_weights(groups, {"Arms_Girth": -0.25}))

    def test_combo_weights_interpolate_neutral_dimension(self) -> None:
        zero = MorphDelta(None, np.zeros((1, 3)))
        raw = {
            f"Torso_Mass-Tone_{mass}-{tone}": zero
            for mass in ("min", "max")
            for tone in ("min", "max")
        }
        groups = combine_morphs(raw)
        weights = morph_weights(groups, {"Torso_Mass": 1.0, "Torso_Tone": 0.0})
        self.assertEqual(0.5, weights["Torso_Mass-Tone_max-min"])
        self.assertEqual(0.5, weights["Torso_Mass-Tone_max-max"])
        self.assertNotIn("Torso_Mass-Tone_min-min", weights)

    def test_applies_sparse_control_without_touching_other_vertices(self) -> None:
        basis = np.zeros((2, 3), dtype=np.float64)
        raw = {
            "Arms_Girth_min": MorphDelta(np.array([0]), np.array([[-1.0, 0.0, 0.0]])),
            "Arms_Girth_max": MorphDelta(np.array([0]), np.array([[1.0, 0.0, 0.0]])),
        }
        vertices, _ = apply_controls(basis, raw, {"Arms_Girth": 0.4})
        np.testing.assert_allclose(vertices[0], [0.4, 0.0, 0.0])
        np.testing.assert_allclose(vertices[1], [0.0, 0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
