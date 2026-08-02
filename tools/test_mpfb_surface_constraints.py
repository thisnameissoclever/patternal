from __future__ import annotations

import math
import unittest

from tools.mpfb_surface_constraints import (
    enforce_bust_to_high_chest_surface,
    enforce_horizontal_torso_circumference,
    enforce_landmark_tape_length,
    enforce_waist_to_underbust_surface,
    measure_horizontal_section,
)


def elliptical_torso(
    circumferences_cm: list[float],
    heights_m: list[float],
    *,
    segments: int = 64,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int, int]]]:
    vertices: list[tuple[float, float, float]] = []
    for circumference_cm, height_m in zip(circumferences_cm, heights_m):
        radius_m = circumference_cm / 100.0 / (2.0 * math.pi)
        for index in range(segments):
            angle = 2.0 * math.pi * index / segments
            vertices.append((
                radius_m * math.cos(angle),
                radius_m * 0.72 * math.sin(angle),
                height_m,
            ))
    faces: list[tuple[int, int, int, int]] = []
    for ring in range(len(heights_m) - 1):
        lower = ring * segments
        upper = (ring + 1) * segments
        for index in range(segments):
            following = (index + 1) % segments
            faces.append((
                lower + index,
                lower + following,
                upper + following,
                upper + index,
            ))
    return vertices, faces


