#!/usr/bin/env python3
"""Build a watertight cloth collider from the CharMorph outer body surface."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import trimesh


@dataclass(frozen=True)
class BoundaryCapReport:
    loop_count: int
    loop_vertex_counts: tuple[int, ...]
    minimum_loop_height_ratio: float
    maximum_loop_height_ratio: float


def boundary_loops(mesh: trimesh.Trimesh) -> list[list[int]]:
    edge_counts = np.bincount(mesh.edges_unique_inverse)
    boundary = mesh.edges_unique[edge_counts == 1]
    adjacency: dict[int, list[int]] = defaultdict(list)
    for first, second in boundary:
        adjacency[int(first)].append(int(second))
        adjacency[int(second)].append(int(first))
    invalid = {vertex: neighbors for vertex, neighbors in adjacency.items() if len(neighbors) != 2}
    if invalid:
        raise ValueError("CharMorph outer surface has a branched boundary graph")

    remaining = {tuple(sorted((int(first), int(second)))) for first, second in boundary}
    result: list[list[int]] = []
    while remaining:
        start, current = next(iter(remaining))
        previous = start
        loop = [start]
        while True:
            remaining.discard(tuple(sorted((previous, current))))
            if current == start:
                break
            loop.append(current)
            candidates = [neighbor for neighbor in adjacency[current] if neighbor != previous]
            if len(candidates) != 1:
                raise ValueError("Could not trace one CharMorph surface boundary")
            previous, current = current, candidates[0]
        result.append(loop)
    return result


def largest_outer_component(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    components = mesh.split(only_watertight=False)
    if not components:
        raise ValueError("CharMorph mesh has no connected components")
    return max(components, key=lambda component: len(component.faces)).copy()


def cap_face_openings(
    outer: trimesh.Trimesh,
    *,
    minimum_height_ratio: float = 0.84,
) -> tuple[trimesh.Trimesh, BoundaryCapReport]:
    """Cap eye and mouth openings without changing the garment-contact surface."""
    loops = boundary_loops(outer)
    if not loops:
        report = BoundaryCapReport(0, (), 1.0, 1.0)
        return outer.copy(), report

    source_vertices = np.asarray(outer.vertices, dtype=float)
    floor = float(source_vertices[:, 2].min())
    height = float(source_vertices[:, 2].max() - floor)
    if height <= 0.0:
        raise ValueError("CharMorph outer surface has no positive height")

    centers: list[np.ndarray] = []
    faces = np.asarray(outer.faces, dtype=np.int64).tolist()
    height_ratios: list[float] = []
    for loop in loops:
        coordinates = source_vertices[np.asarray(loop, dtype=np.int64)]
        center = np.mean(coordinates, axis=0)
        height_ratio = float((center[2] - floor) / height)
        if height_ratio < minimum_height_ratio:
            raise ValueError(
                "Refusing to cap a CharMorph opening on the garment-contact surface: "
                f"height ratio {height_ratio:.4f}"
            )
        center_index = len(source_vertices) + len(centers)
        centers.append(center)
        height_ratios.append(height_ratio)
        for index, first in enumerate(loop):
            second = loop[(index + 1) % len(loop)]
            faces.append([first, second, center_index])

    vertices = np.vstack((source_vertices, np.asarray(centers, dtype=float)))
    collider = trimesh.Trimesh(vertices=vertices, faces=np.asarray(faces), process=False)
    collider.remove_unreferenced_vertices()
    collider.fix_normals(multibody=False)
    if not collider.is_watertight:
        raise ValueError("Capped CharMorph collider is not watertight")
    if len(collider.split(only_watertight=False)) != 1:
        raise ValueError("Capped CharMorph collider is not one connected surface")
    report = BoundaryCapReport(
        loop_count=len(loops),
        loop_vertex_counts=tuple(len(loop) for loop in loops),
        minimum_loop_height_ratio=min(height_ratios),
        maximum_loop_height_ratio=max(height_ratios),
    )
    return collider, report


def build_collision_body(source: trimesh.Trimesh) -> tuple[trimesh.Trimesh, BoundaryCapReport]:
    outer = largest_outer_component(source)
    return cap_face_openings(outer)
