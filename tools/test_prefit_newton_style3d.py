#!/usr/bin/env python3
"""Unit tests for Patterna's Newton Style3D topology adapter."""

from __future__ import annotations

import tempfile
import json
from pathlib import Path
import unittest

import numpy as np
import trimesh

from tools.prefit_newton_style3d import (
    build_anatomical_sewing_anchors,
    build_components,
    build_vertex_edge_adjacency,
    classify_seam_assembly_phases,
    closest_point_batched,
    evaluate_seams,
    evaluate_style3d_acceptance,
    evaluate_strain,
    expand_welded_positions,
    identify_shoulder_seam_groups,
    load_obj_surface,
    load_panel_top_anchors,
    orient_material_triangles,
    orient_spatial_panels_outward,
    project_outside_body,
    signed_distance_batched,
    sewing_schedule_progress,
    sewing_anchor_strength,
    surface_edges,
    weld_surface,
)
from tools.patterna_style3d_sewing import add_seam_matrix_constraints
from newton._src.solvers.style3d.builder import PDMatrixBuilder


class NewtonStyle3DAdapterTests(unittest.TestCase):
    def test_progressive_sewing_schedule_is_smooth_and_bounded(self) -> None:
        self.assertEqual(0.0, sewing_schedule_progress(5, 10, 20))
        self.assertEqual(0.5, sewing_schedule_progress(20, 10, 20))
        self.assertEqual(1.0, sewing_schedule_progress(30, 10, 20))

    def test_vertical_sewing_anchor_releases_after_seam_closure(self) -> None:
        self.assertEqual(1.0, sewing_anchor_strength(69, 10, 20, 3, 20))
        self.assertEqual(0.5, sewing_anchor_strength(80, 10, 20, 3, 20))
        self.assertEqual(0.0, sewing_anchor_strength(90, 10, 20, 3, 20))

    def test_vertical_sewing_anchor_waits_for_body_expansion(self) -> None:
        self.assertEqual(1.0, sewing_anchor_strength(119, 10, 20, 3, 20, 120))
        self.assertEqual(0.5, sewing_anchor_strength(130, 10, 20, 3, 20, 120))
        self.assertEqual(0.0, sewing_anchor_strength(140, 10, 20, 3, 20, 120))

    def test_seam_assembly_uses_anatomy_instead_of_link_count(self) -> None:
        owners = [
            "right_front_center",
            "right_front_side",
            "right_back_center",
            "right_back_side",
            "right_sleeve_front",
        ]
        named_links = [
            ("seam_link_0_0", 0, 1),
            ("seam_link_1_0", 0, 2),
            ("seam_link_2_0", 1, 3),
            ("seam_link_3_0", 1, 3),
            ("seam_link_4_0", 1, 4),
        ]
        material_coordinates = np.asarray(
            [
                [0.0, 12.0],
                [0.0, 15.0],
                [0.0, 10.0],
                [0.0, 14.0],
                [0.0, 8.0],
            ]
        )

        phases = classify_seam_assembly_phases(
            named_links,
            owners,
            material_coordinates,
        )

        np.testing.assert_array_equal(phases, [0, 2, 2, 1, 3])

    def test_short_low_side_segment_is_not_misclassified_as_shoulder(self) -> None:
        owners = [
            "right_front_side",
            "right_back_side",
            "right_front_side",
            "right_back_side",
        ]
        named_links = [
            ("seam_link_8_0", 0, 1),
            ("seam_link_11_0", 2, 3),
        ]
        material_coordinates = np.asarray(
            [[0.0, 40.0], [0.0, 38.0], [0.0, 2.0], [0.0, 2.0]]
        )

        shoulders = identify_shoulder_seam_groups(
            named_links,
            owners,
            material_coordinates,
        )
        phases = classify_seam_assembly_phases(
            named_links,
            owners,
            material_coordinates,
        )

        self.assertEqual({"seam_link_8"}, shoulders)
        np.testing.assert_array_equal(phases, [2, 1])

    def test_adaptive_torso_shoulders_exclude_collar_join(self) -> None:
        owners = [
            "front_torso",
            "back_torso",
            "front_torso",
            "back_torso",
            "front_torso",
            "back_torso",
            "left_collar_front",
            "left_collar_back",
        ]
        named_links = [
            ("seam_link_12_0", 0, 1),
            ("seam_link_27_0", 2, 3),
            ("seam_link_13_0", 4, 5),
            ("seam_link_0_0", 6, 7),
        ]
        material_coordinates = np.asarray(
            [
                [0.0, 62.0],
                [0.0, 61.0],
                [20.0, 62.0],
                [20.0, 61.0],
                [0.0, 8.0],
                [0.0, 8.0],
                [0.0, 0.4],
                [0.0, 0.4],
            ]
        )

        shoulders = identify_shoulder_seam_groups(
            named_links,
            owners,
            material_coordinates,
        )
        phases = classify_seam_assembly_phases(
            named_links,
            owners,
            material_coordinates,
        )

        self.assertEqual({"seam_link_12", "seam_link_27"}, shoulders)
        np.testing.assert_array_equal(phases, [2, 2, 1, 1])

    def test_shoulder_pairs_receive_one_shared_lower_target_height(self) -> None:
        owners = [
            "right_front_center",
            "right_back_center",
            "right_front_center",
            "right_back_center",
        ]
        named_links = [
            ("seam_link_7_0", 0, 1),
            ("seam_link_7_1", 2, 3),
        ]
        material_coordinates = np.asarray(
            [[0.0, 40.0], [0.0, 38.0], [1.0, 39.0], [1.0, 37.0]]
        )
        initial_vertices = np.asarray(
            [
                [0.0, 147.0, -20.0],
                [0.0, 143.0, 20.0],
                [1.0, 146.0, -20.0],
                [1.0, 142.0, 20.0],
            ]
        )

        anchors, shoulders = build_anatomical_sewing_anchors(
            named_links,
            owners,
            material_coordinates,
            initial_vertices,
        )

        self.assertEqual({"seam_link_7"}, shoulders)
        self.assertEqual(4, len(anchors))
        self.assertEqual([143.0, 143.0, 142.0, 142.0], [a.target_height_cm for a in anchors])
        self.assertEqual([-4.0, 0.0, -4.0, 0.0], [a.target_height_cm - a.initial_height_cm for a in anchors])

    def test_one_vertical_anchor_is_selected_at_each_panel_top(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            path = Path(raw_directory) / "panels.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "patterna.style3d-panel-index-map/1.0",
                        "panels": [
                            {"source_panel_name": "front", "vertex_indices": [0, 2]},
                            {"source_panel_name": "back", "vertex_indices": [1, 3]},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            anchors = load_panel_top_anchors(
                path,
                np.asarray([[0.0, 0.0], [0.0, 3.0], [0.0, 4.0], [0.0, 1.0]]),
            )

        self.assertEqual([("front", 2), ("back", 1)], anchors)

    def test_seam_constraint_adds_coupled_positive_semidefinite_matrix(self) -> None:
        builder = PDMatrixBuilder(3, max_neighbor=4)
        add_seam_matrix_constraints(
            builder,
            np.asarray([[0, 1]], dtype=np.int32),
            25.0,
        )

        np.testing.assert_allclose(builder.diags.numpy(), [25.0, 25.0, 0.0])
        np.testing.assert_array_equal(builder.counts.numpy(), [1, 1, 0])
        neighbors = builder.neighbors.numpy()
        values = builder.values.numpy()
        self.assertEqual(1, neighbors[0, 0])
        self.assertEqual(0, neighbors[1, 0])
        self.assertEqual(-25.0, values[0, 0])
        self.assertEqual(-25.0, values[1, 0])

    def test_seam_constraint_supports_per_link_stiffness(self) -> None:
        builder = PDMatrixBuilder(3, max_neighbor=4)
        add_seam_matrix_constraints(
            builder,
            np.asarray([[0, 1], [1, 2]], dtype=np.int32),
            np.asarray([25.0, 100.0], dtype=np.float64),
        )

        np.testing.assert_allclose(builder.diags.numpy(), [25.0, 125.0, 100.0])
        neighbors = builder.neighbors.numpy()
        values = builder.values.numpy()
        row_one = {
            int(neighbors[1, index]): float(values[1, index])
            for index in range(int(builder.counts.numpy()[1]))
        }
        self.assertEqual(-25.0, row_one[0])
        self.assertEqual(-100.0, row_one[2])

    def test_body_proximity_queries_are_batch_invariant(self) -> None:
        body = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
        positions = np.asarray([[0.0, 0.0, 0.0], [1.5, 0.0, 0.0], [0.0, 0.5, 0.0]])

        direct_signed = trimesh.proximity.signed_distance(body, positions)
        direct_closest = trimesh.proximity.closest_point(body, positions)

        np.testing.assert_allclose(
            signed_distance_batched(body, positions, batch_size=1),
            direct_signed,
        )
        batched_closest = closest_point_batched(body, positions, batch_size=1)
        for actual, expected in zip(batched_closest, direct_closest):
            np.testing.assert_allclose(actual, expected)

    def test_body_projection_reports_clearance_after_moving_only_selected_vertices(self) -> None:
        body = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
        positions = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])

        projected, report = project_outside_body(
            positions,
            body.vertices,
            body.faces,
            clearance_m=0.1,
        )

        self.assertEqual(1, report["projected_vertex_count"])
        self.assertGreaterEqual(report["final_minimum_signed_clearance_cm"], 9.99)
        np.testing.assert_allclose(projected[1], positions[1])

    def test_open_panels_are_oriented_against_the_body_surface(self) -> None:
        body = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
        vertices = np.asarray(
            [
                [-0.2, -0.2, 1.2],
                [0.2, -0.2, 1.2],
                [0.0, 0.2, 1.2],
                [-0.2, -0.2, -1.2],
                [0.2, -0.2, -1.2],
                [0.0, 0.2, -1.2],
            ]
        )
        faces = np.asarray([[0, 1, 2], [3, 4, 5]], dtype=np.int32)

        oriented, report, flipped_count = orient_spatial_panels_outward(
            faces,
            vertices,
            ["front"] * 3 + ["back"] * 3,
            body.vertices,
            body.faces,
        )

        np.testing.assert_array_equal(oriented[0], [0, 1, 2])
        np.testing.assert_array_equal(oriented[1], [3, 5, 4])
        self.assertFalse(report["front"]["flipped"])
        self.assertTrue(report["back"]["flipped"])
        self.assertEqual(1, flipped_count)

    def test_obj_loader_preserves_separate_physical_and_pattern_corners(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            path = Path(raw_directory) / "surface.obj"
            path.write_text(
                "\n".join(
                    [
                        "v 0 0 0",
                        "v 1 0 0",
                        "v 0 1 0",
                        "vt 10 10",
                        "vt 11 10",
                        "vt 10 11",
                        "f 1/3 2/1 3/2",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            surface = load_obj_surface(path)

        np.testing.assert_array_equal(surface.faces, [[0, 1, 2]])
        np.testing.assert_array_equal(surface.texture_faces, [[2, 0, 1]])

    def test_component_welding_is_deterministic_and_exact(self) -> None:
        vertices = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 0.2],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ]
        )
        faces = np.asarray([[0, 2, 3], [1, 3, 2]], dtype=np.int32)
        welded = weld_surface(vertices, faces, [(1, 0)])

        self.assertEqual(((0, 1), (2,), (3,)), welded.components)
        np.testing.assert_array_equal(welded.old_to_new, [0, 0, 1, 2])
        np.testing.assert_allclose(welded.vertices[0], [0.0, 0.0, 0.1])
        expanded = expand_welded_positions(welded.vertices, welded.old_to_new)
        np.testing.assert_allclose(expanded[0], expanded[1])

    def test_transitive_multiway_junction_becomes_one_physical_vertex(self) -> None:
        components = build_components(7, [(4, 2), (6, 4), (3, 1)])
        self.assertEqual(((0,), (1, 3), (2, 4, 6), (5,)), components)

    def test_surface_edges_are_unique_undirected_and_stable(self) -> None:
        faces = np.asarray([[2, 1, 0], [2, 3, 1]], dtype=np.int32)
        np.testing.assert_array_equal(
            surface_edges(faces),
            [[0, 1], [0, 2], [1, 2], [1, 3], [2, 3]],
        )

    def test_vertex_edge_adjacency_is_stable_and_complete(self) -> None:
        edges = np.asarray([[0, 1], [0, 2], [1, 2], [2, 3]], dtype=np.int32)

        offsets, incident = build_vertex_edge_adjacency(4, edges)

        np.testing.assert_array_equal(offsets, [0, 2, 4, 7, 8])
        np.testing.assert_array_equal(incident, [0, 1, 0, 2, 1, 2, 3, 3])

    def test_negative_panel_winding_reorders_matching_physical_corners(self) -> None:
        faces = np.asarray([[0, 1, 2]], dtype=np.int32)
        texture_faces = np.asarray([[0, 2, 1]], dtype=np.int32)
        texture_vertices = np.asarray([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])

        oriented_faces, oriented_texture_faces, reversed_count = orient_material_triangles(
            faces,
            texture_faces,
            texture_vertices,
        )

        self.assertEqual(1, reversed_count)
        np.testing.assert_array_equal(oriented_faces, [[0, 2, 1]])
        np.testing.assert_array_equal(oriented_texture_faces, [[0, 1, 2]])

    def test_acceptance_metrics_include_every_material_edge_and_seam(self) -> None:
        positions = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.1, 0.0, 0.0],
                [1.1, 0.0, 0.0],
            ]
        )
        strain = evaluate_strain(positions, {(0, 1): 1.0, (0, 2): 1.0})
        seams = evaluate_seams(positions, [(1, 2)])

        self.assertEqual(2, strain["evaluated_edge_count"])
        self.assertAlmostEqual(0.1, strain["maximum_edge_strain_ratio"])
        self.assertAlmostEqual(
            0.1,
            strain["ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio"],
        )
        self.assertEqual(0, strain["high_strain_edge_count"])
        self.assertEqual(1, seams["seam_link_count"])
        self.assertEqual(0.0, seams["maximum_seam_separation_cm"])

    def test_style3d_acceptance_limits_tail_fraction_instead_of_single_peak(self) -> None:
        positions = np.asarray(
            [[0.0, 0.0, 0.0], [1.5, 0.0, 0.0], [1.0, 0.0, 0.0]]
        )
        strain = evaluate_strain(
            positions,
            {(0, 1): 1.0, (0, 2): 1.0},
            high_strain_threshold_ratio=0.4,
        )
        seams = evaluate_seams(positions, [(1, 1)])

        accepted, reasons = evaluate_style3d_acceptance(
            finite_positions=True,
            static_equilibrium_reached=True,
            body_collisions=0,
            self_collisions=0,
            seam_metrics=seams,
            strain_metrics=strain,
            max_seam_separation_cm=0.25,
            max_p95_edge_strain=1.0,
            max_p999_edge_strain=1.0,
            max_p9999_edge_strain=1.0,
            max_high_strain_edge_fraction=0.25,
        )

        self.assertFalse(accepted)
        self.assertTrue(any("high-strain edge fraction" in reason for reason in reasons))


if __name__ == "__main__":
    unittest.main()
