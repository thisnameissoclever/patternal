from __future__ import annotations

import math
import unittest

import numpy as np

from tools.patterna_shell_assembly import (
    _TorsoSurface,
    arrange_independent_body_aware_panels,
    assemble_body_aware_shell,
    panel_horizontal_bounds,
    preassemble_body_aware_seams,
    set_current_geometry_rest_lengths,
)


class _Edge:
    def __init__(self, first: int, second: int) -> None:
        self.vertex_range = [first, second]


class _Panel:
    def __init__(self, width: float, mirrored: bool = False) -> None:
        outer = -width if mirrored else width
        self.panel_vertices = [
            np.asarray([0.0, 0.0]),
            np.asarray([outer, 0.0]),
            np.asarray([outer, 10.0]),
            np.asarray([0.0, 10.0]),
        ]
        self.edges = [_Edge(0, 1), _Edge(1, 2), _Edge(2, 3), _Edge(3, 0)]
        for edge in self.edges:
            edge.stitch_ref = None
            edge.label = "hem"
        self.panel_faces = [np.asarray([0, 1, 2]), np.asarray([0, 2, 3])]
        self.n_stitches = 4
        self.glob_offset = 0


class _ShellMesh:
    def __init__(self) -> None:
        definitions = (
            ("left_back", 8.0, True),
            ("left_front_side", 6.0, True),
            ("left_front_center", 4.0, True),
            ("right_back", 8.0, False),
            ("right_front_side", 6.0, False),
            ("right_front_center", 4.0, False),
        )
        self.panelNames = [name for name, _, _ in definitions]
        self.panels = {
            name: _Panel(width, mirrored) for name, width, mirrored in definitions
        }
        self.vertices: list[list[float]] = []
        self.verts_loc_glob: dict[tuple[str, int], int] = {}
        self.verts_glob_loc: list[list[tuple[str, int]]] = []
        for panel_name in self.panelNames:
            panel = self.panels[panel_name]
            for local_index, local in enumerate(panel.panel_vertices):
                global_index = len(self.vertices)
                self.verts_loc_glob[(panel_name, local_index)] = global_index
                self.verts_glob_loc.append([(panel_name, local_index)])
                self.vertices.append([float(local[0]), float(local[1]), 0.0])

        def vertex(panel_name: str, local_index: int) -> int:
            return self.verts_loc_glob[(panel_name, local_index)]

        self.seam_links: list[tuple[int, int]] = []
        for bottom_or_top in ((0, 0), (3, 3)):
            right_index, left_index = bottom_or_top
            self.seam_links.append(
                (
                    vertex("right_front_center", right_index),
                    vertex("left_front_center", left_index),
                )
            )
            self.seam_links.append(
                (
                    vertex("right_back", right_index),
                    vertex("left_back", left_index),
                )
            )
        for side in ("right", "left"):
            self.seam_links.extend(
                (
                    (
                        vertex(f"{side}_front_center", 1),
                        vertex(f"{side}_front_side", 0),
                    ),
                    (
                        vertex(f"{side}_front_center", 2),
                        vertex(f"{side}_front_side", 3),
                    ),
                    (
                        vertex(f"{side}_front_side", 1),
                        vertex(f"{side}_back", 1),
                    ),
                    (
                        vertex(f"{side}_front_side", 2),
                        vertex(f"{side}_back", 2),
                    ),
                )
            )


def _cylindrical_body() -> np.ndarray:
    vertices = []
    for y in np.linspace(0.0, 10.0, 5):
        for angle in np.linspace(0.0, math.tau, 48, endpoint=False):
            vertices.append(
                [10.0 * math.sin(angle), y, -10.0 * math.cos(angle)]
            )
    return np.asarray(vertices, dtype=float)


class PanelBoundaryTests(unittest.TestCase):
    def test_horizontal_intersection_uses_true_boundary(self) -> None:
        panel = _Panel(7.0)
        low, high = panel_horizontal_bounds(panel, 4.0)
        self.assertAlmostEqual(0.0, low)
        self.assertAlmostEqual(7.0, high)


