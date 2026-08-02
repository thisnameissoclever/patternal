#!/usr/bin/env python3
"""Report panel-local strain hot spots in a completed Patterna Warp prefit job."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_directory", type=Path)
    parser.add_argument("--top", type=int, default=20)
    return parser.parse_args()


def load_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            vertices.append([float(value) for value in line.split()[1:4]])
        elif line.startswith("f "):
            face = [int(token.split("/", maxsplit=1)[0]) - 1 for token in line.split()[1:]]
            for index in range(1, len(face) - 1):
                faces.append([face[0], face[index], face[index + 1]])
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=int)


def unique_edges(faces: np.ndarray) -> np.ndarray:
    edges = np.concatenate(
        (faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]),
        axis=0,
    )
    return np.unique(np.sort(edges, axis=1), axis=0)


def triangle_quality(vertices: np.ndarray, face: np.ndarray) -> dict[str, object]:
    points = vertices[face]
    lengths = np.asarray(
        [
            np.linalg.norm(points[1] - points[0]),
            np.linalg.norm(points[2] - points[1]),
            np.linalg.norm(points[0] - points[2]),
        ]
    )
    area = 0.5 * np.linalg.norm(np.cross(points[1] - points[0], points[2] - points[0]))
    squared_sum = float(np.dot(lengths, lengths))
    normalized_quality = 4.0 * np.sqrt(3.0) * area / squared_sum if squared_sum > 0 else 0.0
    angles: list[float] = []
    for index in range(3):
        first = points[(index + 1) % 3] - points[index]
        second = points[(index + 2) % 3] - points[index]
        divisor = np.linalg.norm(first) * np.linalg.norm(second)
        cosine = float(np.dot(first, second) / divisor) if divisor > 0 else 1.0
        angles.append(float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))))
    return {
        "vertices": [int(value) for value in face],
        "edge_lengths_cm": lengths.tolist(),
        "area_cm2": float(area),
        "minimum_angle_degrees": min(angles),
        "maximum_angle_degrees": max(angles),
        "normalized_quality": float(normalized_quality),
    }


def adjacent_triangle_quality(
    vertices: np.ndarray,
    faces: np.ndarray,
    first: int,
    second: int,
) -> list[dict[str, object]]:
    return [
        triangle_quality(vertices, face)
        for face in faces
        if first in face and second in face
    ]


def panel_label(vertex_label: str) -> str:
    return "stitch" if vertex_label.startswith("stitch_") else vertex_label


def panel_local_point(
    world_point: np.ndarray,
    panel: dict[str, object],
) -> np.ndarray:
    from pygarment.pattern.rotation import euler_xyz_to_R

    rotation = np.asarray(
        euler_xyz_to_R(np.asarray(panel["rotation"], dtype=float)),
        dtype=float,
    )
    translation = np.asarray(panel["translation"], dtype=float)
    return np.asarray(rotation.T.dot(world_point - translation)).reshape(-1)[:2]


def main() -> None:
    args = parse_args()
    job_directory = args.job_directory.resolve()
    report_path = next(job_directory.glob("warp/*/patterna_warp_prefit_report.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    initial_path = next(job_directory.glob("warp/*/*_boxmesh.obj"))
    final_path = Path(report["output_mesh"])
    segmentation_path = next(job_directory.glob("warp/*/*_sim_segmentation.txt"))
    specification_path = next(job_directory.glob("*.specification.json"))

    initial, initial_faces = load_obj(initial_path)
    final, final_faces = load_obj(final_path)
    if initial.shape != final.shape:
        raise ValueError(f"Vertex shape changed: {initial.shape} -> {final.shape}")
    if not np.array_equal(initial_faces, final_faces):
        raise ValueError("Initial and final face topology differ")

    labels = segmentation_path.read_text(encoding="utf-8").splitlines()
    if len(labels) != len(initial):
        raise ValueError(f"Segmentation has {len(labels)} labels for {len(initial)} vertices")

    specification = json.loads(specification_path.read_text(encoding="utf-8"))
    panels = specification["pattern"]["panels"]
    edges = unique_edges(initial_faces)
    initial_lengths = np.linalg.norm(initial[edges[:, 0]] - initial[edges[:, 1]], axis=1)
    final_lengths = np.linalg.norm(final[edges[:, 0]] - final[edges[:, 1]], axis=1)
    strains = np.abs(final_lengths / initial_lengths - 1.0)
    ranked = np.argsort(strains)[::-1]

    records: list[dict[str, object]] = []
    for edge_index in ranked:
        first, second = (int(value) for value in edges[edge_index])
        first_label = panel_label(labels[first])
        second_label = panel_label(labels[second])
        if first_label == "stitch" or second_label == "stitch":
            continue
        midpoint = (initial[first] + initial[second]) * 0.5
        label = first_label if first_label == second_label else f"{first_label}|{second_label}"
        local_midpoint = (
            panel_local_point(midpoint, panels[label]).tolist()
            if label in panels
            else None
        )
        records.append(
            {
                "vertices": [first, second],
                "panel": label,
                "strain": float(strains[edge_index]),
                "initial_length_cm": float(initial_lengths[edge_index]),
                "final_length_cm": float(final_lengths[edge_index]),
                "initial_midpoint_cm": midpoint.tolist(),
                "panel_local_midpoint_cm": local_midpoint,
                "adjacent_initial_triangles": adjacent_triangle_quality(
                    initial,
                    initial_faces,
                    first,
                    second,
                ),
            }
        )
        if len(records) >= args.top:
            break

    maximum_vertices = [int(value) for value in report["maximum_strain_edge_vertices"]]
    maximum_midpoint = initial[maximum_vertices].mean(axis=0)
    maximum_label = panel_label(labels[maximum_vertices[0]])
    maximum_local = panel_local_point(maximum_midpoint, panels[maximum_label])

    mirror_label = None
    if maximum_label.startswith("left_"):
        mirror_label = "right_" + maximum_label.removeprefix("left_")
    elif maximum_label.startswith("right_"):
        mirror_label = "left_" + maximum_label.removeprefix("right_")

    mirror = None
    if mirror_label in panels:
        candidates = np.asarray(
            [index for index, label in enumerate(labels) if label == mirror_label],
            dtype=int,
        )
        candidate_local = np.asarray(
            [panel_local_point(initial[index], panels[mirror_label]) for index in candidates]
        )
        expected_local = np.asarray([-maximum_local[0], maximum_local[1]])
        distances = np.linalg.norm(candidate_local - expected_local, axis=1)
        nearest_order = np.argsort(distances)[:2]
        mirror_vertices = candidates[nearest_order]
        initial_length = np.linalg.norm(initial[mirror_vertices[0]] - initial[mirror_vertices[1]])
        final_length = np.linalg.norm(final[mirror_vertices[0]] - final[mirror_vertices[1]])
        mirror = {
            "panel": mirror_label,
            "expected_local_midpoint_cm": expected_local.tolist(),
            "nearest_vertices": mirror_vertices.tolist(),
            "nearest_vertex_local_distance_cm": distances[nearest_order].tolist(),
            "edge_exists": bool(
                np.any(np.all(edges == np.sort(mirror_vertices), axis=1))
            ),
            "initial_length_cm": float(initial_length),
            "final_length_cm": float(final_length),
            "strain": float(abs(final_length / initial_length - 1.0)),
        }

    self_intersections: list[dict[str, object]] = []
    for location in report.get("self_intersection_locations", []):
        edge_vertices = [int(value) for value in location["vertices"]]
        face_vertices = [int(value) for value in location["face_vertices"]]
        edge_initial = initial[edge_vertices].mean(axis=0)
        edge_final = final[edge_vertices].mean(axis=0)
        face_initial = initial[face_vertices].mean(axis=0)
        face_final = final[face_vertices].mean(axis=0)
        material_labels = [
            label
            for label in (*location["vertex_labels"], *location["face_vertex_labels"])
            if not label.startswith("stitch_")
        ]
        local_panel = material_labels[0] if material_labels else None
        self_intersections.append(
            {
                **location,
                "edge_initial_midpoint_cm": edge_initial.tolist(),
                "edge_final_midpoint_cm": edge_final.tolist(),
                "face_initial_centroid_cm": face_initial.tolist(),
                "face_final_centroid_cm": face_final.tolist(),
                "panel_local_edge_initial_midpoint_cm": (
                    panel_local_point(edge_initial, panels[local_panel]).tolist()
                    if local_panel in panels
                    else None
                ),
            }
        )

    print(
        json.dumps(
            {
                "job_directory": str(job_directory),
                "vertex_count": int(len(initial)),
                "maximum_reported_edge": {
                    "vertices": maximum_vertices,
                    "panel": maximum_label,
                    "panel_local_midpoint_cm": maximum_local.tolist(),
                    "adjacent_initial_triangles": adjacent_triangle_quality(
                        initial,
                        initial_faces,
                        maximum_vertices[0],
                        maximum_vertices[1],
                    ),
                },
                "mirrored_region": mirror,
                "self_intersections": self_intersections,
                "top_material_edges": records,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
