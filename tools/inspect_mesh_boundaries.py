#!/usr/bin/env python3
"""Report open boundary loops on the largest component of an OBJ mesh."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np
import trimesh


def boundary_loops(mesh: trimesh.Trimesh) -> list[list[int]]:
    edge_counts = np.bincount(mesh.edges_unique_inverse)
    boundary = mesh.edges_unique[edge_counts == 1]
    adjacency: dict[int, list[int]] = defaultdict(list)
    for first, second in boundary:
        adjacency[int(first)].append(int(second))
        adjacency[int(second)].append(int(first))
    invalid = {vertex: neighbors for vertex, neighbors in adjacency.items() if len(neighbors) != 2}
    if invalid:
        raise ValueError(f"Boundary graph is not a set of loops: {invalid}")

    remaining = {tuple(sorted((int(first), int(second)))) for first, second in boundary}
    loops: list[list[int]] = []
    while remaining:
        seed = next(iter(remaining))
        start, current = seed
        loop = [start]
        previous = start
        while True:
            remaining.discard(tuple(sorted((previous, current))))
            if current == start:
                break
            loop.append(current)
            candidates = [neighbor for neighbor in adjacency[current] if neighbor != previous]
            if len(candidates) != 1:
                raise ValueError("Could not trace one boundary loop")
            previous, current = current, candidates[0]
        loops.append(loop)
    return loops


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    args = parser.parse_args()
    loaded = trimesh.load(args.mesh, process=False, maintain_order=True)
    if not isinstance(loaded, trimesh.Trimesh):
        raise TypeError(f"Expected one mesh, received {type(loaded).__name__}")
    body = max(loaded.split(only_watertight=False), key=lambda component: len(component.faces))
    reports = []
    for loop in boundary_loops(body):
        coordinates = body.vertices[np.asarray(loop)]
        reports.append({
            "vertexCount": len(loop),
            "center": np.mean(coordinates, axis=0).tolist(),
            "minimum": np.min(coordinates, axis=0).tolist(),
            "maximum": np.max(coordinates, axis=0).tolist(),
        })
    reports.sort(key=lambda report: report["center"][2], reverse=True)
    print(json.dumps({
        "bodyVertices": len(body.vertices),
        "bodyFaces": len(body.faces),
        "watertight": body.is_watertight,
        "boundaryLoopCount": len(reports),
        "boundaryLoops": reports,
    }, indent=2))


if __name__ == "__main__":
    main()