class MpfbSurfaceConstraintTests(unittest.TestCase):
    def test_nonhorizontal_landmark_tape_fits_without_flattening_height(self) -> None:
        segments = 64
        vertices, _ = elliptical_torso([92.0], [1.00], segments=segments)
        vertices = [
            (x, y, z + 0.003 * math.sin(2.0 * math.pi * index / segments))
            for index, (x, y, z) in enumerate(vertices)
        ]
        landmark = tuple(range(segments)) + (0,)
        before_heights = [vertices[index][2] for index in landmark]
        before_length_cm = sum(
            math.dist(vertices[first], vertices[second]) * 100.0
            for first, second in zip(landmark, landmark[1:])
        )
        target_length_cm = before_length_cm * 0.95
        corrected, report = enforce_landmark_tape_length(
            vertices,
            landmark,
            target_length_cm=target_length_cm,
            name="test-underbust",
        )

        self.assertTrue(report.applied)
        self.assertTrue(report.accepted)
        self.assertAlmostEqual(target_length_cm, report.length_after_cm, delta=0.15)
        self.assertLess(report.radial_scale, 1.0)
        self.assertEqual(
            before_heights,
            [corrected[index][2] for index in landmark],
        )

    def test_horizontal_section_measures_centered_torso(self) -> None:
        vertices, faces = elliptical_torso([100.0, 100.0], [0.0, 1.0])
        section = measure_horizontal_section(vertices, faces, 0.5)
        expected = measure_horizontal_section(vertices, faces, 0.25).perimeter_cm
        self.assertAlmostEqual(section.perimeter_cm, expected, places=6)
        self.assertAlmostEqual(section.center_x_m, 0.0, places=6)
        self.assertAlmostEqual(section.center_y_m, 0.0, places=6)

    def test_false_upper_waist_is_expanded_to_measurement_envelope(self) -> None:
        heights = [-0.05, 0.0, 0.25, 0.50, 0.75, 1.0, 1.05]
        vertices, faces = elliptical_torso(
            [105.0, 100.0, 90.0, 72.0, 96.0, 110.0, 115.0],
            heights,
        )
        segments = 64
        waist_indices = tuple(range(segments, segments * 2))
        underbust_indices = tuple(range(segments * 5, segments * 6))
        corrected, report = enforce_waist_to_underbust_surface(
            vertices,
            faces,
            waist_indices,
            underbust_indices,
            target_waist_cm=82.0,
            target_underbust_cm=90.0,
            tolerance_cm=0.15,
        )
        self.assertTrue(report.applied)
        self.assertTrue(report.accepted)
        self.assertGreater(report.maximum_deficit_before_cm, 10.0)
        self.assertLessEqual(report.maximum_deficit_after_cm, 0.15)
        self.assertGreater(report.minimum_after_cm, report.minimum_before_cm)
        self.assertEqual(corrected[:segments], vertices[:segments])
        self.assertEqual(corrected[-segments:], vertices[-segments:])

    def test_valid_surface_is_not_changed(self) -> None:
        heights = [0.0, 0.5, 1.0]
        vertices, faces = elliptical_torso([100.0, 105.0, 110.0], heights)
        segments = 64
        corrected, report = enforce_waist_to_underbust_surface(
            vertices,
            faces,
            tuple(range(segments)),
            tuple(range(segments * 2, segments * 3)),
            target_waist_cm=70.0,
            target_underbust_cm=78.0,
        )
        self.assertEqual(corrected, vertices)
        self.assertFalse(report.applied)
        self.assertTrue(report.accepted)
        self.assertEqual(report.affected_vertex_count, 0)

    def test_exact_tape_circumference_controls_collision_surface(self) -> None:
        heights = [0.90, 1.00, 1.10]
        vertices, faces = elliptical_torso([108.0, 110.0, 106.0], heights)
        segments = 64
        landmark_indices = tuple(range(segments, segments * 2))
        before = measure_horizontal_section(vertices, faces, 1.00)

        corrected, report = enforce_horizontal_torso_circumference(
            vertices,
            faces,
            landmark_indices,
            target_circumference_cm=85.0,
            name="test-tape",
        )

        after = measure_horizontal_section(corrected, faces, 1.00)
        self.assertTrue(report.applied)
        self.assertTrue(report.accepted)
        self.assertGreater(before.perimeter_cm, 85.0)
        self.assertAlmostEqual(85.0, after.perimeter_cm, delta=0.20)
        self.assertLess(report.depth_scale, 1.0)
        for index in range(segments):
            self.assertEqual(vertices[index], corrected[index])
        for before_point, after_point in zip(vertices, corrected):
            self.assertAlmostEqual(before_point[0], after_point[0], places=10)
            self.assertAlmostEqual(before_point[2], after_point[2], places=10)

    def test_tape_uses_radial_scaling_when_width_exceeds_target(self) -> None:
        vertices, faces = elliptical_torso(
            [108.0, 110.0, 106.0],
            [0.90, 1.00, 1.10],
        )
        segments = 64
        corrected, report = enforce_horizontal_torso_circumference(
            vertices,
            faces,
            tuple(range(segments, segments * 2)),
            target_circumference_cm=60.0,
            name="radial-test-tape",
        )

        after = measure_horizontal_section(corrected, faces, 1.00)
        self.assertTrue(report.accepted)
        self.assertEqual("radial", report.scale_mode)
        self.assertAlmostEqual(60.0, after.perimeter_cm, delta=0.20)
        self.assertNotAlmostEqual(vertices[segments][0], corrected[segments][0])

    def test_infeasible_intermediate_tape_returns_rejected_candidate(self) -> None:
        vertices, faces = elliptical_torso(
            [108.0, 110.0, 106.0],
            [0.90, 1.00, 1.10],
        )
        segments = 64
        corrected, report = enforce_horizontal_torso_circumference(
            vertices,
            faces,
            tuple(range(segments, segments * 2)),
            target_circumference_cm=0.1,
            name="infeasible-intermediate-tape",
        )

        after = measure_horizontal_section(corrected, faces, 1.00)
        self.assertFalse(report.accepted)
        self.assertEqual("radial", report.scale_mode)
        self.assertAlmostEqual(after.perimeter_cm, report.circumference_after_cm)
        self.assertGreater(after.perimeter_cm, report.target_circumference_cm)

    def test_high_chest_depth_is_reconciled_without_changing_width(self) -> None:
        heights = [0.95, 1.00, 1.05, 1.10, 1.15]
        vertices, faces = elliptical_torso(
            [112.0, 112.0, 110.0, 106.0, 104.0],
            heights,
        )
        segments = 64
        bust_indices = tuple(range(segments, segments * 2))
        high_chest_indices = tuple(range(segments * 4, segments * 5))
        before_bust = measure_horizontal_section(vertices, faces, 1.0)
        before_high = measure_horizontal_section(vertices, faces, 1.15)
        target_high = before_high.perimeter_cm - 8.0

        corrected, report = enforce_bust_to_high_chest_surface(
            vertices,
            faces,
            bust_indices,
            high_chest_indices,
            target_high_chest_cm=target_high,
            tolerance_cm=0.20,
        )

        after_high = measure_horizontal_section(corrected, faces, 1.15)
        self.assertTrue(report.applied)
        self.assertTrue(report.accepted)
        self.assertAlmostEqual(target_high, after_high.perimeter_cm, delta=0.20)
        self.assertAlmostEqual(
            before_bust.perimeter_cm,
            report.bust_horizontal_circumference_cm,
            places=6,
        )
        self.assertLess(report.minimum_depth_scale, 1.0)
        for index in range(segments * 2):
            self.assertEqual(
                corrected[index],
                vertices[index],
                "The upper-chest correction must not move bust or lower vertices.",
            )
        for before, after in zip(vertices, corrected):
            self.assertAlmostEqual(before[0], after[0], places=10)
            self.assertAlmostEqual(before[2], after[2], places=10)


if __name__ == "__main__":
    unittest.main()
