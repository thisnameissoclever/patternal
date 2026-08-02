#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np

from tools.charmorph_morphs import apply_controls, load_packed_morphs
from tools.charmorph_profile_controls import PATTERNA_FULL_BUST_CONTROLS
from tools.charmorph_supported_bust import apply_supported_bust_shape
from tools.fit_charmorph_profile import scaled_vertices


REPO_ROOT = Path(__file__).resolve().parents[1]
CHARACTER_DIR = REPO_ROOT / "third_party" / "CharMorph-db" / "characters" / "mb_female"


class CharMorphSupportedBustTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw_morphs = load_packed_morphs(
            CHARACTER_DIR / "morphs" / "L2_packed" / "__main__.npz"
        )
        basis = np.load(CHARACTER_DIR / "morphs" / "L1" / "African.npy")
        cls.vertices = scaled_vertices(
            apply_controls(basis, cls.raw_morphs, PATTERNA_FULL_BUST_CONTROLS)[0],
            167.0,
        )

    @staticmethod
    def measurements(support: float) -> dict[str, float]:
        return {
            "chest": 112.0,
            "underBust": 84.0,
            "bustSupport": support,
            "bustProjectionL": 9.6,
            "bustProjectionR": 9.4,
        }

    def test_zero_support_preserves_the_surface(self) -> None:
        result, evidence = apply_supported_bust_shape(
            self.vertices,
            self.raw_morphs,
            self.measurements(0.0),
        )
        np.testing.assert_array_equal(result, self.vertices)
        self.assertEqual(0.0, evidence.maximum_displacement_cm)

    def test_full_support_creates_two_curved_lower_poles(self) -> None:
        result, evidence = apply_supported_bust_shape(
            self.vertices,
            self.raw_morphs,
            self.measurements(100.0),
        )
        self.assertGreater(evidence.affected_vertex_count, 100)
        self.assertLessEqual(evidence.maximum_displacement_cm, 3.5)
        self.assertTrue(
            all(
                after > before + 0.5
                for before, after in zip(
                    evidence.root_curvature_before_cm,
                    evidence.root_curvature_after_cm,
                    strict=True,
                )
            )
        )
        self.assertFalse(np.array_equal(result, self.vertices))


if __name__ == "__main__":
    unittest.main()
