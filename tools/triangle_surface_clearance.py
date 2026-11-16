#!/usr/bin/env python3
"""Prove a minimum clearance between two nonintersecting triangle surfaces."""

from __future__ import annotations

from collections import defaultdict
import itertools
from typing import Any

import numpy as np


EPSILON = 1.0e-12


def conservative_center_candidates(
    first_centers: np.ndarray,
    first_radii: np.ndarray,
    second_centers: np.ndarray,
    maximum_second_radius: float,
    threshold: float,
) -> list[list[int]]:
    """Return every second center within each conservative query radius.

    A uniform spatial hash keeps the proof independent of SciPy. Each query
    visits every grid cell touched by its bounding cube and then applies the
    exact center-radius test, so it cannot omit a pair that may violate the
    requested surface threshold.
    """

    cell_size = max(maximum_second_radius + threshold, EPSILON)
    cells: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    second_cell_coordinates = np.floor(second_centers / cell_size).astype(np.int64)
    for index, raw_coordinate in enumerate(second_cell_coordinates):
        coordinate = tuple(int(value) for value in raw_coordinate)
        cells[coordinate].append(index)

    result: list[list[int]] = []
    for center, radius in zip(first_centers, first_radii, strict=True):
        query_radius = float(radius) + maximum_second_radius + threshold
        lower = np.floor((center - query_radius) / cell_size).astype(np.int64)
        upper = np.floor((center + query_radius) / cell_size).astype(np.int64)
        candidates: list[int] = []
        coordinate_ranges = (
            range(int(lower[axis]), int(upper[axis]) + 1) for axis in range(3)
        )
        for coordinate in itertools.product(*coordinate_ranges):
            candidates.extend(cells.get(coordinate, ()))
        result.append(candidates)
    return result


def point_triangle_distance(point: np.ndarray, triangle: np.ndarray) -> float:
    """Return the Euclidean distance from one point to one triangle."""

    a, b, c = triangle
    ab = b - a
    ac = c - a
    ap = point - a
    d1 = float(np.dot(ab, ap))
    d2 = float(np.dot(ac, ap))
    if d1 <= 0.0 and d2 <= 0.0:
        return float(np.linalg.norm(ap))

    bp = point - b
    d3 = float(np.dot(ab, bp))
    d4 = float(np.dot(ac, bp))
    if d3 >= 0.0 and d4 <= d3:
        return float(np.linalg.norm(bp))

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        amount = d1 / (d1 - d3)
        return float(np.linalg.norm(point - (a + amount * ab)))

    cp = point - c
    d5 = float(np.dot(ab, cp))
    d6 = float(np.dot(ac, cp))
    if d6 >= 0.0 and d5 <= d6:
        return float(np.linalg.norm(cp))

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        amount = d2 / (d2 - d6)
        return float(np.linalg.norm(point - (a + amount * ac)))

    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        amount = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return float(np.linalg.norm(point - (b + amount * (c - b))))

    denominator = va + vb + vc
    if abs(denominator) <= EPSILON:
        return min(float(np.linalg.norm(point - vertex)) for vertex in triangle)
    inverse = 1.0 / denominator
    amount_b = vb * inverse
    amount_c = vc * inverse
    closest = a + ab * amount_b + ac * amount_c
    return float(np.linalg.norm(point - closest))


def segment_segment_distance(
    first_start: np.ndarray,
    first_end: np.ndarray,
    second_start: np.ndarray,
    second_end: np.ndarray,
) -> float:
    """Return the Euclidean distance between two closed line segments."""

    first_direction = first_end - first_start
    second_direction = second_end - second_start
    offset = first_start - second_start
    first_length_squared = float(np.dot(first_direction, first_direction))
    second_length_squared = float(np.dot(second_direction, second_direction))
    second_projection = float(np.dot(second_direction, offset))

    if first_length_squared <= EPSILON and second_length_squared <= EPSILON:
        return float(np.linalg.norm(first_start - second_start))
    if first_length_squared <= EPSILON:
        first_amount = 0.0
        second_amount = float(np.clip(second_projection / second_length_squared, 0.0, 1.0))
    else:
        first_projection = float(np.dot(first_direction, offset))
        if second_length_squared <= EPSILON:
            second_amount = 0.0
            first_amount = float(np.clip(-first_projection / first_length_squared, 0.0, 1.0))
        else:
            cross_projection = float(np.dot(first_direction, second_direction))
            denominator = (
                first_length_squared * second_length_squared
                - cross_projection * cross_projection
            )
            if abs(denominator) > EPSILON:
                first_amount = float(
                    np.clip(
                        (
                            cross_projection * second_projection
                            - first_projection * second_length_squared
                        )
                        / denominator,
                        0.0,
                        1.0,
                    )
                )
            else:
                first_amount = 0.0
            second_amount = (
                cross_projection * first_amount + second_projection
            ) / second_length_squared
            if second_amount < 0.0:
                second_amount = 0.0
                first_amount = float(
                    np.clip(-first_projection / first_length_squared, 0.0, 1.0)
                )
            elif second_amount > 1.0:
                second_amount = 1.0
                first_amount = float(
                    np.clip(
                        (cross_projection - first_projection) / first_length_squared,
                        0.0,
                        1.0,
                    )
                )

    first_closest = first_start + first_amount * first_direction
    second_closest = second_start + second_amount * second_direction
    return float(np.linalg.norm(first_closest - second_closest))


