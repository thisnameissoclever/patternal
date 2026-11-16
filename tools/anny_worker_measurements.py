"""Deterministic, differentiable measurement objectives for the Anny worker.

Every station rule is declared here in code. Landmarks come from the anny rig's
rest bone heads plus mesh-feature rules; section circumferences, extents, and
projections reuse the proven ``mhr_anthropometry`` edge-intersection machinery.
Topology captures happen at stage boundaries; evaluations stay differentiable
with respect to the vertex tensor inside a stage.

Coordinate convention: the anny body is Z-up with vertices in meters. All
public values are centimeters. The front direction sign is detected from the
foot-to-toe direction and applied so that +front is positive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

import numpy as np
import torch

from mhr_anthropometry import (
    SectionTopology,
    build_section_topology,
    section_extent_cm,
    section_perimeter_cm,
    section_points_cm,
)


VERTICAL = 2


@dataclass(frozen=True)
class Landmarks:
    """Rig- and mesh-derived landmark positions in centimeters (Z-up)."""

    bone_heads_cm: dict[str, np.ndarray]
    floor_z: float
    crown_z: float
    front_sign: float
    left_bust_apex: int
    right_bust_apex: int

    @property
    def stature_cm(self) -> float:
        return self.crown_z - self.floor_z


def detect_front_sign(bone_heads_cm: Mapping[str, np.ndarray]) -> float:
    toe = 0.5 * (bone_heads_cm["toe3-1.L"] + bone_heads_cm["toe3-1.R"])
    heel = 0.5 * (bone_heads_cm["foot.L"] + bone_heads_cm["foot.R"])
    forward = toe[1] - heel[1]
    if forward == 0.0:
        raise ValueError("The anny foot direction is degenerate; cannot detect front.")
    return 1.0 if forward > 0.0 else -1.0


def extract_landmarks(
    vertices_cm: np.ndarray,
    bone_labels: list[str],
    bone_heads_cm: np.ndarray,
) -> Landmarks:
    heads = {label: bone_heads_cm[index] for index, label in enumerate(bone_labels)}
    floor_z = float(vertices_cm[:, VERTICAL].min())
    crown_z = float(vertices_cm[:, VERTICAL].max())
    front = detect_front_sign(heads)

    shoulder_z = 0.5 * (heads["upperarm01.L"][VERTICAL] + heads["upperarm01.R"][VERTICAL])
    hip_z = 0.5 * (heads["upperleg01.L"][VERTICAL] + heads["upperleg01.R"][VERTICAL])
    band_low = hip_z + 0.62 * (shoulder_z - hip_z)
    band_high = shoulder_z - 0.08 * (shoulder_z - hip_z)
    in_band = (vertices_cm[:, VERTICAL] >= band_low) & (vertices_cm[:, VERTICAL] <= band_high)
    torso_width = abs(heads["upperarm01.L"][0] - heads["upperarm01.R"][0])
    near_center = np.abs(vertices_cm[:, 0]) <= 0.5 * torso_width
    candidates = in_band & near_center

    def apex(side_mask: np.ndarray) -> int:
        indices = np.flatnonzero(candidates & side_mask)
        if indices.size == 0:
            raise ValueError("No bust-apex candidate vertices were found.")
        projections = front * vertices_cm[indices, 1]
        return int(indices[int(np.argmax(projections))])

    left_apex = apex(vertices_cm[:, 0] < 0.0)
    right_apex = apex(vertices_cm[:, 0] > 0.0)
    return Landmarks(
        bone_heads_cm=heads,
        floor_z=floor_z,
        crown_z=crown_z,
        front_sign=front,
        left_bust_apex=left_apex,
        right_bust_apex=right_apex,
    )


def _limb_frame(
    origin: np.ndarray, target: np.ndarray, front_sign: float = 1.0
) -> np.ndarray:
    """Rotation whose third row maps the limb axis onto +Z.

    The in-plane axes are arbitrary; anatomical directions are measured with
    ``front-extent``, which projects the body's front direction into the
    section plane at evaluation time.
    """
    del front_sign
    axis = target - origin
    length = float(np.linalg.norm(axis))
    if length <= 0.0:
        raise ValueError("A limb frame requires two distinct joints.")
    z_axis = axis / length
    helper = np.array([1.0, 0.0, 0.0]) if abs(z_axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    x_axis = np.cross(helper, z_axis)
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)
    return np.stack([x_axis, y_axis, z_axis])


@dataclass(frozen=True)
class LimbSection:
    """A circumference section perpendicular to a limb segment."""

    name: str
    vertex_indices: np.ndarray
    rotation: np.ndarray
    topology: SectionTopology


def build_limb_section(
    vertices_cm: np.ndarray,
    faces: np.ndarray,
    *,
    name: str,
    origin_cm: np.ndarray,
    target_cm: np.ndarray,
    fraction: float,
    radius_cm: float,
    front_sign: float = 1.0,
) -> LimbSection:
    rotation = _limb_frame(origin_cm, target_cm, front_sign)
    axis = target_cm - origin_cm
    length = float(np.linalg.norm(axis))
    direction = axis / length
    relative = vertices_cm - origin_cm[None, :]
    along = relative @ direction
    radial = np.linalg.norm(relative - np.outer(along, direction), axis=1)
    keep = (along >= -0.15 * length) & (along <= 1.15 * length) & (radial <= radius_cm)
    vertex_indices = np.flatnonzero(keep)
    if vertex_indices.size < 8:
        raise ValueError(f"Limb section {name} selected too few vertices.")
    remap = -np.ones(len(vertices_cm), dtype=np.int64)
    remap[vertex_indices] = np.arange(vertex_indices.size)
    face_keep = keep[faces].all(axis=1)
    local_faces = remap[faces[face_keep]]
    local_vertices = (vertices_cm[vertex_indices] - origin_cm[None, :]) @ rotation.T
    span = float(local_vertices[:, VERTICAL].max() - local_vertices[:, VERTICAL].min())
    if span <= 0.0:
        raise ValueError(f"Limb section {name} has no axial span.")
    height = fraction * length
    ratio = (height - float(local_vertices[:, VERTICAL].min())) / span
    topology = build_section_topology(
        local_vertices,
        local_faces.astype(np.int64),
        name=name,
        height_ratio=float(np.clip(ratio, 0.02, 0.98)),
        section_axis=VERTICAL,
        require_centered=False,
        torso_half_width_cm=1_000.0,
    )
    return LimbSection(
        name=name,
        vertex_indices=vertex_indices,
        rotation=rotation,
        topology=topology,
    )


def limb_section_points(
    vertices_cm: torch.Tensor,
    section: LimbSection,
    origin_cm: np.ndarray,
) -> torch.Tensor:
    rotation = torch.as_tensor(section.rotation, dtype=vertices_cm.dtype)
    origin = torch.as_tensor(origin_cm, dtype=vertices_cm.dtype)
    local = (vertices_cm[:, section.vertex_indices, :] - origin) @ rotation.T
    return local


def limb_perimeter_cm(
    vertices_cm: torch.Tensor,
    section: LimbSection,
    origin_cm: np.ndarray,
) -> torch.Tensor:
    local = limb_section_points(vertices_cm, section, origin_cm)
    return section_perimeter_cm(local, section.topology)


def limb_extent_cm(
    vertices_cm: torch.Tensor,
    section: LimbSection,
    origin_cm: np.ndarray,
    axis: int,
) -> torch.Tensor:
    local = limb_section_points(vertices_cm, section, origin_cm)
    return section_extent_cm(local, section.topology, axis=axis)


def horizontal_section(
    vertices_cm: np.ndarray,
    faces: np.ndarray,
    *,
    name: str,
    height_cm: float,
    x_window: tuple[float, float] | None = None,
    radial_window: tuple[float, float, float] | None = None,
) -> SectionTopology | LimbSection:
    """A horizontal body section restricted to an x window or a radial window.

    A plane cut sums every loop it crosses, so a neck cut that also clips the
    shoulders reports their perimeters too. ``radial_window`` takes a
    ``(center_x, center_y, radius)`` cylinder about the vertical axis and keeps
    only the vertices inside it, which isolates one anatomical loop.
    """
    if radial_window is not None:
        center_x, center_y, radius = radial_window
        distance = np.hypot(
            vertices_cm[:, 0] - center_x, vertices_cm[:, 1] - center_y
        )
        keep = distance <= radius
        vertex_indices = np.flatnonzero(keep)
        if vertex_indices.size < 8:
            raise ValueError(f"Radial section {name} selected too few vertices.")
        remap = -np.ones(len(vertices_cm), dtype=np.int64)
        remap[vertex_indices] = np.arange(vertex_indices.size)
        face_keep = keep[faces].all(axis=1)
        local_faces = remap[faces[face_keep]].astype(np.int64)
        local_vertices = vertices_cm[vertex_indices]
        floor = float(local_vertices[:, VERTICAL].min())
        span = float(np.ptp(local_vertices[:, VERTICAL]))
        if span <= 0.0:
            raise ValueError(f"Radial section {name} has no vertical span.")
        topology = build_section_topology(
            local_vertices,
            local_faces,
            name=name,
            height_ratio=float(np.clip((height_cm - floor) / span, 0.02, 0.98)),
            section_axis=VERTICAL,
            require_centered=False,
            torso_half_width_cm=1_000.0,
        )
        return LimbSection(
            name=name,
            vertex_indices=vertex_indices,
            rotation=np.eye(3),
            topology=topology,
        )
    if x_window is None:
        floor = float(vertices_cm[:, VERTICAL].min())
        span = float(np.ptp(vertices_cm[:, VERTICAL]))
        return build_section_topology(
            vertices_cm,
            faces,
            name=name,
            height_ratio=(height_cm - floor) / span,
            section_axis=VERTICAL,
            require_centered=False,
            torso_half_width_cm=1_000.0,
        )
    keep = (vertices_cm[:, 0] >= x_window[0]) & (vertices_cm[:, 0] <= x_window[1])
    vertex_indices = np.flatnonzero(keep)
    remap = -np.ones(len(vertices_cm), dtype=np.int64)
    remap[vertex_indices] = np.arange(vertex_indices.size)
    face_keep = keep[faces].all(axis=1)
    local_faces = remap[faces[face_keep]].astype(np.int64)
    local_vertices = vertices_cm[vertex_indices]
    floor = float(local_vertices[:, VERTICAL].min())
    span = float(np.ptp(local_vertices[:, VERTICAL]))
    topology = build_section_topology(
        local_vertices,
        local_faces,
        name=name,
        height_ratio=(height_cm - floor) / span,
        section_axis=VERTICAL,
        require_centered=False,
        torso_half_width_cm=1_000.0,
    )
    return LimbSection(
        name=name,
        vertex_indices=vertex_indices,
        rotation=np.eye(3),
        topology=topology,
    )


def section_value(
    vertices_cm: torch.Tensor,
    section: SectionTopology | LimbSection,
    *,
    kind: str,
    axis: int = 1,
    front_sign: float = 1.0,
) -> torch.Tensor:
    if isinstance(section, LimbSection):
        origin = np.zeros(3)
        local = limb_section_points(vertices_cm, section, origin)
        if kind == "circumference":
            return section_perimeter_cm(local, section.topology)
        if kind == "extent":
            return section_extent_cm(local, section.topology, axis=axis)
        if kind == "front-extent":
            front_local = section.rotation @ np.array([0.0, front_sign, 0.0])
            front_local[2] = 0.0
            norm = np.linalg.norm(front_local)
            if norm < 1.0e-9:
                raise ValueError("The limb axis is parallel to the front direction.")
            front_local /= norm
            direction = torch.as_tensor(front_local, dtype=vertices_cm.dtype)
            points = section_points_cm(local, section.topology)
            values = (points @ direction).flatten(start_dim=1)
            return values.amax(dim=1) - values.amin(dim=1)
        if kind == "front-projection":
            points = section_points_cm(local, section.topology)
            return (front_sign * points[:, :, :, 1]).flatten(start_dim=1).amax(dim=1)
        if kind == "back-projection":
            points = section_points_cm(local, section.topology)
            return (-front_sign * points[:, :, :, 1]).flatten(start_dim=1).amax(dim=1)
        if kind == "front-arc":
            points = section_points_cm(local, section.topology)
            midpoints_front = front_sign * points.mean(dim=2)[:, :, 1]
            lengths = torch.linalg.vector_norm(
                points[:, :, 0, :] - points[:, :, 1, :], dim=2
            )
            return (lengths * (midpoints_front > 0.0)).sum(dim=1)
        if kind == "back-arc":
            points = section_points_cm(local, section.topology)
            midpoints_front = front_sign * points.mean(dim=2)[:, :, 1]
            lengths = torch.linalg.vector_norm(
                points[:, :, 0, :] - points[:, :, 1, :], dim=2
            )
            return (lengths * (midpoints_front <= 0.0)).sum(dim=1)
        raise ValueError(f"Unsupported limb section value kind: {kind}")
    if kind == "circumference":
        return section_perimeter_cm(vertices_cm, section)
    if kind == "extent":
        return section_extent_cm(vertices_cm, section, axis=axis)
    if kind == "front-projection":
        points = section_points_cm(vertices_cm, section)
        return (front_sign * points[:, :, :, 1]).flatten(start_dim=1).amax(dim=1)
    if kind == "back-projection":
        points = section_points_cm(vertices_cm, section)
        return (-front_sign * points[:, :, :, 1]).flatten(start_dim=1).amax(dim=1)
    if kind == "front-arc":
        points = section_points_cm(vertices_cm, section)
        midpoints_front = front_sign * points.mean(dim=2)[:, :, 1]
        lengths = torch.linalg.vector_norm(points[:, :, 0, :] - points[:, :, 1, :], dim=2)
        return (lengths * (midpoints_front > 0.0)).sum(dim=1)
    if kind == "back-arc":
        points = section_points_cm(vertices_cm, section)
        midpoints_front = front_sign * points.mean(dim=2)[:, :, 1]
        lengths = torch.linalg.vector_norm(points[:, :, 0, :] - points[:, :, 1, :], dim=2)
        return (lengths * (midpoints_front <= 0.0)).sum(dim=1)
    raise ValueError(f"Unsupported section value kind: {kind}")


def minimum_circumference_height(
    vertices_cm: np.ndarray,
    faces: np.ndarray,
    *,
    low_cm: float,
    high_cm: float,
    samples: int = 25,
    x_window: tuple[float, float] | None = None,
) -> float:
    """Deterministically locate the minimum-circumference height in a band."""
    best_height = low_cm
    best_value = float("inf")
    tensor = torch.as_tensor(vertices_cm[None, :, :], dtype=torch.float64)
    for step in range(samples):
        height = low_cm + (high_cm - low_cm) * step / (samples - 1)
        try:
            section = horizontal_section(
                vertices_cm, faces, name="scan", height_cm=height, x_window=x_window
            )
            value = float(section_value(tensor, section, kind="circumference")[0])
        except ValueError:
            continue
        if value < best_value:
            best_value = value
            best_height = height
    if not np.isfinite(best_value):
        raise ValueError("No valid circumference section was found in the band.")
    return best_height


def maximum_circumference_height(
    vertices_cm: np.ndarray,
    faces: np.ndarray,
    *,
    low_cm: float,
    high_cm: float,
    samples: int = 25,
    x_window: tuple[float, float] | None = None,
) -> float:
    best_height = low_cm
    best_value = -float("inf")
    tensor = torch.as_tensor(vertices_cm[None, :, :], dtype=torch.float64)
    for step in range(samples):
        height = low_cm + (high_cm - low_cm) * step / (samples - 1)
        try:
            section = horizontal_section(
                vertices_cm, faces, name="scan", height_cm=height, x_window=x_window
            )
            value = float(section_value(tensor, section, kind="circumference")[0])
        except ValueError:
            continue
        if value > best_value:
            best_value = value
            best_height = height
    if not np.isfinite(best_value):
        raise ValueError("No valid circumference section was found in the band.")
    return best_height
