#!/usr/bin/env python3
"""Build and quantify a simplified cloth-collision body with Blender."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


def parse_args() -> argparse.Namespace:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--target-face-count", type=int, default=10000)
    parser.add_argument("--maximum-distance-cm", type=float, default=0.50)
    parser.add_argument("--p95-distance-cm", type=float, default=0.15)
    parser.add_argument("--floor-datum-limit-cm", type=float, default=0.10)
    return parser.parse_args(arguments)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_obj(path: Path) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("v "):
            values = raw_line.split()
            vertex = tuple(float(value) for value in values[1:4])
            if len(vertex) != 3 or not all(math.isfinite(value) for value in vertex):
                raise ValueError(f"OBJ contains an invalid vertex: {path}")
            vertices.append(vertex)
        elif raw_line.startswith("f "):
            corners = raw_line.split()[1:]
            if len(corners) != 3:
                raise ValueError(f"Collision source must be triangulated: {path}")
            face = tuple(int(corner.split("/")[0]) - 1 for corner in corners)
            faces.append(face)
    if not vertices or not faces:
        raise ValueError(f"OBJ contains no usable mesh: {path}")
    if min(min(face) for face in faces) < 0 or max(max(face) for face in faces) >= len(vertices):
        raise ValueError(f"OBJ contains an out-of-range face index: {path}")
    return vertices, faces


def write_obj(
    path: Path,
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    source_hash: str,
) -> None:
    lines = [
        "# Patterna derived cloth-collision proxy",
        f"# source_sha256 {source_hash}",
    ]
    lines.extend(f"v {x:.9f} {y:.9f} {z:.9f}" for x, y, z in vertices)
    lines.extend(f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("Cannot calculate a percentile without samples.")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def distance_metrics(values_m: list[float]) -> dict[str, float | int]:
    if not values_m:
        raise ValueError("Cannot calculate distance metrics without samples.")
    return {
        "sampleCount": len(values_m),
        "maximumDistanceCm": 100.0 * max(values_m),
        "meanDistanceCm": 100.0 * sum(values_m) / len(values_m),
        "rootMeanSquareDistanceCm": 100.0
        * math.sqrt(sum(value * value for value in values_m) / len(values_m)),
        "p95DistanceCm": 100.0 * percentile(values_m, 0.95),
        "p99DistanceCm": 100.0 * percentile(values_m, 0.99),
    }


def edge_topology(faces: list[tuple[int, int, int]]) -> dict[str, int]:
    counts: dict[tuple[int, int], int] = {}
    for face in faces:
        for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = (min(first, second), max(first, second))
            counts[edge] = counts.get(edge, 0) + 1
    vertices = set(index for face in faces for index in face)
    adjacency = {index: set() for index in vertices}
    for first, second in counts:
        adjacency[first].add(second)
        adjacency[second].add(first)
    remaining = set(vertices)
    component_count = 0
    while remaining:
        component_count += 1
        pending = [remaining.pop()]
        while pending:
            current = pending.pop()
            neighbors = adjacency[current] & remaining
            remaining.difference_update(neighbors)
            pending.extend(neighbors)
    return {
        "edgeCount": len(counts),
        "boundaryEdgeCount": sum(count == 1 for count in counts.values()),
        "nonManifoldEdgeCount": sum(count != 2 for count in counts.values()),
        "connectedComponentCount": component_count,
    }


def bounds(vertices: list[tuple[float, float, float]]) -> dict[str, list[float]]:
    return {
        "minimumM": [min(vertex[axis] for vertex in vertices) for axis in range(3)],
        "maximumM": [max(vertex[axis] for vertex in vertices) for axis in range(3)],
    }


def surface_area(vertices, faces) -> float:
    from mathutils import Vector

    return sum(
        0.5 * (Vector(vertices[b]) - Vector(vertices[a])).cross(
            Vector(vertices[c]) - Vector(vertices[a])
        ).length
        for a, b, c in faces
    )


def signed_volume(vertices, faces) -> float:
    from mathutils import Vector

    return sum(
        Vector(vertices[a]).dot(Vector(vertices[b]).cross(Vector(vertices[c]))) / 6.0
        for a, b, c in faces
    )


def semantic_region(vertex, floor_m: float, height_m: float) -> str:
    ratio = (float(vertex[1]) - floor_m) / height_m
    lateral = abs(float(vertex[0]))
    if ratio >= 0.86:
        return "head"
    if ratio < 0.49:
        return "legs"
    arm_boundary = 0.25 if ratio < 0.70 else 0.17 if ratio < 0.77 else 0.22
    return "arms" if lateral > arm_boundary else "torso"


def majority_face_regions(
    faces: list[tuple[int, int, int]],
    vertex_regions: list[str],
) -> list[str]:
    order = {name: index for index, name in enumerate(("head", "torso", "arms", "legs"))}
    regions: list[str] = []
    for face in faces:
        counts = Counter(vertex_regions[index] for index in face)
        regions.append(
            max(counts, key=lambda region: (counts[region], -order[region]))
        )
    return regions


def sample_points_and_regions(vertices, faces, vertex_regions, face_regions):
    from mathutils import Vector

    points = [Vector(vertex) for vertex in vertices]
    points.extend(
        (Vector(vertices[a]) + Vector(vertices[b]) + Vector(vertices[c])) / 3.0
        for a, b, c in faces
    )
    return points, list(vertex_regions) + list(face_regions)


def nearest_distances_by_region(
    points,
    point_regions: list[str],
    surface,
    surface_face_regions: list[str] | None = None,
) -> dict[str, list[float]]:
    distances: dict[str, list[float]] = {
        region: [] for region in ("head", "torso", "arms", "legs")
    }
    for point, point_region in zip(points, point_regions):
        nearest = surface.find_nearest(point)
        if nearest is None:
            raise ValueError("Could not find the nearest collision-proxy surface point.")
        region = (
            surface_face_regions[int(nearest[2])]
            if surface_face_regions is not None
            else point_region
        )
        distances[region].append(float(nearest[3]))
    return distances


def decimate(vertices, faces, target_face_count: int):
    import bmesh
    import bpy

    mesh = bpy.data.meshes.new("PatternaCollisionSource")
    mesh.from_pydata(vertices, [], faces)
    mesh.validate(verbose=False)
    mesh.update()
    source = bpy.data.objects.new("PatternaCollisionSource", mesh)
    bpy.context.collection.objects.link(source)
    modifier = source.modifiers.new("PatternaCollisionDecimate", "DECIMATE")
    modifier.decimate_type = "COLLAPSE"
    modifier.ratio = target_face_count / len(faces)
    modifier.use_collapse_triangulate = True
    evaluated = source.evaluated_get(bpy.context.evaluated_depsgraph_get())
    result = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=False)
    triangulated = bmesh.new()
    triangulated.from_mesh(result)
    bmesh.ops.triangulate(triangulated, faces=list(triangulated.faces))
    triangulated.to_mesh(result)
    triangulated.free()
    result.validate(verbose=False)
    result.update()
    result_vertices = [tuple(float(value) for value in vertex.co) for vertex in result.vertices]
    result_faces = [tuple(int(index) for index in polygon.vertices) for polygon in result.polygons]
    if any(len(face) != 3 for face in result_faces):
        raise ValueError("Blender decimation produced a non-triangular face.")
    return result_vertices, result_faces


def main() -> None:
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    args = parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve()
    report_path = args.report.resolve()
    if args.target_face_count < 100:
        raise ValueError("--target-face-count must be at least 100.")
    if min(args.maximum_distance_cm, args.p95_distance_cm, args.floor_datum_limit_cm) <= 0:
        raise ValueError("Collision-proxy thresholds must be positive.")
    source_vertices, source_faces = read_obj(input_path)
    if args.target_face_count >= len(source_faces):
        raise ValueError("Target face count must simplify the source mesh.")
    source_hash = sha256(input_path)
    proxy_vertices, proxy_faces = decimate(
        source_vertices,
        source_faces,
        args.target_face_count,
    )
    source_surface = BVHTree.FromPolygons(
        [Vector(vertex) for vertex in source_vertices], source_faces, all_triangles=True
    )
    proxy_surface = BVHTree.FromPolygons(
        [Vector(vertex) for vertex in proxy_vertices], proxy_faces, all_triangles=True
    )
    if source_surface is None or proxy_surface is None:
        raise ValueError("Could not build collision-proxy comparison surfaces.")
    floor_m = min(vertex[1] for vertex in source_vertices)
    height_m = max(vertex[1] for vertex in source_vertices) - floor_m
    source_vertex_regions = [
        semantic_region(vertex, floor_m, height_m) for vertex in source_vertices
    ]
    source_face_regions = majority_face_regions(source_faces, source_vertex_regions)
    proxy_vertex_regions = [
        semantic_region(vertex, floor_m, height_m) for vertex in proxy_vertices
    ]
    proxy_face_regions = majority_face_regions(proxy_faces, proxy_vertex_regions)
    source_points, source_point_regions = sample_points_and_regions(
        source_vertices,
        source_faces,
        source_vertex_regions,
        source_face_regions,
    )
    proxy_points, proxy_point_regions = sample_points_and_regions(
        proxy_vertices,
        proxy_faces,
        proxy_vertex_regions,
        proxy_face_regions,
    )
    source_to_proxy_by_region = nearest_distances_by_region(
        source_points,
        source_point_regions,
        proxy_surface,
    )
    proxy_to_source_by_region = nearest_distances_by_region(
        proxy_points,
        proxy_point_regions,
        source_surface,
        source_face_regions,
    )
    source_to_proxy = distance_metrics(
        [value for values in source_to_proxy_by_region.values() for value in values]
    )
    proxy_to_source = distance_metrics(
        [value for values in proxy_to_source_by_region.values() for value in values]
    )
    regional_registration = {
        region: {
            "sourceToProxy": distance_metrics(source_to_proxy_by_region[region]),
            "proxyToSource": distance_metrics(proxy_to_source_by_region[region]),
        }
        for region in source_to_proxy_by_region
    }
    source_edges = edge_topology(source_faces)
    proxy_edges = edge_topology(proxy_faces)
    floor_error_cm = 100.0 * abs(
        min(vertex[1] for vertex in source_vertices)
        - min(vertex[1] for vertex in proxy_vertices)
    )
    source_area = surface_area(source_vertices, source_faces)
    proxy_area = surface_area(proxy_vertices, proxy_faces)
    source_volume = signed_volume(source_vertices, source_faces)
    proxy_volume = signed_volume(proxy_vertices, proxy_faces)
    issues: list[str] = []
    for direction, metrics in (
        ("sourceToProxy", source_to_proxy),
        ("proxyToSource", proxy_to_source),
    ):
        if metrics["maximumDistanceCm"] > args.maximum_distance_cm:
            issues.append(
                f"{direction} maximum {metrics['maximumDistanceCm']:.6f} cm exceeds "
                f"{args.maximum_distance_cm:.6f} cm"
            )
        if metrics["p95DistanceCm"] > args.p95_distance_cm:
            issues.append(
                f"{direction} p95 {metrics['p95DistanceCm']:.6f} cm exceeds "
                f"{args.p95_distance_cm:.6f} cm"
            )
    for region, directions in regional_registration.items():
        for direction, metrics in directions.items():
            if metrics["maximumDistanceCm"] > args.maximum_distance_cm:
                issues.append(
                    f"{region} {direction} maximum "
                    f"{metrics['maximumDistanceCm']:.6f} cm exceeds "
                    f"{args.maximum_distance_cm:.6f} cm"
                )
            if metrics["p95DistanceCm"] > args.p95_distance_cm:
                issues.append(
                    f"{region} {direction} p95 {metrics['p95DistanceCm']:.6f} cm "
                    f"exceeds {args.p95_distance_cm:.6f} cm"
                )
    if proxy_edges["nonManifoldEdgeCount"] != source_edges["nonManifoldEdgeCount"]:
        issues.append("proxy changed the source non-manifold edge count")
    if proxy_edges["connectedComponentCount"] != source_edges["connectedComponentCount"]:
        issues.append("proxy changed the source connected-component count")
    if source_volume == 0.0 or proxy_volume == 0.0 or source_volume * proxy_volume < 0.0:
        issues.append("proxy has zero or reversed signed volume")
    if floor_error_cm > args.floor_datum_limit_cm:
        issues.append(
            f"floor datum error {floor_error_cm:.6f} cm exceeds "
            f"{args.floor_datum_limit_cm:.6f} cm"
        )
    write_obj(output_path, proxy_vertices, proxy_faces, source_hash)
    report: dict[str, Any] = {
        "schemaVersion": "patterna.body-collision-proxy/1.0",
        "accepted": not issues,
        "acceptanceScope": "derived-cloth-collision-surface",
        "productAccepted": False,
        "issues": issues,
        "generator": {
            "blenderVersion": bpy.app.version_string,
            "method": "Blender collapse decimation with triangulation",
            "targetFaceCount": args.target_face_count,
        },
        "thresholds": {
            "maximumDistanceCm": args.maximum_distance_cm,
            "p95DistanceCm": args.p95_distance_cm,
            "floorDatumLimitCm": args.floor_datum_limit_cm,
        },
        "inputs": {
            "sourceMesh": str(input_path),
            "sourceMeshSha256": source_hash,
            "sourceVertexCount": len(source_vertices),
            "sourceFaceCount": len(source_faces),
            "sourceBounds": bounds(source_vertices),
            "sourceTopology": source_edges,
        },
        "surfaceRegistration": {
            "sampling": "all vertices and all triangle centroids in both directions",
            "regionalMethod": (
                "source-body coordinate-semantic head, torso, arms, and legs; "
                "reverse samples inherit the nearest source triangle region"
            ),
            "sourceToProxy": source_to_proxy,
            "proxyToSource": proxy_to_source,
            "regions": regional_registration,
            "floorDatumErrorCm": floor_error_cm,
        },
        "shape": {
            "sourceSurfaceAreaM2": source_area,
            "proxySurfaceAreaM2": proxy_area,
            "relativeSurfaceAreaChange": proxy_area / source_area - 1.0,
            "sourceSignedVolumeM3": source_volume,
            "proxySignedVolumeM3": proxy_volume,
            "relativeSignedVolumeChange": proxy_volume / source_volume - 1.0,
        },
        "outputs": {
            "proxyMesh": str(output_path),
            "proxyMeshSha256": sha256(output_path),
            "proxyVertexCount": len(proxy_vertices),
            "proxyFaceCount": len(proxy_faces),
            "proxyBounds": bounds(proxy_vertices),
            "proxyTopology": proxy_edges,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if issues:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
