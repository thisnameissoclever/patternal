"""Differentiable torso-section measurements for stable MHR topology."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np
import torch


@dataclass(frozen=True)
class SectionTopology:
    name: str
    height_ratio: float
    edge_indices: np.ndarray
    reference_perimeter_cm: float
    section_axis: int = 1


def _edge_intersection(
    vertices_cm: np.ndarray,
    first: int,
    second: int,
    plane_cm: float,
    section_axis: int,
) -> tuple[np.ndarray, tuple[int, int]] | None:
    start = vertices_cm[first]
    end = vertices_cm[second]
    start_distance = float(start[section_axis] - plane_cm)
    end_distance = float(end[section_axis] - plane_cm)
    epsilon = 1.0e-9
    if abs(start_distance) <= epsilon and abs(end_distance) <= epsilon:
        return None
    if abs(start_distance) <= epsilon:
        ratio = 0.0
    elif abs(end_distance) <= epsilon:
        ratio = 1.0
    elif start_distance * end_distance < 0.0:
        ratio = start_distance / (start_distance - end_distance)
    else:
        return None
    point = start + (end - start) * ratio
    point[section_axis] = plane_cm
    return point, (first, second)


def build_section_topology(
    vertices_cm: np.ndarray,
    faces: np.ndarray,
    *,
    name: str,
    height_ratio: float,
    torso_half_width_cm: float = 34.0,
    section_axis: int = 1,
    require_centered: bool = True,
) -> SectionTopology:
    """Capture the centered torso loop as intersected triangle-edge pairs."""
    if vertices_cm.ndim != 2 or vertices_cm.shape[1] != 3:
        raise ValueError("MHR vertices must have shape (vertex_count, 3).")
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError("MHR faces must be triangles.")
    if not 0.0 < height_ratio < 1.0:
        raise ValueError("Section height ratio must be between zero and one.")
    if section_axis not in (0, 1, 2):
        raise ValueError("Section axis must be 0, 1, or 2.")

    floor = float(vertices_cm[:, section_axis].min())
    height = float(vertices_cm[:, section_axis].max() - floor)
    plane = floor + height_ratio * height
    segments: list[tuple[np.ndarray, np.ndarray, tuple[int, int], tuple[int, int]]] = []
    for face in faces:
        crossings: list[tuple[np.ndarray, tuple[int, int]]] = []
        for edge_index in range(3):
            first = int(face[edge_index])
            second = int(face[(edge_index + 1) % 3])
            crossing = _edge_intersection(
                vertices_cm, first, second, plane, section_axis
            )
            if crossing is None:
                continue
            if not any(np.linalg.norm(crossing[0] - existing[0]) <= 1.0e-8 for existing in crossings):
                crossings.append(crossing)
        if len(crossings) != 2:
            continue
        start, end = crossings
        if (
            section_axis == 1
            and abs(float((start[0][0] + end[0][0]) * 0.5)) > torso_half_width_cm
        ):
            continue
        segments.append((start[0], end[0], start[1], end[1]))

    endpoint_segments: dict[tuple[int, int], set[int]] = {}
    endpoint_keys: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for index, segment in enumerate(segments):
        keys = (
            tuple(sorted(segment[2])),
            tuple(sorted(segment[3])),
        )
        endpoint_keys.append(keys)
        for key in keys:
            endpoint_segments.setdefault(key, set()).add(index)

    components: list[set[int]] = []
    unvisited = set(range(len(segments)))
    while unvisited:
        pending = [unvisited.pop()]
        component: set[int] = set()
        while pending:
            segment_index = pending.pop()
            if segment_index in component:
                continue
            component.add(segment_index)
            for key in endpoint_keys[segment_index]:
                for neighbor in endpoint_segments[key]:
                    if neighbor in unvisited:
                        unvisited.remove(neighbor)
                        pending.append(neighbor)
        components.append(component)

    centered: list[tuple[float, set[int]]] = []
    for component in components:
        points = [segments[index][endpoint] for index in component for endpoint in (0, 1)]
        minimum_x = min(float(point[0]) for point in points)
        maximum_x = max(float(point[0]) for point in points)
        if require_centered and (minimum_x >= 0.0 or maximum_x <= 0.0):
            continue
        perimeter = sum(
            float(np.linalg.norm(segments[index][0] - segments[index][1]))
            for index in component
        )
        centered.append((perimeter, component))
    if not centered:
        raise ValueError(f"No centered MHR torso loop exists for {name}.")

    perimeter, selected = max(centered, key=lambda item: item[0])
    edge_indices = np.asarray(
        [[segments[index][2], segments[index][3]] for index in sorted(selected)],
        dtype=np.int64,
    )
    return SectionTopology(
        name=name,
        height_ratio=height_ratio,
        edge_indices=edge_indices,
        reference_perimeter_cm=perimeter,
        section_axis=section_axis,
    )


def section_points_cm(
    vertices_cm: torch.Tensor, topology: SectionTopology
) -> torch.Tensor:
    """Evaluate captured torso-section endpoints for batched MHR vertices."""
    if vertices_cm.ndim != 3 or vertices_cm.shape[2] != 3:
        raise ValueError("Batched MHR vertices must have shape (batch, vertex_count, 3).")
    edge_indices = torch.as_tensor(
        topology.edge_indices, dtype=torch.long, device=vertices_cm.device
    )
    axis = topology.section_axis
    floor = vertices_cm[:, :, axis].amin(dim=1)
    body_height = vertices_cm[:, :, axis].amax(dim=1) - floor
    plane = floor + topology.height_ratio * body_height
    starts = vertices_cm[:, edge_indices[:, :, 0], :]
    ends = vertices_cm[:, edge_indices[:, :, 1], :]
    denominator = ends[:, :, :, axis] - starts[:, :, :, axis]
    if torch.any(torch.abs(denominator) < 1.0e-8):
        raise ValueError(f"MHR section {topology.name} contains a horizontal crossing edge.")
    ratios = (plane[:, None, None] - starts[:, :, :, axis]) / denominator
    return starts + ratios[:, :, :, None] * (ends - starts)


def section_perimeter_cm(
    vertices_cm: torch.Tensor, topology: SectionTopology
) -> torch.Tensor:
    """Evaluate a captured torso perimeter for a batch of MHR vertex arrays."""
    points = section_points_cm(vertices_cm, topology)
    lengths = torch.linalg.vector_norm(points[:, :, 0, :] - points[:, :, 1, :], dim=2)
    return lengths.sum(dim=1)


def section_extent_cm(
    vertices_cm: torch.Tensor, topology: SectionTopology, *, axis: int
) -> torch.Tensor:
    if axis not in (0, 1, 2) or axis == topology.section_axis:
        raise ValueError("A section extent must be perpendicular to its section axis.")
    points = section_points_cm(vertices_cm, topology)
    values = points[:, :, :, axis].flatten(start_dim=1)
    return values.amax(dim=1) - values.amin(dim=1)


def measurement_vector_cm(
    vertices_cm: torch.Tensor, topologies: Sequence[SectionTopology]
) -> torch.Tensor:
    return torch.stack(
        [section_perimeter_cm(vertices_cm, topology) for topology in topologies],
        dim=1,
    )
