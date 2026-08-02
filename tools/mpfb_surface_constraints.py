"""Surface-level anatomical constraints for a measurement-fitted MPFB avatar.

MPFB rulers follow fixed vertex chains. A chain can match its requested length
while a nearby horizontal body section is materially smaller. Garments respond
to the complete collision surface, not only the ruler chain, so Patterna also
enforces a measured torso envelope between the natural waist and underbust.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


Point3 = tuple[float, float, float]
Face = tuple[int, ...]


@dataclass(frozen=True)
class SectionMeasurement:
    height_m: float
    perimeter_cm: float
    center_x_m: float
    center_y_m: float


@dataclass(frozen=True)
class WaistSurfaceConstraintReport:
    name: str
    applied: bool
    accepted: bool
    target_waist_cm: float
    target_underbust_cm: float
    waist_landmark_height_cm: float
    underbust_landmark_height_cm: float
    minimum_before_cm: float
    minimum_before_height_cm: float
    minimum_after_cm: float
    minimum_after_height_cm: float
    maximum_deficit_before_cm: float
    maximum_deficit_after_cm: float
    maximum_radial_scale: float
    affected_vertex_count: int
    sample_count: int
    iterations: int


@dataclass(frozen=True)
class BustToHighChestSurfaceConstraintReport:
    name: str
    applied: bool
    accepted: bool
    bust_landmark_height_cm: float
    high_chest_landmark_height_cm: float
    bust_horizontal_circumference_cm: float
    target_high_chest_cm: float
    high_chest_before_cm: float
    high_chest_after_cm: float
    maximum_error_before_cm: float
    maximum_error_after_cm: float
    minimum_depth_scale: float
    maximum_depth_scale: float
    affected_vertex_count: int
    sample_count: int
    iterations: int


@dataclass(frozen=True)
class HorizontalTorsoCircumferenceConstraintReport:
    name: str
    applied: bool
    accepted: bool
    landmark_height_cm: float
    target_circumference_cm: float
    circumference_before_cm: float
    circumference_after_cm: float
    landmark_ruler_before_cm: float
    landmark_ruler_after_cm: float
    scale_mode: str
    depth_scale: float
    maximum_displacement_cm: float
    affected_vertex_count: int
    iterations: int


@dataclass(frozen=True)
class LandmarkTapeConstraintReport:
    name: str
    applied: bool
    accepted: bool
    target_length_cm: float
    length_before_cm: float
    length_after_cm: float
    radial_scale: float
    vertical_radius_cm: float
    maximum_displacement_cm: float
    affected_vertex_count: int
    iterations: int


def _point(value: Sequence[float]) -> Point3:
    return float(value[0]), float(value[1]), float(value[2])


def _triangle_segments_at_height(
    vertices: Sequence[Point3],
    triangle: tuple[int, int, int],
    height_m: float,
    epsilon: float = 1e-10,
) -> list[tuple[Point3, Point3]]:
    points = [vertices[index] for index in triangle]
    intersections: list[Point3] = []
    for edge_index in range(3):
        start = points[edge_index]
        end = points[(edge_index + 1) % 3]
        start_distance = start[2] - height_m
        end_distance = end[2] - height_m
        if abs(start_distance) <= epsilon and abs(end_distance) <= epsilon:
            continue
        if abs(start_distance) <= epsilon:
            candidate = start
        elif abs(end_distance) <= epsilon:
            candidate = end
        elif start_distance * end_distance < 0.0:
            ratio = start_distance / (start_distance - end_distance)
            candidate = (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
                height_m,
            )
        else:
            continue
        if not any(math.dist(candidate, existing) <= epsilon for existing in intersections):
            intersections.append(candidate)
    if len(intersections) != 2:
        return []
    return [(intersections[0], intersections[1])]


def _triangulate_faces(
    faces: Sequence[Sequence[int]],
) -> list[tuple[int, int, int]]:
    triangles: list[tuple[int, int, int]] = []
    for face_value in faces:
        face = tuple(int(index) for index in face_value)
        if len(face) < 3:
            continue
        triangles.extend(
            (face[0], face[index], face[index + 1])
            for index in range(1, len(face) - 1)
        )
    return triangles


def _measure_horizontal_section_points(
    vertices: Sequence[Point3],
    triangles: Sequence[tuple[int, int, int]],
    height_m: float,
    *,
    torso_half_width_m: float = 0.28,
) -> SectionMeasurement:
    unique_segments: dict[
        tuple[tuple[float, float, float], tuple[float, float, float]],
        tuple[Point3, Point3],
    ] = {}
    for triangle in triangles:
        first = vertices[triangle[0]]
        second = vertices[triangle[1]]
        third = vertices[triangle[2]]
        minimum_height = min(first[2], second[2], third[2])
        maximum_height = max(first[2], second[2], third[2])
        if height_m < minimum_height or height_m > maximum_height:
            continue
        for start, end in _triangle_segments_at_height(vertices, triangle, height_m):
            midpoint_x = (start[0] + end[0]) * 0.5
            if abs(midpoint_x) > torso_half_width_m:
                continue
            start_key = tuple(round(value, 9) for value in start)
            end_key = tuple(round(value, 9) for value in end)
            key = tuple(sorted((start_key, end_key)))
            unique_segments[key] = (start, end)
    endpoint_segments: dict[tuple[float, float, float], set[int]] = {}
    segments = list(unique_segments.values())
    segment_keys: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
    for segment_index, (start, end) in enumerate(segments):
        keys = (
            tuple(round(value, 9) for value in start),
            tuple(round(value, 9) for value in end),
        )
        segment_keys.append(keys)
        for key in keys:
            endpoint_segments.setdefault(key, set()).add(segment_index)
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
            for key in segment_keys[segment_index]:
                for neighbor in endpoint_segments[key]:
                    if neighbor in unvisited:
                        unvisited.remove(neighbor)
                        pending.append(neighbor)
        components.append(component)

    centered_components: list[tuple[float, set[int]]] = []
    for component in components:
        points = [point for index in component for point in segments[index]]
        minimum_x = min(point[0] for point in points)
        maximum_x = max(point[0] for point in points)
        if minimum_x >= 0.0 or maximum_x <= 0.0:
            continue
        perimeter = sum(math.dist(*segments[index]) for index in component)
        centered_components.append((perimeter, component))
    if not centered_components:
        raise ValueError(f"No centered torso section exists at {height_m:.6f} m.")
    perimeter_m, torso_component = max(centered_components, key=lambda item: item[0])
    segment_endpoints = [
        point
        for segment_index in torso_component
        for point in segments[segment_index]
    ]
    if not segment_endpoints or perimeter_m <= 0.0:
        raise ValueError(f"No centered torso section exists at {height_m:.6f} m.")
    x_values = [point[0] for point in segment_endpoints]
    y_values = [point[1] for point in segment_endpoints]
    return SectionMeasurement(
        height_m=height_m,
        perimeter_cm=perimeter_m * 100.0,
        center_x_m=(min(x_values) + max(x_values)) * 0.5,
        center_y_m=(min(y_values) + max(y_values)) * 0.5,
    )


def measure_horizontal_section(
    coordinates: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    height_m: float,
    *,
    torso_half_width_m: float = 0.28,
) -> SectionMeasurement:
    """Measure the centered torso contour cut by one horizontal plane.

    Faces may be triangles or polygons. Polygons are fan-triangulated using the
    same stable vertex ordering used by the exported MPFB body.
    """
    return _measure_horizontal_section_points(
        [_point(value) for value in coordinates],
        _triangulate_faces(faces),
        height_m,
        torso_half_width_m=torso_half_width_m,
    )


def _smoothstep(value: float) -> float:
    clamped = min(max(value, 0.0), 1.0)
    return clamped * clamped * (3.0 - 2.0 * clamped)


def _polyline_length_cm(
    points: Sequence[Sequence[float]],
    indices: Sequence[int],
) -> float:
    return 100.0 * sum(
        math.dist(points[first], points[second])
        for first, second in zip(indices, indices[1:])
    )


def enforce_landmark_tape_length(
    coordinates: Sequence[Sequence[float]],
    landmark_vertex_indices: Sequence[int],
    *,
    target_length_cm: float,
    name: str,
    vertical_radius_m: float = 0.040,
    torso_half_width_m: float = 0.24,
    tolerance_cm: float = 0.15,
    maximum_iterations: int = 30,
) -> tuple[list[Point3], LandmarkTapeConstraintReport]:
    """Fit a nonplanar anatomical tape without flattening a torso section.

    The underbust ruler follows the inframammary root and rib cage, so its
    vertices are not required to share one height. A broad radial field around
    that landmark path corrects the small residual left by MPFB while retaining
    the local breast-root curvature. This is intentionally different from a
    horizontal plane-section constraint.
    """

    points = [_point(value) for value in coordinates]
    indices = tuple(int(index) for index in landmark_vertex_indices)
    if not points or len(indices) < 3:
        raise ValueError("Landmark tape constraint requires body coordinates and a path.")
    if any(index < 0 or index >= len(points) for index in indices):
        raise IndexError("Landmark tape path is incompatible with the body topology.")
    if target_length_cm <= 0.0 or vertical_radius_m <= 0.0:
        raise ValueError("Landmark tape target and vertical radius must be positive.")
    if tolerance_cm <= 0.0 or maximum_iterations < 1:
        raise ValueError("Landmark tape tolerance and iterations must be positive.")

    landmark = [points[index] for index in indices]
    center_x = 0.5 * (min(point[0] for point in landmark) + max(point[0] for point in landmark))
    center_y = 0.5 * (min(point[1] for point in landmark) + max(point[1] for point in landmark))
    center_z = sum(point[2] for point in landmark) / len(landmark)
    before_cm = _polyline_length_cm(points, indices)

    def scaled(scale: float) -> list[Point3]:
        result: list[Point3] = []
        for x, y, z in points:
            if abs(x - center_x) > torso_half_width_m:
                result.append((x, y, z))
                continue
            distance = abs(z - center_z)
            if distance >= vertical_radius_m:
                result.append((x, y, z))
                continue
            weight = _smoothstep(1.0 - distance / vertical_radius_m)
            local_scale = 1.0 + (scale - 1.0) * weight
            result.append((
                center_x + (x - center_x) * local_scale,
                center_y + (y - center_y) * local_scale,
                z,
            ))
        return result

    if abs(before_cm - target_length_cm) <= tolerance_cm:
        after_points = points
        radial_scale = 1.0
        iteration_count = 0
    else:
        low, high = (0.75, 1.0) if before_cm > target_length_cm else (1.0, 1.25)
        low_error = _polyline_length_cm(scaled(low), indices) - target_length_cm
        high_error = _polyline_length_cm(scaled(high), indices) - target_length_cm
        if low_error * high_error > 0.0:
            raise ValueError(
                f"Landmark tape {name} cannot reach {target_length_cm:.3f} cm "
                "within its bounded radial field."
            )
        iteration_count = 0
        for iteration in range(maximum_iterations):
            middle = 0.5 * (low + high)
            middle_error = _polyline_length_cm(scaled(middle), indices) - target_length_cm
            if low_error * middle_error <= 0.0:
                high = middle
            else:
                low = middle
                low_error = middle_error
            iteration_count = iteration + 1
        radial_scale = 0.5 * (low + high)
        after_points = scaled(radial_scale)

    after_cm = _polyline_length_cm(after_points, indices)
    displacements_cm = [
        math.dist(start, end) * 100.0
        for start, end in zip(points, after_points)
    ]
    report = LandmarkTapeConstraintReport(
        name=name,
        applied=any(displacement > 1.0e-8 for displacement in displacements_cm),
        accepted=abs(after_cm - target_length_cm) <= tolerance_cm,
        target_length_cm=target_length_cm,
        length_before_cm=before_cm,
        length_after_cm=after_cm,
        radial_scale=radial_scale,
        vertical_radius_cm=vertical_radius_m * 100.0,
        maximum_displacement_cm=max(displacements_cm, default=0.0),
        affected_vertex_count=sum(
            displacement > 1.0e-8 for displacement in displacements_cm
        ),
        iterations=iteration_count,
    )
    return after_points, report


def _target_envelope_cm(
    height_m: float,
    waist_height_m: float,
    underbust_height_m: float,
    target_waist_cm: float,
    target_underbust_cm: float,
) -> float:
    ratio = (height_m - waist_height_m) / (underbust_height_m - waist_height_m)
    blend = _smoothstep(ratio)
    return target_waist_cm + (target_underbust_cm - target_waist_cm) * blend


def _interpolate(values: Sequence[tuple[float, float]], height_m: float) -> float:
    if height_m <= values[0][0]:
        return values[0][1]
    if height_m >= values[-1][0]:
        return values[-1][1]
    for index in range(1, len(values)):
        upper_height, upper_value = values[index]
        lower_height, lower_value = values[index - 1]
        if height_m <= upper_height:
            ratio = (height_m - lower_height) / (upper_height - lower_height)
            return lower_value + (upper_value - lower_value) * ratio
    return values[-1][1]


def _sample_heights(
    waist_height_m: float,
    underbust_height_m: float,
    sample_count: int,
) -> list[float]:
    span = underbust_height_m - waist_height_m
    endpoint_inset = span * 1e-5
    return [
        waist_height_m
        + endpoint_inset
        + (span - endpoint_inset * 2.0) * index / (sample_count - 1)
        for index in range(sample_count)
    ]


def enforce_waist_to_underbust_surface(
    coordinates: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    waist_vertex_indices: Sequence[int],
    underbust_vertex_indices: Sequence[int],
    *,
    target_waist_cm: float,
    target_underbust_cm: float,
    torso_half_width_m: float = 0.28,
    sample_count: int = 21,
    tolerance_cm: float = 0.20,
    maximum_iterations: int = 5,
    landmark_hold_m: float = 0.015,
    taper_m: float = 0.010,
) -> tuple[list[Point3], WaistSurfaceConstraintReport]:
    """Expand false torso pinches while preserving stable MPFB topology."""
    points = [_point(value) for value in coordinates]
    if not points:
        raise ValueError("Waist surface constraint requires body coordinates.")
    if sample_count < 3 or maximum_iterations < 1:
        raise ValueError("Waist surface constraint sampling limits are invalid.")
    if landmark_hold_m < 0.0 or taper_m < 0.0:
        raise ValueError("Waist surface constraint landmark protection is invalid.")
    if target_waist_cm <= 0.0 or target_underbust_cm <= 0.0:
        raise ValueError("Waist surface constraint targets must be positive.")
    maximum_index = len(points) - 1
    landmark_indices = tuple(waist_vertex_indices) + tuple(underbust_vertex_indices)
    if any(index < 0 or index > maximum_index for index in landmark_indices):
        raise IndexError("Waist surface constraint landmark topology is incompatible.")

    waist_heights = [points[index][2] for index in waist_vertex_indices]
    underbust_heights = [points[index][2] for index in underbust_vertex_indices]
    waist_height_m = sum(waist_heights) / len(waist_heights)
    underbust_height_m = sum(underbust_heights) / len(underbust_heights)
    if underbust_height_m <= waist_height_m + 0.02:
        raise ValueError("Underbust landmark must be above the natural waist landmark.")

    lower_boundary = waist_height_m + landmark_hold_m
    upper_boundary = underbust_height_m - landmark_hold_m
    measurement_start = lower_boundary + taper_m
    measurement_end = upper_boundary - taper_m
    if measurement_end <= measurement_start + 0.02:
        raise ValueError("Waist surface constraint has no interior torso band.")
    heights = _sample_heights(measurement_start, measurement_end, sample_count)
    triangles = _triangulate_faces(faces)

    def measurements(values: Sequence[Sequence[float]]) -> list[SectionMeasurement]:
        measurement_points = [_point(value) for value in values]
        return [
            _measure_horizontal_section_points(
                measurement_points,
                triangles,
                height,
                torso_half_width_m=torso_half_width_m,
            )
            for height in heights
        ]

    before = measurements(points)
    original_points = list(points)
    eligible = [
        abs(point[0]) <= torso_half_width_m
        and lower_boundary <= point[2] <= upper_boundary
        for point in original_points
    ]
    maximum_scale = 1.0
    iteration_count = 0
    for iteration in range(maximum_iterations):
        current = measurements(points)
        deficits = [
            _target_envelope_cm(
                item.height_m,
                waist_height_m,
                underbust_height_m,
                target_waist_cm,
                target_underbust_cm,
            )
            - item.perimeter_cm
            for item in current
        ]
        if max(deficits) <= tolerance_cm:
            break
        scale_profile: list[tuple[float, float]] = []
        center_x_profile: list[tuple[float, float]] = []
        center_y_profile: list[tuple[float, float]] = []
        for item, deficit in zip(current, deficits):
            target = item.perimeter_cm + max(deficit, 0.0)
            scale = min(max(target / item.perimeter_cm, 1.0), 1.20)
            maximum_scale = max(maximum_scale, scale)
            scale_profile.append((item.height_m, scale))
            center_x_profile.append((item.height_m, item.center_x_m))
            center_y_profile.append((item.height_m, item.center_y_m))
        scale_profile = [(lower_boundary, 1.0), *scale_profile, (upper_boundary, 1.0)]
        center_x_profile = [
            (lower_boundary, center_x_profile[0][1]),
            *center_x_profile,
            (upper_boundary, center_x_profile[-1][1]),
        ]
        center_y_profile = [
            (lower_boundary, center_y_profile[0][1]),
            *center_y_profile,
            (upper_boundary, center_y_profile[-1][1]),
        ]
        updated: list[Point3] = []
        for is_eligible, point in zip(eligible, points):
            if not is_eligible:
                updated.append(point)
                continue
            scale = _interpolate(scale_profile, point[2])
            center_x = _interpolate(center_x_profile, point[2])
            center_y = _interpolate(center_y_profile, point[2])
            updated.append((
                center_x + (point[0] - center_x) * scale,
                center_y + (point[1] - center_y) * scale,
                point[2],
            ))
        points = updated
        iteration_count = iteration + 1

    after = measurements(points)
    before_deficits = [
        _target_envelope_cm(
            item.height_m,
            waist_height_m,
            underbust_height_m,
            target_waist_cm,
            target_underbust_cm,
        )
        - item.perimeter_cm
        for item in before
    ]
    after_deficits = [
        _target_envelope_cm(
            item.height_m,
            waist_height_m,
            underbust_height_m,
            target_waist_cm,
            target_underbust_cm,
        )
        - item.perimeter_cm
        for item in after
    ]
    minimum_before = min(before, key=lambda item: item.perimeter_cm)
    minimum_after = min(after, key=lambda item: item.perimeter_cm)
    displacements = [math.dist(start, end) for start, end in zip(original_points, points)]
    maximum_after_deficit = max(after_deficits)
    report = WaistSurfaceConstraintReport(
        name="waist-to-underbust-surface-envelope",
        applied=any(displacement > 1e-10 for displacement in displacements),
        accepted=maximum_after_deficit <= tolerance_cm,
        target_waist_cm=target_waist_cm,
        target_underbust_cm=target_underbust_cm,
        waist_landmark_height_cm=waist_height_m * 100.0,
        underbust_landmark_height_cm=underbust_height_m * 100.0,
        minimum_before_cm=minimum_before.perimeter_cm,
        minimum_before_height_cm=minimum_before.height_m * 100.0,
        minimum_after_cm=minimum_after.perimeter_cm,
        minimum_after_height_cm=minimum_after.height_m * 100.0,
        maximum_deficit_before_cm=max(before_deficits),
        maximum_deficit_after_cm=maximum_after_deficit,
        maximum_radial_scale=maximum_scale,
        affected_vertex_count=sum(displacement > 1e-10 for displacement in displacements),
        sample_count=sample_count,
        iterations=iteration_count,
    )
    return points, report


def enforce_horizontal_torso_circumference(
    coordinates: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    landmark_vertex_indices: Sequence[int],
    *,
    target_circumference_cm: float,
    name: str,
    torso_half_width_m: float = 0.22,
    hold_half_height_m: float = 0.004,
    taper_height_m: float = 0.020,
    tolerance_cm: float = 0.20,
    maximum_iterations: int = 20,
) -> tuple[list[Point3], HorizontalTorsoCircumferenceConstraintReport]:
    """Fit one editable tape circumference to the actual collision surface."""

    points = [_point(value) for value in coordinates]
    if not points or not landmark_vertex_indices:
        raise ValueError("A torso circumference constraint needs body landmarks.")
    if target_circumference_cm <= 0.0 or not math.isfinite(target_circumference_cm):
        raise ValueError("Torso circumference target must be positive and finite.")
    if hold_half_height_m < 0.0 or taper_height_m <= 0.0:
        raise ValueError("Torso circumference band dimensions are invalid.")
    maximum_index = len(points) - 1
    if any(index < 0 or index > maximum_index for index in landmark_vertex_indices):
        raise IndexError("Torso circumference landmark topology is incompatible.")

    height_m = sum(points[index][2] for index in landmark_vertex_indices) / len(
        landmark_vertex_indices
    )
    triangles = _triangulate_faces(faces)
    before = _measure_horizontal_section_points(
        points,
        triangles,
        height_m,
        torso_half_width_m=torso_half_width_m,
    )
    original_points = list(points)
    scale_width = False
    band_limit = hold_half_height_m + taper_height_m
    landmark_half_width_m = max(
        abs(points[index][0] - before.center_x_m)
        for index in landmark_vertex_indices
    )
    deformation_half_width_m = max(
        torso_half_width_m,
        landmark_half_width_m + 0.12,
    )
    eligible = [
        abs(point[0] - before.center_x_m) <= deformation_half_width_m
        and abs(point[2] - height_m) <= band_limit
        for point in points
    ]

    def scaled_points(depth_scale: float) -> list[Point3]:
        updated: list[Point3] = []
        for is_eligible, point in zip(eligible, original_points):
            if not is_eligible:
                updated.append(point)
                continue
            distance = abs(point[2] - height_m)
            if distance <= hold_half_height_m:
                influence = 1.0
            else:
                ratio = (distance - hold_half_height_m) / taper_height_m
                influence = 1.0 - _smoothstep(ratio)
            scale = 1.0 + (depth_scale - 1.0) * influence
            updated.append((
                (
                    before.center_x_m + (point[0] - before.center_x_m) * scale
                    if scale_width
                    else point[0]
                ),
                before.center_y_m + (point[1] - before.center_y_m) * scale,
                point[2],
            ))
        return updated

    if abs(before.perimeter_cm - target_circumference_cm) <= tolerance_cm:
        depth_scale = 1.0
        iteration_count = 0
    else:
        def perimeter(scale: float) -> float:
            return _measure_horizontal_section_points(
                scaled_points(scale),
                triangles,
                height_m,
                torso_half_width_m=torso_half_width_m,
            ).perimeter_cm

        search_low = 0.02 if target_circumference_cm < before.perimeter_cm else 1.0
        search_high = 1.0 if target_circumference_cm < before.perimeter_cm else 2.0

        def nearest_bracket() -> tuple[
            tuple[float, float, float, float] | None,
            list[tuple[float, float]],
        ]:
            if target_circumference_cm < before.perimeter_cm:
                candidates = [
                    0.90,
                    0.80,
                    0.70,
                    0.60,
                    0.50,
                    0.40,
                    0.30,
                    0.20,
                    0.10,
                    0.05,
                    search_low,
                ]
            else:
                candidates = [
                    1.10,
                    1.20,
                    1.30,
                    1.40,
                    1.50,
                    1.60,
                    1.70,
                    1.80,
                    1.90,
                    search_high,
                ]
            samples = [(1.0, before.perimeter_cm - target_circumference_cm)]
            for scale in candidates:
                error = perimeter(scale) - target_circumference_cm
                previous_scale, previous_error = samples[-1]
                samples.append((scale, error))
                if previous_error == 0.0 or previous_error * error <= 0.0:
                    if scale < previous_scale:
                        return (
                            scale,
                            previous_scale,
                            error,
                            previous_error,
                        ), samples
                    return (
                        previous_scale,
                        scale,
                        previous_error,
                        error,
                    ), samples
            return None, samples

        bracket, endpoints = nearest_bracket()
        if bracket is None and target_circumference_cm < before.perimeter_cm:
            # Some intermediate fitter states are wider than the requested
            # tape even with zero anatomical depth. In that case the ribcage
            # itself must narrow; record the radial fallback explicitly.
            scale_width = True
            bracket, endpoints = nearest_bracket()
        if bracket is None:
            # A coupled fitter can visit an infeasible intermediate body. Keep
            # the closest measurable candidate so the outer fit can recover,
            # then let the final accepted flag fail closed if it never does.
            depth_scale, _ = min(
                endpoints,
                key=lambda item: abs(item[1]),
            )
            iteration_count = 0
        else:
            # Search outward from the undeformed body and retain the first
            # crossing. This avoids both full scans and collapsed-loop aliases.
            low, high, low_error, _ = bracket
            iteration_count = 0
            for iteration in range(maximum_iterations):
                middle = 0.5 * (low + high)
                middle_error = perimeter(middle) - target_circumference_cm
                if low_error * middle_error <= 0.0:
                    high = middle
                else:
                    low = middle
                    low_error = middle_error
                iteration_count = iteration + 1
            depth_scale = 0.5 * (low + high)

    points = scaled_points(depth_scale)
    after = _measure_horizontal_section_points(
        points,
        triangles,
        height_m,
        torso_half_width_m=torso_half_width_m,
    )
    displacements_cm = [
        math.dist(start, end) * 100.0
        for start, end in zip(original_points, points)
    ]
    report = HorizontalTorsoCircumferenceConstraintReport(
        name=name,
        applied=any(displacement > 1.0e-8 for displacement in displacements_cm),
        accepted=(
            abs(after.perimeter_cm - target_circumference_cm) <= tolerance_cm
        ),
        landmark_height_cm=height_m * 100.0,
        target_circumference_cm=target_circumference_cm,
        circumference_before_cm=before.perimeter_cm,
        circumference_after_cm=after.perimeter_cm,
        landmark_ruler_before_cm=_polyline_length_cm(
            original_points,
            landmark_vertex_indices,
        ),
        landmark_ruler_after_cm=_polyline_length_cm(
            points,
            landmark_vertex_indices,
        ),
        scale_mode="radial" if scale_width else "depth-only",
        depth_scale=depth_scale,
        maximum_displacement_cm=max(displacements_cm, default=0.0),
        affected_vertex_count=sum(
            displacement > 1.0e-8 for displacement in displacements_cm
        ),
        iterations=iteration_count,
    )
    return points, report


def enforce_bust_to_high_chest_surface(
    coordinates: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    bust_vertex_indices: Sequence[int],
    high_chest_vertex_indices: Sequence[int],
    *,
    target_high_chest_cm: float,
    torso_half_width_m: float = 0.22,
    sample_count: int = 17,
    tolerance_cm: float = 0.25,
    maximum_iterations: int = 20,
    upper_taper_m: float = 0.025,
) -> tuple[list[Point3], BustToHighChestSurfaceConstraintReport]:
    """Reconcile the upper torso surface with an editable high-chest girth.

    The across-front ruler fixes the lateral high-chest width. Scaling only
    anatomical depth preserves that ruler while correcting the complete torso
    perimeter. The depth correction starts above every full-bust ruler vertex
    and reaches a constant scale before the high-chest plane, preserving both
    the hard bust ruler and local mesh regularity.
    """

    points = [_point(value) for value in coordinates]
    if not points:
        raise ValueError("High-chest surface constraint requires body coordinates.")
    if sample_count < 3 or maximum_iterations < 1:
        raise ValueError("High-chest surface constraint sampling limits are invalid.")
    if target_high_chest_cm <= 0.0 or not math.isfinite(target_high_chest_cm):
        raise ValueError("High-chest circumference must be positive and finite.")
    maximum_index = len(points) - 1
    landmark_indices = tuple(bust_vertex_indices) + tuple(high_chest_vertex_indices)
    if any(index < 0 or index > maximum_index for index in landmark_indices):
        raise IndexError("High-chest surface landmark topology is incompatible.")

    bust_height_m = sum(points[index][2] for index in bust_vertex_indices) / len(
        bust_vertex_indices
    )
    high_chest_height_m = sum(
        points[index][2] for index in high_chest_vertex_indices
    ) / len(high_chest_vertex_indices)
    if high_chest_height_m <= bust_height_m + 0.03:
        raise ValueError("High-chest landmark must be above the full-bust landmark.")
    triangles = _triangulate_faces(faces)
    heights = _sample_heights(bust_height_m, high_chest_height_m, sample_count)

    def measurements(values: Sequence[Sequence[float]]) -> list[SectionMeasurement]:
        measurement_points = [_point(value) for value in values]
        return [
            _measure_horizontal_section_points(
                measurement_points,
                triangles,
                height,
                torso_half_width_m=torso_half_width_m,
            )
            for height in heights
        ]

    before = measurements(points)
    bust_section = _measure_horizontal_section_points(
        points,
        triangles,
        bust_height_m,
        torso_half_width_m=torso_half_width_m,
    )

    def target_at(height_m: float) -> float:
        ratio = (height_m - bust_height_m) / (
            high_chest_height_m - bust_height_m
        )
        return bust_section.perimeter_cm + (
            target_high_chest_cm - bust_section.perimeter_cm
        ) * _smoothstep(ratio)

    original_points = list(points)
    upper_hold_m = 0.015
    bust_protection_height_m = max(
        points[index][2] for index in bust_vertex_indices
    )
    lower_hold_height_m = high_chest_height_m - upper_hold_m
    if lower_hold_height_m <= bust_protection_height_m + 0.02:
        raise ValueError(
            "High-chest correction has insufficient space above the bust ruler."
        )
    eligible = [
        abs(point[0]) <= torso_half_width_m
        and bust_protection_height_m
        <= point[2]
        <= high_chest_height_m + upper_hold_m + upper_taper_m
        for point in points
    ]
    high_chest_center_y_m = before[-1].center_y_m

    def scaled_points(high_chest_scale: float) -> list[Point3]:
        updated: list[Point3] = []
        for is_eligible, point in zip(eligible, original_points):
            if not is_eligible:
                updated.append(point)
                continue
            if point[2] < lower_hold_height_m:
                ratio = (
                    point[2] - bust_protection_height_m
                ) / (lower_hold_height_m - bust_protection_height_m)
                influence = _smoothstep(ratio)
            elif point[2] <= high_chest_height_m + upper_hold_m:
                influence = 1.0
            elif upper_taper_m > 0.0:
                ratio = (
                    point[2] - high_chest_height_m - upper_hold_m
                ) / upper_taper_m
                influence = 1.0 - _smoothstep(ratio)
            else:
                influence = 0.0
            scale = 1.0 + (high_chest_scale - 1.0) * influence
            center_ratio = (point[2] - bust_height_m) / (
                high_chest_height_m - bust_height_m
            )
            center_y = bust_section.center_y_m + (
                high_chest_center_y_m - bust_section.center_y_m
            ) * _smoothstep(center_ratio)
            updated.append(
                (
                    point[0],
                    center_y + (point[1] - center_y) * scale,
                    point[2],
                )
            )
        return updated

    before_high_chest = _measure_horizontal_section_points(
        points,
        triangles,
        high_chest_height_m,
        torso_half_width_m=torso_half_width_m,
    ).perimeter_cm
    if abs(before_high_chest - target_high_chest_cm) <= tolerance_cm:
        high_chest_scale = 1.0
        iteration_count = 0
    else:
        low = 0.25 if target_high_chest_cm < before_high_chest else 1.0
        high = 1.0 if target_high_chest_cm < before_high_chest else 2.0
        low_measurement = _measure_horizontal_section_points(
            scaled_points(low),
            triangles,
            high_chest_height_m,
            torso_half_width_m=torso_half_width_m,
        ).perimeter_cm
        high_measurement = _measure_horizontal_section_points(
            scaled_points(high),
            triangles,
            high_chest_height_m,
            torso_half_width_m=torso_half_width_m,
        ).perimeter_cm
        if not low_measurement <= target_high_chest_cm <= high_measurement:
            raise ValueError(
                "High-chest circumference cannot be reached by a smooth depth "
                f"correction: target {target_high_chest_cm:.3f} cm, range "
                f"{low_measurement:.3f} through {high_measurement:.3f} cm."
            )
        iteration_count = 0
        for iteration in range(maximum_iterations):
            middle = 0.5 * (low + high)
            middle_measurement = _measure_horizontal_section_points(
                scaled_points(middle),
                triangles,
                high_chest_height_m,
                torso_half_width_m=torso_half_width_m,
            ).perimeter_cm
            if middle_measurement < target_high_chest_cm:
                low = middle
            else:
                high = middle
            iteration_count = iteration + 1
        high_chest_scale = 0.5 * (low + high)
    points = scaled_points(high_chest_scale)
    minimum_scale = min(1.0, high_chest_scale)
    maximum_scale = max(1.0, high_chest_scale)

    after = measurements(points)
    before_errors = [
        item.perimeter_cm - target_at(item.height_m) for item in before
    ]
    after_errors = [
        item.perimeter_cm - target_at(item.height_m) for item in after
    ]
    high_chest_before = min(
        before,
        key=lambda item: abs(item.height_m - high_chest_height_m),
    )
    high_chest_after = min(
        after,
        key=lambda item: abs(item.height_m - high_chest_height_m),
    )
    displacements = [math.dist(start, end) for start, end in zip(original_points, points)]
    maximum_after_error = max(abs(error) for error in after_errors)
    high_chest_error = abs(
        high_chest_after.perimeter_cm - target_high_chest_cm
    )
    report = BustToHighChestSurfaceConstraintReport(
        name="bust-to-high-chest-depth-envelope",
        applied=any(displacement > 1.0e-10 for displacement in displacements),
        accepted=high_chest_error <= tolerance_cm,
        bust_landmark_height_cm=bust_height_m * 100.0,
        high_chest_landmark_height_cm=high_chest_height_m * 100.0,
        bust_horizontal_circumference_cm=bust_section.perimeter_cm,
        target_high_chest_cm=target_high_chest_cm,
        high_chest_before_cm=high_chest_before.perimeter_cm,
        high_chest_after_cm=high_chest_after.perimeter_cm,
        maximum_error_before_cm=max(abs(error) for error in before_errors),
        maximum_error_after_cm=maximum_after_error,
        minimum_depth_scale=minimum_scale,
        maximum_depth_scale=maximum_scale,
        affected_vertex_count=sum(displacement > 1.0e-10 for displacement in displacements),
        sample_count=sample_count,
        iterations=iteration_count,
    )
    return points, report
