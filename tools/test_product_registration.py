from __future__ import annotations

import unittest

from tools.product_registration import evaluate_upper_body_registration


BODY_BOUNDS = {
    "minimum": [-0.5416407585, -0.1215356737, 0.0],
    "maximum": [0.5416407585, 0.3237942457, 1.6700000763],
}
GARMENT_BOUNDS = {
    "minimum": [-0.35325104, -0.1349679083, 0.9459300041],
    "maximum": [0.3577574193, 0.2322409749, 1.4571510553],
}


class ProductRegistrationTests(unittest.TestCase):
    def test_current_upper_body_registration_is_accepted(self) -> None:
        result = evaluate_upper_body_registration(BODY_BOUNDS, GARMENT_BOUNDS)

        self.assertTrue(result["accepted"])
        self.assertEqual([], result["issues"])
        coverage = result["anatomical_vertical_coverage"]
        self.assertAlmostEqual(
            0.5664251,
            coverage["garment_minimum_body_height_fraction"],
            places=6,
        )
        self.assertAlmostEqual(
            0.8725455,
            coverage["garment_maximum_body_height_fraction"],
            places=6,
        )

    def test_mpfb_floor_offset_regression_is_rejected(self) -> None:
        shifted_body = {
            "minimum": [-0.5397534, -0.0969033, 0.206631556],
            "maximum": [0.5397534, 0.3718025, 1.8766315],
        }

        result = evaluate_upper_body_registration(shifted_body, GARMENT_BOUNDS)

        self.assertFalse(result["accepted"])
        self.assertIn(
            "The display avatar is not upright on the studio floor.",
            result["issues"],
        )
        self.assertIn(
            "The garment neckline is outside the body's upper-torso region.",
            result["issues"],
        )

    def test_left_right_misregistration_is_rejected(self) -> None:
        shifted_garment = {
            "minimum": [
                value + 0.12 if index == 0 else value
                for index, value in enumerate(GARMENT_BOUNDS["minimum"])
            ],
            "maximum": [
                value + 0.12 if index == 0 else value
                for index, value in enumerate(GARMENT_BOUNDS["maximum"])
            ],
        }

        result = evaluate_upper_body_registration(BODY_BOUNDS, shifted_garment)

        self.assertFalse(result["accepted"])
        self.assertIn(
            "The garment is not centered on the body's left-right axis.",
            result["issues"],
        )


if __name__ == "__main__":
    unittest.main()
