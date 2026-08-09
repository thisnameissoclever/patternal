from __future__ import annotations

import math
import unittest

import numpy as np
import trimesh

from tools.mesh_torso_arcs import (
    back_fraction_from_across_measurements,
    measure_front_surface_ruler,
    split_front_back_arc,
)


def _asymmetric_loop(reverse: bool = False) -> np.ndarray:
    angles = np.linspace(math.pi, 0.0, 41)
    front = np.column_stack(
        (
            0.16 * np.cos(angles),
            np.ones_like(angles),
            0.12 * np.sin(angles),
        )
    )
    angles = np.linspace(0.0, -math.pi, 41)
    back = np.column_stack(
        (
            0.16 * np.cos(angles),
            np.ones_like(angles),
            0.07 * np.sin(angles),
        )
    )
    loop = np.vstack((front, back[1:], front[:1]))
    return loop[::-1] if reverse else loop


class TorsoArcTests(unittest.TestCase):
    def test_high_bust_back_fraction_uses_across_body_measurements(self) -> None:
        self.assertAlmostEqual(
            37.0 / (36.7 + 37.0),
            back_fraction_from_across_measurements(36.7, 37.0),
        )

    def test_high_bust_back_fraction_rejects_invalid_measurements(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive and finite"):
            back_fraction_from_across_measurements(math.nan, 37.0)
        with self.assertRaisesRegex(ValueError, "outside the torso domain"):
            back_fraction_from_across_measurements(5.0, 95.0)

    def test_front_surface_ruler_follows_exact_vertical_mesh_section(self) -> None:
        vertices = []
        segments = 64
        for height in (0.90, 1.00, 1.10, 1.20):
            for index in range(segments):
                angle = 2.0 * math.pi * index / segments
                vertices.append(
                    [0.20 * math.cos(angle), height, 0.12 * math.sin(angle)]
                )
        faces = []
        for ring in range(3):
            for index in range(segments):
                following = (index + 1) % segments
                lower = ring * segments
                upper = (ring + 1) * segments
                faces.append(
                    [
                        lower + index,
                        lower + following,
                        upper + following,
                        upper + index,
                    ]
                )
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

        ruler = measure_front_surface_ruler(
            mesh,
            start_height_cm=92.0,
            end_height_cm=118.0,
            start_x_cm=8.0,
            end_x_cm=8.0,
        )

        self.assertAlmostEqual(26.0, ruler, places=5)

    def test_default_mpfb_front_is_positive_depth(self) -> None:
        front, back, front_depth, back_depth = split_front_back_arc(
            _asymmetric_loop()
        )

        self.assertGreater(front, back)
        self.assertGreater(front_depth, back_depth)

    def test_negative_depth_convention_can_be_requested_explicitly(self) -> None:
        front, back, front_depth, back_depth = split_front_back_arc(
            _asymmetric_loop(),
            front_is_positive_depth=False,
        )

        self.assertLess(front, back)
        self.assertLess(front_depth, back_depth)

    def test_loop_direction_does_not_change_the_measurement(self) -> None:
        forward = split_front_back_arc(_asymmetric_loop())
        reversed_loop = split_front_back_arc(_asymmetric_loop(reverse=True))

        for first, second in zip(forward, reversed_loop):
            self.assertAlmostEqual(first, second, places=8)

    def test_explicit_side_seam_depth_preserves_total_circuit(self) -> None:
        default = split_front_back_arc(_asymmetric_loop())
        shifted = split_front_back_arc(
            _asymmetric_loop(),
            side_seam_depth_cm=3.0,
        )

        self.assertAlmostEqual(default[0] + default[1], shifted[0] + shifted[1], places=8)
        self.assertNotAlmostEqual(default[0], shifted[0], places=4)

    def test_non_finite_section_is_rejected(self) -> None:
        loop = _asymmetric_loop()
        loop[4, 2] = math.nan

        with self.assertRaisesRegex(ValueError, "non-finite"):
            split_front_back_arc(loop)


if __name__ == "__main__":
    unittest.main()
