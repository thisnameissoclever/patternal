#!/usr/bin/env python3
"""Run and gate Patterna's reversible Blender cloth backend candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIAGNOSTIC_PYTHON = Path(".venv-garmentcode/Scripts/python.exe")
DEFAULT_AVATAR_MANIFEST = Path("Patternal/Assets/Production/Avatar/manifest.json")
DEFAULT_BODY = Path("Patternal/Assets/Production/patterna-mpfb-female.obj")
DEFAULT_GARMENT = Path("Patternal/Assets/Production/patterna-production-crew-neck.obj")
DEFAULT_SIMULATION_GARMENT = Path(
    "artifacts/full-panel-validation/warp-zero-contact-v3/"
    "PatternaFullPanel/PatternaFullPanel_sim.obj"
)
DEFAULT_OUTPUT_DIRECTORY = Path("artifacts/blender-cloth-vertical-slice/current")

MAXIMUM_MOTION_MM_PER_FRAME = 0.50
MAXIMUM_MEAN_MOTION_MM_PER_FRAME = 0.05
MAXIMUM_REFINEMENT_STRAIN = 0.40
MAXIMUM_REFINEMENT_P95_STRAIN = 0.15
MAXIMUM_REFINEMENT_P999_STRAIN = 0.29


def default_blender() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        tools_root = Path(local_app_data) / "Patterna" / "Tools"
        managed_runtimes = sorted(
            tools_root.glob("Blender-*/blender.exe"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if managed_runtimes:
            return managed_runtimes[0]

    repository_runtime = REPO_ROOT / (
        ".runtime/blender/blender-4.5.9-windows-x64/blender.exe"
    )
    return repository_runtime


def resolve(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_file(path: Path, description: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {description}: {path}")
    return path


def read_json(path: Path) -> dict[str, object]:
    with require_file(path, "pipeline JSON").open("r", encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def run(command: list[str], description: str) -> None:
    print(f"Patterna: {description}")
    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"{description} exited with code {completed.returncode}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", type=Path, default=default_blender())
    parser.add_argument(
        "--diagnostic-python",
        type=Path,
        default=DEFAULT_DIAGNOSTIC_PYTHON,
    )
    parser.add_argument("--avatar-manifest", type=Path, default=DEFAULT_AVATAR_MANIFEST)
    parser.add_argument("--body", type=Path, default=DEFAULT_BODY)
    parser.add_argument("--garment", type=Path, default=DEFAULT_GARMENT)
    parser.add_argument(
        "--simulation-garment",
        type=Path,
        default=DEFAULT_SIMULATION_GARMENT,
    )
    parser.add_argument(
        "--simulation-source",
        choices=("remesh", "external"),
        default="remesh",
    )
    parser.add_argument(
        "--external-edge-mode",
        choices=("surface-only", "sewing-springs"),
        default="surface-only",
        help=(
            "Treat loose edges in an external OBJ as export artifacts by default; "
            "enable sewing-springs only for an unwelded sewing proxy."
        ),
    )
    parser.add_argument("--simulation-target-faces", type=int, default=8000)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--quality", type=int, default=8)
    parser.add_argument(
        "--fabric-preset",
        choices=(
            "cotton-jersey",
            "cotton-poplin",
            "cotton-jersey-stable",
            "cotton-jersey-damped",
        ),
        default="cotton-jersey",
    )
    parser.add_argument("--resolution-x", type=int, default=720)
    parser.add_argument("--resolution-y", type=int, default=900)
    parser.add_argument(
        "--render-view-set",
        choices=("all", "front", "none"),
        default="all",
    )
    parser.add_argument(
        "--collision-start-horizontal-scale",
        type=float,
        default=1.0,
    )
    parser.add_argument("--collision-ramp-frames", type=int, default=0)
    parser.add_argument("--skip-solve", action="store_true")
    return parser.parse_args()


def append_limit_failure(
    reasons: list[str],
    value: object,
    limit: float,
    description: str,
) -> None:
    if not isinstance(value, (int, float)):
        reasons.append(f"missing {description}")
    elif not float(value) <= limit:
        reasons.append(f"{description} {float(value):.6f} exceeds {limit:.6f}")


def main() -> int:
    args = parse_args()
    blender = require_file(resolve(args.blender), "Blender executable")
    diagnostic_python = require_file(
        resolve(args.diagnostic_python),
        "diagnostic Python executable",
    )
    manifest = require_file(resolve(args.avatar_manifest), "avatar manifest")
    body = require_file(resolve(args.body), "collision body")
    garment = require_file(resolve(args.garment), "source garment")
    simulation_garment = (
        require_file(
            resolve(args.simulation_garment),
            "source simulation garment",
        )
        if args.simulation_source == "external"
        else None
    )
    output_directory = resolve(args.output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    if not args.skip_solve:
        blender_command = [
            str(blender),
            "-b",
            "--factory-startup",
            "-P",
            str(REPO_ROOT / "tools" / "refine_garment_blender_cloth.py"),
            "--",
            "--avatar-manifest",
            str(manifest),
            "--garment",
            str(garment),
            "--simulation-source",
            args.simulation_source,
            "--simulation-target-faces",
            str(args.simulation_target_faces),
            "--external-edge-mode",
            args.external_edge_mode,
            "--output-directory",
            str(output_directory),
            "--frames",
            str(args.frames),
            "--quality",
            str(args.quality),
            "--fabric-preset",
            args.fabric_preset,
            "--resolution-x",
            str(args.resolution_x),
            "--resolution-y",
            str(args.resolution_y),
            "--render-view-set",
            args.render_view_set,
            "--collision-start-horizontal-scale",
            str(args.collision_start_horizontal_scale),
            "--collision-ramp-frames",
            str(args.collision_ramp_frames),
        ]
        if simulation_garment is not None:
            blender_command.extend(
                ["--simulation-garment", str(simulation_garment)]
            )
        run(
            blender_command,
            "running Blender cloth",
        )

    cloth = require_file(
        output_directory / "garment-simulation-refined-cm.obj",
        "Blender cloth result",
    )
    render_cloth = require_file(
        output_directory / "garment-refined-cm.obj",
        "Blender render result",
    )
    body_report_path = output_directory / "body-intersections-exact.json"
    render_body_report_path = output_directory / "render-body-intersections-exact.json"
    self_report_path = output_directory / "self-intersections-exact.json"

    run(
        [
            str(diagnostic_python),
            str(REPO_ROOT / "tools" / "diagnose_body_intersections.py"),
            "--cloth",
            str(cloth),
            "--body",
            str(body),
            "--device",
            "cuda:0",
            "--output",
            str(body_report_path),
        ],
        "checking exact body intersections",
    )
    run(
        [
            str(diagnostic_python),
            str(REPO_ROOT / "tools" / "diagnose_body_intersections.py"),
            "--cloth",
            str(render_cloth),
            "--body",
            str(body),
            "--device",
            "cuda:0",
            "--output",
            str(render_body_report_path),
        ],
        "checking exact render-surface body intersections",
    )
    run(
        [
            str(diagnostic_python),
            str(REPO_ROOT / "tools" / "diagnose_cloth_self_intersections.py"),
            "--cloth",
            str(cloth),
            "--device",
            "cuda:0",
            "--output",
            str(self_report_path),
        ],
        "checking exact self intersections",
    )

    blender_report_path = output_directory / "report.json"
    blender_report = read_json(blender_report_path)
    body_report = read_json(body_report_path)
    render_body_report = read_json(render_body_report_path)
    self_report = read_json(self_report_path)
    motion = blender_report.get("motion")
    strain = blender_report.get("refinement_strain")
    motion = motion if isinstance(motion, dict) else {}
    strain = strain if isinstance(strain, dict) else {}

    reasons: list[str] = []
    if body_report.get("count") != 0:
        reasons.append(f"body intersections {body_report.get('count')} exceed 0")
    if render_body_report.get("count") != 0:
        reasons.append(
            "render-surface body intersections "
            f"{render_body_report.get('count')} exceed 0"
        )
    if self_report.get("count") != 0:
        reasons.append(f"self intersections {self_report.get('count')} exceed 0")
    append_limit_failure(
        reasons,
        motion.get("maximum_displacement_mm_per_frame"),
        MAXIMUM_MOTION_MM_PER_FRAME,
        "maximum motion in millimeters per frame",
    )
    append_limit_failure(
        reasons,
        motion.get("mean_displacement_mm_per_frame"),
        MAXIMUM_MEAN_MOTION_MM_PER_FRAME,
        "mean motion in millimeters per frame",
    )
    append_limit_failure(
        reasons,
        strain.get("maximum_absolute_strain_ratio"),
        MAXIMUM_REFINEMENT_STRAIN,
        "maximum Blender refinement strain",
    )
    append_limit_failure(
        reasons,
        strain.get("ninety_fifth_percentile_absolute_strain_ratio"),
        MAXIMUM_REFINEMENT_P95_STRAIN,
        "95th-percentile Blender refinement strain",
    )
    append_limit_failure(
        reasons,
        strain.get("ninety_ninth_point_ninth_percentile_absolute_strain_ratio"),
        MAXIMUM_REFINEMENT_P999_STRAIN,
        "99.9th-percentile Blender refinement strain",
    )

    result = {
        "schema_version": "patterna.blender-cloth-pipeline/1.0",
        "accepted": not reasons,
        "rejection_reasons": reasons,
        "source_garment": str(garment),
        "source_garment_sha256": sha256(garment),
        "simulation_source": args.simulation_source,
        "simulation_target_faces": args.simulation_target_faces,
        "source_simulation_garment": (
            str(simulation_garment) if simulation_garment else None
        ),
        "source_simulation_garment_sha256": (
            sha256(simulation_garment) if simulation_garment else None
        ),
        "avatar_manifest": str(manifest),
        "avatar_manifest_sha256": sha256(manifest),
        "collision_body": str(body),
        "collision_body_sha256": sha256(body),
        "cloth_output": str(cloth),
        "cloth_output_sha256": sha256(cloth),
        "render_output": str(render_cloth),
        "render_output_sha256": sha256(render_cloth),
        "limits": {
            "maximum_motion_mm_per_frame": MAXIMUM_MOTION_MM_PER_FRAME,
            "maximum_mean_motion_mm_per_frame": MAXIMUM_MEAN_MOTION_MM_PER_FRAME,
            "maximum_refinement_strain_ratio": MAXIMUM_REFINEMENT_STRAIN,
            "maximum_refinement_p95_strain_ratio": MAXIMUM_REFINEMENT_P95_STRAIN,
            "maximum_refinement_p999_strain_ratio": MAXIMUM_REFINEMENT_P999_STRAIN,
            "maximum_body_intersections": 0,
            "maximum_self_intersections": 0,
        },
        "blender_report": blender_report_path.name,
        "blender_report_sha256": sha256(blender_report_path),
        "body_report": body_report_path.name,
        "body_report_sha256": sha256(body_report_path),
        "render_body_report": render_body_report_path.name,
        "render_body_report_sha256": sha256(render_body_report_path),
        "self_report": self_report_path.name,
        "self_report_sha256": sha256(self_report_path),
    }
    output_path = output_directory / "pipeline-report.json"
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Patterna Blender cloth candidate accepted: {result['accepted']}")
    for reason in reasons:
        print(f"Rejected: {reason}")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
