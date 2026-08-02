from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import numpy as np

from tools.prefit_garmentcode_warp import (
    apply_staged_initial_mesh,
    create_radially_scaled_body,
    evaluate_edge_strain,
    evaluate_static_quality,
    fit_panel_rigid_positions,
    hash_material_rest_graph,
    hash_physical_topology,
    hash_seam_constraint_graph,
    interpolate_animated_body,
    read_obj_topology,
    transfer_positions_by_panel_identity,
    transfer_drape_by_panel_barycentric,
)


class _Mesh:
    def __init__(self) -> None:
        self.vertices = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        self.faces = [[0, 1, 2]]


class _IdentityMesh:
    def __init__(self, vertices, verts_loc_glob, verts_glob_loc) -> None:
        self.vertices = vertices
        self.verts_loc_glob = verts_loc_glob
        self.verts_glob_loc = verts_glob_loc


class PrefitStagingTests(unittest.TestCase):
    def test_panel_space_remesh_transfer_interpolates_dressed_surface(self) -> None:
        source = SimpleNamespace(
            vertices=[[0.0, 0.0, 0.0]] * 3,
            panels={
                "front": SimpleNamespace(
                    panel_vertices=[[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
                    panel_faces=[[0, 1, 2]],
                )
            },
            verts_loc_glob={
                ("front", 0): 0,
                ("front", 1): 1,
                ("front", 2): 2,
            },
        )
        target = SimpleNamespace(
            vertices=[[0.0, 0.0, 0.0]] * 4,
            panels={
                "front": SimpleNamespace(
                    panel_vertices=[
                        [0.0, 0.0],
                        [1.0, 0.0],
                        [0.0, 1.0],
                        [0.25, 0.25],
                    ],
                    panel_faces=[[0, 1, 3], [0, 3, 2], [1, 2, 3]],
                )
            },
            verts_loc_glob={
                ("front", 0): 0,
                ("front", 1): 1,
                ("front", 2): 2,
                ("front", 3): 3,
            },
        )

        diagnostics = transfer_drape_by_panel_barycentric(
            source,
            target,
            np.asarray(
                [[0.0, 0.0, 1.0], [2.0, 0.0, 1.0], [0.0, 2.0, 1.0]]
            ),
        )

        np.testing.assert_allclose(
            np.asarray(target.vertices)[3],
            np.asarray([0.5, 0.5, 1.0]),
        )
        self.assertEqual(3, diagnostics["source_vertex_count"])
        self.assertEqual(4, diagnostics["target_vertex_count"])
        self.assertAlmostEqual(
            0.0,
            diagnostics["maximum_material_projection_distance_cm"],
        )

    def test_rigid_panel_fit_preserves_material_shape(self) -> None:
        source = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [10.0, 0.0, 0.0],
                [11.0, 0.0, 0.0],
                [10.0, 1.0, 0.0],
            ]
        )
        target = np.asarray(
            [
                [2.0, 3.0, 4.0],
                [2.0, 4.0, 4.0],
                [1.0, 3.0, 4.0],
                [-2.0, 1.0, 5.0],
                [-1.0, 1.0, 5.0],
                [-2.0, 2.0, 5.0],
            ]
        )

        fitted, diagnostics = fit_panel_rigid_positions(
            source,
            target,
            ["front", "front", "front", "back", "back", "back"],
        )

        source_lengths = np.linalg.norm(source[[1, 4]] - source[[0, 3]], axis=1)
        fitted_lengths = np.linalg.norm(fitted[[1, 4]] - fitted[[0, 3]], axis=1)
        np.testing.assert_allclose(fitted_lengths, source_lengths)
        np.testing.assert_allclose(fitted, target, atol=1e-12)
        self.assertEqual(2, diagnostics["panel_count"])
        self.assertAlmostEqual(0.0, diagnostics["maximum_target_distance_cm"])

    def test_topology_identical_mesh_replaces_only_positions(self) -> None:
        mesh = _Mesh()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "initial.obj"
            path.write_text(
                "v 0 0 1\nv 1 0 1\nv 0 1 1\nf 1 2 3\n",
                encoding="utf-8",
            )
            apply_staged_initial_mesh(mesh, path)

        self.assertEqual([[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]], mesh.vertices)
        self.assertEqual([[0, 1, 2]], mesh.faces)

    def test_face_mismatch_is_rejected(self) -> None:
        mesh = _Mesh()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "initial.obj"
            path.write_text(
                "v 0 0 1\nv 1 0 1\nv 0 1 1\nf 1 3 2\n",
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                apply_staged_initial_mesh(mesh, path)

    def test_close_explicit_seam_transfers_into_continuous_topology(self) -> None:
        source = _IdentityMesh(
            [[0.0, 0.0, 0.0], [0.1, 0.0, 0.0], [1.0, 0.0, 0.0]],
            {("front", 0): 0, ("back", 0): 1, ("front", 1): 2},
            [[("front", 0)], [("back", 0)], [("front", 1)]],
        )
        target = _IdentityMesh(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            {("front", 0): 0, ("back", 0): 0, ("front", 1): 1},
            [[("front", 0), ("back", 0)], [("front", 1)]],
        )

        diagnostics = transfer_positions_by_panel_identity(
            source,
            target,
            np.asarray(source.vertices, dtype=float),
            max_weld_separation_cm=0.25,
        )

        np.testing.assert_allclose(
            np.asarray(target.vertices),
            np.asarray([[0.05, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        )
        self.assertEqual(1, diagnostics["welded_vertex_count"])
        self.assertEqual(2, diagnostics["welded_source_vertex_count"])
        self.assertAlmostEqual(0.1, diagnostics["maximum_input_separation_cm"])

    def test_open_explicit_seam_is_not_welded(self) -> None:
        source = _IdentityMesh(
            [[0.0, 0.0, 0.0], [0.3, 0.0, 0.0]],
            {("front", 0): 0, ("back", 0): 1},
            [[("front", 0)], [("back", 0)]],
        )
        target = _IdentityMesh(
            [[0.0, 0.0, 0.0]],
            {("front", 0): 0, ("back", 0): 0},
            [[("front", 0), ("back", 0)]],
        )

        with self.assertRaisesRegex(RuntimeError, "Refusing to weld"):
            transfer_positions_by_panel_identity(
                source,
                target,
                np.asarray(source.vertices, dtype=float),
                max_weld_separation_cm=0.25,
            )


class StaticQualityTests(unittest.TestCase):
    _limits = {
        "max_body_collisions": 0,
        "max_self_collisions": 0,
        "max_edge_strain_ratio": 0.40,
        "max_ninety_fifth_percentile_edge_strain_ratio": 0.10,
        "max_ninety_ninth_point_ninth_percentile_edge_strain_ratio": 0.25,
        "seam_link_count": 12,
        "maximum_seam_separation_cm": 0.0,
        "max_seam_separation_cm": 0.25,
    }

    def test_static_velocity_does_not_accept_remaining_self_intersections(self) -> None:
        reasons = evaluate_static_quality(
            body_collisions=0,
            self_collisions=7,
            maximum_edge_strain_ratio=0.30,
            ninety_fifth_percentile_edge_strain_ratio=0.05,
            ninety_ninth_point_ninth_percentile_edge_strain_ratio=0.15,
            **self._limits,
        )

        self.assertEqual(["7 self intersections"], reasons)

    def test_static_velocity_does_not_accept_excess_peak_strain(self) -> None:
        reasons = evaluate_static_quality(
            body_collisions=0,
            self_collisions=0,
            maximum_edge_strain_ratio=0.412,
            ninety_fifth_percentile_edge_strain_ratio=0.05,
            ninety_ninth_point_ninth_percentile_edge_strain_ratio=0.15,
            **self._limits,
        )

        self.assertEqual(["peak strain 0.412"], reasons)

    def test_all_physical_gates_accept_static_candidate(self) -> None:
        reasons = evaluate_static_quality(
            body_collisions=0,
            self_collisions=0,
            maximum_edge_strain_ratio=0.385,
            ninety_fifth_percentile_edge_strain_ratio=0.058,
            ninety_ninth_point_ninth_percentile_edge_strain_ratio=0.213,
            **self._limits,
        )

        self.assertEqual([], reasons)


class AnimatedBodyTests(unittest.TestCase):
    def test_radial_start_preserves_height_and_topology(self) -> None:
        target = np.asarray([[10.0, 20.0, -8.0], [-6.0, 40.0, 4.0]])

        start = create_radially_scaled_body(target, 0.5)

        np.testing.assert_allclose(
            start,
            np.asarray([[5.0, 20.0, -4.0], [-3.0, 40.0, 2.0]]),
        )
        np.testing.assert_allclose(start[:, 1], target[:, 1])

    def test_smoothstep_animation_reaches_exact_target(self) -> None:
        start = np.asarray([[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]])
        target = np.asarray([[0.0, 1.0, 0.0], [3.0, 2.0, 1.0]])

        midpoint, midpoint_progress = interpolate_animated_body(start, target, 4, 10)
        final, final_progress = interpolate_animated_body(start, target, 9, 10)

        self.assertAlmostEqual(0.5, midpoint_progress)
        np.testing.assert_allclose((start + target) * 0.5, midpoint)
        self.assertEqual(1.0, final_progress)
        np.testing.assert_allclose(target, final)

    def test_animation_rejects_mismatched_topology(self) -> None:
        with self.assertRaises(ValueError):
            interpolate_animated_body(np.zeros((2, 3)), np.zeros((3, 3)), 0, 10)


class MaterialSpaceStrainTests(unittest.TestCase):
    def test_material_rest_lengths_replace_invalid_welded_reference_edges(self) -> None:
        reference = np.asarray(
            [[0.0, 0.0, 0.0], [5.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        )
        final = np.asarray(
            [[0.0, 0.0, 0.0], [1.2, 0.0, 0.0], [0.0, 1.0, 0.0]]
        )
        faces = np.asarray([[0, 1, 2]])

        result = evaluate_edge_strain(
            reference,
            final,
            faces,
            {(0, 1): 1.0, (0, 2): 1.0, (1, 2): 2.0**0.5},
        )

        self.assertAlmostEqual(0.2, result[0])
        self.assertEqual(3, result[3])
        self.assertEqual(3, result[4])
        self.assertEqual(0, result[5])
        self.assertEqual([0, 1], result[6])

    def test_invalid_material_rest_length_is_rejected(self) -> None:
        vertices = np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        )
        with self.assertRaises(RuntimeError):
            evaluate_edge_strain(
                vertices,
                vertices,
                np.asarray([[0, 1, 2]]),
                {(0, 1): 0.0},
            )


class PhysicalIdentityTests(unittest.TestCase):
    def test_topology_hash_changes_with_connectivity(self) -> None:
        first = hash_physical_topology(4, np.asarray([[0, 1, 2], [0, 2, 3]]))
        second = hash_physical_topology(4, np.asarray([[0, 1, 3], [1, 2, 3]]))

        self.assertNotEqual(first, second)

    def test_material_rest_hash_is_order_independent(self) -> None:
        first_hash, first_count = hash_material_rest_graph(
            {(2, 0): 2.5, (1, 0): 1.25}
        )
        second_hash, second_count = hash_material_rest_graph(
            {(0, 1): 1.25, (0, 2): 2.5}
        )

        self.assertEqual(first_hash, second_hash)
        self.assertEqual(2, first_count)
        self.assertEqual(first_count, second_count)

    def test_obj_identity_distinguishes_welded_corner_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            welded = root / "welded.obj"
            explicit = root / "explicit.obj"
            shared_texture = "vt 0 0\nvt 1 0\nvt 0 1\nvt 1 1\n"
            welded.write_text(
                "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
                + shared_texture
                + "f 1/1 2/2 3/3\nf 1/4 3/3 2/2\n",
                encoding="utf-8",
            )
            explicit.write_text(
                "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 0\n"
                + shared_texture
                + "f 1/1 2/2 3/3\nf 4/4 3/3 2/2\n",
                encoding="utf-8",
            )

            welded_identity = read_obj_topology(welded)
            explicit_identity = read_obj_topology(explicit)

        self.assertEqual(3, welded_identity["vertex_count"])
        self.assertEqual(4, explicit_identity["vertex_count"])
        self.assertNotEqual(
            welded_identity["surface_corner_mapping_sha256"],
            explicit_identity["surface_corner_mapping_sha256"],
        )

    def test_seam_graph_hash_binds_mode_corner_mapping_and_links(self) -> None:
        explicit = hash_seam_constraint_graph(
            "explicit",
            "a" * 64,
            {"seam_link_1_0": (3, 1), "seam_link_0_0": (0, 2)},
        )
        reordered = hash_seam_constraint_graph(
            "explicit",
            "a" * 64,
            {"seam_link_0_0": (2, 0), "seam_link_1_0": (1, 3)},
        )
        welded = hash_seam_constraint_graph(
            "welded-bootstrap",
            "a" * 64,
            {"seam_link_0_0": (2, 0), "seam_link_1_0": (1, 3)},
        )

        self.assertEqual(explicit, reordered)
        self.assertNotEqual(explicit, welded)


if __name__ == "__main__":
    unittest.main()
