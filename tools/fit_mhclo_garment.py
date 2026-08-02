#!/usr/bin/env python3
"""Transfer a fitted MakeHuman garment onto Patterna's exact final body surface."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_vertices(path: Path) -> tuple[list[str], np.ndarray]:
    lines = path.read_text(encoding="utf-8").splitlines()
    vertices = [
        [float(value) for value in line.split()[1:4]]
        for line in lines
        if line.startswith("v ")
    ]
    if not vertices:
        raise ValueError(f"Garment OBJ has no vertices: {path}")
    return lines, np.asarray(vertices, dtype=np.float64)


def write_vertices(path: Path, lines: list[str], vertices: np.ndarray) -> None:
    output: list[str] = []
    vertex_index = 0
    for line in lines:
        if line.startswith("v "):
            vertex = vertices[vertex_index]
            output.append(f"v {vertex[0]:.9f} {vertex[1]:.9f} {vertex[2]:.9f}")
            vertex_index += 1
        else:
            output.append(line)
    if vertex_index != len(vertices):
        raise RuntimeError("Garment vertex ordering changed during transfer.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def project_outside(
    body: trimesh.Trimesh,
    vertices: np.ndarray,
    clearance_m: float,
) -> tuple[np.ndarray, dict[str, float | int]]:
    fitted = vertices.copy()
    initial_signed = trimesh.proximity.signed_distance(body, fitted)
    selected = initial_signed > -clearance_m
    if np.any(selected):
        closest, _, face_ids = trimesh.proximity.closest_point(body, fitted[selected])
        normals = body.face_normals[face_ids]
        candidate = closest + normals * clearance_m
        candidate_signed = trimesh.proximity.signed_distance(body, candidate)
        flip = candidate_signed > 0.0
        normals[flip] *= -1.0
        fitted[selected] = closest + normals * clearance_m

    for _ in range(3):
        signed = trimesh.proximity.signed_distance(body, fitted)
        unresolved = signed > -clearance_m * 0.98
        if not np.any(unresolved):
            break
        closest, _, face_ids = trimesh.proximity.closest_point(body, fitted[unresolved])
        normals = body.face_normals[face_ids]
        candidate = closest + normals * clearance_m
        candidate_signed = trimesh.proximity.signed_distance(body, candidate)
        normals[candidate_signed > 0.0] *= -1.0
        fitted[unresolved] = closest + normals * clearance_m

    final_signed = trimesh.proximity.signed_distance(body, fitted)
    return fitted, {
        "initial_inside_vertex_count": int(np.count_nonzero(initial_signed > 0.0)),
        "projected_vertex_count": int(np.count_nonzero(selected)),
        "final_inside_vertex_count": int(np.count_nonzero(final_signed > 0.0)),
        "minimum_final_clearance_cm": float(-np.max(final_signed) * 100.0),
        "maximum_vertex_displacement_cm": float(
            np.max(np.linalg.norm(fitted - vertices, axis=1)) * 100.0
        ),
        "mean_projected_displacement_cm": float(
            np.mean(np.linalg.norm(fitted[selected] - vertices[selected], axis=1)) * 100.0
        ) if np.any(selected) else 0.0,
    }


def convert_output_vertices(
    vertices: np.ndarray,
    body_floor_m: float,
    coordinate_system: str,
) -> tuple[np.ndarray, str]:
    if coordinate_system == "blender-meters":
        return vertices, "Blender meters"
    if coordinate_system != "garmentcode-centimeters":
        raise ValueError(f"Unsupported output coordinate system: {coordinate_system}")
    converted = np.empty_like(vertices)
    converted[:, 0] = vertices[:, 0] * 100.0
    converted[:, 1] = (vertices[:, 2] - body_floor_m) * 100.0
    converted[:, 2] = vertices[:, 1] * 100.0
    return converted, "x,y,z meters to x,z-floor,y centimeters"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--garment", required=True, type=Path)
    parser.add_argument("--body", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--clearance-cm", type=float, default=0.35)
    parser.add_argument(
        "--output-coordinate-system",
        choices=("blender-meters", "garmentcode-centimeters"),
        default="blender-meters",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    garment_path = args.garment.resolve()
    body_path = args.body.resolve()
    output_path = args.output.resolve()
    lines, vertices = parse_vertices(garment_path)
    body = trimesh.load(body_path, process=True)
    if not isinstance(body, trimesh.Trimesh) or not body.is_watertight:
        raise ValueError("The final Patterna body must be one watertight mesh.")
    fitted, metrics = project_outside(
        body,
        vertices,
        args.clearance_cm * 0.01,
    )
    output_vertices, coordinate_transform = convert_output_vertices(
        fitted,
        float(body.bounds[0, 2]),
        args.output_coordinate_system,
    )
    write_vertices(output_path, lines, output_vertices)
    report = {
        "schema_version": "patterna.mhclo-garment-fit/1.0",
        "source_garment": str(garment_path),
        "source_garment_sha256": sha256(garment_path),
        "body": str(body_path),
        "body_sha256": sha256(body_path),
        "output": str(output_path),
        "output_sha256": sha256(output_path),
        "vertex_count": len(vertices),
        "clearance_cm": args.clearance_cm,
        "output_coordinate_system": args.output_coordinate_system,
        "coordinate_transform": coordinate_transform,
        **metrics,
        "accepted": metrics["final_inside_vertex_count"] == 0,
    }
    report_path = output_path.with_suffix(".fit-report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["accepted"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