class BodyAwareShellTests(unittest.TestCase):
    def test_surface_cache_does_not_quantize_nearby_cloth_vertices(self) -> None:
        surface = _TorsoSurface(_cylindrical_body(), clearance_cm=1.5)

        first = surface.point(5.0, 0.4, 1.0)
        second = surface.point(5.05, 0.405, 1.0)

        self.assertGreater(float(np.linalg.norm(first - second)), 0.01)

    def test_shell_closes_seams_and_respects_anatomical_orientation(self) -> None:
        mesh = _ShellMesh()
        diagnostics = assemble_body_aware_shell(
            mesh,
            _cylindrical_body(),
            clearance_cm=1.5,
        )
        vertices = np.asarray(mesh.vertices, dtype=float)

        self.assertEqual(6, diagnostics.panel_count)
        self.assertEqual(24, diagnostics.vertex_count)
        self.assertAlmostEqual(0.0, diagnostics.maximum_seam_separation_cm)
        for first, second in mesh.seam_links:
            np.testing.assert_allclose(vertices[first], vertices[second])

        right_front = mesh.verts_loc_glob[("right_front_center", 0)]
        right_back = mesh.verts_loc_glob[("right_back", 0)]
        right_side = mesh.verts_loc_glob[("right_front_side", 1)]
        left_side = mesh.verts_loc_glob[("left_front_side", 1)]
        self.assertGreater(vertices[right_front, 2], 0.0)
        self.assertLess(vertices[right_back, 2], 0.0)
        self.assertGreater(vertices[right_side, 0], 0.0)
        self.assertLess(vertices[left_side, 0], 0.0)

    def test_live_profile_staging_uses_measured_surface_without_moving_height(self) -> None:
        mesh = _ShellMesh()
        source = np.asarray(mesh.vertices, dtype=float).copy()

        def section(height: float, radius: float) -> dict[str, object]:
            points = []
            for angle in np.linspace(-math.pi, math.pi, 48, endpoint=False):
                points.append(
                    {
                        "angleRadians": float(angle),
                        "xCm": float(radius * math.cos(angle)),
                        "yCm": float(radius * math.sin(angle)),
                    }
                )
            return {
                "heightCm": height,
                "centerXCm": 0.0,
                "centerYCm": 0.0,
                "surfacePoints": points,
            }

        profile = {
            "schemaVersion": "patterna.live-body-profile/1.1",
            "sections": [section(0.0, 10.0), section(10.0, 10.0)],
        }
        diagnostics = arrange_independent_body_aware_panels(
            mesh,
            _cylindrical_body(),
            clearance_cm=1.0,
            body_profile=profile,
            upper_blend_start_cm=20.0,
            upper_blend_end_cm=30.0,
        )
        vertices = np.asarray(mesh.vertices, dtype=float)

        self.assertEqual(2, diagnostics.body_slice_count)
        np.testing.assert_array_equal(vertices[:, 1], source[:, 1])
        self.assertTrue(np.isfinite(vertices).all())

    def test_arap_preassembly_reduces_seams_without_changing_topology(self) -> None:
        mesh = _ShellMesh()
        source = np.asarray(mesh.vertices, dtype=float).copy()

        def section(height: float) -> dict[str, object]:
            return {
                "heightCm": height,
                "centerXCm": 0.0,
                "centerYCm": 0.0,
                "surfacePoints": [
                    {
                        "angleRadians": float(angle),
                        "xCm": float(10.0 * math.cos(angle)),
                        "yCm": float(10.0 * math.sin(angle)),
                    }
                    for angle in np.linspace(-math.pi, math.pi, 48, endpoint=False)
                ],
            }

        profile = {
            "schemaVersion": "patterna.live-body-profile/1.1",
            "sections": [section(0.0), section(10.0)],
        }
        diagnostics = preassemble_body_aware_seams(
            mesh,
            _cylindrical_body(),
            profile,
            clearance_cm=1.0,
            seam_constraint_weight=20.0,
            arap_iterations=5,
        )
        vertices = np.asarray(mesh.vertices, dtype=float)

        self.assertEqual(len(source), diagnostics.vertex_count)
        self.assertLess(
            diagnostics.maximum_seam_separation_cm,
            diagnostics.initial_maximum_seam_separation_cm,
        )
        self.assertTrue(np.isfinite(vertices).all())

    def test_independent_panel_staging_preserves_topology_and_anatomical_sides(self) -> None:
        mesh = _ShellMesh()
        source = np.asarray(mesh.vertices, dtype=float).copy()

        diagnostics = arrange_independent_body_aware_panels(
            mesh,
            _cylindrical_body(),
            clearance_cm=1.5,
        )
        vertices = np.asarray(mesh.vertices, dtype=float)

        self.assertEqual(6, diagnostics.panel_count)
        self.assertEqual(len(source), diagnostics.vertex_count)
        self.assertEqual(len(mesh.seam_links), diagnostics.seam_link_count)
        self.assertGreater(diagnostics.maximum_seam_separation_cm, 0.0)
        self.assertTrue(np.isfinite(vertices).all())
        np.testing.assert_array_equal(vertices[:, 1], source[:, 1])

        right_front = mesh.verts_loc_glob[("right_front_center", 0)]
        right_back = mesh.verts_loc_glob[("right_back", 0)]
        self.assertGreater(vertices[right_front, 2], 0.0)
        self.assertLess(vertices[right_back, 2], 0.0)

    def test_bootstrap_rest_lengths_match_assembled_geometry(self) -> None:
        mesh = _ShellMesh()
        mesh.orig_lens = {(0, 1): 99.0, (1, 2): 99.0}

        diagnostics = set_current_geometry_rest_lengths(mesh)

        self.assertEqual(2, diagnostics["edge_count"])
        self.assertAlmostEqual(8.0, mesh.orig_lens[(0, 1)])
        self.assertAlmostEqual(10.0, mesh.orig_lens[(1, 2)])

    def test_bootstrap_rest_lengths_preserve_zero_gap_sewing_links(self) -> None:
        mesh = _ShellMesh()
        seam_edge = tuple(mesh.seam_links[0])
        first, second = seam_edge
        mesh.vertices[second] = list(mesh.vertices[first])
        mesh.orig_lens = {seam_edge: 0.01, (0, 1): 99.0}

        diagnostics = set_current_geometry_rest_lengths(mesh)

        self.assertEqual(1, diagnostics["edge_count"])
        self.assertEqual(len(mesh.seam_links), diagnostics["excluded_seam_edge_count"])
        self.assertAlmostEqual(0.01, mesh.orig_lens[seam_edge])
        self.assertAlmostEqual(8.0, mesh.orig_lens[(0, 1)])


if __name__ == "__main__":
    unittest.main()
