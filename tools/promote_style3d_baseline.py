#!/usr/bin/env python3
"""Promote one hash-bound Style3D job and its matching display avatar."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct


REQUIRED_DISPLAY_ASSETS = (
    "body",
    "bra",
    "eyes",
    "teeth",
    "eyebrows",
    "eyelashes",
    "hair",
)
MAXIMUM_BRA_SURFACE_OFFSET_M = 0.0001


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def obj_vertex_digest(path: Path) -> tuple[str, int]:
    """Hash only OBJ vertex coordinates so UV-enabled and collider OBJs can match."""
    digest = hashlib.sha256()
    vertex_count = 0
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            if not line.startswith("v "):
                continue
            values = line.split()[1:4]
            if len(values) != 3:
                raise ValueError(f"Invalid OBJ vertex in {path}")
            digest.update(struct.pack("<3d", *(float(value) for value in values)))
            vertex_count += 1
    if vertex_count == 0:
        raise ValueError(f"OBJ has no vertices: {path}")
    return digest.hexdigest(), vertex_count


def require_file(path: Path, description: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Missing {description}: {resolved}")
    return resolved


def require_json(path: Path, description: str) -> tuple[Path, dict[str, object]]:
    resolved = require_file(path, description)
    value = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{description} must contain one JSON object.")
    return resolved, value


def require_report_file(report: dict[str, object], path_key: str, hash_key: str) -> Path:
    path = require_file(Path(str(report[path_key])), path_key)
    expected_hash = str(report[hash_key]).lower()
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise ValueError(
            f"{path_key} hash mismatch: expected {expected_hash}, found {actual_hash}"
        )
    return path


def same_path(first: Path, second: Path) -> bool:
    return first.resolve() == second.resolve()


def validate_style3d_report(report: dict[str, object]) -> tuple[Path, Path]:
    if report.get("schema_version") != "patterna.newton-style3d-report/1.0":
        raise ValueError("Style3D promotion requires report schema 1.0.")
    if report.get("accepted") is not True or report.get("rejection_reasons") != []:
        raise ValueError("Style3D promotion requires an accepted report without rejections.")
    if report.get("static_equilibrium_reached") is not True:
        raise ValueError("Style3D promotion requires static equilibrium.")
    if report.get("finite_positions") is not True:
        raise ValueError("Style3D promotion requires finite solver positions.")
    if int(report.get("body_collisions", -1)) != 0:
        raise ValueError("Style3D promotion requires zero body intersections.")
    if int(report.get("self_collisions", -1)) != 0:
        raise ValueError("Style3D promotion requires zero self intersections.")
    if float(report.get("maximum_seam_separation_cm", -1.0)) > 1.0e-6:
        raise ValueError("Style3D promotion requires exact seam closure.")
    if float(report.get("high_strain_edge_fraction", 1.0)) > float(
        report.get("max_high_strain_edge_fraction", 0.0)
    ):
        raise ValueError("Style3D promotion requires the high-strain tail gate.")
    for value_key, limit_key in (
        (
            "ninety_fifth_percentile_edge_strain_ratio",
            "max_ninety_fifth_percentile_edge_strain_ratio",
        ),
        (
            "ninety_ninth_point_ninth_percentile_edge_strain_ratio",
            "max_ninety_ninth_point_ninth_percentile_edge_strain_ratio",
        ),
        (
            "ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio",
            "max_ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio",
        ),
    ):
        if float(report.get(value_key, float("inf"))) > float(
            report.get(limit_key, float("-inf"))
        ):
            raise ValueError(f"Style3D promotion requires {value_key} to pass.")
    for prefix in (
        "source_report",
        "material_surface",
        "material_coordinates",
        "panel_ownership",
        "rest_lengths",
        "panel_index_map",
        "physical_output_mesh",
        "adapter_implementation",
    ):
        require_report_file(report, f"{prefix}_path", f"{prefix}_sha256")
    solver_files = report.get("solver_files")
    if not isinstance(solver_files, dict) or len(solver_files) < 2:
        raise ValueError("Style3D promotion requires exact solver implementation files.")
    for path, expected_hash in solver_files.items():
        solver_path = require_file(Path(str(path)), "Style3D solver implementation")
        if sha256_file(solver_path) != str(expected_hash).lower():
            raise ValueError(f"Style3D solver hash mismatch: {solver_path}")
    solved_surface = require_report_file(
        report,
        "output_mesh_path",
        "output_mesh_sha256",
    )
    collision_body = require_report_file(
        report,
        "body_mesh_path",
        "body_mesh_sha256",
    )
    return solved_surface, collision_body


def validate_display_fit_report(
    report_path: Path,
) -> tuple[Path, dict[str, object], Path]:
    resolved, report = require_json(report_path, "display avatar fit report")
    if report.get("schema_version") != "patterna.mpfb-avatar-fit/1.2":
        raise ValueError("Display avatar promotion requires MPFB fit report schema 1.2.")
    if report.get("accepted") is not True:
        raise ValueError("Display avatar promotion requires an accepted MPFB fit report.")
    source_body = require_file(Path(str(report["output_body"])), "MPFB source body")
    if sha256_file(source_body) != str(report["output_body_sha256"]).lower():
        raise ValueError("The MPFB fit report does not match its output body.")
    return resolved, report, source_body


def validate_display_manifest(
    source_directory: Path,
    source_body: Path,
) -> tuple[dict[str, object], list[tuple[Path, str]]]:
    source_directory = source_directory.resolve()
    manifest_path, manifest = require_json(
        source_directory / "manifest.json",
        "display avatar manifest",
    )
    if manifest.get("schema_version") != "patterna.display-avatar/1.0":
        raise ValueError("Display avatar promotion requires manifest schema 1.0.")
    assets = manifest.get("assets")
    if not isinstance(assets, dict):
        raise ValueError("Display avatar manifest has no asset map.")
    if set(assets) != set(REQUIRED_DISPLAY_ASSETS):
        raise ValueError("Display avatar promotion requires the complete seven-part stack.")
    copies: list[tuple[Path, str]] = []
    geometry_paths: dict[str, Path] = {}
    for key in REQUIRED_DISPLAY_ASSETS:
        asset = assets.get(key)
        if not isinstance(asset, dict):
            raise ValueError(f"Display avatar is missing {key}.")
        for property_name in ("geometry", "texture"):
            relative_name = str(asset.get(property_name, ""))
            if not relative_name or Path(relative_name).name != relative_name:
                raise ValueError(f"Display avatar {key} has an invalid {property_name} path.")
            path = require_file(
                source_directory / relative_name,
                f"display avatar {key} {property_name}",
            )
            copies.append((path, relative_name))
            if property_name == "geometry":
                geometry_paths[key] = path
    bra = assets["bra"]
    if bra.get("display_optional") is not True:
        raise ValueError("The visible bra must remain a display-only option.")
    bra_offset = float(bra.get("maximum_surface_offset_m", float("inf")))
    if not 0.0 <= bra_offset <= MAXIMUM_BRA_SURFACE_OFFSET_M:
        raise ValueError("The visible bra exceeds the 0.10 mm display-shell limit.")
    source_digest, source_count = obj_vertex_digest(source_body)
    display_digest, display_count = obj_vertex_digest(geometry_paths["body"])
    if source_count != display_count or source_digest != display_digest:
        raise ValueError("The visible body does not match the fitted source-body coordinates.")
    manifest.pop("default_garment", None)
    manifest["collision_geometry"] = "../patterna-mpfb-female.obj"
    manifest["source_body_geometry_sha256"] = source_digest
    manifest["source_body_vertex_count"] = source_count
    return manifest, copies


def validate_simulation_job(
    job_path: Path,
    report_path: Path,
    report: dict[str, object],
    collision_body: Path,
    display_fit: dict[str, object],
) -> tuple[Path, Path, dict[str, object], Path, dict[str, object]]:
    resolved_job_path, job = require_json(job_path, "simulation job")
    if job.get("accepted") is not True:
        raise ValueError("Promotion requires an accepted simulation job.")
    if not same_path(Path(str(job["fitReportPath"])), report_path):
        raise ValueError("The simulation job is not bound to the supplied Style3D report.")
    if not same_path(Path(str(job["bodyPath"])), collision_body):
        raise ValueError("The simulation job body differs from the Style3D collision body.")

    render_mesh = require_file(Path(str(job["renderMeshPath"])), "compiled render mesh")
    compiler_manifest_path, compiler_manifest = require_json(
        Path(str(job["manifestPath"])),
        "compiled garment manifest",
    )
    if compiler_manifest.get("schemaVersion") != "patterna.full-garment-usd/1.1":
        raise ValueError("Promotion requires compiled garment manifest schema 1.1.")
    render = compiler_manifest.get("render")
    simulation = compiler_manifest.get("simulation")
    if not isinstance(render, dict) or not isinstance(simulation, dict):
        raise ValueError("Compiled garment manifest is missing render or simulation evidence.")
    if sha256_file(render_mesh) != str(render.get("objSha256", "")).lower():
        raise ValueError("Compiled render mesh hash does not match its manifest.")
    expected_source_vertices = int(report.get("render_vertex_count", -1))
    if int(render.get("sourceVertexCount", -2)) != expected_source_vertices:
        raise ValueError("Compiled render surface is not derived from the accepted Style3D surface.")
    if int(simulation.get("vertexCount", -2)) != expected_source_vertices:
        raise ValueError("Compiler simulation topology differs from the accepted Style3D surface.")
    if int(simulation.get("triangleCount", -2)) != int(report["physical_face_count"]):
        raise ValueError("Compiler triangle topology differs from the accepted Style3D surface.")
    if render.get("uvCoordinateSource") != "authoritative 2D panel rest coordinates":
        raise ValueError("Compiled render mesh has no authoritative pattern-space UV evidence.")

    body_report_path, body_report = require_json(
        Path(str(job["dressedPoseReportPath"])),
        "prepared collision-body report",
    )
    if body_report.get("schemaVersion") != "patterna.mpfb-garmentcode-body/1.0":
        raise ValueError("Prepared collision body requires report schema 1.0.")
    if (
        body_report.get("accepted") is not True
        or body_report.get("watertight") is not True
        or int(body_report.get("connectedComponents", -1)) != 1
    ):
        raise ValueError("Prepared collision body must be accepted, watertight, and contiguous.")
    if str(body_report.get("outputBodySha256", "")).lower() != str(
        report["body_mesh_sha256"]
    ).lower():
        raise ValueError("Prepared collision-body report differs from the Style3D body.")
    if str(body_report.get("sourceBodySha256", "")).lower() != str(
        display_fit["output_body_sha256"]
    ).lower():
        raise ValueError("Prepared collider and visible avatar do not share one source body.")
    return (
        resolved_job_path,
        render_mesh,
        compiler_manifest,
        body_report_path,
        body_report,
    )


def promote(
    report_path: Path,
    simulation_job_path: Path,
    display_avatar_directory: Path,
    display_fit_report_path: Path,
    target_directory: Path,
) -> dict[str, object]:
    report_path, report = require_json(report_path, "Style3D report")
    solved_surface, collision_body = validate_style3d_report(report)
    display_fit_path, display_fit, source_body = validate_display_fit_report(
        display_fit_report_path
    )
    avatar_manifest, avatar_copies = validate_display_manifest(
        display_avatar_directory,
        source_body,
    )
    (
        simulation_job_path,
        render_mesh,
        compiler_manifest,
        body_report_path,
        body_report,
    ) = validate_simulation_job(
        simulation_job_path,
        report_path,
        report,
        collision_body,
        display_fit,
    )

    target_directory = target_directory.resolve()
    target_avatar_directory = target_directory / "Avatar"
    target_avatar_directory.mkdir(parents=True, exist_ok=True)
    garment_target = target_directory / "patterna-production-crew-neck.obj"
    garment_manifest_target = target_directory / "patterna-production-crew-neck.compile.json"
    body_target = target_directory / "patterna-mpfb-female.obj"
    source_body_target = target_directory / "patterna-mpfb-female.source.obj"
    body_report_target = target_directory / "patterna-mpfb-female.report.json"
    display_fit_target = target_directory / "patterna-full-bust-default-fit-report.json"
    evidence_target = target_directory / "patterna-production-crew-neck.fit.json"

    shutil.copyfile(render_mesh, garment_target)
    shutil.copyfile(collision_body, body_target)
    shutil.copyfile(source_body, source_body_target)
    shutil.copyfile(display_fit_path, display_fit_target)
    for source, relative_name in avatar_copies:
        shutil.copyfile(source, target_avatar_directory / relative_name)
    (target_avatar_directory / "manifest.json").write_text(
        json.dumps(avatar_manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    garment_manifest_target.write_text(
        json.dumps(compiler_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    bundled_body_report = dict(body_report)
    bundled_body_report.update(
        {
            "bundledSourceBody": source_body_target.name,
            "bundledSourceBodySha256": sha256_file(source_body_target),
            "bundledSourceFitReport": display_fit_target.name,
            "bundledSourceFitReportSha256": sha256_file(display_fit_target),
            "bundledOutputBody": body_target.name,
            "bundledOutputBodySha256": sha256_file(body_target),
            "bundledSourceReportSha256": sha256_file(body_report_path),
        }
    )
    body_report_target.write_text(
        json.dumps(bundled_body_report, indent=2) + "\n",
        encoding="utf-8",
    )

    bundled_report = dict(report)
    bundled_report.update(
        {
            "bundled_source_report_sha256": sha256_file(report_path),
            "bundled_simulation_job_sha256": sha256_file(simulation_job_path),
            "bundled_solved_surface": solved_surface.name,
            "bundled_solved_surface_sha256": sha256_file(solved_surface),
            "bundled_render_mesh": garment_target.name,
            "bundled_render_mesh_sha256": sha256_file(garment_target),
            "bundled_compiler_manifest": garment_manifest_target.name,
            "bundled_compiler_manifest_sha256": sha256_file(garment_manifest_target),
            "bundled_body_mesh": body_target.name,
            "bundled_body_mesh_sha256": sha256_file(body_target),
            "bundled_source_body": source_body_target.name,
            "bundled_source_body_sha256": sha256_file(source_body_target),
            "bundled_display_manifest": "Avatar/manifest.json",
            "bundled_display_manifest_sha256": sha256_file(
                target_avatar_directory / "manifest.json"
            ),
        }
    )
    evidence_target.write_text(
        json.dumps(bundled_report, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "accepted": True,
        "report": str(evidence_target),
        "garment": str(garment_target),
        "garment_sha256": sha256_file(garment_target),
        "body": str(body_target),
        "body_sha256": sha256_file(body_target),
        "source_body": str(source_body_target),
        "source_body_sha256": sha256_file(source_body_target),
        "display_avatar_manifest": str(target_avatar_directory / "manifest.json"),
        "physical_vertex_count": report["physical_vertex_count"],
        "physical_face_count": report["physical_face_count"],
        "render_vertex_count": compiler_manifest["render"]["vertexCount"],
        "render_face_count": compiler_manifest["render"]["triangleCount"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--simulation-job", required=True, type=Path)
    parser.add_argument("--display-avatar", required=True, type=Path)
    parser.add_argument("--display-fit-report", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            promote(
                args.report,
                args.simulation_job,
                args.display_avatar,
                args.display_fit_report,
                args.target,
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
