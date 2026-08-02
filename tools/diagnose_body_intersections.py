#!/usr/bin/env python3
"""Locate cloth edges that cross the avatar collision surface."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh
import warp as wp


@wp.kernel
def locate_intersections(
    edges: wp.array(dtype=wp.int32),
    cloth_points: wp.array(dtype=wp.vec3),
    body_mesh_id: wp.uint64,
    hit_faces: wp.array(dtype=wp.int32),
    hit_distances: wp.array(dtype=float),
):
    edge_index = wp.tid()
    first = edges[edge_index * 2]
    second = edges[edge_index * 2 + 1]
    origin = cloth_points[first]
    segment = cloth_points[second] - origin
    length = wp.length(segment)
    if length <= 0.0:
        return

    distance = float(0.0)
    face_u = float(0.0)
    face_v = float(0.0)
    sign = float(0.0)
    normal = wp.vec3()
    face_index = int(-1)
    if wp.mesh_query_ray(
        body_mesh_id,
        origin,
        wp.normalize(segment),
        length,
        distance,
        face_u,
        face_v,
        sign,
        normal,
        face_index,
    ):
        hit_faces[edge_index] = face_index
        hit_distances[edge_index] = distance


def load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(path, process=False)
    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError(f"Expected one triangle mesh at {path}.")
    return loaded


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def obj_surface_position_count(path: Path) -> int:
    referenced_positions: set[int] = set()
    with path.open("r", encoding="utf-8", errors="replace") as source:
        for line in source:
            if not line.startswith("f "):
                continue
            for corner in line.split()[1:]:
                position = corner.split("/", 1)[0]
                if position:
                    referenced_positions.add(int(position))
    return len(referenced_positions)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloth", required=True, type=Path)
    parser.add_argument("--body", required=True, type=Path)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cloth_path = args.cloth.resolve()
    body_path = args.body.resolve()
    cloth = load_mesh(cloth_path)
    body = load_mesh(body_path)
    if float(body.extents.max()) < 10.0 and float(cloth.extents.max()) > 10.0:
        body.apply_scale(100.0)

    wp.init()
    device = "cuda:0" if args.device == "auto" and wp.is_cuda_available() else args.device
    if device == "auto":
        device = "cpu"
    body_points = wp.array(np.asarray(body.vertices, dtype=np.float32), dtype=wp.vec3, device=device)
    body_indices = wp.array(np.asarray(body.faces, dtype=np.int32).reshape(-1), dtype=wp.int32, device=device)
    body_mesh = wp.Mesh(body_points, body_indices)

    cloth_points_np = np.asarray(cloth.vertices, dtype=np.float32)
    edges_np = np.asarray(cloth.edges_unique, dtype=np.int32)
    cloth_points = wp.array(cloth_points_np, dtype=wp.vec3, device=device)
    edges = wp.array(edges_np.reshape(-1), dtype=wp.int32, device=device)
    hit_faces = wp.full(len(edges_np), -1, dtype=wp.int32, device=device)
    hit_distances = wp.zeros(len(edges_np), dtype=float, device=device)
    wp.launch(
        locate_intersections,
        dim=len(edges_np),
        inputs=[edges, cloth_points, body_mesh.id],
        outputs=[hit_faces, hit_distances],
        device=device,
    )
    wp.synchronize_device(device)

    faces_np = hit_faces.numpy()
    distances_np = hit_distances.numpy()
    intersections = []
    for edge_index in np.flatnonzero(faces_np >= 0):
        first, second = edges_np[edge_index]
        origin = cloth_points_np[first]
        endpoint = cloth_points_np[second]
        direction = endpoint - origin
        length = float(np.linalg.norm(direction))
        location = origin + direction * (float(distances_np[edge_index]) / length)
        intersections.append(
            {
                "edge_index": int(edge_index),
                "vertex_indices": [int(first), int(second)],
                "body_face": int(faces_np[edge_index]),
                "location_cm": [float(value) for value in location],
                "edge_start_cm": [float(value) for value in origin],
                "edge_end_cm": [float(value) for value in endpoint],
            }
        )
    result = {
                "schema_version": "patterna.render-surface-intersections/1.0",
                "cloth_path": str(cloth_path),
                "cloth_sha256": sha256(cloth_path),
                "cloth_source_surface_vertex_count": obj_surface_position_count(cloth_path),
                "cloth_evaluated_vertex_count": int(len(cloth.vertices)),
                "cloth_triangle_count": int(len(cloth.faces)),
                "cloth_edge_count": int(len(edges_np)),
                "body_path": str(body_path),
                "body_sha256": sha256(body_path),
                "body_vertex_count": int(len(body.vertices)),
                "body_triangle_count": int(len(body.faces)),
                "count": len(intersections),
                "intersections": intersections,
    }
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        output_path = args.output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized, encoding="utf-8")
        print(f"Wrote render-surface intersection evidence to {output_path}")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
