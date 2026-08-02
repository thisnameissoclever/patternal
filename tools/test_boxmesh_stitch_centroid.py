#!/usr/bin/env python3
"""Regression tests for material-preserving BoxMesh seam topology."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from pygarment.meshgen.boxmeshgen import BoxMesh


class _Panel:
    def __init__(self, name: str, point: list[float]) -> None:
        self.panel_name = name
        self.panel_vertices = [np.asarray(point, dtype=float)]

    def rot_trans_vertex(self, point: np.ndarray) -> np.ndarray:
        return point


class StitchCentroidTests(unittest.TestCase):
    def test_production_curves_use_mesh_coordinates_for_intersection_check(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        pattern_path = (
            project_root
            / "PatternaUnreal"
            / "SourceAssets"
            / "GarmentCode"
            / "PatternaProductionCrewNeck.specification.json"
        )

        mesh = BoxMesh(str(pattern_path), 2.0)

        self.assertFalse(mesh.is_self_intersecting())

    def test_production_pattern_keeps_panel_material_vertices_distinct(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        pattern_path = (
            project_root
            / "PatternaUnreal"
            / "SourceAssets"
            / "GarmentCode"
            / "PatternaFemaleAdaptiveCrewNeck.specification.json"
        )
        mesh = BoxMesh(str(pattern_path), 2.0)
        mesh.load()

        self.assertGreater(len(mesh.seam_links), 100)
        self.assertTrue(all(first != second for first, second in mesh.seam_links))
        self.assertTrue(all(len(locations) == 1 for locations in mesh.verts_glob_loc))
        seam_separations = [
            np.linalg.norm(np.asarray(mesh.vertices[first]) - np.asarray(mesh.vertices[second]))
            for first, second in mesh.seam_links
        ]
        self.assertGreater(max(seam_separations), 5.0)
        triangle_edges = {
            tuple(sorted((int(face[first]), int(face[second]))))
            for face in mesh.faces
            for first, second in ((0, 1), (1, 2), (2, 0))
        }
        self.assertEqual(set(mesh.orig_lens), triangle_edges)
        for first, second in triangle_edges:
            placed_length = np.linalg.norm(
                np.asarray(mesh.vertices[first]) - np.asarray(mesh.vertices[second])
            )
            self.assertAlmostEqual(
                placed_length,
                mesh.orig_lens[(first, second)],
                places=5,
                msg=f"Material edge {(first, second)} was distorted during seam staging.",
            )

    def test_merging_existing_groups_uses_all_local_vertices(self) -> None:
        mesh = object.__new__(BoxMesh)
        mesh.vertices = [np.asarray([0.0, 0.0, 0.0]), np.asarray([10.0, 0.0, 0.0])]
        mesh.verts_glob_loc = [
            [("a", 0), ("b", 0), ("c", 0)],
            [("d", 0)],
        ]
        mesh.verts_loc_glob = {
            location: global_index
            for global_index, locations in enumerate(mesh.verts_glob_loc)
            for location in locations
        }
        mesh.stitch_segmentation = [["stitch_0"], ["stitch_1"]]

        mesh._stitch_two_diff_existent_glob_verts(0, 1, 2, 2)

        np.testing.assert_allclose(mesh.vertices[0], [2.5, 0.0, 0.0])
        self.assertEqual(len(mesh.verts_glob_loc[0]), 4)

    def test_adding_one_vertex_preserves_running_centroid(self) -> None:
        mesh = object.__new__(BoxMesh)
        mesh.vertices = [np.asarray([2.0, 0.0, 0.0])]
        mesh.verts_glob_loc = [[("a", 0), ("b", 0), ("c", 0)]]
        mesh.verts_loc_glob = {location: 0 for location in mesh.verts_glob_loc[0]}
        mesh.stitch_segmentation = [["stitch_0"]]
        existing_panel = _Panel("a", [0.0, 0.0, 0.0])
        new_panel = _Panel("d", [10.0, 0.0, 0.0])

        mesh._stitch_one_existent_glob_vert(existing_panel, new_panel, 0, 0, 1)

        np.testing.assert_allclose(mesh.vertices[0], [4.0, 0.0, 0.0])
        self.assertEqual(len(mesh.verts_glob_loc[0]), 4)

    def test_external_seam_accepts_a_valid_closed_dart_mouth_junction(self) -> None:
        mesh = object.__new__(BoxMesh)
        mesh.stitches = [
            SimpleNamespace(panel_1="front", panel_2="back"),
            SimpleNamespace(panel_1="front", panel_2="front"),
        ]
        mesh._valid_stitch_front_end = lambda stitch: True
        mesh._valid_stitch_same_panel = lambda stitch, links: False

        valid, invalid = mesh._is_stitching_valid({}, front_end_only=False)

        self.assertFalse(valid)
        self.assertEqual(invalid, [1])


if __name__ == "__main__":
    unittest.main()
