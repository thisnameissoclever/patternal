"""Measure front and back horizontal arcs from the exact collision body."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np
import trimesh


@dataclass(frozen=True)
class TorsoArcSection:
    height_cm: float
    circumference_cm: float
    front_arc_cm: float
    back_arc_cm: float
    front_fraction: float
    back_fraction: float
    front_mean_depth_cm: float
    back_mean_depth_cm: float
    point_count: int

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def _path_length_cm(points: np.ndarray) -> float:
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum() * 100.0)


def _forward_arc(points: np.ndarray, start: int, end: int) -> np.ndarray:
    if start <= end:
        return points[start : end + 1]
    return np.vstack((points[start:], points[: end + 1]))


def _length_weighted_depth_cm(points: np.ndarray) -> float:
    segments = np.diff(points, axis=0)
    lengths = np.linalg.norm(segments, axis=1)
    total = float(lengths.sum())
    if total <= 1.0e-10:
        raise ValueError("Torso section arc has zero length.")
    midpoints = 0.5 * (points[:-1, 2] + points[1:, 2])
    return float(np.dot(midpoints, lengths) / total * 100.0)


def split_front_back_arc(
    loop: np.ndarray,
    *,
    front_is_positive_depth: bool = True,
    side_seam_depth_cm: float | None = None,
) -> tuple[float, float, float, float]:
    """Split an ordered closed X/Y/Z loop at its lateral extrema.

    The returned tuple is front arc, back arc, front mean depth, and back
    mean depth, all in centimeters. The fitted MPFB collision body faces
    anatomical front toward positive GarmentCode Z. Blender's OBJ import maps
    that source axis to the positive camera-facing depth used by the diagnostic
    renderer, and the long bust arc lies on the same side.
    """

    points = np.asarray(loop, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 8:
        raise ValueError("Torso section must contain at least eight 3D points.")
    if not np.isfinite(points).all():
        raise ValueError("Torso section contains a non-finite coordinate.")
    if np.linalg.norm(points[0] - points[-1]) <= 1.0e-8:
        points = points[:-1]
    if len(points) < 8:
        raise ValueError("Torso section has too few unique points.")

    if side_seam_depth_cm is None:
        left = int(np.argmin(points[:, 0]))
        right = int(np.argmax(points[:, 0]))
    else:
        if not math.isfinite(side_seam_depth_cm):
            raise ValueError("Side-seam depth must be finite.")
        target_depth_m = side_seam_depth_cm / 100.0
        lateral_extent = float(np.max(np.abs(points[:, 0])))
        left_scores = np.where(
            points[:, 0] < 0.0,
            np.abs(points[:, 2] - target_depth_m)
            + 0.5 * np.abs(np.abs(points[:, 0]) - lateral_extent),
            np.inf,
        )
        right_scores = np.where(
            points[:, 0] > 0.0,
            np.abs(points[:, 2] - target_depth_m)
            + 0.5 * np.abs(np.abs(points[:, 0]) - lateral_extent),
            np.inf,
        )
        left = int(np.argmin(left_scores))
        right = int(np.argmin(right_scores))
    if left == right:
        raise ValueError("Torso section has no lateral width.")
    first = _forward_arc(points, left, right)
    second = _forward_arc(points, right, left)
    first_length = _path_length_cm(first)
    second_length = _path_length_cm(second)
    first_depth = _length_weighted_depth_cm(first)
    second_depth = _length_weighted_depth_cm(second)

    first_is_front = first_depth > second_depth
    if not front_is_positive_depth:
        first_is_front = not first_is_front
    if first_is_front:
        return first_length, second_length, first_depth, second_depth
    return second_length, first_length, second_depth, first_depth


def _central_torso_loop(section: trimesh.path.Path3D) -> np.ndarray:
    candidates: list[tuple[float, np.ndarray]] = []
    for raw_loop in section.discrete:
        loop = np.asarray(raw_loop, dtype=float)
        if len(loop) < 8:
            continue
        minimum_x = float(loop[:, 0].min())
        maximum_x = float(loop[:, 0].max())
        if minimum_x >= 0.0 or maximum_x <= 0.0:
            continue
        width = maximum_x - minimum_x
        if abs(float(loop[:, 0].mean())) > width * 0.12:
            continue
        perimeter = _path_length_cm(loop)
        candidates.append((perimeter, loop))
    if not candidates:
        raise RuntimeError("No centered closed torso loop crossed the requested plane.")
    return max(candidates, key=lambda candidate: candidate[0])[1]


def _front_point_at_x(
    loop: np.ndarray,
    target_x_m: float,
    *,
    front_is_positive_depth: bool = True,
    clamp_to_surface: bool = False,
) -> np.ndarray:
    points = np.asarray(loop, dtype=float)
    if np.linalg.norm(points[0] - points[-1]) > 1.0e-8:
        points = np.vstack((points, points[0]))
    if clamp_to_surface:
        margin = max(1.0e-6, float(np.ptp(points[:, 0])) * 0.005)
        target_x_m = float(np.clip(
            target_x_m,
            float(points[:, 0].min()) + margin,
            float(points[:, 0].max()) - margin,
        ))
    candidates: list[np.ndarray] = []
    for start, end in zip(points[:-1], points[1:]):
        low = min(start[0], end[0])
        high = max(start[0], end[0])
        if target_x_m < low - 1.0e-9 or target_x_m > high + 1.0e-9:
            continue
        delta_x = end[0] - start[0]
        if abs(delta_x) <= 1.0e-10:
            if abs(target_x_m - start[0]) <= 1.0e-9:
                candidates.extend((start, end))
            continue
        ratio = (target_x_m - start[0]) / delta_x
        candidates.append(start + (end - start) * ratio)
    if not candidates:
        raise RuntimeError(
            f"Torso section does not cross princess X={target_x_m:.6f} m."
        )
    selector = max if front_is_positive_depth else min
    return selector(candidates, key=lambda point: float(point[2]))


def measure_front_surface_ruler(
    mesh: trimesh.Trimesh,
    *,
    start_height_cm: float,
    end_height_cm: float,
    start_x_cm: float,
    end_x_cm: float,
    sample_count: int = 65,
    front_is_positive_depth: bool = True,
    clamp_to_surface: bool = False,
) -> float:
    """Measure a vertical front-torso ruler from exact mesh cross sections."""

    if sample_count < 3:
        raise ValueError("A front-surface ruler needs at least three samples.")
    values = (start_height_cm, end_height_cm, start_x_cm, end_x_cm)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Front-surface ruler inputs must be finite.")
    if end_height_cm <= start_height_cm:
        raise ValueError("Front-surface ruler must progress upward.")
    samples: list[np.ndarray] = []
    for index in range(sample_count):
        ratio = index / (sample_count - 1)
        height_cm = start_height_cm + (end_height_cm - start_height_cm) * ratio
        target_x_m = (start_x_cm + (end_x_cm - start_x_cm) * ratio) / 100.0
        section = mesh.section(
            plane_origin=np.asarray([0.0, height_cm / 100.0, 0.0]),
            plane_normal=np.asarray([0.0, 1.0, 0.0]),
        )
        if section is None:
            raise RuntimeError(f"No body surface crosses {height_cm:.3f} cm.")
        samples.append(
            _front_point_at_x(
                _central_torso_loop(section),
                target_x_m,
                front_is_positive_depth=front_is_positive_depth,
                clamp_to_surface=clamp_to_surface,
            )
        )
    return _path_length_cm(np.asarray(samples, dtype=float))


def measure_torso_arc_section(
    mesh: trimesh.Trimesh,
    height_cm: float,
    *,
    front_is_positive_depth: bool = True,
    side_seam_depth_cm: float | None = None,
) -> TorsoArcSection:
    if not math.isfinite(height_cm):
        raise ValueError("Torso section height must be finite.")
    section = mesh.section(
        plane_origin=np.asarray([0.0, height_cm / 100.0, 0.0]),
        plane_normal=np.asarray([0.0, 1.0, 0.0]),
    )
    if section is None:
        raise RuntimeError(f"No body surface crosses {height_cm:.3f} cm.")
    loop = _central_torso_loop(section)
    front, back, front_depth, back_depth = split_front_back_arc(
        loop,
        front_is_positive_depth=front_is_positive_depth,
        side_seam_depth_cm=side_seam_depth_cm,
    )
    circumference = front + back
    if circumference <= 0.0:
        raise RuntimeError("Measured torso circumference is not positive.")
    back_fraction = back / circumference
    if not 0.25 <= back_fraction <= 0.70:
        raise RuntimeError(
            f"Measured back fraction {back_fraction:.4f} is outside the torso domain."
        )
    return TorsoArcSection(
        height_cm=float(height_cm),
        circumference_cm=circumference,
        front_arc_cm=front,
        back_arc_cm=back,
        front_fraction=front / circumference,
        back_fraction=back_fraction,
        front_mean_depth_cm=front_depth,
        back_mean_depth_cm=back_depth,
        point_count=int(len(loop)),
    )


def lateral_extrema_depth_cm(mesh: trimesh.Trimesh, height_cm: float) -> float:
    """Return the mean depth of the left and right torso extrema."""
    section = mesh.section(
        plane_origin=np.asarray([0.0, height_cm / 100.0, 0.0]),
        plane_normal=np.asarray([0.0, 1.0, 0.0]),
    )
    if section is None:
        raise RuntimeError(f"No body surface crosses {height_cm:.3f} cm.")
    loop = _central_torso_loop(section)
    left = loop[int(np.argmin(loop[:, 0]))]
    right = loop[int(np.argmax(loop[:, 0]))]
    return float((left[2] + right[2]) * 50.0)
