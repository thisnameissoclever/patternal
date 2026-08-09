from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from tools.run_ppf_patterna_bundle import (
    active_seam_links_for_phase,
    classify_seam_phase,
    cross_pair_details,
    cross_group_pairs,
    final_frame_indices,
    load_seam_links,
    mapped_object_vertices,
    read_obj,
    resolve_body_mesh,
    resolve_garment_mesh,
    seam_metrics,
    seam_assembly_plan,
    stage_body_clearance,
    stage_cross_panel_intersections,
    stitch_arrays,
    strain_metrics,
    triangle_area_metrics_cm2,
)


class RunPpfPatternaBundleTests(unittest.TestCase):
    def test_garment_override_requires_hash_bound_completed_ppf_phase(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            canonical = root / "canonical.obj"
            canonical.write_text("v 0 0 0\n", encoding="utf-8")
            source_report_path = root / "source.json"
            source_report = {
                "physical_mesh_path": str(canonical),
                "physical_mesh_sha256": hashlib.sha256(canonical.read_bytes()).hexdigest(),
            }
            source_report_path.write_text(
                json.dumps(source_report),
                encoding="utf-8",
            )
            override = root / "phase.obj"
            override.write_text("v 1 0 0\n", encoding="utf-8")
            override_hash = hashlib.sha256(override.read_bytes()).hexdigest()
            phase_report = root / "phase.json"
            phase_report.write_text(
                json.dumps(
                    {
                        "schemaVersion": "patterna.ppf-common-bundle/1.0",
                        "status": "completed-requires-acceptance-grading",
                        "inputs": {
                            "sourceReportSha256": hashlib.sha256(
                                source_report_path.read_bytes()
                            ).hexdigest()
                        },
                        "outputs": {"finalObjSha256": override_hash},
                    }
                ),
                encoding="utf-8",
            )
            resolved, identity = resolve_garment_mesh(
                source_report,
                source_report_path,
                override,
                phase_report,
            )
            self.assertEqual(override, resolved)
            self.assertTrue(identity["simulationGarmentOverride"])
            override.write_text("v 2 0 0\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash does not match"):
                resolve_garment_mesh(
                    source_report,
                    source_report_path,
                    override,
                    phase_report,
                )

    def test_active_seams_are_cumulative_by_phase(self) -> None:
        links = [
            ("dart", 0, 1),
            ("side", 2, 3),
            ("cap", 4, 5),
        ]
        owners = [
            "front_torso",
            "front_torso",
            "front_torso",
            "back_torso",
            "left_sleeve_f",
            "front_torso",
        ]
        self.assertEqual([links[0]], active_seam_links_for_phase(links, owners, 0))
        self.assertEqual(links[:2], active_seam_links_for_phase(links, owners, 2))
        self.assertEqual(links, active_seam_links_for_phase(links, owners, 5))

    def test_seam_phases_follow_semantic_construction_order(self) -> None:
        self.assertEqual(
            "internal-shaping",
            classify_seam_phase("front_torso", "front_torso"),
        )
        self.assertEqual(
            "detached-shells",
            classify_seam_phase("left_sleeve_f", "left_sleeve_b"),
        )
        self.assertEqual(
            "detached-shells",
            classify_seam_phase("left_collar_front", "left_collar_back"),
        )
        self.assertEqual(
            "torso-shell",
            classify_seam_phase("front_torso", "back_torso"),
        )
        self.assertEqual(
            "finishing-bands",
            classify_seam_phase("left_sleeve_f", "sl_left_cuff_f"),
        )
        self.assertEqual(
            "neckline",
            classify_seam_phase("left_collar_front", "front_torso"),
        )
        self.assertEqual(
            "sleeve-caps",
            classify_seam_phase("left_sleeve_f", "front_torso"),
        )

    def test_seam_assembly_plan_is_cumulative_and_complete(self) -> None:
        vertices = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [0.01, 0.0, 0.0],
                [0.0, 0.0, 0.0],
                [0.0, 0.02, 0.0],
            ]
        )
        plan = seam_assembly_plan(
            vertices,
            [("dart", 0, 1), ("side", 2, 3)],
            ["front_torso", "front_torso", "front_torso", "back_torso"],
        )
        self.assertEqual(2, plan["authoredLinkCount"])
        self.assertEqual(
            [1, 1, 2, 2, 2, 2],
            [phase["cumulativeLinkCount"] for phase in plan["phases"]],
        )
        self.assertAlmostEqual(
            2.0,
            plan["phases"][2]["maximumInitialSeparationCm"],
        )

    def test_unknown_seam_roles_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "no supported construction phase"):
            classify_seam_phase("mystery_a", "mystery_b")

    def test_cross_pair_details_restore_garment_and_body_roles(self) -> None:
        details = cross_pair_details(
            [(1, 4), (5, 0)],
            3,
            np.asarray([[0, 1, 2], [3, 4, 5], [6, 7, 8]]),
            ["front"] * 3 + ["back"] * 3 + ["sleeve"] * 3,
        )
        self.assertEqual(
            [
                {"garmentFaceIndex": 1, "bodyFaceIndex": 1, "panel": "back"},
                {"garmentFaceIndex": 0, "bodyFaceIndex": 2, "panel": "front"},
            ],
            details,
        )

    def test_cross_group_pairs_exclude_pairs_within_one_mesh(self) -> None:
        self.assertEqual(
            [(1, 3), (4, 0)],
            cross_group_pairs([(0, 1), (1, 3), (3, 4), (4, 0)], 3),
        )

    def test_latest_frame_index_is_the_final_snapshot(self) -> None:
        self.assertEqual((19, 20), final_frame_indices(20))
        with self.assertRaisesRegex(ValueError, "initial and one simulated"):
            final_frame_indices(0)

    def test_seam_labels_map_to_exact_authored_vertex_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            path = Path(raw_directory) / "segmentation.txt"
            path.write_text(
                "panel,seam_link_1_0\npanel,seam_link_2_0\n"
                "panel,seam_link_1_0\npanel,seam_link_2_0\n",
                encoding="utf-8",
            )
            self.assertEqual(
                [("seam_link_1_0", 0, 2), ("seam_link_2_0", 1, 3)],
                load_seam_links(path, 4),
            )

    def test_invalid_seam_membership_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            path = Path(raw_directory) / "segmentation.txt"
            path.write_text("seam_link_1_0\npanel\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "two distinct vertices"):
                load_seam_links(path, 2)

    def test_vertex_pairs_use_ppf_legacy_point_to_edge_contract(self) -> None:
        indices, weights = stitch_arrays([("seam_link_1_0", 3, 7)])
        np.testing.assert_array_equal(indices, [[3, 7, 7, 7]])
        np.testing.assert_allclose(weights, [[1.0, 1.0, 0.0, 0.0]])

    def test_metrics_preserve_centimeter_acceptance_units(self) -> None:
        vertices_m = np.asarray([[0.0, 0.0, 0.0], [0.001, 0.0, 0.0]])
        seams = seam_metrics(vertices_m, [("seam_link_1_0", 0, 1)])
        strain = strain_metrics(vertices_m, {(0, 1): 0.1})
        self.assertAlmostEqual(0.1, seams["maximumSeparationCm"])
        self.assertAlmostEqual(0.0, strain["maximumRatio"])

    def test_triangle_area_metrics_accept_2d_and_3d_centimeter_inputs(self) -> None:
        faces = np.asarray([[0, 1, 2]])
        planar = np.asarray([[0.0, 0.0], [2.0, 0.0], [0.0, 1.0]])
        spatial = np.column_stack((planar, np.zeros(3)))
        self.assertAlmostEqual(
            1.0,
            triangle_area_metrics_cm2(planar, faces)["minimumAreaCm2"],
        )
        self.assertAlmostEqual(
            1.0,
            triangle_area_metrics_cm2(spatial, faces)["minimumAreaCm2"],
        )

    def test_obj_reader_rejects_non_triangular_faces(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            path = Path(raw_directory) / "quad.obj"
            path.write_text(
                "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "triangulated"):
                read_obj(path)

    def test_rigid_staging_moves_only_conflicting_panels(self) -> None:
        vertices = np.asarray(
            [
                [-1.0, 0.0, 1.0],
                [0.0, 1.0, 1.0],
                [0.0, 0.0, 1.0],
                [1.0, 0.0, 1.0],
                [0.0, 1.0, 1.0],
                [0.0, 0.0, 1.0],
                [3.0, 0.0, 1.0],
                [4.0, 0.0, 1.0],
                [3.0, 1.0, 1.0],
            ]
        )
        faces = np.asarray([[0, 1, 2], [3, 4, 5], [6, 7, 8]])

        def finder(points, _faces):
            return [(0, 1)] if np.allclose(points, vertices) else []

        staged, report = stage_cross_panel_intersections(
            vertices,
            faces,
            ["left"] * 3 + ["right"] * 3 + ["clear"] * 3,
            finder,
        )
        self.assertEqual(1, report["initialIntersectionCount"])
        self.assertEqual(0, report["finalIntersectionCount"])
        self.assertFalse(np.allclose(staged[:6], vertices[:6]))
        np.testing.assert_allclose(staged[6:], vertices[6:])

    def test_body_clearance_staging_moves_only_violating_panels(self) -> None:
        vertices = np.asarray(
            [
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [1.0, 0.0, 1.0],
                [-2.0, 0.0, 0.0],
                [-2.0, 1.0, 0.0],
                [-2.0, 0.0, 1.0],
            ]
        )
        faces = np.asarray([[0, 1, 2], [3, 4, 5]])

        def violations(points):
            return [0] if points[0, 0] < 1.0005 else []

        staged, report = stage_body_clearance(
            vertices,
            faces,
            ["right"] * 3 + ["left"] * 3,
            np.asarray([[-0.5, 0.0, -0.5], [0.5, 1.0, 0.5]]),
            violations,
            lambda _points, _faces: [],
        )
        self.assertEqual(1, report["initialViolationCount"])
        self.assertEqual(0, report["finalViolationCount"])
        self.assertGreater(staged[0, 0], vertices[0, 0])
        np.testing.assert_allclose(staged[3:], vertices[3:])

    def test_object_vertex_map_restores_source_order(self) -> None:
        global_vertices = np.asarray(
            [[20.0, 0.0, 0.0], [30.0, 0.0, 0.0], [10.0, 0.0, 0.0]]
        )
        restored = mapped_object_vertices(global_vertices, [2, 0, 1])
        np.testing.assert_allclose(
            restored,
            [[10.0, 0.0, 0.0], [20.0, 0.0, 0.0], [30.0, 0.0, 0.0]],
        )

    def test_body_override_requires_hash_bound_accepted_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            canonical = root / "canonical.obj"
            proxy = root / "proxy.obj"
            report = root / "proxy-report.json"
            canonical.write_text("canonical", encoding="utf-8")
            proxy.write_text("proxy", encoding="utf-8")
            import hashlib
            import json

            canonical_hash = hashlib.sha256(canonical.read_bytes()).hexdigest()
            proxy_hash = hashlib.sha256(proxy.read_bytes()).hexdigest()
            source_report = {
                "body_mesh_path": str(canonical),
                "body_mesh_sha256": canonical_hash,
            }
            report.write_text(
                json.dumps(
                    {
                        "schemaVersion": "patterna.body-collision-proxy/1.0",
                        "accepted": True,
                        "inputs": {"sourceMeshSha256": canonical_hash},
                        "outputs": {"proxyMeshSha256": proxy_hash},
                    }
                ),
                encoding="utf-8",
            )
            resolved, identity = resolve_body_mesh(source_report, proxy, report)
            self.assertEqual(proxy.resolve(), resolved)
            self.assertTrue(identity["collisionBodyOverride"])

            proxy.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash does not match"):
                resolve_body_mesh(source_report, proxy, report)


if __name__ == "__main__":
    unittest.main()
