#!/usr/bin/env python3
"""Run a deterministic two-stage search for a physically valid shirt block."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Candidate:
    style: str
    shirt_width: float
    shirt_length: float
    shirt_flare: float
    chest_ease: float
    waist_ease: float
    hip_ease: float
    neck_width: float
    front_neck_depth: float
    back_neck_depth: float
    neck_band_depth: float
    sleeve_length: float
    sleeve_angle: int
    sleeve_end_width: float
    sleeve_cuff_depth: float
    hem_extension_depth: float
    hem_extension_ease: float

    @property
    def stable_key(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate, screen, rank, and fully solve body-specific GarmentCode "
            "shirt candidates without promoting any result automatically."
        )
    )
    parser.add_argument(
        "--body",
        type=Path,
        default=Path(
            "third_party/GarmentCode/assets/bodies/patterna_mpfb_female.yaml"
        ),
        help=(
            "Body parameters used to draft every candidate. This must describe "
            "the same body mesh selected by --simulation-body."
        ),
    )
    parser.add_argument("--simulation-body", default="patterna_mpfb_female")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(
            "PatternaUnreal/SourceAssets/GarmentCode/PatternaSoftCottonPrefit.yaml"
        ),
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument("--screen-frames", type=int, default=80)
    parser.add_argument("--final-frames", type=int, default=500)
    parser.add_argument("--top", type=int, default=6)
    parser.add_argument("--max-candidates", type=int, default=48)
    parser.add_argument("--max-visual-fit-score", type=float, default=1.5)
    parser.add_argument("--max-sleeve-hang-score", type=float, default=0.65)
    parser.add_argument(
        "--max-final-body-collisions",
        type=int,
        default=0,
        help="Reject final candidates with more body intersections than this limit.",
    )
    parser.add_argument(
        "--allow-raw-edges",
        action="store_true",
        help="Allow candidates without both a sewn neck band and sewn sleeve bands.",
    )
    parser.add_argument("--output-directory", type=Path, default=None)
    parser.add_argument(
        "--styles",
        default="patterna-shaped-crew-neck-shirt",
        help="Comma-separated GarmentCode shirt blocks to evaluate.",
    )
    parser.add_argument("--shirt-widths", default="1.00")
    parser.add_argument("--shirt-lengths", default="1.34,1.38,1.42")
    parser.add_argument("--shirt-flares", default="1.00")
    parser.add_argument("--chest-eases", default="4,6,8")
    parser.add_argument("--waist-eases", default="6,8,10")
    parser.add_argument("--hip-eases", default="8,10,12")
    parser.add_argument("--neck-widths", default="-0.32,-0.22")
    parser.add_argument("--front-neck-depths", default="0.22")
    parser.add_argument("--back-neck-depths", default="0.02,0.05")
    parser.add_argument("--neck-band-depths", default="0.8,1.2")
    parser.add_argument("--sleeve-lengths", default="0.24,0.30")
    parser.add_argument("--sleeve-angles", default="42,48")
    parser.add_argument("--sleeve-end-widths", default="0.88,0.94")
    parser.add_argument("--sleeve-cuff-depths", default="1.2")
    parser.add_argument("--hem-extension-depths", default="0")
    parser.add_argument("--hem-extension-eases", default="6")
    return parser.parse_args()


def parse_number_list(raw: str, value_type: type[float] | type[int]) -> tuple[float | int, ...]:
    values = tuple(value_type(value.strip()) for value in raw.split(",") if value.strip())
    if not values:
        raise ValueError("Candidate parameter lists cannot be empty.")
    return values


def candidate_space(args: argparse.Namespace) -> list[Candidate]:
    candidates: list[Candidate] = []
    supported_styles = {
        "crew-neck-shirt",
        "fitted-crew-neck-shirt",
        "patterna-shaped-crew-neck-shirt",
    }
    styles = tuple(style.strip() for style in args.styles.split(",") if style.strip())
    unsupported_styles = sorted(set(styles) - supported_styles)
    if not styles or unsupported_styles:
        raise ValueError(
            f"Shirt styles must be selected from {sorted(supported_styles)}; "
            f"received unsupported values {unsupported_styles}."
        )
    styles_and_widths = {
        style: parse_number_list(args.shirt_widths, float)
        for style in styles
    }
    shared_values = itertools.product(
        parse_number_list(args.shirt_lengths, float),
        parse_number_list(args.shirt_flares, float),
        parse_number_list(args.chest_eases, float),
        parse_number_list(args.waist_eases, float),
        parse_number_list(args.hip_eases, float),
        parse_number_list(args.neck_widths, float),
        parse_number_list(args.front_neck_depths, float),
        parse_number_list(args.back_neck_depths, float),
        parse_number_list(args.neck_band_depths, float),
        parse_number_list(args.sleeve_lengths, float),
        parse_number_list(args.sleeve_angles, int),
        parse_number_list(args.sleeve_end_widths, float),
        parse_number_list(args.sleeve_cuff_depths, float),
        parse_number_list(args.hem_extension_depths, float),
        parse_number_list(args.hem_extension_eases, float),
    )
    shared = list(shared_values)
    for style, widths in styles_and_widths.items():
        for width in widths:
            for (
                shirt_length,
                shirt_flare,
                chest_ease,
                waist_ease,
                hip_ease,
                neck_width,
                front_depth,
                back_depth,
                neck_band_depth,
                sleeve_length,
                angle,
                sleeve_end_width,
                sleeve_cuff_depth,
                hem_extension_depth,
                hem_extension_ease,
            ) in shared:
                candidates.append(
                    Candidate(
                        style=style,
                        shirt_width=width,
                        shirt_length=shirt_length,
                        shirt_flare=shirt_flare,
                        chest_ease=chest_ease,
                        waist_ease=waist_ease,
                        hip_ease=hip_ease,
                        neck_width=neck_width,
                        front_neck_depth=front_depth,
                        back_neck_depth=back_depth,
                        neck_band_depth=neck_band_depth,
                        sleeve_length=sleeve_length,
                        sleeve_angle=angle,
                        sleeve_end_width=sleeve_end_width,
                        sleeve_cuff_depth=sleeve_cuff_depth,
                        hem_extension_depth=hem_extension_depth,
                        hem_extension_ease=hem_extension_ease,
                    )
                )
    return sorted(candidates, key=lambda candidate: candidate.stable_key)


def resolve_from_repo(repo_root: Path, value: Path) -> Path:
    return value.resolve() if value.is_absolute() else (repo_root / value).resolve()


def run_command(arguments: list[str], log_path: Path) -> int:
    completed = subprocess.run(
        arguments,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.write_text(completed.stdout, encoding="utf-8")
    return completed.returncode


def generate_candidate(
    repo_root: Path,
    body_path: Path,
    output_path: Path,
    candidate: Candidate,
    log_path: Path,
) -> int:
    return run_command(
        [
            sys.executable,
            str(repo_root / "tools" / "generate_garmentcode_pattern.py"),
            "--garmentcode-root",
            str(repo_root / "third_party" / "GarmentCode"),
            "--body",
            str(body_path),
            "--output",
            str(output_path),
            "--style",
            candidate.style,
            "--shirt-width",
            str(candidate.shirt_width),
            "--shirt-length",
            str(candidate.shirt_length),
            "--shirt-flare",
            str(candidate.shirt_flare),
            "--chest-ease",
            str(candidate.chest_ease),
            "--waist-ease",
            str(candidate.waist_ease),
            "--hip-ease",
            str(candidate.hip_ease),
            "--neck-width",
            str(candidate.neck_width),
            "--front-neck-depth",
            str(candidate.front_neck_depth),
            "--back-neck-depth",
            str(candidate.back_neck_depth),
            "--neck-band-depth",
            str(candidate.neck_band_depth),
            "--sleeve-length",
            str(candidate.sleeve_length),
            "--sleeve-angle",
            str(candidate.sleeve_angle),
            "--sleeve-end-width",
            str(candidate.sleeve_end_width),
            "--sleeve-cuff-depth",
            str(candidate.sleeve_cuff_depth),
            "--hem-extension-depth",
            str(candidate.hem_extension_depth),
            "--hem-extension-ease",
            str(candidate.hem_extension_ease),
        ],
        log_path,
    )


def solve_candidate(
    repo_root: Path,
    pattern_path: Path,
    config_path: Path,
    simulation_body_mesh: Path,
    simulation_body_parameters: Path,
    simulation_body_segmentation: Path,
    device: str,
    frames: int,
    stop_when_static: bool,
    log_path: Path,
) -> tuple[int, Path]:
    arguments = [
        sys.executable,
        str(repo_root / "tools" / "prefit_garmentcode_warp.py"),
        "--pattern",
        str(pattern_path),
        "--config",
        str(config_path),
        "--body-obj",
        str(simulation_body_mesh),
        "--body-measurements",
        str(simulation_body_parameters),
        "--body-segmentation",
        str(simulation_body_segmentation),
        "--frames",
        str(frames),
        "--rebuild-mesh",
        "--count-collisions",
        "--device",
        device,
    ]
    if stop_when_static:
        arguments.append("--stop-when-static")
    exit_code = run_command(arguments, log_path)
    garment_name = pattern_path.stem.removesuffix(".specification")
    report_path = (
        repo_root
        / "PatternaUnreal"
        / "Saved"
        / "Patterna"
        / "GarmentCodeWarp"
        / garment_name
        / "patterna_warp_prefit_report.json"
    )
    return exit_code, report_path


def load_report(report_path: Path) -> dict[str, Any] | None:
    if not report_path.is_file():
        return None
    with report_path.open("r", encoding="utf-8") as report_file:
        return json.load(report_file)


def pattern_construction_metrics(pattern_path: Path) -> dict[str, Any]:
    payload = json.loads(pattern_path.read_text(encoding="utf-8"))
    pattern = payload.get("pattern", {})
    panels = pattern.get("panels", {})
    stitches = pattern.get("stitches", [])
    design = payload.get("patterna", {}).get("design", {})
    neck_band_depth = float(design.get("neck_band_depth", 0.0))
    sleeve_cuff_depth = float(design.get("sleeve_cuff_depth", 0.0))
    panel_names = tuple(panels) if isinstance(panels, dict) else ()
    collar_panel_count = sum("collar" in name for name in panel_names)
    cuff_panel_count = sum("cuff" in name for name in panel_names)
    torso_panel_count = sum("torso" in name for name in panel_names)
    finished = (
        isinstance(panels, dict)
        and len(panels) >= 14
        and isinstance(stitches, list)
        and len(stitches) >= 34
        and torso_panel_count >= 2
        and collar_panel_count >= 4
        and cuff_panel_count >= 4
        and neck_band_depth > 0
        and sleeve_cuff_depth > 0
    )
    return {
        "panel_count": len(panels) if isinstance(panels, dict) else 0,
        "stitch_count": len(stitches) if isinstance(stitches, list) else 0,
        "torso_panel_count": torso_panel_count,
        "collar_panel_count": collar_panel_count,
        "cuff_panel_count": cuff_panel_count,
        "neck_band_depth_cm": neck_band_depth,
        "sleeve_cuff_depth_cm": sleeve_cuff_depth,
        "finished_construction": finished,
    }


def metric(report: dict[str, Any], key: str, fallback: float) -> float:
    value = report.get(key)
    return float(value) if isinstance(value, (int, float)) else fallback


def load_obj_mesh_cm(path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        if line.startswith("v "):
            vertices.append([float(value) for value in line.split()[1:4]])
        elif line.startswith("f "):
            indices = [int(token.split("/")[0]) - 1 for token in line.split()[1:]]
            for index in range(1, len(indices) - 1):
                faces.append([indices[0], indices[index], indices[index + 1]])
    vertex_array = np.asarray(vertices, dtype=float)
    face_array = np.asarray(faces, dtype=int)
    vertices = vertex_array
    if vertices.ndim != 2 or vertices.shape[0] < 100 or vertices.shape[1] != 3:
        raise ValueError(f"OBJ mesh {path} does not contain a usable vertex surface.")
    if face_array.ndim != 2 or face_array.shape[0] < 100 or face_array.shape[1] != 3:
        raise ValueError(f"OBJ mesh {path} does not contain usable triangle faces.")
    if float(np.max(vertices[:, 1]) - np.min(vertices[:, 1])) < 10.0:
        vertices *= 100.0
    return vertices, face_array


def load_vertices_cm(path: Path) -> np.ndarray:
    return load_obj_mesh_cm(path)[0]


def sleeve_hang_metrics(
    garment_vertices: np.ndarray,
    torso_vertices: np.ndarray,
) -> dict[str, Any] | None:
    torso_outer_x = float(np.percentile(np.abs(torso_vertices[:, 0]), 95.0))
    sleeve_vertices = garment_vertices[
        (np.abs(garment_vertices[:, 0]) > torso_outer_x + 1.5)
        & (garment_vertices[:, 1] > 95.0)
    ]
    side_drops: dict[str, float] = {}
    for side, sign in (("left", -1.0), ("right", 1.0)):
        side_vertices = sleeve_vertices[sign * sleeve_vertices[:, 0] > 0]
        if len(side_vertices) < 24:
            continue
        absolute_x = np.abs(side_vertices[:, 0])
        inner_cutoff = float(np.percentile(absolute_x, 25.0))
        outer_cutoff = float(np.percentile(absolute_x, 85.0))
        inner_height = float(
            np.percentile(side_vertices[absolute_x <= inner_cutoff, 1], 90.0)
        )
        outer_height = float(
            np.percentile(side_vertices[absolute_x >= outer_cutoff, 1], 90.0)
        )
        side_drops[side] = inner_height - outer_height
    if len(side_drops) != 2:
        return None
    minimum_drop_cm = 8.0
    maximum_drop_cm = 30.0
    hang_penalty = float(np.mean([
        max(0.0, minimum_drop_cm - drop) / minimum_drop_cm
        + max(0.0, drop - maximum_drop_cm) / 15.0
        for drop in side_drops.values()
    ]))
    symmetry_penalty = abs(side_drops["left"] - side_drops["right"]) / 5.0
    return {
        "left_drop_cm": side_drops["left"],
        "right_drop_cm": side_drops["right"],
        "minimum_drop_cm": minimum_drop_cm,
        "maximum_drop_cm": maximum_drop_cm,
        "hang_penalty": hang_penalty,
        "symmetry_penalty": symmetry_penalty,
        "score": hang_penalty + symmetry_penalty,
    }


def visual_fit_metrics(
    report: dict[str, Any] | None,
    body_mesh_path: Path,
    body_segmentation_path: Path,
) -> dict[str, Any] | None:
    if report is None or not report.get("finite_positions", False):
        return None
    output_mesh = report.get("output_mesh")
    if not isinstance(output_mesh, str) or not Path(output_mesh).is_file():
        return None
    body_vertices = load_vertices_cm(body_mesh_path)
    segmentation = json.loads(body_segmentation_path.read_text(encoding="utf-8"))
    torso_indices = np.asarray(segmentation.get("body", []), dtype=int)
    if torso_indices.size < 100 or np.max(torso_indices) >= len(body_vertices):
        raise ValueError(f"Body segmentation {body_segmentation_path} has no usable torso region.")
    body_vertices = body_vertices[torso_indices]
    garment_vertices = load_vertices_cm(Path(output_mesh))
    body_center_x = float(np.median(body_vertices[:, 0]))
    torso_half_width = float(
        np.percentile(np.abs(body_vertices[:, 0] - body_center_x), 97.0)
    )
    garment_torso_vertices = garment_vertices[
        np.abs(garment_vertices[:, 0] - body_center_x) <= torso_half_width + 5.0
    ]
    if len(garment_torso_vertices) < 100:
        raise ValueError(f"Could not isolate torso vertices in {output_mesh}.")
    slices: list[dict[str, float]] = []
    for height_cm, width_ease_range_cm, depth_ease_range_cm in (
        (95.0, (0.0, 8.0), (0.0, 8.0)),
        (105.0, (0.0, 7.0), (0.0, 8.0)),
        (115.0, (0.0, 8.0), (0.0, 6.0)),
        (125.0, (0.0, 10.0), (-0.5, 6.0)),
    ):
        body_slice = body_vertices[np.abs(body_vertices[:, 1] - height_cm) <= 1.5]
        garment_slice = garment_torso_vertices[
            np.abs(garment_torso_vertices[:, 1] - height_cm) <= 1.5
        ]
        if len(body_slice) < 16 or len(garment_slice) < 16:
            continue
        body_x_bounds = np.percentile(body_slice[:, 0], [5.0, 95.0])
        garment_x_bounds = np.percentile(garment_slice[:, 0], [5.0, 95.0])
        body_z_bounds = np.percentile(body_slice[:, 2], [5.0, 95.0])
        garment_z_bounds = np.percentile(garment_slice[:, 2], [5.0, 95.0])
        body_width = float(body_x_bounds[1] - body_x_bounds[0])
        garment_width = float(garment_x_bounds[1] - garment_x_bounds[0])
        body_depth = float(body_z_bounds[1] - body_z_bounds[0])
        garment_depth = float(garment_z_bounds[1] - garment_z_bounds[0])
        garment_center_x = float(np.median(garment_slice[:, 0]))
        body_center_x = float(np.median(body_slice[:, 0]))
        slices.append(
            {
                "height_cm": height_cm,
                "width_ease_cm": garment_width - body_width,
                "depth_ease_cm": garment_depth - body_depth,
                "width_ease_range_cm": list(width_ease_range_cm),
                "depth_ease_range_cm": list(depth_ease_range_cm),
                "center_offset_cm": garment_center_x - body_center_x,
            }
        )
    if len(slices) < 3:
        return None
    ease_error = float(
        np.mean(
            [
                (
                    max(0.0, item["width_ease_range_cm"][0] - item["width_ease_cm"])
                    + max(0.0, item["width_ease_cm"] - item["width_ease_range_cm"][1])
                )
                / 4.0
                + (
                    max(0.0, item["depth_ease_range_cm"][0] - item["depth_ease_cm"])
                    + max(0.0, item["depth_ease_cm"] - item["depth_ease_range_cm"][1])
                )
                / 4.0
                + max(0.0, abs(item["center_offset_cm"]) - 1.0) / 2.0
                for item in slices
            ]
        )
    )
    hem_height_cm = float(np.min(garment_torso_vertices[:, 1]))
    neckline_height_cm = float(np.max(garment_torso_vertices[:, 1]))
    preferred_hem_min_cm = 78.0
    preferred_hem_max_cm = 88.0
    length_penalty = (
        max(0.0, preferred_hem_min_cm - hem_height_cm)
        + max(0.0, hem_height_cm - preferred_hem_max_cm)
    ) / 10.0
    sleeve_hang = sleeve_hang_metrics(garment_vertices, body_vertices)
    sleeve_score = metric(sleeve_hang or {}, "score", 3.0)
    return {
        "slice_count": len(slices),
        "slices": slices,
        "hem_height_cm": hem_height_cm,
        "preferred_hem_range_cm": [preferred_hem_min_cm, preferred_hem_max_cm],
        "neckline_height_cm": neckline_height_cm,
        "ease_error": ease_error,
        "length_penalty": length_penalty,
        "sleeve_hang": sleeve_hang,
        "sleeve_hang_penalty": sleeve_score,
        "score": ease_error + length_penalty + sleeve_score,
    }


def screening_score(
    report: dict[str, Any] | None,
    visual_fit: dict[str, Any] | None = None,
) -> float:
    if report is None or not report.get("finite_positions", False):
        return 1.0e9
    max_body = max(metric(report, "max_body_collisions", 1.0), 1.0)
    max_self = max(metric(report, "max_self_collisions", 1.0), 1.0)
    max_peak = max(metric(report, "max_edge_strain_ratio", 0.01), 0.01)
    max_p95 = max(
        metric(report, "max_ninety_fifth_percentile_edge_strain_ratio", 0.01),
        0.01,
    )
    max_p999 = max(
        metric(
            report,
            "max_ninety_ninth_point_ninth_percentile_edge_strain_ratio",
            0.01,
        ),
        0.01,
    )
    physics_score = (
        4.0 * metric(report, "body_collisions", 1.0e6) / max_body
        + 2.0 * metric(report, "self_collisions", 1.0e6) / max_self
        + metric(report, "maximum_edge_strain_ratio", 1.0e6) / max_peak
        + 4.0
        * metric(report, "ninety_fifth_percentile_edge_strain_ratio", 1.0e6)
        / max_p95
        + 3.0
        * metric(
            report,
            "ninety_ninth_point_ninth_percentile_edge_strain_ratio",
            1.0e6,
        )
        / max_p999
    )
    visual_score = metric(visual_fit or {}, "score", 20.0)
    return physics_score + 4.0 * visual_score


def main() -> int:
    args = parse_args()
    if args.screen_frames <= 0 or args.final_frames <= 0:
        raise ValueError("Frame counts must be positive.")
    if args.top <= 0 or args.max_candidates <= 0:
        raise ValueError("Candidate counts must be positive.")
    if args.max_visual_fit_score <= 0:
        raise ValueError("The visual-fit threshold must be positive.")
    if args.max_sleeve_hang_score <= 0:
        raise ValueError("The sleeve-hang threshold must be positive.")
    if args.max_final_body_collisions < 0:
        raise ValueError("The final body-collision threshold cannot be negative.")

    repo_root = Path(__file__).resolve().parents[1]
    body_path = resolve_from_repo(repo_root, args.body)
    config_path = resolve_from_repo(repo_root, args.config)
    if not body_path.is_file():
        raise FileNotFoundError(body_path)
    if not config_path.is_file():
        raise FileNotFoundError(config_path)
    simulation_body_root = (
        repo_root / "third_party" / "GarmentCode" / "assets" / "bodies"
    )
    simulation_body_mesh = simulation_body_root / f"{args.simulation_body}.obj"
    simulation_body_parameters = simulation_body_root / f"{args.simulation_body}.yaml"
    simulation_body_segmentation = (
        simulation_body_root / f"{args.simulation_body}.segmentation.json"
    )
    if not simulation_body_mesh.is_file():
        raise FileNotFoundError(simulation_body_mesh)
    if not simulation_body_parameters.is_file():
        raise FileNotFoundError(simulation_body_parameters)
    if not simulation_body_segmentation.is_file():
        raise FileNotFoundError(simulation_body_segmentation)
    if body_path.resolve() != simulation_body_parameters.resolve():
        raise ValueError(
            "Pattern drafting and cloth simulation must use one body source of "
            f"truth. Expected {simulation_body_parameters}, received {body_path}."
        )

    run_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_directory = (
        resolve_from_repo(repo_root, args.output_directory)
        if args.output_directory is not None
        else repo_root
        / "PatternaUnreal"
        / "Saved"
        / "Patterna"
        / "ShirtSearch"
        / run_tag
    )
    output_directory.mkdir(parents=True, exist_ok=False)

    candidates = candidate_space(args)[: args.max_candidates]
    records: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        candidate_id = f"PatternaShirtSearch_{run_tag}_{index:03d}"
        pattern_path = output_directory / f"{candidate_id}.specification.json"
        record: dict[str, Any] = {
            "candidate_id": candidate_id,
            "candidate": asdict(candidate),
            "screen_status": "generation_failed",
        }
        generation_exit = generate_candidate(
            repo_root,
            body_path,
            pattern_path,
            candidate,
            output_directory / f"{candidate_id}.generate.log",
        )
        record["generation_exit_code"] = generation_exit
        if generation_exit == 0:
            construction = pattern_construction_metrics(pattern_path)
            record["construction"] = construction
            if not construction["finished_construction"] and not args.allow_raw_edges:
                record["screen_status"] = "unfinished_construction_rejected"
                records.append(record)
                print(
                    f"Screened {index}/{len(candidates)} {candidate_id}: "
                    "unfinished construction"
                )
                continue
            solve_exit, report_path = solve_candidate(
                repo_root,
                pattern_path,
                config_path,
                simulation_body_mesh,
                simulation_body_parameters,
                simulation_body_segmentation,
                args.device,
                args.screen_frames,
                False,
                output_directory / f"{candidate_id}.screen.log",
            )
            report = load_report(report_path)
            visual_fit = visual_fit_metrics(
                report,
                simulation_body_mesh,
                simulation_body_segmentation,
            )
            record["screen_exit_code"] = solve_exit
            record["screen_status"] = "reported" if report is not None else "no_report"
            record["screen_report"] = report
            record["screen_visual_fit"] = visual_fit
            record["screen_score"] = screening_score(report, visual_fit)
            if report is not None:
                shutil.copy2(
                    report_path,
                    output_directory / f"{candidate_id}.screen.report.json",
                )
        records.append(record)
        print(
            f"Screened {index}/{len(candidates)} {candidate_id}: "
            f"{record.get('screen_score', 'failed')}"
        )

    ranked = sorted(records, key=lambda record: record.get("screen_score", 1.0e9))
    finalists = [
        record for record in ranked if record.get("screen_status") == "reported"
    ][: args.top]
    for rank, record in enumerate(finalists, start=1):
        candidate_id = record["candidate_id"]
        pattern_path = output_directory / f"{candidate_id}.specification.json"
        solve_exit, report_path = solve_candidate(
            repo_root,
            pattern_path,
            config_path,
            simulation_body_mesh,
            simulation_body_parameters,
            simulation_body_segmentation,
            args.device,
            args.final_frames,
            True,
            output_directory / f"{candidate_id}.final.log",
        )
        report = load_report(report_path)
        visual_fit = visual_fit_metrics(
            report,
            simulation_body_mesh,
            simulation_body_segmentation,
        )
        record["final_rank"] = rank
        record["final_exit_code"] = solve_exit
        record["final_report"] = report
        record["final_visual_fit"] = visual_fit
        record["final_score"] = screening_score(report, visual_fit)
        record["final_physics_accepted"] = bool(
            report
            and report.get("accepted", False)
            and int(report.get("body_collisions", 1_000_000))
            <= args.max_final_body_collisions
        )
        record["final_visual_accepted"] = bool(
            visual_fit
            and metric(visual_fit, "score", 1.0e9) <= args.max_visual_fit_score
            and metric(visual_fit, "sleeve_hang_penalty", 1.0e9)
            <= args.max_sleeve_hang_score
        )
        record["final_accepted"] = bool(
            record["final_physics_accepted"] and record["final_visual_accepted"]
        )
        if report is not None:
            shutil.copy2(
                report_path,
                output_directory / f"{candidate_id}.final.report.json",
            )
        print(
            f"Finalized {rank}/{len(finalists)} {candidate_id}: "
            f"accepted={record['final_accepted']}"
        )

    manifest = {
        "schema_version": "patterna.shirt-search/1.2",
        "run_tag": run_tag,
        "device": args.device,
        "body_parameters": str(body_path),
        "simulation_body": args.simulation_body,
        "simulation_body_mesh": str(simulation_body_mesh),
        "simulation_body_segmentation": str(simulation_body_segmentation),
        "screen_frames": args.screen_frames,
        "final_frames": args.final_frames,
        "max_visual_fit_score": args.max_visual_fit_score,
        "max_sleeve_hang_score": args.max_sleeve_hang_score,
        "max_final_body_collisions": args.max_final_body_collisions,
        "raw_edges_allowed": args.allow_raw_edges,
        "candidate_count": len(candidates),
        "finalist_count": len(finalists),
        "accepted_candidate_ids": [
            record["candidate_id"]
            for record in finalists
            if record.get("final_accepted", False)
        ],
        "records": ranked,
    }
    manifest_path = output_directory / "shirt-search.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "accepted": manifest["accepted_candidate_ids"]}))
    return 0 if manifest["accepted_candidate_ids"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
