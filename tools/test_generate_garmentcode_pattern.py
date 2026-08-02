from __future__ import annotations

import unittest

from tools.generate_garmentcode_pattern import apply_fitted_bodice_ease


class _Body(dict):
    def __setitem__(self, key, value):
        super().__setitem__(key, value)


class FittedBodiceEaseTests(unittest.TestCase):
    def test_ease_is_distributed_between_front_and_back_before_darts(self) -> None:
        body = _Body(
            bust=94.0,
            back_width=38.0,
            waist=76.0,
            waist_back_width=34.0,
        )

        measurements = apply_fitted_bodice_ease(body, 4.0, 2.0)

        self.assertAlmostEqual(98.0, body["bust"])
        self.assertAlmostEqual(78.0, body["waist"])
        self.assertAlmostEqual(38.0 / 94.0, body["back_width"] / body["bust"])
        self.assertAlmostEqual(
            34.0 / 76.0,
            body["waist_back_width"] / body["waist"],
        )
        self.assertEqual(94.0, measurements["base_bust_cm"])
        self.assertEqual(98.0, measurements["drafting_bust_cm"])

    def test_invalid_back_share_is_rejected(self) -> None:
        body = _Body(
            bust=94.0,
            back_width=94.0,
            waist=76.0,
            waist_back_width=34.0,
        )

        with self.assertRaisesRegex(ValueError, "Back widths"):
            apply_fitted_bodice_ease(body, 4.0, 2.0)


if __name__ == "__main__":
    unittest.main()
