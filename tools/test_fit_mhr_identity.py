from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

import torch

from tools.fit_mhr_identity import (
    loss_for_predictions,
    measurement_acceptance,
    scaled_to_height,
)


class FitMhrIdentityTests(unittest.TestCase):
    def test_script_entrypoint_resolves_repository_tools_package(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(repository_root / "tools" / "fit_mhr_identity.py"), "--help"],
            cwd=repository_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)

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

    def test_measurement_acceptance_reports_each_rejected_residual(self) -> None:
        result = measurement_acceptance(
            {
                "waistCircumference": 82.75,
                "waistDepth": torch.tensor([22.0]),
            },
            {"waistCircumference": 82.0, "waistDepth": 21.0},
        )
        self.assertEqual("rejected", result["status"])
        self.assertEqual(["waistDepth"], result["rejectedMeasurements"])
        self.assertTrue(result["measurements"]["waistCircumference"]["accepted"])
        self.assertEqual(
            0.75, result["measurements"]["waistDepth"]["toleranceCm"]
        )


if __name__ == "__main__":
    unittest.main()
