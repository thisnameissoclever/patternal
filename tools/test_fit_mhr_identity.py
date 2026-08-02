from __future__ import annotations

import unittest

import torch

from tools.fit_mhr_identity import loss_for_predictions, scaled_to_height


class FitMhrIdentityTests(unittest.TestCase):
    def test_height_scaling_is_exact(self) -> None:
        vertices = torch.tensor(
            [[[0.0, 2.0, 0.0], [0.0, 12.0, 0.0], [1.0, 7.0, 1.0]]]
        )
        scaled = scaled_to_height(vertices, 167.0)
        height = scaled[:, :, 1].amax(dim=1) - scaled[:, :, 1].amin(dim=1)
        self.assertAlmostEqual(167.0, float(height.item()), places=5)

    def test_exact_predictions_leave_only_regularization(self) -> None:
        predictions = {
            "waistCircumference": torch.tensor([82.0]),
            "waistDepth": torch.tensor([21.0]),
        }
        targets = {"waistCircumference": 82.0, "waistDepth": 21.0}
        coefficients = torch.ones((1, 20))
        loss = loss_for_predictions(predictions, targets, coefficients, 0.025)
        self.assertAlmostEqual(0.025, float(loss.item()), places=6)


if __name__ == "__main__":
    unittest.main()
