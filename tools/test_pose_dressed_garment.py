from __future__ import annotations

import unittest

import numpy as np

from tools.pose_dressed_garment import (
    structural_edge_strain,
    transfer_body_displacement,
    transfer_rig_pose,
)


class PoseDressedGarmentTests(unittest.TestCase):
    def test_sewn_vertex_edges_are_not_hidden_from_pose_strain(self) -> None:
        original = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        )
        posed = original.copy()
        posed[0, 0] = 10.0
        faces = np.asarray([[0, 1, 2]])

        maximum, _, _, edge, excluded = structural_edge_strain(
            original,
            posed,
            faces,
        )

        self.assertGreater(maximum, 8.0)
        self.assertIn(0, edge)
        self.assertEqual(0, excluded)

    def test_rigid_body_motion_transfers_without_structural_strain(self) -> None:
        source_body = np.asarray(
            [
                [-1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [-1.0, 1.0, 0.0],
                [1.0, 1.0, 0.0],
            ]
        )
        posed_body = source_body + np.asarray([0.0, 0.0, 0.25])
        garment_cm = np.asarray(
            [
                [-50.0, 10.0, 2.0],
                [50.0, 10.0, 2.0],
                [-50.0, 90.0, 2.0],
                [50.0, 90.0, 2.0],
            ]
        )
        faces = np.asarray([[0, 1, 2], [1, 3, 2]])

        posed, evidence = transfer_body_displacement(
            garment_cm,
            source_body,
            posed_body,
            neighbors=4,
        )
        maximum, p95, p999, maximum_edge, excluded = structural_edge_strain(
            garment_cm,
            posed,
            faces,
        )

        np.testing.assert_allclose(posed[:, 2], garment_cm[:, 2] + 25.0)
        self.assertAlmostEqual(0.0, maximum, places=12)
        self.assertAlmostEqual(0.0, p95, places=12)
        self.assertAlmostEqual(0.0, p999, places=12)
        self.assertEqual([0, 1], maximum_edge)
        self.assertEqual(0, excluded)
        self.assertEqual(4, evidence["affected_vertex_count"])

    def test_rejects_mismatched_body_topology(self) -> None:
        with self.assertRaises(ValueError):
            transfer_body_displacement(
                np.zeros((1, 3)),
                np.zeros((2, 3)),
                np.zeros((3, 3)),
            )

    def test_panel_aware_rig_transfer_keeps_torso_fixed(self) -> None:
        source_body = np.asarray(
            [
                [0.15, 1.35, 0.0],
                [0.35, 1.35, 0.0],
                [-0.15, 1.35, 0.0],
                [-0.35, 1.35, 0.0],
            ]
        )
        garment_cm = np.asarray(
            [
                [20.0, 135.0, 0.0],
                [30.0, 135.0, 0.0],
                [0.0, 120.0, 0.0],
            ]
        )
        rig_weights = {
            "weights": {
                "upperarm01.L": [[0, 1.0], [1, 1.0]],
                "upperarm01.R": [[2, 1.0], [3, 1.0]],
            }
        }
        pose_report = {
            "arm_lowering_degrees": 22.0,
            "sides": {
                "positive_x_arm": {"shoulder_pivot_m": [0.15, 0.0, 1.35]},
                "negative_x_arm": {"shoulder_pivot_m": [-0.15, 0.0, 1.35]},
            },
        }

        posed, evidence = transfer_rig_pose(
            garment_cm,
            source_body,
            rig_weights,
            pose_report,
            ["left_sleeve_f", "left_sleeve_f", "front_torso"],
            neighbors=1,
        )

        np.testing.assert_allclose(posed[2], garment_cm[2])
        self.assertLess(posed[1, 1], garment_cm[1, 1])
        self.assertEqual(
            2,
            evidence["sides"]["positive_x_arm"]["rigid_panel_vertex_count"],
        )


if __name__ == "__main__":
    unittest.main()