def triangle_triangle_distance(first: np.ndarray, second: np.ndarray) -> float:
    """Return distance for triangles already proven not to intersect."""

    distances = [
        *(point_triangle_distance(point, second) for point in first),
        *(point_triangle_distance(point, first) for point in second),
    ]
    edge_indices = ((0, 1), (1, 2), (2, 0))
    distances.extend(
        segment_segment_distance(
            first[first_edge[0]],
            first[first_edge[1]],
            second[second_edge[0]],
            second[second_edge[1]],
        )
        for first_edge in edge_indices
        for second_edge in edge_indices
    )
    return min(distances)


def prove_surface_clearance(
    first_vertices: np.ndarray,
    first_faces: np.ndarray,
    second_vertices: np.ndarray,
    second_faces: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    """Prove that two nonintersecting triangle surfaces meet a threshold.

    Bounding spheres conservatively select every triangle pair that could be
    closer than the threshold. Exact triangle distance then grades those pairs.
    When the gate passes, the reported metric is a proven lower bound rather
    than an invented global minimum above that bound.
    """

    if not np.isfinite(threshold) or threshold <= 0.0:
        raise ValueError("The clearance threshold must be finite and positive.")
    first_triangles = np.asarray(first_vertices, dtype=np.float64)[
        np.asarray(first_faces, dtype=np.int64)
    ]
    second_triangles = np.asarray(second_vertices, dtype=np.float64)[
        np.asarray(second_faces, dtype=np.int64)
    ]
    if first_triangles.ndim != 3 or first_triangles.shape[1:] != (3, 3):
        raise ValueError("The first surface does not contain valid triangles.")
    if second_triangles.ndim != 3 or second_triangles.shape[1:] != (3, 3):
        raise ValueError("The second surface does not contain valid triangles.")
    if not np.isfinite(first_triangles).all() or not np.isfinite(second_triangles).all():
        raise ValueError("Surface positions must be finite.")

    first_centers = np.mean(first_triangles, axis=1)
    second_centers = np.mean(second_triangles, axis=1)
    first_radii = np.max(
        np.linalg.norm(first_triangles - first_centers[:, None, :], axis=2),
        axis=1,
    )
    second_radii = np.max(
        np.linalg.norm(second_triangles - second_centers[:, None, :], axis=2),
        axis=1,
    )
    maximum_second_radius = float(np.max(second_radii))
    candidate_lists = conservative_center_candidates(
        first_centers,
        first_radii,
        second_centers,
        maximum_second_radius,
        threshold,
    )
    tested_pairs = 0
    minimum_candidate_distance = float("inf")
    closest_pair: tuple[int, int] | None = None
    for first_index, candidates in enumerate(candidate_lists):
        for second_index in candidates:
            center_distance = float(
                np.linalg.norm(first_centers[first_index] - second_centers[second_index])
            )
            if center_distance > first_radii[first_index] + second_radii[second_index] + threshold:
                continue
            tested_pairs += 1
            distance = triangle_triangle_distance(
                first_triangles[first_index],
                second_triangles[second_index],
            )
            if distance < minimum_candidate_distance:
                minimum_candidate_distance = distance
                closest_pair = (first_index, int(second_index))
            if distance < threshold:
                return {
                    "passed": False,
                    "requiredMinimum": float(threshold),
                    "measuredDistance": float(distance),
                    "provenLowerBound": None,
                    "closestTrianglePair": list(closest_pair),
                    "testedCandidatePairs": tested_pairs,
                    "method": "uniform spatial hash, conservative bounding spheres, and exact triangle distance",
                }
    return {
        "passed": True,
        "requiredMinimum": float(threshold),
        "measuredDistance": None,
        "provenLowerBound": float(threshold),
        "closestTrianglePair": None,
        "testedCandidatePairs": tested_pairs,
        "method": "uniform spatial hash, conservative bounding spheres, and exact triangle distance",
    }
