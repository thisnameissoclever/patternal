"""Construct a sewn garment shell around a measured body before cloth solving."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class ShellAssemblyDiagnostics:
    panel_count: int
    vertex_count: int
    seam_link_count: int
    maximum_seam_separation_cm: float
    clearance_cm: float
    body_slice_count: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "panel_count": self.panel_count,
            "vertex_count": self.vertex_count,
            "seam_link_count": self.seam_link_count,
            "maximum_seam_separation_cm": self.maximum_seam_separation_cm,
            "clearance_cm": self.clearance_cm,
            "body_slice_count": self.body_slice_count,
        }


@dataclass(frozen=True)
class IndependentPanelStagingDiagnostics:
    panel_count: int
    vertex_count: int
    seam_link_count: int
    maximum_seam_separation_cm: float
    mean_seam_separation_cm: float
    ninety_fifth_percentile_seam_separation_cm: float
    maximum_material_edge_strain_ratio: float
    ninety_fifth_percentile_material_edge_strain_ratio: float
    ninety_ninth_point_ninth_percentile_material_edge_strain_ratio: float
    clearance_cm: float
    body_slice_count: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "panel_count": self.panel_count,
            "vertex_count": self.vertex_count,
            "seam_link_count": self.seam_link_count,
            "maximum_seam_separation_cm": self.maximum_seam_separation_cm,
            "mean_seam_separation_cm": self.mean_seam_separation_cm,
            "ninety_fifth_percentile_seam_separation_cm": (
                self.ninety_fifth_percentile_seam_separation_cm
            ),
            "maximum_material_edge_strain_ratio": (
                self.maximum_material_edge_strain_ratio
            ),
            "ninety_fifth_percentile_material_edge_strain_ratio": (
                self.ninety_fifth_percentile_material_edge_strain_ratio
            ),
            "ninety_ninth_point_ninth_percentile_material_edge_strain_ratio": (
                self.ninety_ninth_point_ninth_percentile_material_edge_strain_ratio
            ),
            "clearance_cm": self.clearance_cm,
            "body_slice_count": self.body_slice_count,
        }


@dataclass(frozen=True)
class SeamPreassemblyDiagnostics:
    panel_count: int
    vertex_count: int
    seam_link_count: int
    arap_iteration_count: int
    seam_constraint_weight: float
    initial_maximum_seam_separation_cm: float
    maximum_seam_separation_cm: float
    mean_seam_separation_cm: float
    ninety_fifth_percentile_seam_separation_cm: float
    maximum_material_edge_strain_ratio: float
    ninety_fifth_percentile_material_edge_strain_ratio: float
    ninety_ninth_point_ninth_percentile_material_edge_strain_ratio: float
    minimum_height_cm: float
    maximum_height_cm: float
    center_x_cm: float
    clearance_cm: float
    body_slice_count: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }


def load_obj_vertices_centimeters(path: Path) -> np.ndarray:
    """Load OBJ positions and normalize meter-authored bodies to centimeters."""
    vertices: list[list[float]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            fields = line.split()
            vertices.append([float(fields[1]), float(fields[2]), float(fields[3])])
    result = np.asarray(vertices, dtype=float)
    if result.ndim != 2 or result.shape[1] != 3 or not np.isfinite(result).all():
        raise RuntimeError(f"Body OBJ contains no finite vertex positions: {path}")
    if float(np.ptp(result[:, 1])) < 10.0:
        result *= 100.0
    return result


def _global_vertex_index(mesh, panel_name: str, local_index: int) -> int:
    mapped = mesh.verts_loc_glob.get((panel_name, local_index))
    if mapped is not None:
        return int(mapped)
    panel = mesh.panels[panel_name]
    if local_index < panel.n_stitches:
        raise RuntimeError(
            f"No global vertex maps sewn point {(panel_name, local_index)!r}."
        )
    return int(local_index + panel.glob_offset - panel.n_stitches)


def _edge_segments(panel) -> Iterable[tuple[np.ndarray, np.ndarray]]:
    points = np.asarray(panel.panel_vertices, dtype=float)
    for edge in panel.edges:
        indices = list(edge.vertex_range)
        for first, second in zip(indices, indices[1:]):
            yield points[int(first)], points[int(second)]


def panel_horizontal_bounds(panel, y: float) -> tuple[float, float]:
    """Intersect a panel boundary with a horizontal material-space line."""
    points = np.asarray(panel.panel_vertices, dtype=float)
    boundary_indices = sorted(
        {int(index) for edge in panel.edges for index in edge.vertex_range}
    )
    boundary_y = points[boundary_indices, 1]
    query_y = float(np.clip(y, np.min(boundary_y), np.max(boundary_y)))
    intersections: list[float] = []
    epsilon = 1.0e-8
    for first, second in _edge_segments(panel):
        low = min(float(first[1]), float(second[1]))
        high = max(float(first[1]), float(second[1]))
        if query_y < low - epsilon or query_y > high + epsilon:
            continue
        delta_y = float(second[1] - first[1])
        if abs(delta_y) <= epsilon:
            if abs(query_y - float(first[1])) <= epsilon:
                intersections.extend((float(first[0]), float(second[0])))
            continue
        progress = (query_y - float(first[1])) / delta_y
        if -epsilon <= progress <= 1.0 + epsilon:
            intersections.append(
                float(first[0] + progress * (second[0] - first[0]))
            )
    if len(intersections) < 2:
        nearest = np.argsort(np.abs(boundary_y - query_y))[:4]
        intersections = points[np.asarray(boundary_indices)[nearest], 0].astype(float).tolist()
    return min(intersections), max(intersections)


def _canonical_horizontal_bounds(panel, y: float, side_sign: float) -> tuple[float, float]:
    low, high = panel_horizontal_bounds(panel, y)
    values = (low * side_sign, high * side_sign)
    return min(values), max(values)


def _panel_role(panel_name: str) -> tuple[str, float]:
    if panel_name.startswith("right_"):
        side_sign = 1.0
        role = panel_name.removeprefix("right_")
    elif panel_name.startswith("left_"):
        side_sign = -1.0
        role = panel_name.removeprefix("left_")
    else:
        raise RuntimeError(
            f"Body shell assembly requires left/right panel ownership: {panel_name}"
        )
    if role not in {
        "front_center",
        "front_side",
        "back",
        "back_side",
        "back_center",
    }:
        raise RuntimeError(f"Unsupported cup-aware shell panel role: {panel_name}")
    return role, side_sign


class _TorsoSurface:
    def __init__(self, body_vertices: np.ndarray, clearance_cm: float) -> None:
        vertices = np.asarray(body_vertices, dtype=float)
        if vertices.ndim != 2 or vertices.shape[1] != 3:
            raise ValueError("Body vertices must be an N by 3 array.")
        if len(vertices) < 24 or not np.isfinite(vertices).all():
            raise ValueError("Body shell assembly needs at least 24 finite torso vertices.")
        if not np.isfinite(clearance_cm) or clearance_cm <= 0.0:
            raise ValueError("Shell clearance must be positive and finite.")
        self.vertices = vertices
        self.clearance_cm = float(clearance_cm)
        self._theta_grid = np.linspace(0.0, math.pi, 73)
        self._grid_y = np.arange(
            math.floor(float(np.min(vertices[:, 1])) * 2.0) / 2.0,
            math.ceil(float(np.max(vertices[:, 1])) * 2.0) / 2.0 + 0.25,
            0.5,
        )
        raw_profiles = np.asarray(
            [self._measure_profile(y) for y in self._grid_y],
            dtype=float,
        )
        self._profiles = self._smooth_profiles(raw_profiles)
        self.slice_count = len(self._grid_y)
        self._cache: dict[tuple[float, float, int], np.ndarray] = {}

    def _slice(self, y: float) -> np.ndarray:
        distance = np.abs(self.vertices[:, 1] - y)
        selection = self.vertices[distance <= 2.5]
        if len(selection) < 24:
            selection = self.vertices[np.argsort(distance)[:64]]
        return selection

    def _measure_profile(self, y: float) -> np.ndarray:
        from scipy.spatial import ConvexHull

        section = self._slice(y)
        cross_section = section[:, [0, 2]]
        z_min = float(np.min(cross_section[:, 1]))
        z_max = float(np.max(cross_section[:, 1]))
        center_z = (z_min + z_max) * 0.5
        origin = np.asarray([0.0, center_z], dtype=float)
        hull = ConvexHull(cross_section)
        polygon = cross_section[hull.vertices]

        def ray_radius(direction: np.ndarray) -> float:
            hits: list[float] = []
            for index, first in enumerate(polygon):
                second = polygon[(index + 1) % len(polygon)]
                edge = second - first
                matrix = np.column_stack((direction, -edge))
                determinant = float(np.linalg.det(matrix))
                if abs(determinant) <= 1.0e-10:
                    continue
                distance, progress = np.linalg.solve(matrix, first - origin)
                if distance >= 0.0 and -1.0e-8 <= progress <= 1.0 + 1.0e-8:
                    hits.append(float(distance))
            if hits:
                return min(hits) + self.clearance_cm
            return float(np.max(np.linalg.norm(cross_section - origin, axis=1))) + self.clearance_cm

        radii = []
        for side_sign in (1.0, -1.0):
            radii.extend(
                ray_radius(
                    np.asarray(
                        [
                            side_sign * math.sin(theta),
                            math.cos(theta),
                        ],
                        dtype=float,
                    )
                )
                for theta in self._theta_grid
            )
        return np.asarray([center_z, *radii], dtype=float)

    @staticmethod
    def _smooth_profiles(raw: np.ndarray) -> np.ndarray:
        if len(raw) < 5:
            return raw
        padded = np.pad(raw, ((4, 4), (0, 0)), mode="edge")
        weights = np.asarray([1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 1.0])
        weights /= np.sum(weights)
        smoothed = np.vstack(
            [
                np.sum(padded[index : index + len(weights)] * weights[:, None], axis=0)
                for index in range(len(raw))
            ]
        )
        smoothed[:, 0] = raw[:, 0]
        smoothed[:, 1:] = np.maximum(smoothed[:, 1:], raw[:, 1:])
        return smoothed

    def _profile(self, y: float) -> np.ndarray:
        return np.asarray(
            [
                np.interp(y, self._grid_y, self._profiles[:, column])
                for column in range(self._profiles.shape[1])
            ],
            dtype=float,
        )

    def point(self, y: float, theta: float, side_sign: float) -> np.ndarray:
        theta = float(np.clip(theta, 0.0, math.pi))
        # Cache only identical surface queries. Quantizing these coordinates
        # collapses nearby cloth vertices onto one 3D point and creates zero-area
        # triangles before the solver starts.
        key = (y, theta, int(side_sign))
        cached = self._cache.get(key)
        if cached is not None:
            return cached.copy()

        profile = self._profile(y)
        center_z = profile[0]
        side_offset = 0 if side_sign > 0.0 else len(self._theta_grid)
        radius_values = profile[
            1 + side_offset : 1 + side_offset + len(self._theta_grid)
        ]
        radius = float(np.interp(theta, self._theta_grid, radius_values))
        result = np.asarray(
            [
                side_sign * radius * math.sin(theta),
                y,
                center_z + radius * math.cos(theta),
            ],
            dtype=float,
        )
        self._cache[key] = result
        return result.copy()


class _LiveBodyProfileSurface:
    """Continuous torso surface reconstructed from compiler cross sections."""

    def __init__(self, document: dict[str, object], clearance_cm: float) -> None:
        if document.get("schemaVersion") != "patterna.live-body-profile/1.1":
            raise ValueError("Unsupported live body profile schema.")
        raw_sections = document.get("sections")
        if not isinstance(raw_sections, list) or len(raw_sections) < 2:
            raise ValueError("Live body profile must contain at least two sections.")
        if not np.isfinite(clearance_cm) or clearance_cm <= 0.0:
            raise ValueError("Profile surface clearance must be positive and finite.")
        self.clearance_cm = float(clearance_cm)
        self._angles = np.linspace(-math.pi, math.pi, 361)
        sections: list[tuple[float, float, float, np.ndarray, np.ndarray, float, float]] = []
        for raw_section in raw_sections:
            if not isinstance(raw_section, dict):
                raise ValueError("Live body profile contains a non-object section.")
            raw_points = raw_section.get("surfacePoints")
            if not isinstance(raw_points, list) or len(raw_points) < 12:
                raise ValueError("Live body profile section has insufficient surface points.")
            samples: dict[float, list[tuple[float, float]]] = {}
            for raw_point in raw_points:
                if not isinstance(raw_point, dict):
                    raise ValueError("Live body profile contains a non-object surface point.")
                angle = float(raw_point["angleRadians"])
                point = (float(raw_point["xCm"]), float(raw_point["yCm"]))
                if not np.isfinite([angle, *point]).all():
                    raise ValueError("Live body profile contains a non-finite surface point.")
                samples.setdefault(round(angle, 12), []).append(point)
            sample_angles = np.asarray(sorted(samples), dtype=float)
            sample_points = np.asarray(
                [np.mean(samples[key], axis=0) for key in sorted(samples)],
                dtype=float,
            )
            extended_angles = np.concatenate(
                (sample_angles - math.tau, sample_angles, sample_angles + math.tau)
            )
            extended_points = np.vstack((sample_points, sample_points, sample_points))
            profile_x = np.interp(self._angles, extended_angles, extended_points[:, 0])
            profile_z = np.interp(self._angles, extended_angles, extended_points[:, 1])
            right = (self._angles >= -0.5 * math.pi) & (self._angles <= 0.5 * math.pi)
            left_first = self._angles <= -0.5 * math.pi
            left_second = self._angles >= 0.5 * math.pi

            def path_length(mask: np.ndarray) -> float:
                points = np.column_stack((profile_x[mask], profile_z[mask]))
                return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))

            right_length = path_length(right)
            left_length = path_length(left_first) + path_length(left_second)
            if min(right_length, left_length) <= 1.0:
                raise ValueError("Live body profile contains a degenerate half section.")
            sections.append(
                (
                    float(raw_section["heightCm"]),
                    float(raw_section["centerXCm"]),
                    float(raw_section["centerYCm"]),
                    profile_x,
                    profile_z,
                    right_length,
                    left_length,
                )
            )
        sections.sort(key=lambda section: section[0])
        self._heights = np.asarray([section[0] for section in sections], dtype=float)
        self._centers_x = np.asarray([section[1] for section in sections], dtype=float)
        self._centers_z = np.asarray([section[2] for section in sections], dtype=float)
        self._profiles_x = np.asarray([section[3] for section in sections], dtype=float)
        self._profiles_z = np.asarray([section[4] for section in sections], dtype=float)
        self._right_lengths = np.asarray([section[5] for section in sections], dtype=float)
        self._left_lengths = np.asarray([section[6] for section in sections], dtype=float)
        self.slice_count = len(sections)

    def _height_sample(self, values: np.ndarray, y: float) -> np.ndarray | float:
        if values.ndim == 1:
            return float(np.interp(y, self._heights, values))
        return np.asarray(
            [np.interp(y, self._heights, values[:, column]) for column in range(values.shape[1])],
            dtype=float,
        )

    def point(
        self,
        y: float,
        theta: float,
        side_sign: float,
        target_half_arc_length_cm: float,
    ) -> np.ndarray:
        theta = float(np.clip(theta, 0.0, math.pi))
        angle = 0.5 * math.pi - side_sign * theta
        angle = ((angle + math.pi) % math.tau) - math.pi
        profile_x = self._height_sample(self._profiles_x, y)
        profile_z = self._height_sample(self._profiles_z, y)
        assert isinstance(profile_x, np.ndarray)
        assert isinstance(profile_z, np.ndarray)
        center_x = float(self._height_sample(self._centers_x, y))
        center_z = float(self._height_sample(self._centers_z, y))
        body_half_arc = float(
            self._height_sample(
                self._right_lengths if side_sign > 0.0 else self._left_lengths,
                y,
            )
        )
        required_half_arc = max(
            float(target_half_arc_length_cm),
            body_half_arc + math.pi * self.clearance_cm,
        )
        scale = required_half_arc / body_half_arc
        x = float(np.interp(angle, self._angles, profile_x))
        z = float(np.interp(angle, self._angles, profile_z))
        return np.asarray(
            [
                center_x + (x - center_x) * scale,
                y,
                center_z + (z - center_z) * scale,
            ],
            dtype=float,
        )


def _maximum_seam_separation(vertices: np.ndarray, seam_links) -> float:
    if not seam_links:
        return 0.0
    return max(
        float(np.linalg.norm(vertices[int(first)] - vertices[int(second)]))
        for first, second in seam_links
    )


def _seam_separations(vertices: np.ndarray, seam_links) -> np.ndarray:
    return np.asarray(
        [
            np.linalg.norm(vertices[int(first)] - vertices[int(second)])
            for first, second in seam_links
        ],
        dtype=float,
    )


def _panel_material_edges(mesh) -> np.ndarray:
    edges: set[tuple[int, int]] = set()
    for panel_name in mesh.panelNames:
        panel = mesh.panels[panel_name]
        global_indices = [
            _global_vertex_index(mesh, panel_name, local_index)
            for local_index in range(len(panel.panel_vertices))
        ]
        for face in panel.panel_faces:
            indices = [global_indices[int(value)] for value in face]
            for first, second in ((0, 1), (1, 2), (2, 0)):
                edges.add(tuple(sorted((indices[first], indices[second]))))
    return np.asarray(sorted(edges), dtype=np.int32)


def arrange_independent_body_aware_panels(
    mesh,
    torso_vertices_cm: np.ndarray,
    clearance_cm: float = 1.5,
    *,
    body_profile: dict[str, object] | None = None,
    upper_blend_start_cm: float = 132.0,
    upper_blend_end_cm: float = 142.0,
    preserve_material_shape: bool = False,
) -> IndependentPanelStagingDiagnostics:
    """Wrap separate princess panels onto one torso chart without welding seams.

    The chart preserves every panel vertex and material edge. Adjacent panels
    occupy contiguous front, side, and back sectors, while their authored
    balance heights remain independent so the cloth solver can form the cup.
    """
    six_panel_roles = {
        "left_front_center",
        "left_front_side",
        "left_back",
        "right_front_center",
        "right_front_side",
        "right_back",
    }
    eight_panel_roles = {
        "left_front_center",
        "left_front_side",
        "left_back_side",
        "left_back_center",
        "right_front_center",
        "right_front_side",
        "right_back_side",
        "right_back_center",
    }
    sleeve_roles = {
        "left_sleeve_front",
        "left_sleeve_back",
        "right_sleeve_front",
        "right_sleeve_back",
    }
    available = set(mesh.panelNames)
    available_sleeves = available & sleeve_roles
    if available_sleeves and available_sleeves != sleeve_roles:
        raise RuntimeError(
            "Independent body-aware staging requires all four fitted sleeve "
            f"panels; missing {sorted(sleeve_roles - available_sleeves)}."
        )
    torso_available = available - sleeve_roles
    if torso_available == six_panel_roles:
        ordered_roles = ("front_center", "front_side", "back")
    elif torso_available == eight_panel_roles:
        ordered_roles = (
            "front_center",
            "front_side",
            "back_side",
            "back_center",
        )
    else:
        expected = (
            eight_panel_roles if len(torso_available) >= 8 else six_panel_roles
        )
        missing = sorted(expected - torso_available)
        unexpected = sorted(torso_available - expected)
        raise RuntimeError(
            "Independent body-aware staging topology mismatch. "
            f"Missing panels: {missing}; unexpected panels: {unexpected}."
        )

    source_vertices = np.asarray(mesh.vertices, dtype=float)
    if source_vertices.ndim != 2 or source_vertices.shape[1] != 3:
        raise RuntimeError("Independent body-aware staging needs 3D source vertices.")
    if not np.isfinite(source_vertices).all():
        raise RuntimeError("Independent body-aware staging source is not finite.")

    if not np.isfinite([upper_blend_start_cm, upper_blend_end_cm]).all():
        raise ValueError("Independent staging blend heights must be finite.")
    if upper_blend_end_cm <= upper_blend_start_cm:
        raise ValueError("Independent staging blend end must exceed its start.")
    surface = (
        _LiveBodyProfileSurface(body_profile, clearance_cm)
        if body_profile is not None
        else _TorsoSurface(torso_vertices_cm, clearance_cm)
    )
    arranged = np.full_like(source_vertices, np.nan)
    material_edges = _panel_material_edges(mesh)
    if len(material_edges) == 0:
        raise RuntimeError("Independent body-aware staging found no material edges.")
    source_edge_lengths = np.linalg.norm(
        source_vertices[material_edges[:, 0]] - source_vertices[material_edges[:, 1]],
        axis=1,
    )
    if np.any(source_edge_lengths <= 1.0e-8):
        raise RuntimeError("Independent body-aware staging source has degenerate edges.")

    for panel_name in mesh.panelNames:
        panel = mesh.panels[panel_name]
        if panel_name in sleeve_roles:
            panel_indices = np.asarray(
                [
                    _global_vertex_index(mesh, panel_name, local_index)
                    for local_index in range(len(panel.panel_vertices))
                ],
                dtype=np.int32,
            )
            # GarmentCode already places its two sleeve halves on opposite
            # sides of the upper arm. Keep that rigid placement instead of
            # flattening an arm panel onto the torso's circumference chart.
            arranged[panel_indices] = source_vertices[panel_indices]
            continue
        role, side_sign = _panel_role(panel_name)
        side_prefix = "right" if side_sign > 0.0 else "left"
        side_panels = {
            name: mesh.panels[f"{side_prefix}_{name}"]
            for name in ordered_roles
        }
        panel_vertices = np.asarray(panel.panel_vertices, dtype=float)
        for local_index, local in enumerate(panel_vertices):
            global_index = _global_vertex_index(mesh, panel_name, local_index)
            world_y = float(source_vertices[global_index, 1])
            material_y = float(local[1])
            canonical_x = float(local[0] * side_sign)
            spans = {
                name: _canonical_horizontal_bounds(candidate, material_y, side_sign)
                for name, candidate in side_panels.items()
            }
            widths = {
                name: max(0.01, high - low)
                for name, (low, high) in spans.items()
            }
            total_width = sum(widths.values())
            low, high = spans[role]
            within = float(np.clip(canonical_x, low, high) - low)
            preceding_width = sum(
                widths[name]
                for name in ordered_roles[: ordered_roles.index(role)]
            )
            if role in {"front_center", "front_side"}:
                circumference = preceding_width + (high - canonical_x)
            elif role == "back":
                circumference = total_width - within
            else:
                circumference = preceding_width + within
            theta = math.pi * float(
                np.clip(circumference / total_width, 0.0, 1.0)
            )
            if isinstance(surface, _LiveBodyProfileSurface):
                mapped = surface.point(world_y, theta, side_sign, total_width)
            else:
                mapped = surface.point(world_y, theta, side_sign)
            blend = float(
                np.clip(
                    (world_y - upper_blend_start_cm)
                    / (upper_blend_end_cm - upper_blend_start_cm),
                    0.0,
                    1.0,
                )
            )
            blend = blend * blend * (3.0 - 2.0 * blend)
            arranged[global_index] = mapped * (1.0 - blend) + source_vertices[
                global_index
            ] * blend

    if not np.isfinite(arranged).all():
        raise RuntimeError("Independent body-aware staging did not map every vertex.")

    if preserve_material_shape:
        rigid_arranged = arranged.copy()
        for panel_name in mesh.panelNames:
            if panel_name in sleeve_roles:
                continue
            panel = mesh.panels[panel_name]
            indices = np.asarray(
                [
                    _global_vertex_index(mesh, panel_name, local_index)
                    for local_index in range(len(panel.panel_vertices))
                ],
                dtype=np.int32,
            )
            rotation, translation = _best_rigid_transform(
                source_vertices[indices],
                arranged[indices],
            )
            rigid_arranged[indices] = (
                (rotation @ source_vertices[indices].T).T + translation
            )
        if not np.isfinite(rigid_arranged).all():
            raise RuntimeError("Rigid body-aware staging did not map every vertex.")
        arranged = rigid_arranged

    if available_sleeves:
        vertex_owner = [""] * len(source_vertices)
        panel_indices_by_name: dict[str, np.ndarray] = {}
        sleeve_target_centers_xz: dict[str, np.ndarray] = {}
        for panel_name in mesh.panelNames:
            panel = mesh.panels[panel_name]
            indices = np.asarray(
                [
                    _global_vertex_index(mesh, panel_name, local_index)
                    for local_index in range(len(panel.panel_vertices))
                ],
                dtype=np.int32,
            )
            panel_indices_by_name[panel_name] = indices
            for index in indices:
                vertex_owner[int(index)] = panel_name
        for panel_name in sorted(available_sleeves):
            sleeve_points = []
            torso_targets = []
            for first, second in getattr(mesh, "seam_links", []):
                first = int(first)
                second = int(second)
                if vertex_owner[first] == panel_name and vertex_owner[
                    second
                ] not in sleeve_roles:
                    sleeve_points.append(source_vertices[first])
                    torso_targets.append(arranged[second])
                elif vertex_owner[second] == panel_name and vertex_owner[
                    first
                ] not in sleeve_roles:
                    sleeve_points.append(source_vertices[second])
                    torso_targets.append(arranged[first])
            if len(sleeve_points) < 3:
                raise RuntimeError(
                    f"Sleeve panel {panel_name} has too few armhole seam targets."
                )
            rotation, translation = _best_rigid_transform(
                np.asarray(sleeve_points, dtype=float),
                np.asarray(torso_targets, dtype=float),
            )
            indices = panel_indices_by_name[panel_name]
            arranged[indices] = (
                (rotation @ source_vertices[indices].T).T + translation
            )
            sleeve_target_centers_xz[panel_name] = np.mean(
                np.asarray(torso_targets, dtype=float)[:, [0, 2]], axis=0
            )

        # Open each two-panel sleeve around the armhole like an unclosed book.
        # A rigid front and back sleeve half occupy the same planar volume when
        # both are registered directly onto a curved armhole. The solver cannot
        # recover from that invalid self-intersection. Spreading the halves in
        # opposite tangential directions keeps every panel undeformed while the
        # progressive sleeve seams close them around the arm.
        dressing_spread_cm = max(4.0, clearance_cm * 0.6)
        for side_prefix in ("left", "right"):
            pair = (
                f"{side_prefix}_sleeve_front",
                f"{side_prefix}_sleeve_back",
            )
            midpoint = np.mean(
                [sleeve_target_centers_xz[name] for name in pair], axis=0
            )
            for panel_name in pair:
                direction_xz = sleeve_target_centers_xz[panel_name] - midpoint
                direction_length = float(np.linalg.norm(direction_xz))
                if direction_length <= 1.0e-8:
                    raise RuntimeError(
                        f"Sleeve panel {panel_name} has no tangential dressing direction."
                    )
                direction_xz /= direction_length
                indices = panel_indices_by_name[panel_name]
                arranged[indices, 0] += direction_xz[0] * dressing_spread_cm
                arranged[indices, 2] += direction_xz[1] * dressing_spread_cm

    arranged_edge_lengths = np.linalg.norm(
        arranged[material_edges[:, 0]] - arranged[material_edges[:, 1]],
        axis=1,
    )
    strains = np.abs(arranged_edge_lengths / source_edge_lengths - 1.0)
    seam_links = list(getattr(mesh, "seam_links", []))
    seam_separations = _seam_separations(arranged, seam_links)
    mesh.vertices = arranged.tolist()
    return IndependentPanelStagingDiagnostics(
        panel_count=len(mesh.panelNames),
        vertex_count=len(arranged),
        seam_link_count=len(seam_links),
        maximum_seam_separation_cm=(
            float(np.max(seam_separations)) if len(seam_separations) else 0.0
        ),
        mean_seam_separation_cm=(
            float(np.mean(seam_separations)) if len(seam_separations) else 0.0
        ),
        ninety_fifth_percentile_seam_separation_cm=(
            float(np.percentile(seam_separations, 95.0))
            if len(seam_separations)
            else 0.0
        ),
        maximum_material_edge_strain_ratio=float(np.max(strains)),
        ninety_fifth_percentile_material_edge_strain_ratio=float(
            np.percentile(strains, 95.0)
        ),
        ninety_ninth_point_ninth_percentile_material_edge_strain_ratio=float(
            np.percentile(strains, 99.9)
        ),
        clearance_cm=float(clearance_cm),
        body_slice_count=surface.slice_count,
    )


def _best_rigid_transform(
    source: np.ndarray,
    target: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 3:
        raise ValueError("Rigid registration requires matching N by 3 arrays.")
    if len(source) < 3:
        raise ValueError("Rigid registration requires at least three points.")
    source_center = np.mean(source, axis=0)
    target_center = np.mean(target, axis=0)
    covariance = (source - source_center).T @ (target - target_center)
    first, _, second_transposed = np.linalg.svd(covariance)
    rotation = second_transposed.T @ first.T
    if np.linalg.det(rotation) < 0.0:
        second_transposed[-1] *= -1.0
        rotation = second_transposed.T @ first.T
    translation = target_center - rotation @ source_center
    return rotation, translation


def preassemble_body_aware_seams(
    mesh,
    torso_vertices_cm: np.ndarray,
    body_profile: dict[str, object] | None,
    clearance_cm: float = 0.4,
    *,
    seam_constraint_weight: float = 25.0,
    arap_iterations: int = 20,
) -> SeamPreassemblyDiagnostics:
    """Bend separate panels toward shared anatomical seams with ARAP energy."""
    if not np.isfinite(seam_constraint_weight) or seam_constraint_weight <= 0.0:
        raise ValueError("Seam constraint weight must be positive and finite.")
    if arap_iterations < 1:
        raise ValueError("ARAP preassembly requires at least one iteration.")
    source = np.asarray(mesh.vertices, dtype=float).copy()
    seam_links = [(int(first), int(second)) for first, second in mesh.seam_links]
    if not seam_links:
        raise RuntimeError("ARAP preassembly requires explicit seam links.")
    initial_separations = _seam_separations(source, seam_links)
    edges = _panel_material_edges(mesh)
    source_edge_lengths = np.linalg.norm(
        source[edges[:, 0]] - source[edges[:, 1]],
        axis=1,
    )
    if np.any(source_edge_lengths <= 1.0e-8):
        raise RuntimeError("ARAP preassembly source has degenerate material edges.")

    arrange_independent_body_aware_panels(
        mesh,
        torso_vertices_cm,
        clearance_cm,
        body_profile=body_profile,
        upper_blend_start_cm=1000.0,
        upper_blend_end_cm=1001.0,
    )
    chart = np.asarray(mesh.vertices, dtype=float).copy()
    mesh.vertices = source.tolist()

    target_sums = np.zeros_like(source)
    target_counts = np.zeros(len(source), dtype=np.int32)
    for first, second in seam_links:
        target = 0.5 * (chart[first] + chart[second])
        target_sums[first] += target
        target_sums[second] += target
        target_counts[first] += 1
        target_counts[second] += 1
    constrained = target_counts > 0
    targets = np.zeros_like(source)
    targets[constrained] = target_sums[constrained] / target_counts[constrained, None]

    current = source.copy()
    for panel_name in mesh.panelNames:
        panel = mesh.panels[panel_name]
        panel_indices = np.asarray(
            [
                _global_vertex_index(mesh, panel_name, local_index)
                for local_index in range(len(panel.panel_vertices))
            ],
            dtype=np.int32,
        )
        panel_constraints = panel_indices[constrained[panel_indices]]
        if len(panel_constraints) < 3:
            raise RuntimeError(
                f"Panel {panel_name} has insufficient seam constraints for registration."
            )
        rotation, translation = _best_rigid_transform(
            source[panel_constraints],
            targets[panel_constraints],
        )
        current[panel_indices] = source[panel_indices] @ rotation.T + translation

    from scipy.sparse import coo_matrix, diags
    from scipy.sparse.linalg import factorized

    first_indices = edges[:, 0]
    second_indices = edges[:, 1]
    vertex_count = len(source)
    rows = np.concatenate(
        (first_indices, second_indices, first_indices, second_indices)
    )
    columns = np.concatenate(
        (first_indices, second_indices, second_indices, first_indices)
    )
    values = np.concatenate(
        (
            np.ones(len(edges)),
            np.ones(len(edges)),
            -np.ones(len(edges)),
            -np.ones(len(edges)),
        )
    )
    laplacian = coo_matrix(
        (values, (rows, columns)),
        shape=(vertex_count, vertex_count),
    ).tocsc()
    constraint_diagonal = constrained.astype(float) * seam_constraint_weight
    solve = factorized(laplacian + diags(constraint_diagonal, format="csc"))
    reference_edges = source[first_indices] - source[second_indices]

    for _ in range(arap_iterations):
        current_edges = current[first_indices] - current[second_indices]
        covariance = np.zeros((vertex_count, 3, 3), dtype=float)
        edge_covariance = current_edges[:, :, None] * reference_edges[:, None, :]
        np.add.at(covariance, first_indices, edge_covariance)
        np.add.at(covariance, second_indices, edge_covariance)
        first_rotation, _, second_rotation_transposed = np.linalg.svd(covariance)
        rotations = first_rotation @ second_rotation_transposed
        reflected = np.linalg.det(rotations) < 0.0
        if np.any(reflected):
            first_rotation[reflected, :, -1] *= -1.0
            rotations[reflected] = (
                first_rotation[reflected] @ second_rotation_transposed[reflected]
            )
        desired_edges = 0.5 * np.einsum(
            "nij,nj->ni",
            rotations[first_indices] + rotations[second_indices],
            reference_edges,
        )
        right_hand = np.zeros_like(source)
        np.add.at(right_hand, first_indices, desired_edges)
        np.add.at(right_hand, second_indices, -desired_edges)
        right_hand[constrained] += (
            seam_constraint_weight * targets[constrained]
        )
        current = np.column_stack(
            [solve(right_hand[:, coordinate]) for coordinate in range(3)]
        )

    if not np.isfinite(current).all():
        raise RuntimeError("ARAP preassembly produced non-finite vertices.")
    final_edge_lengths = np.linalg.norm(
        current[first_indices] - current[second_indices],
        axis=1,
    )
    strains = np.abs(final_edge_lengths / source_edge_lengths - 1.0)
    seam_separations = _seam_separations(current, seam_links)
    mesh.vertices = current.tolist()
    return SeamPreassemblyDiagnostics(
        panel_count=len(mesh.panelNames),
        vertex_count=len(current),
        seam_link_count=len(seam_links),
        arap_iteration_count=arap_iterations,
        seam_constraint_weight=float(seam_constraint_weight),
        initial_maximum_seam_separation_cm=float(np.max(initial_separations)),
        maximum_seam_separation_cm=float(np.max(seam_separations)),
        mean_seam_separation_cm=float(np.mean(seam_separations)),
        ninety_fifth_percentile_seam_separation_cm=float(
            np.percentile(seam_separations, 95.0)
        ),
        maximum_material_edge_strain_ratio=float(np.max(strains)),
        ninety_fifth_percentile_material_edge_strain_ratio=float(
            np.percentile(strains, 95.0)
        ),
        ninety_ninth_point_ninth_percentile_material_edge_strain_ratio=float(
            np.percentile(strains, 99.9)
        ),
        minimum_height_cm=float(np.min(current[:, 1])),
        maximum_height_cm=float(np.max(current[:, 1])),
        center_x_cm=float(0.5 * (np.min(current[:, 0]) + np.max(current[:, 0]))),
        clearance_cm=float(clearance_cm),
        body_slice_count=(
            len(body_profile["sections"])
            if body_profile is not None
            else _TorsoSurface(torso_vertices_cm, clearance_cm).slice_count
        ),
    )


def set_current_geometry_rest_lengths(mesh) -> dict[str, float | int]:
    """Use an assembled shell as a temporary, non-production bootstrap rest pose."""
    if not getattr(mesh, "orig_lens", None):
        raise RuntimeError("The garment mesh contains no material rest lengths.")
    vertices = np.asarray(mesh.vertices, dtype=float)
    seam_edges = {
        tuple(sorted((int(first), int(second))))
        for first, second in getattr(mesh, "seam_links", [])
    }
    lengths: list[float] = []
    for edge in list(mesh.orig_lens):
        first, second = (int(value) for value in edge)
        if tuple(sorted((first, second))) in seam_edges:
            # The assembled shell intentionally makes paired seam vertices
            # coincident. Sewing links are constraints, not material edges,
            # so their original closure rest value must not be replaced by a
            # zero-length fabric spring.
            continue
        if min(first, second) < 0 or max(first, second) >= len(vertices):
            raise RuntimeError(f"Material edge references an invalid vertex: {edge!r}")
        length = float(np.linalg.norm(vertices[first] - vertices[second]))
        if not np.isfinite(length) or length <= 1.0e-6:
            raise RuntimeError(f"Assembled shell contains a degenerate edge: {edge!r}")
        mesh.orig_lens[edge] = length
        lengths.append(length)
    return {
        "edge_count": len(lengths),
        "excluded_seam_edge_count": len(seam_edges),
        "minimum_rest_length_cm": min(lengths),
        "maximum_rest_length_cm": max(lengths),
    }


def _harmonic_sewn_parameters(
    mesh,
    parameter_y: np.ndarray,
    parameter_theta: np.ndarray,
    parameter_sign: np.ndarray,
    find,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Solve one smooth torso chart across all panels and sewn interfaces."""
    from scipy.sparse import lil_matrix
    from scipy.sparse.linalg import spsolve

    roots = np.asarray([find(index) for index in range(len(parameter_y))], dtype=int)
    unique_roots = sorted(set(roots.tolist()))
    root_to_node = {root: node for node, root in enumerate(unique_roots)}
    vertex_nodes = np.asarray([root_to_node[root] for root in roots], dtype=int)
    node_members: list[list[int]] = [[] for _ in unique_roots]
    for vertex, node in enumerate(vertex_nodes):
        node_members[int(node)].append(vertex)

    node_y = np.asarray(
        [float(np.mean(parameter_y[members])) for members in node_members],
        dtype=float,
    )
    node_theta = np.asarray(
        [float(np.mean(parameter_theta[members])) for members in node_members],
        dtype=float,
    )
    node_sign = np.asarray(
        [
            1.0 if float(np.mean(parameter_sign[members])) >= 0.0 else -1.0
            for members in node_members
        ],
        dtype=float,
    )

    adjacency: list[set[int]] = [set() for _ in unique_roots]
    fixed_theta_nodes: set[int] = set()
    for panel_name in mesh.panelNames:
        panel = mesh.panels[panel_name]
        global_indices = [
            _global_vertex_index(mesh, panel_name, local_index)
            for local_index in range(len(panel.panel_vertices))
        ]
        for face in panel.panel_faces:
            nodes = [vertex_nodes[global_indices[int(value)]] for value in face]
            for first, second in ((0, 1), (1, 2), (2, 0)):
                if nodes[first] != nodes[second]:
                    adjacency[int(nodes[first])].add(int(nodes[second]))
                    adjacency[int(nodes[second])].add(int(nodes[first]))
        for edge in panel.edges:
            edge_nodes = {
                int(vertex_nodes[global_indices[int(local_index)]])
                for local_index in edge.vertex_range
            }
            cardinal_center = edge.label in {"center_front", "center_back"}
            if edge.label == "hem" or cardinal_center:
                fixed_theta_nodes.update(edge_nodes)

    def solve_coordinate(values: np.ndarray, fixed_nodes: set[int]) -> np.ndarray:
        unknown_nodes = [
            node for node in range(len(unique_roots)) if node not in fixed_nodes
        ]
        if not unknown_nodes:
            return values.copy()
        unknown_lookup = {node: row for row, node in enumerate(unknown_nodes)}
        matrix = lil_matrix((len(unknown_nodes), len(unknown_nodes)), dtype=float)
        right_hand = np.zeros(len(unknown_nodes), dtype=float)
        for node in unknown_nodes:
            row = unknown_lookup[node]
            neighbors = sorted(adjacency[node])
            if not neighbors:
                matrix[row, row] = 1.0
                right_hand[row] = values[node]
                continue
            matrix[row, row] = float(len(neighbors))
            for neighbor in neighbors:
                neighbor_row = unknown_lookup.get(neighbor)
                if neighbor_row is None:
                    right_hand[row] += values[neighbor]
                else:
                    matrix[row, neighbor_row] -= 1.0
        solved = values.copy()
        solved[unknown_nodes] = spsolve(matrix.tocsr(), right_hand)
        return solved

    node_theta = np.clip(
        solve_coordinate(node_theta, fixed_theta_nodes),
        0.0,
        math.pi,
    )
    return (
        node_y[vertex_nodes],
        node_theta[vertex_nodes],
        node_sign[vertex_nodes],
    )


