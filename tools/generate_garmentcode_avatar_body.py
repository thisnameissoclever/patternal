#!/usr/bin/env python3
"""Morph GarmentCode's segmented female body to Patterna's measured torso profile."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil

import numpy as np
import trimesh


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("PatternaUnreal/Saved/Patterna/LiveBodyProfile.json"),
    )
    parser.add_argument(
        "--source-body",
        type=Path,
        default=Path("third_party/GarmentCode/assets/bodies/mean_female.obj"),
    )
    parser.add_argument(
        "--source-measurements",
        type=Path,
        default=Path("third_party/GarmentCode/assets/bodies/mean_female.yaml"),
    )
    parser.add_argument(
        "--segmentation",
        type=Path,
        default=Path("third_party/GarmentCode/assets/bodies/ggg_body_segmentation.json"),
    )
    parser.add_argument(
        "--output-body",
        type=Path,
        default=Path("third_party/GarmentCode/assets/bodies/patterna_live_female.obj"),
    )
    parser.add_argument(
        "--output-measurements",
        type=Path,
        default=Path("third_party/GarmentCode/assets/bodies/patterna_live_female.yaml"),
    )
    return parser.parse_args()


def resolve(repo_root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def interpolate_section(sections: list[dict], height_cm: float) -> dict[str, float]:
    upper_index = next(
        (index for index, section in enumerate(sections) if section["heightCm"] >= height_cm),
        len(sections) - 1,
    )
    lower_index = max(0, upper_index - 1)
    lower = sections[lower_index]
    upper = sections[upper_index]
    span = max(float(upper["heightCm"] - lower["heightCm"]), 1e-9)
    blend = min(1.0, max(0.0, (height_cm - lower["heightCm"]) / span))
    return {
        key: float(lower[key]) * (1.0 - blend) + float(upper[key]) * blend
        for key in ("centerXCm", "centerYCm", "widthCm", "depthCm")
    }


def source_centers(vertices_cm: np.ndarray, torso_vertices: np.ndarray, heights: np.ndarray) -> np.ndarray:
    centers = np.zeros((len(heights), 2), dtype=float)
    torso = vertices_cm[torso_vertices]
    for index, height in enumerate(heights):
        distances = np.abs(torso[:, 1] - height)
        selected = torso[distances <= 0.8]
        if len(selected) < 8:
            selected = torso[np.argsort(distances)[:64]]
        centers[index] = np.median(selected[:, [0, 2]], axis=0)
    return centers


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    profile_path = resolve(repo_root, args.profile)
    source_body_path = resolve(repo_root, args.source_body)
    source_measurements_path = resolve(repo_root, args.source_measurements)
    segmentation_path = resolve(repo_root, args.segmentation)
    output_body_path = resolve(repo_root, args.output_body)
    output_measurements_path = resolve(repo_root, args.output_measurements)

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    sections = sorted(profile["sections"], key=lambda section: section["heightCm"])
    mesh = trimesh.load_mesh(source_body_path, process=False)
    vertices_cm = np.asarray(mesh.vertices, dtype=float) * 100.0
    original_vertices_cm = vertices_cm.copy()
    shift_cm = max(0.0, -float(vertices_cm[:, 1].min()))
    shifted_heights = vertices_cm[:, 1] + shift_cm

    segmentation = json.loads(segmentation_path.read_text(encoding="utf-8"))
    torso_faces = np.asarray(segmentation["body"], dtype=int)
    torso_vertices = np.unique(np.asarray(mesh.faces, dtype=int)[torso_faces].reshape(-1))
    torso_mask = np.zeros(len(vertices_cm), dtype=bool)
    torso_mask[torso_vertices] = True

    minimum_height = float(sections[0]["heightCm"])
    maximum_height = float(sections[-1]["heightCm"])
    center_heights = np.arange(minimum_height, maximum_height + 0.5, 0.5)
    centers = source_centers(vertices_cm, torso_vertices, center_heights)

    moved = 0
    for vertex_index, vertex in enumerate(vertices_cm):
        height = shifted_heights[vertex_index]
        if not torso_mask[vertex_index] or height < minimum_height - 2.0 or height > maximum_height + 2.0:
            continue

        source_center_x = float(np.interp(height, center_heights, centers[:, 0]))
        source_center_z = float(np.interp(height, center_heights, centers[:, 1]))
        source_radius = math.hypot(
            vertex[0] - source_center_x,
            vertex[2] - source_center_z,
        )
        angle = math.atan2(vertex[2] - source_center_z, vertex[0] - source_center_x)
        target = interpolate_section(sections, min(max(height, minimum_height), maximum_height))
        half_width = max(target["widthCm"] * 0.5, 0.1)
        half_depth = max(target["depthCm"] * 0.5, 0.1)
        denominator = math.sqrt(
            (half_depth * math.cos(angle)) ** 2 +
            (half_width * math.sin(angle)) ** 2
        )
        target_radius = half_width * half_depth / max(denominator, 1e-9)
        target_x = target["centerXCm"] + target_radius * math.cos(angle)
        target_z = target["centerYCm"] + target_radius * math.sin(angle)
        blend = min(
            1.0,
            max(0.0, (height - (minimum_height - 2.0)) / 2.0),
            max(0.0, ((maximum_height + 2.0) - height) / 2.0),
        )
        blend *= min(1.0, max(0.0, (35.0 - source_radius) / 15.0))
        vertex[0] = vertex[0] * (1.0 - blend) + target_x * blend
        vertex[2] = vertex[2] * (1.0 - blend) + target_z * blend
        moved += 1

    displacement = vertices_cm - original_vertices_cm
    edges = np.asarray(mesh.edges_unique, dtype=int)
    smoothing_mask = (
        (shifted_heights >= minimum_height - 5.0) &
        (shifted_heights <= maximum_height + 5.0)
    )
    for _ in range(16):
        neighbor_sum = np.zeros_like(displacement)
        neighbor_count = np.zeros(len(displacement), dtype=float)
        np.add.at(neighbor_sum, edges[:, 0], displacement[edges[:, 1]])
        np.add.at(neighbor_sum, edges[:, 1], displacement[edges[:, 0]])
        np.add.at(neighbor_count, edges[:, 0], 1.0)
        np.add.at(neighbor_count, edges[:, 1], 1.0)
        neighbor_average = neighbor_sum / np.maximum(neighbor_count[:, None], 1.0)
        displacement[smoothing_mask] = (
            displacement[smoothing_mask] * 0.45 +
            neighbor_average[smoothing_mask] * 0.55
        )
    vertices_cm = original_vertices_cm + displacement

    morphed = trimesh.Trimesh(
        vertices=vertices_cm / 100.0,
        faces=np.asarray(mesh.faces, dtype=int),
        process=False,
    )
    output_body_path.parent.mkdir(parents=True, exist_ok=True)
    output_body_path.write_text(
        trimesh.exchange.obj.export_obj(
            morphed,
            include_normals=False,
            include_texture=False,
        ),
        encoding="utf-8",
    )
    shutil.copyfile(source_measurements_path, output_measurements_path)
    report = {
        "schemaVersion": "patterna.garmentcode-avatar-body/1.0",
        "sourceBody": str(source_body_path),
        "sourceProfile": str(profile_path),
        "vertexCount": int(len(morphed.vertices)),
        "faceCount": int(len(morphed.faces)),
        "morphedTorsoVertexCount": moved,
        "minimumProfileHeightCm": minimum_height,
        "maximumProfileHeightCm": maximum_height,
        "preservesGarmentCodeSegmentationIndices": True,
    }
    report_path = output_body_path.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
