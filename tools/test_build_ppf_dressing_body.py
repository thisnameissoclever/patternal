from __future__ import annotations

import unittest

import numpy as np

from tools.build_ppf_dressing_body import scaled_body_vertices


class BuildPpfDressingBodyTests(unittest.TestCase):
    def test_scaling_preserves_height_and_bounds_center(self) -> None:
        source = np.asarray(
            [
                [-2.0, 0.0, -4.0],
                [4.0, 3.0, 2.0],
                [1.0, 7.0, -1.0],
            ]
        )
        result, center, scales = scaled_body_vertices(source, 0.5)
        np.testing.assert_allclose([1.0, -1.0], center)
        np.testing.assert_allclose([0.5, 0.5, 0.5], scales)
        np.testing.assert_allclose(source[:, 1], result[:, 1])
        np.testing.assert_allclose([-0.5, 0.0, -2.5], result[0])
        np.testing.assert_allclose([2.5, 3.0, 0.5], result[1])

    def test_scaling_rejects_non_reduced_factors(self) -> None:
        source = np.zeros((3, 3))
        for value in (0.0, 1.0, 1.5):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "between zero and one"):
                    scaled_body_vertices(source, value)

    def test_upper_taper_is_smooth_and_preserves_height(self) -> None:
        source = np.asarray(
            [
                [2.0, 1.30, 0.0],
                [2.0, 1.37, 0.0],
                [2.0, 1.44, 0.0],
                [-2.0, 1.44, 0.0],
            ]
        )
        result, _, scales = scaled_body_vertices(
            source,
            0.4,
            upper_scale_xz=0.1,
            blend_start_y_m=1.32,
            blend_end_y_m=1.42,
        )
        self.assertAlmostEqual(0.4, scales[0])
        self.assertGreater(scales[1], 0.1)
        self.assertLess(scales[1], 0.4)
        self.assertAlmostEqual(0.1, scales[2])
        np.testing.assert_allclose(source[:, 1], result[:, 1])


if __name__ == "__main__":
    unittest.main()
