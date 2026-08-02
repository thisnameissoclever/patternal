#!/usr/bin/env python3
"""Unit tests for the hash-bound Style3D product promotion gate."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.promote_style3d_baseline import promote, sha256_file


class PromoteStyle3DBaselineTests(unittest.TestCase):
    def create_fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        solved_mesh = root / "solved.obj"
        physical_mesh = root / "physical.obj"
        collision_body = root / "collision-body.obj"
        source_body = root / "source-body.obj"
        render_mesh = root / "render.obj"
        solved_mesh.write_text("v 0 0 0\n", encoding="utf-8")
        physical_mesh.write_text("v 0 0 0\n", encoding="utf-8")
        collision_body.write_text("v 1 1 1\n", encoding="utf-8")
        source_body.write_text("v 2 2 2\n", encoding="utf-8")
        render_mesh.write_text("v 3 3 3\n", encoding="utf-8")

        evidence_files: dict[str, Path] = {}
        for prefix in (
            "source_report",
            "material_surface",
            "material_coordinates",
            "panel_ownership",
            "rest_lengths",
            "panel_index_map",
            "adapter_implementation",
        ):
            path = root / f"{prefix}.dat"
            path.write_text(prefix, encoding="utf-8")
            evidence_files[prefix] = path
        evidence_files["physical_output_mesh"] = physical_mesh
        solver_files = []
        for index in range(2):
            path = root / f"solver-{index}.py"
            path.write_text(f"solver {index}", encoding="utf-8")
            solver_files.append(path)

        report = {
            "schema_version": "patterna.newton-style3d-report/1.0",
            "accepted": True,
            "rejection_reasons": [],
            "finite_positions": True,
            "static_equilibrium_reached": True,
            "body_collisions": 0,
            "self_collisions": 0,
            "maximum_seam_separation_cm": 0.0,
            "high_strain_edge_fraction": 0.0002,
            "max_high_strain_edge_fraction": 0.0005,
            "ninety_fifth_percentile_edge_strain_ratio": 0.06,
            "max_ninety_fifth_percentile_edge_strain_ratio": 0.15,
            "ninety_ninth_point_ninth_percentile_edge_strain_ratio": 0.25,
            "max_ninety_ninth_point_ninth_percentile_edge_strain_ratio": 0.29,
            "ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio": 0.49,
            "max_ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio": 0.55,
            "output_mesh_path": str(solved_mesh),
            "output_mesh_sha256": sha256_file(solved_mesh),
            "body_mesh_path": str(collision_body),
            "body_mesh_sha256": sha256_file(collision_body),
            "device": "cuda:0",
            "physical_vertex_count": 3,
            "physical_face_count": 1,
            "render_vertex_count": 4,
            "solver_files": {str(path): sha256_file(path) for path in solver_files},
        }
        for prefix, path in evidence_files.items():
            report[f"{prefix}_path"] = str(path)
            report[f"{prefix}_sha256"] = sha256_file(path)
        report_path = root / "report.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")

        fit_report = {
            "schema_version": "patterna.mpfb-avatar-fit/1.2",
            "accepted": True,
            "source_profile_sha256": "a" * 64,
            "output_body": str(source_body),
            "output_body_sha256": sha256_file(source_body),
        }
        fit_report_path = root / "display-fit.json"
        fit_report_path.write_text(json.dumps(fit_report), encoding="utf-8")

        avatar = root / "avatar"
        avatar.mkdir()
        assets = {}
        for key in ("body", "bra", "eyes", "teeth", "eyebrows", "eyelashes", "hair"):
            geometry = f"{key}.obj"
            texture = f"{key}.png"
            geometry_text = "v 2 2 2\n" if key == "body" else "v 0 0 0\n"
            (avatar / geometry).write_text(geometry_text, encoding="utf-8")
            (avatar / texture).write_bytes(f"{key} texture".encode())
            assets[key] = {"geometry": geometry, "texture": texture}
        assets["bra"].update(
            {
                "display_optional": True,
                "maximum_surface_offset_m": 0.0001,
            }
        )
        (avatar / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "patterna.display-avatar/1.0",
                    "assets": assets,
                    "default_garment": {"geometry": "retired.obj"},
                }
            ),
            encoding="utf-8",
        )

        compiler_manifest = {
            "schemaVersion": "patterna.full-garment-usd/1.1",
            "simulation": {"vertexCount": 4, "triangleCount": 1},
            "render": {
                "sourceVertexCount": 4,
                "vertexCount": 8,
                "triangleCount": 4,
                "objSha256": sha256_file(render_mesh),
                "uvCoordinateSource": "authoritative 2D panel rest coordinates",
            },
        }
        compiler_manifest_path = root / "compiler-manifest.json"
        compiler_manifest_path.write_text(json.dumps(compiler_manifest), encoding="utf-8")

        body_report = {
            "schemaVersion": "patterna.mpfb-garmentcode-body/1.0",
            "accepted": True,
            "watertight": True,
            "connectedComponents": 1,
            "sourceBodySha256": sha256_file(source_body),
            "outputBodySha256": sha256_file(collision_body),
        }
        body_report_path = root / "body-report.json"
        body_report_path.write_text(json.dumps(body_report), encoding="utf-8")

        simulation_job = {
            "accepted": True,
            "fitReportPath": str(report_path),
            "bodyPath": str(collision_body),
            "renderMeshPath": str(render_mesh),
            "manifestPath": str(compiler_manifest_path),
            "dressedPoseReportPath": str(body_report_path),
        }
        simulation_job_path = root / "simulation-job.json"
        simulation_job_path.write_text(json.dumps(simulation_job), encoding="utf-8")
        return report_path, simulation_job_path, avatar, fit_report_path

    def test_promotes_one_verified_collider_display_body_and_render_surface(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            report, job, avatar, fit_report = self.create_fixture(root)
            target = root / "target"

            result = promote(report, job, avatar, fit_report, target)

            self.assertTrue(result["accepted"])
            bundled = json.loads(
                (target / "patterna-production-crew-neck.fit.json").read_text()
            )
            manifest = json.loads((target / "Avatar" / "manifest.json").read_text())
            body_report = json.loads(
                (target / "patterna-mpfb-female.report.json").read_text()
            )
            self.assertEqual(
                sha256_file(target / "patterna-production-crew-neck.obj"),
                bundled["bundled_render_mesh_sha256"],
            )
            self.assertEqual(
                sha256_file(target / "patterna-mpfb-female.obj"),
                bundled["bundled_body_mesh_sha256"],
            )
            self.assertNotIn("default_garment", manifest)
            self.assertEqual(
                "../patterna-mpfb-female.obj",
                manifest["collision_geometry"],
            )
            self.assertIn("bra", manifest["assets"])
            self.assertEqual(
                body_report["sourceBodySha256"],
                body_report["bundledSourceBodySha256"],
            )

    def test_rejects_a_report_with_any_self_intersection(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            report_path, job, avatar, fit_report = self.create_fixture(root)
            report = json.loads(report_path.read_text())
            report["self_collisions"] = 1
            report_path.write_text(json.dumps(report), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "zero self intersections"):
                promote(report_path, job, avatar, fit_report, root / "target")

    def test_rejects_a_display_body_that_differs_from_the_collider_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            report, job, avatar, fit_report = self.create_fixture(root)
            (avatar / "body.obj").write_text("v 9 9 9\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "visible body"):
                promote(report, job, avatar, fit_report, root / "target")


if __name__ == "__main__":
    unittest.main()