def assemble_body_aware_shell(
    mesh,
    torso_vertices_cm: np.ndarray,
    clearance_cm: float = 1.5,
) -> ShellAssemblyDiagnostics:
    """Wrap the cup-aware block around a torso and close every authored seam."""
    required_roles = {
        "left_front_center",
        "left_front_side",
        "left_back",
        "right_front_center",
        "right_front_side",
        "right_back",
    }
    available = set(mesh.panelNames)
    if available != required_roles:
        missing = sorted(required_roles - available)
        unexpected = sorted(available - required_roles)
        raise RuntimeError(
            "Cup-aware shell topology mismatch. "
            f"Missing panels: {missing}; unexpected panels: {unexpected}."
        )

    surface = _TorsoSurface(torso_vertices_cm, clearance_cm)
    parameters: list[list[tuple[float, float, float]]] = [
        [] for _ in mesh.vertices
    ]

    for panel_name in mesh.panelNames:
        panel = mesh.panels[panel_name]
        role, side_sign = _panel_role(panel_name)
        side_panels = {
            "front_center": mesh.panels[f"{'right' if side_sign > 0 else 'left'}_front_center"],
            "front_side": mesh.panels[f"{'right' if side_sign > 0 else 'left'}_front_side"],
            "back": mesh.panels[f"{'right' if side_sign > 0 else 'left'}_back"],
        }
        panel_vertices = np.asarray(panel.panel_vertices, dtype=float)
        for local_index, local in enumerate(panel_vertices):
            y = float(np.asarray(mesh.vertices[_global_vertex_index(mesh, panel_name, local_index)])[1])
            canonical_x = float(local[0] * side_sign)
            spans: dict[str, tuple[float, float]] = {
                name: _canonical_horizontal_bounds(candidate, float(local[1]), side_sign)
                for name, candidate in side_panels.items()
            }
            widths = {
                name: max(0.01, high - low)
                for name, (low, high) in spans.items()
            }
            total_width = sum(widths.values())
            low, high = spans[role]
            within = float(np.clip(canonical_x, low, high) - low)
            if role == "front_center":
                circumference = within
            elif role == "front_side":
                circumference = widths["front_center"] + within
            else:
                circumference = total_width - within
            theta = math.pi * float(np.clip(circumference / total_width, 0.0, 1.0))
            global_index = _global_vertex_index(mesh, panel_name, local_index)
            parameters[global_index].append((y, theta, side_sign))

    parameter_y = np.zeros(len(mesh.vertices), dtype=float)
    parameter_theta = np.zeros(len(mesh.vertices), dtype=float)
    parameter_sign = np.ones(len(mesh.vertices), dtype=float)
    for index, owned_parameters in enumerate(parameters):
        if not owned_parameters:
            raise RuntimeError(f"Shell assembly did not map garment vertex {index}.")
        parameter_y[index] = float(np.mean([value[0] for value in owned_parameters]))
        vectors = np.asarray(
            [
                [value[2] * math.sin(value[1]), -math.cos(value[1])]
                for value in owned_parameters
            ],
            dtype=float,
        )
        direction = np.mean(vectors, axis=0)
        parameter_sign[index] = (
            1.0
            if float(np.mean([value[2] for value in owned_parameters])) >= 0.0
            else -1.0
        )
        parameter_theta[index] = math.atan2(
            abs(float(direction[0])), -float(direction[1])
        )

    seam_links = list(getattr(mesh, "seam_links", []))
    parent = list(range(len(mesh.vertices)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for first, second in seam_links:
        first_root = find(int(first))
        second_root = find(int(second))
        if first_root != second_root:
            parent[second_root] = first_root

    components: dict[int, list[int]] = {}
    for first, second in seam_links:
        for index in (int(first), int(second)):
            components.setdefault(find(index), []).append(index)
    for component in components.values():
        indices = sorted(set(component))
        mean_y = float(np.mean(parameter_y[indices]))
        vectors = np.asarray(
            [
                [
                    parameter_sign[index] * math.sin(parameter_theta[index]),
                    -math.cos(parameter_theta[index]),
                ]
                for index in indices
            ],
            dtype=float,
        )
        direction = np.mean(vectors, axis=0)
        mean_sign = float(np.mean(parameter_sign[indices]))
        side_sign = 1.0 if mean_sign >= 0.0 else -1.0
        theta = math.atan2(abs(float(direction[0])), -float(direction[1]))
        parameter_y[indices] = mean_y
        parameter_theta[indices] = theta
        parameter_sign[indices] = side_sign

    parameter_y, parameter_theta, parameter_sign = _harmonic_sewn_parameters(
        mesh,
        parameter_y,
        parameter_theta,
        parameter_sign,
        find,
    )
    arranged = np.asarray(
        [
            surface.point(
                float(parameter_y[index]),
                float(parameter_theta[index]),
                float(parameter_sign[index]),
            )
            for index in range(len(mesh.vertices))
        ],
        dtype=float,
    )

    if not np.isfinite(arranged).all():
        raise RuntimeError("Body-aware shell assembly produced non-finite positions.")
    mesh.vertices = arranged.tolist()
    maximum_separation = _maximum_seam_separation(arranged, seam_links)
    return ShellAssemblyDiagnostics(
        panel_count=len(mesh.panelNames),
        vertex_count=len(arranged),
        seam_link_count=len(seam_links),
        maximum_seam_separation_cm=maximum_separation,
        clearance_cm=float(clearance_cm),
        body_slice_count=surface.slice_count,
    )
