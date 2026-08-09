from __future__ import annotations

import unittest
from pathlib import Path
import json
import tempfile

import numpy as np

from tools.build_style3d_source import (
    body_aware_vertices,
    initial_arrangement_rejection_reasons,
    normalized_panel_key,
    resolve_inputs,
    segmentation_row,
)


class BuildStyle3DSourceTests(unittest.TestCase):
    def test_panel_keys_match_compiler_ids_to_garmentcode_names(self) -> None:
        self.assertEqual("fronttorso", normalized_panel_key("front_torso"))
        self.assertEqual("fronttorso", normalized_panel_key("front-torso-panel"))

    def test_body_aware_vertices_follow_panel_local_indices(self) -> None:
        arrangement = {
            "panels": [
                {
                    "panelId": "front-torso-panel",
                    "pieceId": "front-torso",
                    "vertices": [
                        {"index": 1, "x": 4.0, "y": 5.0, "z": 6.0},
                        {"index": 0, "x": 1.0, "y": 2.0, "z": 3.0},
                    ],
                }
            ]
        }
        result = body_aware_vertices(arrangement, {"front_torso": [1, 0]}, 2)
        np.testing.assert_allclose(result[[1, 0]], [[1, 3, 2], [4, 6, 5]])

    def test_segmentation_row_preserves_all_explicit_labels(self) -> None:
        self.assertEqual("front_torso", segmentation_row("front_torso"))
        self.assertEqual(
            "stitch_7,seam_link_7_0",
            segmentation_row(["stitch_7", "seam_link_7_0"]),
        )

    def test_segmentation_row_rejects_unknown_types(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            segmentation_row(12)

    def test_initial_arrangement_gate_accepts_verified_metrics(self) -> None:
        self.assertEqual(
            [],
            initial_arrangement_rejection_reasons(
                {
                    "minimumTriangleAreaCm2": 0.001,
                    "maximumEdgeStrainRatio": 2.0,
                    "ninetyFifthPercentileEdgeStrainRatio": 0.25,
                    "minimumTorsoClearanceCm": 0.25,
                }
            ),
        )

    def test_initial_arrangement_gate_reports_every_failed_metric(self) -> None:
        reasons = initial_arrangement_rejection_reasons(
            {
                "minimumTriangleAreaCm2": 0.00007,
                "maximumEdgeStrainRatio": 3.78,
                "ninetyFifthPercentileEdgeStrainRatio": 0.36,
                "minimumTorsoClearanceCm": float("nan"),
            }
        )

        self.assertEqual(4, len(reasons))
        self.assertTrue(any("minimumTriangleAreaCm2" in reason for reason in reasons))
        self.assertTrue(any("maximumEdgeStrainRatio" in reason for reason in reasons))
        self.assertTrue(any("ninetyFifthPercentileEdgeStrainRatio" in reason for reason in reasons))
        self.assertTrue(any("minimumTorsoClearanceCm" in reason for reason in reasons))

    def test_direct_inputs_do_not_require_a_legacy_solver_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            pattern = root / "pattern.json"
            body = root / "body.obj"
            pattern.write_text("{}", encoding="utf-8")
            body.write_text("v 0 0 0\n", encoding="utf-8")

            source, report, resolved_pattern, resolved_body = resolve_inputs(
                None,
                pattern,
                body,
            )

            self.assertIsNone(source)
            self.assertEqual({}, report)
            self.assertEqual(pattern.resolve(), resolved_pattern)
            self.assertEqual(body.resolve(), resolved_body)

    def test_direct_inputs_override_legacy_report_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            old_pattern = root / "old-pattern.json"
            old_body = root / "old-body.obj"
            new_pattern = root / "new-pattern.json"
            new_body = root / "new-body.obj"
            for path in (old_pattern, new_pattern):
                path.write_text("{}", encoding="utf-8")
            for path in (old_body, new_body):
                path.write_text("v 0 0 0\n", encoding="utf-8")
            report_path = root / "source.json"
            report_path.write_text(
                json.dumps(
                    {
                        "pattern_specification_path": str(old_pattern),
                        "body_mesh_path": str(old_body),
                    }
                ),
                encoding="utf-8",
            )

            _, _, resolved_pattern, resolved_body = resolve_inputs(
                report_path,
                new_pattern,
                new_body,
            )

            self.assertEqual(new_pattern.resolve(), resolved_pattern)
            self.assertEqual(new_body.resolve(), resolved_body)


if __name__ == "__main__":
    unittest.main()
