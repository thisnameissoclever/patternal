from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import unittest

import numpy as np

from tools.polish_newton_vbd import (
    material_triangle_rest_state,
    required_report_path,
    scheduled_seam_rest_lengths,
    sewing_schedule_progress,
    triangle_quality,
    validate_arguments,
)


def valid_arguments() -> argparse.Namespace:
    return argparse.Namespace(
        frames=4,
        substeps=1,
        iterations=1,
        topology_mode="explicit-springs",
        source_report=Path("source.json"),
        style3d_report=None,
        sdf_voxel_size_cm=0.5,
        contact_margin_cm=1.5,
        particle_radius_cm=0.034,
        contact_stiffness=10000.0,
        contact_damping=100.0,
        body_friction=0.45,
        shape_stiffness=10000.0,
        shape_area_stiffness=10000.0,
        shape_damping=50.0,
        bend_stiffness=10.0,
        bend_damping=1.0,
        density_kg_m2=0.12,
        initial_body_clearance_cm=0.35,
        seam_stiffness=10000.0,
        seam_damping=100.0,
        seam_rest_length_cm=0.001,
        sewing_ramp_delay_frames=1,
        sewing_ramp_frames=1,
        sewing_settle_frames=1,
        gravity_m_s2=0.0,
        minimum_initial_triangle_area_cm2=0.01,
        minimum_initial_triangle_angle_deg=5.0,
        maximum_initial_triangle_aspect_ratio=20.0,
        max_seam_separation_cm=0.25,
        max_edge_strain=0.40,
        max_p95_edge_strain=0.15,
        max_p999_edge_strain=0.29,
    )


class VbdPolishUnitTests(unittest.TestCase):
    def test_material_triangle_rest_state_uses_pattern_coordinates(self) -> None:
        poses, areas = material_triangle_rest_state(
            np.asarray([[0.0, 0.0], [100.0, 0.0], [0.0, 100.0]]),
            np.asarray([[0, 1, 2]], dtype=np.int32),
        )

        np.testing.assert_allclose(poses, np.eye(2)[None, ...])
        np.testing.assert_allclose(areas, [0.5])

    def test_validate_arguments_accepts_full_surface_defaults(self) -> None:
        validate_arguments(valid_arguments())

    def test_validate_arguments_rejects_nonpositive_counts(self) -> None:
        for field in ("frames", "substeps", "iterations"):
            with self.subTest(field=field):
                args = valid_arguments()
                setattr(args, field, 0)
                with self.assertRaisesRegex(ValueError, "must be positive"):
                    validate_arguments(args)

    def test_validate_arguments_requires_one_explicit_source_manifest(self) -> None:
        args = valid_arguments()
        args.source_report = None
        with self.assertRaisesRegex(ValueError, "exactly one"):
            validate_arguments(args)

        args.source_report = Path("source.json")
        args.style3d_report = Path("style3d.json")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            validate_arguments(args)

    def test_validate_arguments_requires_full_sewing_schedule(self) -> None:
        args = valid_arguments()
        args.frames = 2
        with self.assertRaisesRegex(ValueError, "delay, ramp, and settling"):
            validate_arguments(args)

    def test_sewing_schedule_smoothly_reduces_rest_lengths(self) -> None:
        initial = np.asarray([0.36, 0.12], dtype=np.float32)
        np.testing.assert_allclose(
            scheduled_seam_rest_lengths(initial, 0.001, 5, 10, 20),
            initial,
        )
        midpoint = scheduled_seam_rest_lengths(initial, 0.001, 20, 10, 20)
        np.testing.assert_allclose(midpoint, initial + (0.001 - initial) * 0.5)
        np.testing.assert_allclose(
            scheduled_seam_rest_lengths(initial, 0.001, 30, 10, 20),
            [0.001, 0.001],
            atol=1.0e-7,
        )
        self.assertEqual(0.0, sewing_schedule_progress(0, 10, 20))
        self.assertEqual(1.0, sewing_schedule_progress(30, 10, 20))

    def test_triangle_quality_reports_regular_triangle(self) -> None:
        quality = triangle_quality(
            np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 0.8660254, 0.0]]),
            np.asarray([[0, 1, 2]], dtype=np.int32),
        )

        self.assertAlmostEqual(0.4330127, quality["minimum_triangle_area_cm2"], places=6)
        self.assertAlmostEqual(60.0, quality["minimum_triangle_angle_deg"], places=5)
        self.assertAlmostEqual(
            1.1547005,
            quality["maximum_triangle_aspect_ratio"],
            places=5,
        )

    def test_required_report_path_rejects_missing_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing"):
            required_report_path({}, "body_mesh_path")

    def test_required_report_path_resolves_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "body.obj"
            source.write_text("v 0 0 0\n", encoding="utf-8")
            self.assertEqual(
                required_report_path({"body_mesh_path": str(source)}, "body_mesh_path"),
                source,
            )


if __name__ == "__main__":
    unittest.main()
