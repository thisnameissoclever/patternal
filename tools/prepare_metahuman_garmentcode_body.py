#!/usr/bin/env python3
"""Prepare Unreal's exact posed MetaHuman surface for GarmentCode and Warp."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

import numpy as np
from scipy.spatial import cKDTree
import trimesh


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live-body",
        type=Path,
        default=Path("PatternaUnreal/Saved/Patterna/LiveBodyMesh.obj"),
    )
    parser.add_argument(
        "--reference-body",
        type=Path,
        default=Path("third_party/GarmentCode/assets/bodies/patterna_live_female.obj"),
    )
    parser.add_argument(
        "--reference-segmentation",
        type=Path,
        default=Path("third_party/GarmentCode/assets/bodies/ggg_body_segmentation.json"),
    )
    parser.add_argument(
        "--reference-measurements",
        type=Path,
        default=Path("third_party/GarmentCode/assets/bodies/patterna_live_female.yaml"),
    )
    parser.add_argument(
        "--output-body",
        type=Path,
        default=Path("third_party/GarmentCode/assets/bodies/patterna_metahuman_female.obj"),
    )
    parser.add_argument("--voxel-pitch-cm", type=float, default=1.5)
    return parser.parse_args()


def resolve(repo_root: Path, value: Path) -> Path:
    return value.resolve() if value.is_absolute() else (repo_root / value).resolve()


def load_mesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load(path, process=False, maintain_order=True)
    if not isinstance(mesh, trimesh.Trimesh):
        raise TypeError(f"Expected one mesh in {path}, received {type(mesh).__name__}")
    return mesh


def transfer_segmentation(
    target_vertices: np.ndarray,
    reference_vertices: np.ndarray,
    reference_segmentation: dict[str, list[int]],
) -> tuple[dict[str, list[int]], np.ndarray]:
    labels_by_reference_vertex: list[list[str]] = [
        [] for _ in range(len(reference_vertices))
    ]
    for label, vertex_indices in reference_segmentation.items():
        for vertex_index in vertex_indices:
            if 0 <= vertex_index < len(labels_by_reference_vertex):
                labels_by_reference_vertex[vertex_index].append(label)

    distances, nearest_indices = cKDTree(reference_vertices).query(
        target_vertices,
        k=1,
        workers=-1,
    )
    transferred = {label: [] for label in reference_segmentation}
    for target_index, reference_index in enumerate(nearest_indices):
        labels = labels_by_reference_vertex[int(reference_index)] or ["body"]
        for label in labels:
            transferred.setdefault(label, []).append(target_index)
    return transferred, np.asarray(distances, dtype=float)


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    live_body_path = resolve(repo_root, args.live_body)
    reference_body_path = resolve(repo_root, args.reference_body)
    reference_segmentation_path = resolve(repo_root, args.reference_segmentation)
    reference_measurements_path = resolve(repo_root, args.reference_measurements)
    output_body_path = resolve(repo_root, args.output_body)
    output_segmentation_path = output_body_path.with_suffix(".segmentation.json")
    output_measurements_path = output_body_path.with_suffix(".yaml")
    output_report_path = output_body_path.with_suffix(".report.json")

    live_body = load_mesh(live_body_path)
    reference_body = load_mesh(reference_body_path)
    voxel_pitch_m = args.voxel_pitch_cm / 100.0
    if voxel_pitch_m <= 0.0:
        raise ValueError("--voxel-pitch-cm must be positive")
    voxel_grid = live_body.copy().process(validate=True).voxelized(voxel_pitch_m).fill()
    collision_body = voxel_grid.marching_cubes
    collision_body.apply_transform(voxel_grid.transform)
    collision_body.remove_unreferenced_vertices()
    collision_body.fix_normals()
    reference_segmentation = json.loads(
        reference_segmentation_path.read_text(encoding="utf-8")
    )
    transferred_segmentation, distances = transfer_segmentation(
        np.asarray(collision_body.vertices, dtype=float),
        np.asarray(reference_body.vertices, dtype=float),
        reference_segmentation,
    )

    output_body_path.parent.mkdir(parents=True, exist_ok=True)
    collision_body.export(output_body_path)
    shutil.copyfile(reference_measurements_path, output_measurements_path)
    output_segmentation_path.write_text(
        json.dumps(transferred_segmentation, indent=2) + "\n",
        encoding="utf-8",
    )

    report = {
        "schemaVersion": "patterna.metahuman-garmentcode-body/1.0",
        "sourceBody": str(live_body_path),
        "referenceBody": str(reference_body_path),
        "outputBody": str(output_body_path),
        "sourceVertexCount": int(len(live_body.vertices)),
        "sourceFaceCount": int(len(live_body.faces)),
        "voxelPitchCm": float(args.voxel_pitch_cm),
        "vertexCount": int(len(collision_body.vertices)),
        "faceCount": int(len(collision_body.faces)),
        "watertight": bool(collision_body.is_watertight),
        "connectedComponents": int(len(collision_body.split(only_watertight=False))),
        "boundsMeters": np.asarray(collision_body.bounds, dtype=float).tolist(),
        "segmentationCounts": {
            key: len(value) for key, value in transferred_segmentation.items()
        },
        "nearestReferenceDistanceCm": {
            "mean": float(np.mean(distances) * 100.0),
            "p95": float(np.percentile(distances, 95.0) * 100.0),
            "max": float(np.max(distances) * 100.0),
        },
    }
    output_report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
