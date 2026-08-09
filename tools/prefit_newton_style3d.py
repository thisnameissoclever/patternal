#!/usr/bin/env python3
"""Relax a Patterna garment with Newton's implicit Style3D cloth solver."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import inspect
import json
from pathlib import Path
import pickle
import time
from typing import Iterable

import numpy as np
import trimesh
import warp as wp

# Newton 1.4.0's Style3D cloth helper calls NumPy's C-style atan2 spelling.
# NumPy exposes the same ufunc as arctan2, so provide the missing compatibility
# alias until the upstream solver switches to the canonical name.
if not hasattr(np, "atan2"):
    setattr(np, "atan2", np.arctan2)
if not hasattr(np, "pow"):
    setattr(np, "pow", np.power)

import newton
from newton import Mesh
from newton.solvers import SolverStyle3D, style3d

try:
    from tools.prefit_garmentcode_warp import (
        create_radially_scaled_body,
        evaluate_acceptance,
        interpolate_animated_body,
    )
    from tools.patterna_style3d_sewing import PatternaStyle3DSewingSolver
except ModuleNotFoundError:
    from prefit_garmentcode_warp import (
        create_radially_scaled_body,
        evaluate_acceptance,
        interpolate_animated_body,
    )
    from patterna_style3d_sewing import PatternaStyle3DSewingSolver


REPORT_SCHEMA_VERSION = "patterna.newton-style3d-report/1.0"


@dataclass(frozen=True)
class ObjSurface:
    vertices: np.ndarray
    texture_vertices: np.ndarray
    faces: np.ndarray
    texture_faces: np.ndarray


@dataclass(frozen=True)
class WeldedSurface:
    vertices: np.ndarray
    faces: np.ndarray
    old_to_new: np.ndarray
    components: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class SewingAnchor:
    panel_name: str
    vertex_index: int
    target_height_cm: float
    initial_height_cm: float
    source: str
    partner_panel_name: str | None = None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_obj_surface(path: Path) -> ObjSurface:
    vertices: list[list[float]] = []
    texture_vertices: list[list[float]] = []
    faces: list[list[int]] = []
    texture_faces: list[list[int]] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("v "):
            values = line.split()
            vertices.append([float(values[1]), float(values[2]), float(values[3])])
        elif line.startswith("vt "):
            values = line.split()
            texture_vertices.append([float(values[1]), float(values[2])])
        elif line.startswith("f "):
            corners = line.split()[1:]
            if len(corners) != 3:
                raise ValueError(f"OBJ surface must be triangulated: {line}")
            face: list[int] = []
            texture_face: list[int] = []
            for corner in corners:
                parts = corner.split("/")
                if not parts[0] or int(parts[0]) <= 0:
                    raise ValueError("OBJ surface requires positive absolute vertex indices.")
                face.append(int(parts[0]) - 1)
                if len(parts) < 2 or not parts[1] or int(parts[1]) <= 0:
                    raise ValueError("OBJ surface requires positive absolute texture indices.")
                texture_face.append(int(parts[1]) - 1)
            faces.append(face)
            texture_faces.append(texture_face)

    vertex_array = np.asarray(vertices, dtype=np.float64)
    texture_array = np.asarray(texture_vertices, dtype=np.float64)
    face_array = np.asarray(faces, dtype=np.int32)
    texture_face_array = np.asarray(texture_faces, dtype=np.int32)
    if vertex_array.ndim != 2 or vertex_array.shape[1] != 3 or not len(vertex_array):
        raise ValueError(f"OBJ surface contains no usable vertices: {path}")
    if texture_array.ndim != 2 or texture_array.shape[1] != 2 or not len(texture_array):
        raise ValueError(f"OBJ surface contains no usable texture coordinates: {path}")
    if face_array.ndim != 2 or face_array.shape[1] != 3 or not len(face_array):
        raise ValueError(f"OBJ surface contains no usable triangles: {path}")
    if face_array.max() >= len(vertex_array) or texture_face_array.max() >= len(texture_array):
        raise ValueError("OBJ surface contains an out-of-range corner index.")
    if not np.isfinite(vertex_array).all() or not np.isfinite(texture_array).all():
        raise ValueError("OBJ surface contains non-finite coordinates.")
    return ObjSurface(
        vertices=vertex_array,
        texture_vertices=texture_array,
        faces=face_array,
        texture_faces=texture_face_array,
    )


def load_obj_geometry(path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("v "):
            values = line.split()
            vertices.append([float(values[1]), float(values[2]), float(values[3])])
        elif line.startswith("f "):
            corners = line.split()[1:]
            if len(corners) != 3:
                raise ValueError(f"OBJ geometry must be triangulated: {line}")
            faces.append([int(corner.split("/")[0]) - 1 for corner in corners])
    vertex_array = np.asarray(vertices, dtype=np.float64)
    face_array = np.asarray(faces, dtype=np.int32)
    if vertex_array.ndim != 2 or vertex_array.shape[1] != 3 or not len(vertex_array):
        raise ValueError(f"OBJ geometry contains no usable vertices: {path}")
    if face_array.ndim != 2 or face_array.shape[1] != 3 or not len(face_array):
        raise ValueError(f"OBJ geometry contains no usable triangles: {path}")
    if face_array.min() < 0 or face_array.max() >= len(vertex_array):
        raise ValueError("OBJ geometry contains an out-of-range vertex index.")
    if not np.isfinite(vertex_array).all():
        raise ValueError("OBJ geometry contains non-finite coordinates.")
    return vertex_array, face_array


def load_named_seam_links(
    path: Path,
    vertex_count: int,
) -> list[tuple[str, int, int]]:
    seam_vertices: dict[str, list[int]] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) != vertex_count:
        raise ValueError(
            f"Segmentation has {len(lines)} rows for {vertex_count} surface vertices."
        )
    for vertex_index, line in enumerate(lines):
        for label in line.split(","):
            label = label.strip()
            if label.startswith("seam_link_"):
                seam_vertices.setdefault(label, []).append(vertex_index)
    invalid = {
        label: values
        for label, values in seam_vertices.items()
        if len(values) != 2 or values[0] == values[1]
    }
    if invalid:
        preview = list(sorted(invalid.items()))[:8]
        raise ValueError(f"Each seam link must join two distinct vertices: {preview}")
    return [
        (label, int(values[0]), int(values[1]))
        for label, values in sorted(seam_vertices.items())
    ]


def load_seam_links(path: Path, vertex_count: int) -> list[tuple[int, int]]:
    return [
        (first, second)
        for _, first, second in load_named_seam_links(path, vertex_count)
    ]


def load_panel_vertex_owners(path: Path, vertex_count: int) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    panels = document.get("panels")
    if document.get("schema_version") != "patterna.style3d-panel-index-map/1.0" or not panels:
        raise ValueError("Panel index map has an unsupported schema or no panels.")
    owners = [""] * vertex_count
    for panel in panels:
        name = str(panel.get("source_panel_name", "")).strip()
        indices = np.asarray(panel.get("vertex_indices", []), dtype=np.int32)
        if not name or indices.ndim != 1 or not len(indices):
            raise ValueError("Each panel index-map entry must have a name and vertices.")
        if indices.min() < 0 or indices.max() >= vertex_count:
            raise ValueError(f"Panel {name} contains an out-of-range vertex index.")
        for raw_index in indices:
            index = int(raw_index)
            if owners[index]:
                raise ValueError(
                    f"Panel vertices must have one owner; {name} repeats {index}."
                )
            owners[index] = name
    if any(not owner for owner in owners):
        raise ValueError("Panel index map does not own every material vertex exactly once.")
    return owners


def load_panel_top_anchors(
    path: Path,
    panel_vertices_cm: np.ndarray,
) -> list[tuple[str, int]]:
    """Choose one deterministic vertical support point at each panel's top edge."""
    document = json.loads(path.read_text(encoding="utf-8"))
    panels = document["panels"]
    vertex_count = len(panel_vertices_cm)
    owners = load_panel_vertex_owners(path, vertex_count)
    anchors: list[tuple[str, int]] = []
    for panel in panels:
        name = str(panel["source_panel_name"]).strip()
        indices = np.asarray(panel.get("vertex_indices", []), dtype=np.int32)
        panel_heights = panel_vertices_cm[indices, 1]
        anchor = int(indices[int(np.argmax(panel_heights))])
        if owners[anchor] != name:
            raise ValueError(f"Panel anchor ownership changed unexpectedly for {name}.")
        anchors.append((name, anchor))
    return anchors


def seam_group_name(label: str) -> str:
    """Remove the per-link suffix while preserving the authored stitch index."""
    name, separator, link_index = label.rpartition("_")
    if not separator or not link_index.isdigit():
        raise ValueError(f"Seam-link label has no numeric link suffix: {label}")
    return name


def group_named_seam_links(
    named_links: list[tuple[str, int, int]],
) -> dict[str, list[tuple[int, int, int]]]:
    grouped: dict[str, list[tuple[int, int, int]]] = {}
    for link_index, (label, first, second) in enumerate(named_links):
        grouped.setdefault(seam_group_name(label), []).append(
            (link_index, first, second)
        )
    return grouped


def _is_torso_front_back_pair(panel_names: set[str]) -> bool:
    finishing_tokens = ("sleeve", "collar", "cuff", "band", "tie")
    if len(panel_names) != 2 or any(
        token in name
        for name in panel_names
        for token in finishing_tokens
    ):
        return False
    front = [name for name in panel_names if "front" in name]
    back = [name for name in panel_names if "back" in name]
    if len(front) != 1 or len(back) != 1:
        return False

    def construction_key(name: str) -> tuple[str, ...]:
        return tuple(
            token
            for token in name.replace("-", "_").split("_")
            if token and token not in {"front", "back"}
        )

    return construction_key(front[0]) == construction_key(back[0])


def identify_shoulder_seam_groups(
    named_links: list[tuple[str, int, int]],
    vertex_owners: list[str],
    panel_vertices_cm: np.ndarray,
) -> set[str]:
    """Identify anatomical shoulder stitches by ownership and material height.

    A princess side panel has four separate front-to-back stitches: one shoulder
    stitch and three vertically segmented side-seam stitches. Link count cannot
    distinguish them. The shoulder is the highest stitch for each matching
    front/back torso panel pair in material space.
    """
    if len(panel_vertices_cm) != len(vertex_owners):
        raise ValueError("Material coordinates and panel ownership must align.")
    candidates: dict[tuple[str, str], list[tuple[float, float, str]]] = {}
    for seam_name, links in group_named_seam_links(named_links).items():
        panel_names = {
            vertex_owners[vertex]
            for _, first, second in links
            for vertex in (first, second)
        }
        if not _is_torso_front_back_pair(panel_names):
            continue
        owner_pair = tuple(sorted(panel_names))
        seam_vertices = np.asarray(
            [vertex for _, first, second in links for vertex in (first, second)],
            dtype=np.int32,
        )
        mean_height_cm = float(np.mean(panel_vertices_cm[seam_vertices, 1]))
        mean_horizontal_cm = float(np.mean(panel_vertices_cm[seam_vertices, 0]))
        candidates.setdefault(owner_pair, []).append(
            (mean_height_cm, mean_horizontal_cm, seam_name)
        )
    shoulder_groups: set[str] = set()
    for pair_candidates in candidates.values():
        maximum_height = max(height for height, _, _ in pair_candidates)
        selected_horizontal_positions: list[float] = []
        for height, horizontal, seam_name in sorted(
            pair_candidates,
            key=lambda item: item[0],
            reverse=True,
        ):
            if maximum_height - height > 1.0:
                continue
            if any(
                abs(horizontal - selected) <= 1.0
                for selected in selected_horizontal_positions
            ):
                continue
            shoulder_groups.add(seam_name)
            selected_horizontal_positions.append(horizontal)
    return shoulder_groups


def build_anatomical_sewing_anchors(
    named_links: list[tuple[str, int, int]],
    vertex_owners: list[str],
    panel_vertices_cm: np.ndarray,
    initial_vertices_cm: np.ndarray,
) -> tuple[list[SewingAnchor], set[str]]:
    """Create shared-height shoulder supports plus one support per sleeve half."""
    if initial_vertices_cm.shape != (len(vertex_owners), 3):
        raise ValueError("Initial garment vertices and panel ownership must align.")
    shoulder_seams = identify_shoulder_seam_groups(
        named_links,
        vertex_owners,
        panel_vertices_cm,
    )
    anchors: list[SewingAnchor] = []
    anchored_vertices: set[int] = set()
    grouped = group_named_seam_links(named_links)
    for seam_name in sorted(shoulder_seams):
        for _, first, second in grouped[seam_name]:
            first_height = float(initial_vertices_cm[first, 1])
            second_height = float(initial_vertices_cm[second, 1])
            target_height = min(first_height, second_height)
            for vertex_index, partner_index, initial_height in (
                (first, second, first_height),
                (second, first, second_height),
            ):
                if vertex_index in anchored_vertices:
                    continue
                anchors.append(
                    SewingAnchor(
                        panel_name=vertex_owners[vertex_index],
                        vertex_index=vertex_index,
                        target_height_cm=target_height,
                        initial_height_cm=initial_height,
                        source=seam_name,
                        partner_panel_name=vertex_owners[partner_index],
                    )
                )
                anchored_vertices.add(vertex_index)

    panel_indices: dict[str, list[int]] = {}
    for vertex_index, owner in enumerate(vertex_owners):
        if "sleeve" in owner:
            panel_indices.setdefault(owner, []).append(vertex_index)
    for panel_name, indices in sorted(panel_indices.items()):
        unanchored = [index for index in indices if index not in anchored_vertices]
        if not unanchored:
            continue
        vertex_index = max(
            unanchored,
            key=lambda index: float(initial_vertices_cm[index, 1]),
        )
        height_cm = float(initial_vertices_cm[vertex_index, 1])
        anchors.append(
            SewingAnchor(
                panel_name=panel_name,
                vertex_index=vertex_index,
                target_height_cm=height_cm,
                initial_height_cm=height_cm,
                source="sleeve_vertical_support",
            )
        )
        anchored_vertices.add(vertex_index)
    return anchors, shoulder_seams


def classify_seam_assembly_phases(
    named_links: list[tuple[str, int, int]],
    vertex_owners: list[str],
    panel_vertices_cm: np.ndarray,
) -> np.ndarray:
    """Order construction seams, finishing joins, shoulders, then sleeve caps.

    Closing shoulders before the side seams can pull detached side panels over
    the outside of an A-pose arm. Once body collision is active, the arm becomes
    trapped inside the cloth and the closing side seam lifts the bodice hem.
    Closing the long side seams first establishes the torso shell and leaves the
    short shoulder seams to close around the existing armhole opening.
    """
    grouped = group_named_seam_links(named_links)
    shoulder_seams = identify_shoulder_seam_groups(
        named_links,
        vertex_owners,
        panel_vertices_cm,
    )
    phases = np.empty(len(named_links), dtype=np.int32)
    for seam_name, links in grouped.items():
        panel_names = {
            vertex_owners[vertex]
            for _, first, second in links
            for vertex in (first, second)
        }
        all_front = all("front" in panel for panel in panel_names)
        all_back = all("back" in panel for panel in panel_names)
        all_sleeve = all("sleeve" in panel for panel in panel_names)
        has_sleeve = any("sleeve" in panel for panel in panel_names)
        has_finishing = any(
            token in panel
            for panel in panel_names
            for token in ("cuff", "band")
        )
        sleeve_to_finishing = has_sleeve and has_finishing
        torso_to_sleeve = has_sleeve and not all_sleeve and not has_finishing
        if all_sleeve:
            phase = 0
        elif sleeve_to_finishing:
            # Close each sleeve and its finishing strip before asking the cap
            # to cross the armhole. Treating a cuff join as a sleeve cap made
            # both ends of the sleeve close simultaneously in the final phase,
            # which left the narrow finishing strips visibly open and twisted.
            phase = 1
        elif torso_to_sleeve:
            phase = 3
        elif all_front or all_back:
            phase = 0
        elif seam_name in shoulder_seams:
            phase = 2
        else:
            phase = 1
        for link_index, _, _ in links:
            phases[link_index] = phase
    return phases


def build_components(vertex_count: int, links: Iterable[tuple[int, int]]) -> tuple[tuple[int, ...], ...]:
    parent = list(range(vertex_count))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(first: int, second: int) -> None:
        root_first = find(first)
        root_second = find(second)
        if root_first == root_second:
            return
        if root_first < root_second:
            parent[root_second] = root_first
        else:
            parent[root_first] = root_second

    for first, second in links:
        if first < 0 or first >= vertex_count or second < 0 or second >= vertex_count:
            raise ValueError(f"Seam link is out of range: {(first, second)}")
        union(first, second)

    grouped: dict[int, list[int]] = {}
    for vertex in range(vertex_count):
        grouped.setdefault(find(vertex), []).append(vertex)
    return tuple(tuple(group) for group in sorted(grouped.values(), key=lambda values: values[0]))


def component_topology_ids(
    vertex_count: int,
    components: tuple[tuple[int, ...], ...],
) -> np.ndarray:
    topology_ids = np.full(vertex_count, -1, dtype=np.int32)
    for component_index, component in enumerate(components):
        topology_ids[np.asarray(component, dtype=np.int32)] = component_index
    if np.any(topology_ids < 0):
        raise ValueError("Every surface vertex must belong to one seam-topology component.")
    return topology_ids


def weld_surface(
    vertices: np.ndarray,
    faces: np.ndarray,
    seam_links: list[tuple[int, int]],
) -> WeldedSurface:
    source_vertices = np.asarray(vertices, dtype=np.float64)
    source_faces = np.asarray(faces, dtype=np.int32)
    components = build_components(len(source_vertices), seam_links)
    old_to_new = np.empty(len(source_vertices), dtype=np.int32)
    welded_vertices = np.empty((len(components), 3), dtype=np.float64)
    for welded_index, component in enumerate(components):
        old_to_new[np.asarray(component, dtype=np.int32)] = welded_index
        welded_vertices[welded_index] = source_vertices[np.asarray(component)].mean(axis=0)
    welded_faces = old_to_new[source_faces]
    degenerate = (
        (welded_faces[:, 0] == welded_faces[:, 1])
        | (welded_faces[:, 1] == welded_faces[:, 2])
        | (welded_faces[:, 2] == welded_faces[:, 0])
    )
    if np.any(degenerate):
        indices = np.flatnonzero(degenerate)[:10].tolist()
        raise ValueError(f"Seam welding produced degenerate faces: {indices}")
    return WeldedSurface(
        vertices=welded_vertices,
        faces=welded_faces,
        old_to_new=old_to_new,
        components=components,
    )


def expand_welded_positions(welded_positions: np.ndarray, old_to_new: np.ndarray) -> np.ndarray:
    positions = np.asarray(welded_positions, dtype=np.float64)
    mapping = np.asarray(old_to_new, dtype=np.int32)
    if mapping.min() < 0 or mapping.max() >= len(positions):
        raise ValueError("Weld mapping references an out-of-range physical vertex.")
    return positions[mapping]


def surface_edges(faces: np.ndarray) -> np.ndarray:
    """Return each undirected triangle edge exactly once in stable order."""
    triangle_faces = np.asarray(faces, dtype=np.int32)
    if triangle_faces.ndim != 2 or triangle_faces.shape[1] != 3:
        raise ValueError("Surface faces must be a triangle matrix.")
    edges = np.concatenate(
        (
            triangle_faces[:, [0, 1]],
            triangle_faces[:, [1, 2]],
            triangle_faces[:, [2, 0]],
        ),
        axis=0,
    )
    edges.sort(axis=1)
    return np.unique(edges, axis=0)


def build_vertex_edge_adjacency(
    vertex_count: int,
    edges: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Build stable CSR adjacency from vertices to incident surface edges."""
    if vertex_count <= 0:
        raise ValueError("Vertex count must be positive.")
    edge_indices = np.asarray(edges, dtype=np.int32)
    if edge_indices.ndim != 2 or edge_indices.shape[1] != 2:
        raise ValueError("Surface edges must be an edge matrix.")
    if len(edge_indices) and (
        edge_indices.min() < 0 or edge_indices.max() >= vertex_count
    ):
        raise ValueError("Surface edge references an out-of-range vertex.")

    counts = np.zeros(vertex_count, dtype=np.int32)
    if len(edge_indices):
        np.add.at(counts, edge_indices[:, 0], 1)
        np.add.at(counts, edge_indices[:, 1], 1)
    offsets = np.zeros(vertex_count + 1, dtype=np.int32)
    offsets[1:] = np.cumsum(counts, dtype=np.int32)
    incident_edges = np.empty(int(offsets[-1]), dtype=np.int32)
    cursors = offsets[:-1].copy()
    for edge_index, (first, second) in enumerate(edge_indices):
        incident_edges[cursors[first]] = edge_index
        cursors[first] += 1
        incident_edges[cursors[second]] = edge_index
        cursors[second] += 1
    return offsets, incident_edges


def project_outside_body(
    positions_m: np.ndarray,
    body_vertices_m: np.ndarray,
    body_faces: np.ndarray,
    clearance_m: float,
) -> tuple[np.ndarray, dict[str, float | int]]:
    if clearance_m <= 0.0:
        raise ValueError("Body clearance must be positive.")
    positions = np.asarray(positions_m, dtype=np.float64)
    body = trimesh.Trimesh(
        vertices=np.asarray(body_vertices_m, dtype=np.float64),
        faces=np.asarray(body_faces, dtype=np.int32),
        process=False,
    )
    if not body.is_watertight:
        raise ValueError("Body-clearance projection requires a watertight avatar mesh.")
    signed_distance = signed_distance_batched(body, positions)
    selected = signed_distance > -clearance_m
    projected = positions.copy()
    maximum_shift = 0.0
    if np.any(selected):
        selected_positions = positions[selected]
        closest, distance, face_index = closest_point_batched(body, selected_positions)
        inside = signed_distance[selected] >= 0.0
        direction = selected_positions - closest
        direction[inside] *= -1.0
        lengths = np.linalg.norm(direction, axis=1)
        zero_length = lengths <= 1.0e-12
        if np.any(zero_length):
            direction[zero_length] = body.face_normals[face_index[zero_length]]
            lengths[zero_length] = 1.0
        direction /= lengths[:, np.newaxis]
        targets = closest + direction * clearance_m
        shifts = np.linalg.norm(targets - selected_positions, axis=1)
        maximum_shift = float(np.max(shifts)) if len(shifts) else 0.0
        projected[selected] = targets
    final_signed_distance = signed_distance.copy()
    if np.any(selected):
        final_signed_distance[selected] = signed_distance_batched(
            body,
            projected[selected],
        )
    return projected, {
        "projected_vertex_count": int(np.count_nonzero(selected)),
        "initial_minimum_signed_clearance_cm": float(-np.max(signed_distance) * 100.0),
        "final_minimum_signed_clearance_cm": float(-np.max(final_signed_distance) * 100.0),
        "maximum_projection_shift_cm": maximum_shift * 100.0,
    }


def signed_distance_batched(
    body: trimesh.Trimesh,
    positions: np.ndarray,
    batch_size: int = 2048,
) -> np.ndarray:
    positions = np.asarray(positions, dtype=np.float64)
    result = np.empty(len(positions), dtype=np.float64)
    for start in range(0, len(positions), batch_size):
        end = min(start + batch_size, len(positions))
        result[start:end] = trimesh.proximity.signed_distance(body, positions[start:end])
    return result


def closest_point_batched(
    body: trimesh.Trimesh,
    positions: np.ndarray,
    batch_size: int = 2048,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    positions = np.asarray(positions, dtype=np.float64)
    closest = np.empty_like(positions)
    distance = np.empty(len(positions), dtype=np.float64)
    face_index = np.empty(len(positions), dtype=np.int64)
    for start in range(0, len(positions), batch_size):
        end = min(start + batch_size, len(positions))
        batch_closest, batch_distance, batch_face_index = trimesh.proximity.closest_point(
            body,
            positions[start:end],
        )
        closest[start:end] = batch_closest
        distance[start:end] = batch_distance
        face_index[start:end] = batch_face_index
    return closest, distance, face_index


def unique_edges(faces: np.ndarray) -> np.ndarray:
    triangles = np.asarray(faces, dtype=np.int32)
    edges = np.concatenate(
        [triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]],
        axis=0,
    )
    edges.sort(axis=1)
    return np.unique(edges, axis=0)


def orient_material_triangles(
    faces: np.ndarray,
    texture_faces: np.ndarray,
    texture_vertices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, int]:
    oriented_faces = np.asarray(faces, dtype=np.int32).copy()
    oriented_texture_faces = np.asarray(texture_faces, dtype=np.int32).copy()
    texture_positions = np.asarray(texture_vertices, dtype=np.float64)
    first = texture_positions[oriented_texture_faces[:, 0]]
    second = texture_positions[oriented_texture_faces[:, 1]]
    third = texture_positions[oriented_texture_faces[:, 2]]
    signed_double_area = (
        (second[:, 0] - first[:, 0]) * (third[:, 1] - first[:, 1])
        - (second[:, 1] - first[:, 1]) * (third[:, 0] - first[:, 0])
    )
    if np.any(np.abs(signed_double_area) <= 1.0e-12):
        indices = np.flatnonzero(np.abs(signed_double_area) <= 1.0e-12)[:10].tolist()
        raise ValueError(f"Material surface contains degenerate 2D triangles: {indices}")
    reversed_indices = np.flatnonzero(signed_double_area < 0.0)
    if len(reversed_indices):
        oriented_faces[reversed_indices, 1:3] = oriented_faces[reversed_indices, 2:0:-1]
        oriented_texture_faces[reversed_indices, 1:3] = oriented_texture_faces[
            reversed_indices, 2:0:-1
        ]
    return oriented_faces, oriented_texture_faces, len(reversed_indices)


def orient_spatial_panels_outward(
    faces: np.ndarray,
    vertices_m: np.ndarray,
    vertex_owners: list[str],
    body_vertices_m: np.ndarray,
    body_faces: np.ndarray,
) -> tuple[np.ndarray, dict[str, dict[str, object]], int]:
    """Orient each open cloth panel toward the measured body exterior.

    A shared positive winding in flat pattern coordinates does not guarantee a
    shared outward winding after independently arranged panels are mapped into
    three dimensions. This is especially important for side-front and
    side-back pieces, whose rigid placement can face the opposite direction
    from center panels while remaining geometrically valid.
    """

    oriented = np.asarray(faces, dtype=np.int32).copy()
    positions = np.asarray(vertices_m, dtype=np.float64)
    owners = np.asarray(vertex_owners, dtype=object)
    face_owners = owners[oriented[:, 0]]
    if np.any(owners[oriented[:, 1]] != face_owners) or np.any(
        owners[oriented[:, 2]] != face_owners
    ):
        raise ValueError("A material triangle crosses panel ownership boundaries.")

    body = trimesh.Trimesh(
        vertices=np.asarray(body_vertices_m, dtype=np.float64),
        faces=np.asarray(body_faces, dtype=np.int32),
        process=False,
    )
    body.fix_normals()
    triangle_vertices = positions[oriented]
    centroids = triangle_vertices.mean(axis=1)
    normals = np.cross(
        triangle_vertices[:, 1] - triangle_vertices[:, 0],
        triangle_vertices[:, 2] - triangle_vertices[:, 0],
    )
    magnitudes = np.linalg.norm(normals, axis=1)
    if np.any(magnitudes <= 1.0e-12):
        raise ValueError("Spatial material surface contains degenerate triangles.")
    normals /= magnitudes[:, None]
    closest, _, body_face_indices = closest_point_batched(body, centroids)
    body_normals = body.face_normals[body_face_indices]
    normal_alignment = np.einsum("ij,ij->i", normals, body_normals)
    radial = centroids - closest
    radial_magnitudes = np.linalg.norm(radial, axis=1)
    valid_radial = radial_magnitudes > 1.0e-9
    radial[valid_radial] /= radial_magnitudes[valid_radial, None]
    radial_alignment = np.einsum("ij,ij->i", normals, radial)

    report: dict[str, dict[str, object]] = {}
    flipped_triangle_count = 0
    for panel_name in sorted(set(face_owners.tolist())):
        panel_indices = np.flatnonzero(face_owners == panel_name)
        surface_score = float(np.median(normal_alignment[panel_indices]))
        radial_values = radial_alignment[panel_indices][valid_radial[panel_indices]]
        radial_score = (
            float(np.median(radial_values)) if len(radial_values) else 0.0
        )
        score = surface_score if abs(surface_score) >= 0.05 else radial_score
        flipped = score < 0.0
        if flipped:
            oriented[panel_indices, 1:3] = oriented[panel_indices, 2:0:-1]
            flipped_triangle_count += len(panel_indices)
        report[panel_name] = {
            "triangle_count": int(len(panel_indices)),
            "body_normal_alignment_median": surface_score,
            "radial_alignment_median": radial_score,
            "flipped": flipped,
        }
    return oriented, report, flipped_triangle_count


def load_rest_lengths(path: Path, vertex_count: int) -> dict[tuple[int, int], float]:
    with path.open("rb") as stream:
        raw = pickle.load(stream)
    result: dict[tuple[int, int], float] = {}
    for raw_pair, raw_length in raw.items():
        first, second = int(raw_pair[0]), int(raw_pair[1])
        if first < 0 or second < 0 or first >= vertex_count or second >= vertex_count:
            raise ValueError(f"Material rest edge is out of range: {(first, second)}")
        length = float(raw_length)
        if not np.isfinite(length) or length <= 0.0:
            raise ValueError(f"Material rest edge has invalid length: {raw_pair} = {length}")
        result[(first, second)] = length
    return result


def evaluate_strain(
    expanded_positions_cm: np.ndarray,
    rest_lengths_cm: dict[tuple[int, int], float],
    high_strain_threshold_ratio: float = 0.40,
) -> dict[str, object]:
    if high_strain_threshold_ratio <= 0.0:
        raise ValueError("High-strain threshold must be positive.")
    ordered = list(rest_lengths_cm.items())
    first = np.asarray([pair[0] for pair, _ in ordered], dtype=np.int32)
    second = np.asarray([pair[1] for pair, _ in ordered], dtype=np.int32)
    rest = np.asarray([length for _, length in ordered], dtype=np.float64)
    current = np.linalg.norm(expanded_positions_cm[first] - expanded_positions_cm[second], axis=1)
    strain = np.abs(current / rest - 1.0)
    maximum_index = int(np.argmax(strain))
    high_strain_edge_count = int(np.count_nonzero(strain > high_strain_threshold_ratio))
    return {
        "evaluated_edge_count": len(strain),
        "maximum_edge_strain_ratio": float(strain[maximum_index]),
        "ninety_fifth_percentile_edge_strain_ratio": float(np.percentile(strain, 95.0)),
        "ninety_ninth_point_ninth_percentile_edge_strain_ratio": float(
            np.percentile(strain, 99.9)
        ),
        "ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio": float(
            np.percentile(strain, 99.99)
        ),
        "high_strain_edge_threshold_ratio": high_strain_threshold_ratio,
        "high_strain_edge_count": high_strain_edge_count,
        "high_strain_edge_fraction": high_strain_edge_count / len(strain),
        "maximum_strain_edge_vertices": list(ordered[maximum_index][0]),
    }


def evaluate_style3d_acceptance(
    *,
    finite_positions: bool,
    static_equilibrium_reached: bool,
    body_collisions: int,
    self_collisions: int,
    seam_metrics: dict[str, object],
    strain_metrics: dict[str, object],
    max_seam_separation_cm: float,
    max_p95_edge_strain: float,
    max_p999_edge_strain: float,
    max_p9999_edge_strain: float,
    max_high_strain_edge_fraction: float,
) -> tuple[bool, list[str]]:
    accepted, reasons = evaluate_acceptance(
        finite_positions=finite_positions,
        equilibrium_gate_evaluated=True,
        static_equilibrium_reached=static_equilibrium_reached,
        edge_contact_buffer_saturated=False,
        maximum_observed_edge_contacts=0,
        edge_contact_capacity=0,
        body_collisions=body_collisions,
        self_collisions=self_collisions,
        seam_link_count=int(seam_metrics["seam_link_count"]),
        maximum_seam_separation_cm=seam_metrics["maximum_seam_separation_cm"],
        max_seam_separation_cm=max_seam_separation_cm,
        maximum_edge_strain_ratio=float(strain_metrics["maximum_edge_strain_ratio"]),
        ninety_fifth_percentile_edge_strain_ratio=float(
            strain_metrics["ninety_fifth_percentile_edge_strain_ratio"]
        ),
        ninety_ninth_point_ninth_percentile_edge_strain_ratio=float(
            strain_metrics["ninety_ninth_point_ninth_percentile_edge_strain_ratio"]
        ),
        max_body_collisions=0,
        max_self_collisions=0,
        max_edge_strain_ratio=float("inf"),
        max_ninety_fifth_percentile_edge_strain_ratio=max_p95_edge_strain,
        max_ninety_ninth_point_ninth_percentile_edge_strain_ratio=max_p999_edge_strain,
    )
    p9999 = float(
        strain_metrics["ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio"]
    )
    high_fraction = float(strain_metrics["high_strain_edge_fraction"])
    if p9999 > max_p9999_edge_strain:
        reasons.append(
            "99.99th-percentile edge strain "
            f"{p9999:.3f} exceeds limit {max_p9999_edge_strain:.3f}"
        )
    if high_fraction > max_high_strain_edge_fraction:
        reasons.append(
            "high-strain edge fraction "
            f"{high_fraction:.6f} exceeds limit {max_high_strain_edge_fraction:.6f}"
        )
    return not reasons, reasons


def evaluate_seams(
    expanded_positions_cm: np.ndarray,
    seam_links: list[tuple[int, int]],
) -> dict[str, float | int | list[int] | None]:
    if not seam_links:
        return {
            "seam_link_count": 0,
            "maximum_seam_separation_cm": None,
            "mean_seam_separation_cm": None,
            "ninety_fifth_percentile_seam_separation_cm": None,
            "maximum_seam_separation_edge_vertices": None,
        }
    first = np.asarray([pair[0] for pair in seam_links], dtype=np.int32)
    second = np.asarray([pair[1] for pair in seam_links], dtype=np.int32)
    distances = np.linalg.norm(
        expanded_positions_cm[first] - expanded_positions_cm[second], axis=1
    )
    maximum_index = int(np.argmax(distances))
    return {
        "seam_link_count": len(seam_links),
        "maximum_seam_separation_cm": float(distances[maximum_index]),
        "mean_seam_separation_cm": float(np.mean(distances)),
        "ninety_fifth_percentile_seam_separation_cm": float(
            np.percentile(distances, 95.0)
        ),
        "maximum_seam_separation_edge_vertices": list(seam_links[maximum_index]),
    }


@wp.func
def component_min(first: wp.vec3, second: wp.vec3) -> wp.vec3:
    return wp.vec3(
        wp.min(first[0], second[0]),
        wp.min(first[1], second[1]),
        wp.min(first[2], second[2]),
    )


@wp.func
def component_max(first: wp.vec3, second: wp.vec3) -> wp.vec3:
    return wp.vec3(
        wp.max(first[0], second[0]),
        wp.max(first[1], second[1]),
        wp.max(first[2], second[2]),
    )


@wp.kernel
def enforce_body_clearance_kernel(
    positions: wp.array(dtype=wp.vec3),
    velocities: wp.array(dtype=wp.vec3),
    body_mesh_id: wp.uint64,
    clearance: float,
    correction_count: wp.array(dtype=int),
):
    vertex_index = wp.tid()
    position = positions[vertex_index]
    query = wp.mesh_query_point_sign_winding_number(body_mesh_id, position, 10.0)
    if not query.result:
        return
    closest = wp.mesh_eval_position(body_mesh_id, query.face, query.u, query.v)
    offset = position - closest
    distance = wp.length(offset) * query.sign
    error = distance - clearance
    if error >= 0.0:
        return
    outward = wp.normalize(offset) * query.sign
    corrected = position - outward * error
    velocity = velocities[vertex_index]
    inward_speed = wp.dot(velocity, outward)
    if inward_speed < 0.0:
        velocity = velocity - outward * inward_speed
    positions[vertex_index] = corrected
    velocities[vertex_index] = velocity
    wp.atomic_add(correction_count, 0, 1)


@wp.kernel
def compute_body_edge_clearance_corrections_kernel(
    positions: wp.array(dtype=wp.vec3),
    edge_indices: wp.array2d(dtype=int),
    body_mesh_id: wp.uint64,
    clearance: float,
    edge_corrections: wp.array(dtype=wp.vec3),
    correction_count: wp.array(dtype=int),
):
    """Find body-crossing cloth edges and calculate one translation per edge."""
    edge_index = wp.tid()
    first_index = edge_indices[edge_index, 0]
    second_index = edge_indices[edge_index, 1]
    origin = positions[first_index]
    edge_vector = positions[second_index] - origin
    edge_length = wp.length(edge_vector)
    edge_corrections[edge_index] = wp.vec3(0.0, 0.0, 0.0)
    if edge_length <= 1.0e-12:
        return

    ray_direction = wp.normalize(edge_vector)
    hit_distance = float(0.0)
    hit_u = float(0.0)
    hit_v = float(0.0)
    hit_sign = float(0.0)
    hit_normal = wp.vec3()
    hit_face = int(0)
    if not wp.mesh_query_ray(
        body_mesh_id,
        origin,
        ray_direction,
        edge_length,
        hit_distance,
        hit_u,
        hit_v,
        hit_sign,
        hit_normal,
        hit_face,
    ):
        return

    outward_hit_normal = hit_normal
    if wp.dot(outward_hit_normal, ray_direction) > 0.0:
        outward_hit_normal = -outward_hit_normal
    strongest_correction = outward_hit_normal * clearance
    strongest_squared_length = wp.dot(strongest_correction, strongest_correction)

    # Seven interior samples bound the unsampled span to one eighth of an edge.
    # At the supported 1 cm material resolution this is a 1.25 mm rest span.
    for sample_index in range(7):
        sample_fraction = float(sample_index + 1) / 8.0
        sample_position = origin + edge_vector * sample_fraction
        query = wp.mesh_query_point_sign_winding_number(
            body_mesh_id,
            sample_position,
            10.0,
        )
        if not query.result:
            continue
        closest = wp.mesh_eval_position(body_mesh_id, query.face, query.u, query.v)
        offset = sample_position - closest
        signed_distance = wp.length(offset) * query.sign
        error = signed_distance - clearance
        if error >= 0.0:
            continue
        outward = outward_hit_normal
        if wp.length(offset) > 1.0e-12:
            outward = wp.normalize(offset) * query.sign
        correction = outward * (-error)
        squared_length = wp.dot(correction, correction)
        if squared_length > strongest_squared_length:
            strongest_correction = correction
            strongest_squared_length = squared_length

    edge_corrections[edge_index] = strongest_correction
    wp.atomic_add(correction_count, 0, 1)


@wp.kernel
def apply_body_edge_clearance_corrections_kernel(
    positions: wp.array(dtype=wp.vec3),
    velocities: wp.array(dtype=wp.vec3),
    vertex_edge_offsets: wp.array(dtype=int),
    incident_edge_indices: wp.array(dtype=int),
    edge_corrections: wp.array(dtype=wp.vec3),
    corrected_positions: wp.array(dtype=wp.vec3),
    corrected_velocities: wp.array(dtype=wp.vec3),
):
    """Apply the strongest incident edge correction without concurrent writes."""
    vertex_index = wp.tid()
    strongest_correction = wp.vec3(0.0, 0.0, 0.0)
    strongest_squared_length = float(0.0)
    start = vertex_edge_offsets[vertex_index]
    end = vertex_edge_offsets[vertex_index + 1]
    for adjacency_index in range(start, end):
        correction = edge_corrections[incident_edge_indices[adjacency_index]]
        squared_length = wp.dot(correction, correction)
        if squared_length > strongest_squared_length:
            strongest_correction = correction
            strongest_squared_length = squared_length

    position = positions[vertex_index]
    velocity = velocities[vertex_index]
    if strongest_squared_length > 0.0:
        position = position + strongest_correction
        outward = wp.normalize(strongest_correction)
        inward_speed = wp.dot(velocity, outward)
        if inward_speed < 0.0:
            velocity = velocity - outward * inward_speed
    corrected_positions[vertex_index] = position
    corrected_velocities[vertex_index] = velocity


@wp.kernel
def enforce_vertical_sewing_anchors_kernel(
    positions: wp.array(dtype=wp.vec3),
    velocities: wp.array(dtype=wp.vec3),
    anchor_indices: wp.array(dtype=int),
    anchor_heights: wp.array(dtype=float),
    strength: float,
):
    anchor_index = wp.tid()
    vertex_index = anchor_indices[anchor_index]
    position = positions[vertex_index]
    velocity = velocities[vertex_index]
    positions[vertex_index] = wp.vec3(
        position[0],
        position[1] + (anchor_heights[anchor_index] - position[1]) * strength,
        position[2],
    )
    velocities[vertex_index] = wp.vec3(
        velocity[0],
        velocity[1] * (1.0 - strength),
        velocity[2],
    )


@wp.kernel
def project_seam_components_kernel(
    positions: wp.array(dtype=wp.vec3),
    velocities: wp.array(dtype=wp.vec3),
    component_offsets: wp.array(dtype=int),
    component_members: wp.array(dtype=int),
):
    component_index = wp.tid()
    start = component_offsets[component_index]
    end = component_offsets[component_index + 1]
    member_count = end - start
    if member_count <= 1:
        return
    mean_position = wp.vec3(0.0, 0.0, 0.0)
    mean_velocity = wp.vec3(0.0, 0.0, 0.0)
    for member_offset in range(start, end):
        vertex_index = component_members[member_offset]
        mean_position += positions[vertex_index]
        mean_velocity += velocities[vertex_index]
    inverse_count = 1.0 / float(member_count)
    mean_position *= inverse_count
    mean_velocity *= inverse_count
    for member_offset in range(start, end):
        vertex_index = component_members[member_offset]
        positions[vertex_index] = mean_position
        velocities[vertex_index] = mean_velocity


@wp.kernel
def count_self_edge_intersections_kernel(
    edge_indices: wp.array2d(dtype=int),
    triangle_indices: wp.array2d(dtype=int),
    topology_ids: wp.array(dtype=int),
    cloth_mesh_id: wp.uint64,
    intersection_face_indices: wp.array(dtype=int),
):
    edge_index = wp.tid()
    first_index = edge_indices[edge_index, 0]
    second_index = edge_indices[edge_index, 1]
    first_topology = topology_ids[first_index]
    second_topology = topology_ids[second_index]
    cloth_mesh = wp.mesh_get(cloth_mesh_id)
    origin = cloth_mesh.points[first_index]
    endpoint = cloth_mesh.points[second_index]
    lower = component_min(origin, endpoint)
    upper = component_max(origin, endpoint)
    query = wp.mesh_query_aabb(cloth_mesh_id, lower, upper)
    face_index = int(0)
    while wp.mesh_query_aabb_next(query, face_index):
        candidate_first = triangle_indices[face_index, 0]
        candidate_second = triangle_indices[face_index, 1]
        candidate_third = triangle_indices[face_index, 2]
        if (
            topology_ids[candidate_first] == first_topology
            or topology_ids[candidate_first] == second_topology
            or topology_ids[candidate_second] == first_topology
            or topology_ids[candidate_second] == second_topology
            or topology_ids[candidate_third] == first_topology
            or topology_ids[candidate_third] == second_topology
        ):
            continue
        first = cloth_mesh.points[candidate_first]
        second = cloth_mesh.points[candidate_second]
        third = cloth_mesh.points[candidate_third]
        direction = endpoint - origin
        first_edge = second - first
        second_edge = third - first
        cross_direction = wp.cross(direction, second_edge)
        determinant = wp.dot(first_edge, cross_direction)
        if wp.abs(determinant) <= 1.0e-10:
            continue
        inverse_determinant = 1.0 / determinant
        offset = origin - first
        barycentric_u = wp.dot(offset, cross_direction) * inverse_determinant
        if barycentric_u < 0.0 or barycentric_u > 1.0:
            continue
        cross_offset = wp.cross(offset, first_edge)
        barycentric_v = wp.dot(direction, cross_offset) * inverse_determinant
        if barycentric_v < 0.0 or barycentric_u + barycentric_v > 1.0:
            continue
        segment_t = wp.dot(second_edge, cross_offset) * inverse_determinant
        if segment_t > 1.0e-6 and segment_t < 1.0 - 1.0e-6:
            intersection_face_indices[edge_index] = face_index
            return


@wp.kernel
def count_body_edge_intersections_kernel(
    cloth_positions: wp.array(dtype=wp.vec3),
    edge_indices: wp.array2d(dtype=int),
    body_mesh_id: wp.uint64,
    intersection_flags: wp.array(dtype=int),
):
    edge_index = wp.tid()
    origin = cloth_positions[edge_indices[edge_index, 0]]
    direction = cloth_positions[edge_indices[edge_index, 1]] - origin
    maximum_distance = wp.length(direction)
    if maximum_distance <= 1.0e-12:
        return
    distance = float(0.0)
    face_index = int(0)
    face_u = float(0.0)
    face_v = float(0.0)
    sign = float(0.0)
    normal = wp.vec3()
    if wp.mesh_query_ray(
        body_mesh_id,
        origin,
        wp.normalize(direction),
        maximum_distance,
        distance,
        face_u,
        face_v,
        sign,
        normal,
        face_index,
    ):
        intersection_flags[edge_index] = 1


def find_intersection_edges(
    cloth_positions_m: np.ndarray,
    cloth_faces: np.ndarray,
    body_positions_m: np.ndarray,
    body_faces: np.ndarray,
    device: str,
    collision_topology_ids: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    topology_ids = (
        np.arange(len(cloth_positions_m), dtype=np.int32)
        if collision_topology_ids is None
        else np.asarray(collision_topology_ids, dtype=np.int32)
    )
    if topology_ids.shape != (len(cloth_positions_m),):
        raise ValueError("Collision topology must contain one id per cloth vertex.")
    cloth_points = wp.array(cloth_positions_m.astype(np.float32), dtype=wp.vec3, device=device)
    cloth_indices = wp.array(cloth_faces.reshape(-1), dtype=int, device=device)
    body_points = wp.array(body_positions_m.astype(np.float32), dtype=wp.vec3, device=device)
    body_indices = wp.array(body_faces.reshape(-1), dtype=int, device=device)
    cloth_mesh = wp.Mesh(cloth_points, cloth_indices)
    body_mesh = wp.Mesh(body_points, body_indices)
    face_array = wp.array(cloth_faces, dtype=int, device=device)
    topology_array = wp.array(topology_ids, dtype=int, device=device)
    edges = surface_edges(cloth_faces)
    edge_array = wp.array(edges, dtype=int, device=device)
    self_face_indices = wp.full(len(edges), -1, dtype=int, device=device)
    body_flags = wp.zeros(len(edges), dtype=int, device=device)
    wp.launch(
        count_self_edge_intersections_kernel,
        dim=len(edges),
        inputs=[edge_array, face_array, topology_array, cloth_mesh.id],
        outputs=[self_face_indices],
        device=device,
    )
    wp.launch(
        count_body_edge_intersections_kernel,
        dim=len(edges),
        inputs=[cloth_points, edge_array, body_mesh.id],
        outputs=[body_flags],
        device=device,
    )
    wp.synchronize_device(device)
    body_edges = edges[np.flatnonzero(body_flags.numpy())]
    self_edges = edges[np.flatnonzero(self_face_indices.numpy() >= 0)]
    return body_edges, self_edges


def find_self_intersection_edge_face_pairs(
    cloth_positions_m: np.ndarray,
    cloth_faces: np.ndarray,
    device: str,
    collision_topology_ids: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return each intersecting cloth edge and the first face it crosses."""
    topology_ids = (
        np.arange(len(cloth_positions_m), dtype=np.int32)
        if collision_topology_ids is None
        else np.asarray(collision_topology_ids, dtype=np.int32)
    )
    if topology_ids.shape != (len(cloth_positions_m),):
        raise ValueError("Collision topology must contain one id per cloth vertex.")
    cloth_points = wp.array(
        cloth_positions_m.astype(np.float32), dtype=wp.vec3, device=device
    )
    cloth_indices = wp.array(cloth_faces.reshape(-1), dtype=int, device=device)
    cloth_mesh = wp.Mesh(cloth_points, cloth_indices)
    face_array = wp.array(cloth_faces, dtype=int, device=device)
    topology_array = wp.array(topology_ids, dtype=int, device=device)
    edges = surface_edges(cloth_faces)
    edge_array = wp.array(edges, dtype=int, device=device)
    hit_faces = wp.full(len(edges), -1, dtype=int, device=device)
    wp.launch(
        count_self_edge_intersections_kernel,
        dim=len(edges),
        inputs=[edge_array, face_array, topology_array, cloth_mesh.id],
        outputs=[hit_faces],
        device=device,
    )
    wp.synchronize_device(device)
    hit_face_indices = hit_faces.numpy()
    intersecting = np.flatnonzero(hit_face_indices >= 0)
    return edges[intersecting], hit_face_indices[intersecting]


def count_intersections(
    cloth_positions_m: np.ndarray,
    cloth_faces: np.ndarray,
    body_positions_m: np.ndarray,
    body_faces: np.ndarray,
    device: str,
    collision_topology_ids: np.ndarray | None = None,
) -> tuple[int, int]:
    body_edges, self_edges = find_intersection_edges(
        cloth_positions_m,
        cloth_faces,
        body_positions_m,
        body_faces,
        device,
        collision_topology_ids,
    )
    return len(body_edges), len(self_edges)


def write_expanded_obj(
    template_path: Path,
    output_path: Path,
    vertices_cm: np.ndarray,
    faces: np.ndarray | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    vertex_index = 0
    face_index = 0
    for raw_line in template_path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("v "):
            vertex = vertices_cm[vertex_index]
            lines.append(f"v {vertex[0]:.9f} {vertex[1]:.9f} {vertex[2]:.9f}")
            vertex_index += 1
        elif raw_line.startswith("f ") and faces is not None:
            tokens = raw_line.split()[1:]
            source_indices = [int(token.split("/")[0]) - 1 for token in tokens]
            if len(tokens) != 3 or len(set(source_indices)) != 3:
                raise ValueError("Expanded OBJ template must contain triangular faces.")
            token_by_vertex = dict(zip(source_indices, tokens))
            target_indices = np.asarray(faces[face_index], dtype=np.int32).tolist()
            if set(target_indices) != set(source_indices):
                raise ValueError(
                    f"Expanded face {face_index} does not match its template vertices."
                )
            lines.append(
                "f " + " ".join(token_by_vertex[index] for index in target_indices)
            )
            face_index += 1
        else:
            lines.append(raw_line)
    if vertex_index != len(vertices_cm):
        raise ValueError(
            f"Template contains {vertex_index} vertices for {len(vertices_cm)} outputs."
        )
    if faces is not None and face_index != len(faces):
        raise ValueError(
            f"Template contains {face_index} faces for {len(faces)} outputs."
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_physical_obj(output_path: Path, vertices_cm: np.ndarray, faces: np.ndarray) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"v {vertex[0]:.9f} {vertex[1]:.9f} {vertex[2]:.9f}" for vertex in vertices_cm]
    lines.extend(
        f"f {face[0] + 1} {face[1] + 1} {face[2] + 1}" for face in faces
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_path(raw_value: str | Path) -> Path:
    return Path(raw_value).expanduser().resolve()


def source_paths(source_report_path: Path) -> dict[str, Path]:
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    physical_mesh = resolve_path(source_report["physical_mesh_path"])
    initial_mesh = resolve_path(source_report["output_mesh_path"])
    return {
        "physical_mesh": physical_mesh,
        "initial_mesh": initial_mesh,
        "segmentation": resolve_path(source_report["panel_ownership_path"]),
        "rest_lengths": resolve_path(source_report["rest_lengths_path"]),
        "panel_index_map": resolve_path(source_report["panel_index_map_path"]),
        "body_mesh": resolve_path(source_report["body_mesh_path"]),
    }


def load_material_coordinates(
    path: Path,
    expected_vertex_count: int,
    expected_faces: np.ndarray,
) -> np.ndarray:
    with np.load(path, allow_pickle=False) as archive:
        panel_vertices_cm = np.asarray(archive["panel_vertices_cm"], dtype=np.float64)
        panel_faces = np.asarray(archive["panel_faces"], dtype=np.int32)
    if panel_vertices_cm.shape != (expected_vertex_count, 2):
        raise ValueError(
            "Material-coordinate artifact does not match the render vertex count."
        )
    if not np.array_equal(panel_faces, expected_faces):
        raise ValueError("Material-coordinate artifact does not match the surface faces.")
    if not np.isfinite(panel_vertices_cm).all():
        raise ValueError("Material-coordinate artifact contains non-finite values.")
    return panel_vertices_cm


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", required=True, type=Path)
    parser.add_argument("--material-coordinates", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--initial-mesh",
        type=Path,
        help="Override the source report's rejected drape with a topology-identical starting surface.",
    )
    parser.add_argument(
        "--body-start-source",
        type=Path,
        help=(
            "Topology-identical raised-arm body used while sewing. The collider "
            "animates to the source report body after assembly."
        ),
    )
    parser.add_argument(
        "--body-start-radial-scale",
        type=float,
        help=(
            "Create a topology-identical narrow dressing body by scaling the "
            "target body's horizontal axes while preserving anatomical heights."
        ),
    )
    parser.add_argument("--body-animation-delay-frames", type=int, default=0)
    parser.add_argument("--body-animation-frames", type=int, default=0)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--frames", type=int, default=650)
    parser.add_argument("--minimum-frames", type=int, default=120)
    parser.add_argument("--substeps", type=int, default=10)
    parser.add_argument("--nonlinear-iterations", type=int, default=4)
    parser.add_argument("--linear-iterations", type=int, default=10)
    parser.add_argument("--static-consecutive-frames", type=int, default=15)
    parser.add_argument("--static-threshold-cm", type=float, default=0.01)
    parser.add_argument("--non-static-percent", type=float, default=5.0)
    parser.add_argument("--static-mean-threshold-cm", type=float, default=0.001)
    parser.add_argument("--static-p999-threshold-cm", type=float, default=0.03)
    parser.add_argument("--density-kg-m2", type=float, default=0.12)
    parser.add_argument("--weft-stiffness", type=float, default=400.0)
    parser.add_argument("--warp-stiffness", type=float, default=400.0)
    parser.add_argument("--shear-stiffness", type=float, default=40.0)
    parser.add_argument("--bend-weft", type=float, default=2.0e-5)
    parser.add_argument("--bend-warp", type=float, default=1.0e-5)
    parser.add_argument("--bend-bias", type=float, default=5.0e-6)
    parser.add_argument("--cloth-thickness-cm", type=float, default=0.034)
    parser.add_argument("--self-contact-thickness-cm", type=float, default=0.07)
    parser.add_argument("--body-contact-radius-cm", type=float, default=0.20)
    parser.add_argument("--body-contact-margin-cm", type=float, default=0.35)
    parser.add_argument("--body-contact-stiffness", type=float, default=100.0)
    parser.add_argument("--body-friction", type=float, default=0.45)
    parser.add_argument("--initial-body-clearance-cm", type=float, default=0.20)
    parser.add_argument("--hard-body-clearance-cm", type=float, default=0.0)
    parser.add_argument("--hard-body-edge-clearance-cm", type=float, default=0.10)
    parser.add_argument("--hard-body-edge-passes", type=int, default=2)
    parser.add_argument(
        "--hard-body-clearance-mode",
        choices=("continuous", "during-sewing"),
        default="continuous",
    )
    parser.add_argument(
        "--seam-topology-mode",
        choices=("welded-components", "explicit-progressive"),
        default="welded-components",
    )
    parser.add_argument("--seam-stiffness", type=float, default=400.0)
    parser.add_argument("--dart-seam-stiffness", type=float, default=4000.0)
    parser.add_argument("--seam-rest-length-cm", type=float, default=0.07)
    parser.add_argument("--velocity-retention-per-substep", type=float, default=1.0)
    parser.add_argument("--self-contact-vf-stiffness", type=float, default=0.5)
    parser.add_argument("--self-contact-ee-stiffness", type=float, default=0.1)
    parser.add_argument("--self-contact-ef-stiffness", type=float, default=1.0)
    parser.add_argument("--sewing-ramp-delay-frames", type=int, default=10)
    parser.add_argument("--sewing-ramp-frames", type=int, default=100)
    parser.add_argument("--sewing-anchor-release-frames", type=int, default=90)
    parser.add_argument("--sewing-settle-frames", type=int, default=120)
    parser.add_argument("--max-seam-separation-cm", type=float, default=0.25)
    parser.add_argument("--max-edge-strain", type=float, default=0.40)
    parser.add_argument("--max-p95-edge-strain", type=float, default=0.15)
    parser.add_argument("--max-p999-edge-strain", type=float, default=0.29)
    parser.add_argument("--max-p9999-edge-strain", type=float, default=0.55)
    parser.add_argument("--max-high-strain-edge-fraction", type=float, default=0.0005)
    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    positive_integer_fields = [
        "frames",
        "minimum_frames",
        "substeps",
        "nonlinear_iterations",
        "linear_iterations",
        "static_consecutive_frames",
    ]
    for field in positive_integer_fields:
        if getattr(args, field) <= 0:
            raise ValueError(f"--{field.replace('_', '-')} must be positive.")
    if args.minimum_frames > args.frames:
        raise ValueError("--minimum-frames cannot exceed --frames.")
    if args.static_threshold_cm <= 0.0:
        raise ValueError("--static-threshold-cm must be positive.")
    if args.static_mean_threshold_cm <= 0.0:
        raise ValueError("--static-mean-threshold-cm must be positive.")
    if args.static_p999_threshold_cm <= 0.0:
        raise ValueError("--static-p999-threshold-cm must be positive.")
    if args.hard_body_clearance_cm < 0.0:
        raise ValueError("--hard-body-clearance-cm cannot be negative.")
    if args.hard_body_edge_clearance_cm < 0.0:
        raise ValueError("--hard-body-edge-clearance-cm cannot be negative.")
    if args.hard_body_edge_passes < 0:
        raise ValueError("--hard-body-edge-passes cannot be negative.")
    if args.non_static_percent < 0.0 or args.non_static_percent > 100.0:
        raise ValueError("--non-static-percent must be between 0 and 100.")
    if args.max_high_strain_edge_fraction < 0.0 or args.max_high_strain_edge_fraction > 1.0:
        raise ValueError("--max-high-strain-edge-fraction must be between 0 and 1.")
    if args.seam_stiffness <= 0.0 or not np.isfinite(args.seam_stiffness):
        raise ValueError("--seam-stiffness must be finite and positive.")
    if args.dart_seam_stiffness <= 0.0 or not np.isfinite(args.dart_seam_stiffness):
        raise ValueError("--dart-seam-stiffness must be finite and positive.")
    if args.seam_rest_length_cm < 0.0 or not np.isfinite(args.seam_rest_length_cm):
        raise ValueError("--seam-rest-length-cm must be finite and non-negative.")
    if (
        args.velocity_retention_per_substep <= 0.0
        or args.velocity_retention_per_substep > 1.0
        or not np.isfinite(args.velocity_retention_per_substep)
    ):
        raise ValueError("--velocity-retention-per-substep must be in the interval (0, 1].")
    for field in (
        "self_contact_vf_stiffness",
        "self_contact_ee_stiffness",
        "self_contact_ef_stiffness",
    ):
        if getattr(args, field) < 0.0 or not np.isfinite(getattr(args, field)):
            raise ValueError(f"--{field.replace('_', '-')} must be finite and non-negative.")
    for field in (
        "sewing_ramp_delay_frames",
        "sewing_ramp_frames",
        "sewing_anchor_release_frames",
        "sewing_settle_frames",
        "body_animation_delay_frames",
        "body_animation_frames",
    ):
        if getattr(args, field) < 0:
            raise ValueError(f"--{field.replace('_', '-')} must be non-negative.")
    body_animation_requested = (
        args.body_start_source is not None
        or args.body_start_radial_scale is not None
    )
    if args.body_start_source is not None and args.body_start_radial_scale is not None:
        raise ValueError(
            "--body-start-source and --body-start-radial-scale are mutually exclusive."
        )
    if args.body_start_radial_scale is not None and not (
        np.isfinite(args.body_start_radial_scale)
        and 0.1 <= args.body_start_radial_scale < 1.0
    ):
        raise ValueError("--body-start-radial-scale must be between 0.1 and 1.0.")
    if body_animation_requested and args.body_animation_frames < 1:
        raise ValueError(
            "--body-animation-frames must be positive when body animation is used."
        )
    if not body_animation_requested and (
        args.body_animation_delay_frames > 0 or args.body_animation_frames > 0
    ):
        raise ValueError(
            "Body animation timing requires a body start source or radial scale."
        )
    if args.seam_topology_mode == "explicit-progressive":
        required_frames = (
            args.sewing_ramp_delay_frames
            + args.sewing_ramp_frames * 4
            + args.sewing_anchor_release_frames
            + args.sewing_settle_frames
        )
        if args.frames < required_frames:
            raise ValueError(
                "--frames must cover explicit sewing, anchor release, and settling; "
                f"need at least {required_frames}."
            )
    if body_animation_requested:
        required_animation_frames = (
            args.body_animation_delay_frames
            + args.body_animation_frames
            + args.sewing_anchor_release_frames
            + args.sewing_settle_frames
        )
        if args.frames < required_animation_frames:
            raise ValueError(
                "--frames must cover body animation and settling; need at least "
                f"{required_animation_frames}."
            )


def sewing_schedule_progress(frame: int, delay_frames: int, ramp_frames: int) -> float:
    if ramp_frames <= 0:
        return 1.0 if frame >= delay_frames else 0.0
    raw = float(np.clip((frame - delay_frames) / ramp_frames, 0.0, 1.0))
    return raw * raw * (3.0 - 2.0 * raw)


def sewing_anchor_strength(
    frame: int,
    sewing_delay_frames: int,
    sewing_ramp_frames: int,
    assembly_phase_count: int,
    release_frames: int,
    body_animation_end_frame: int | None = None,
) -> float:
    """Support anatomical height through sewing and body expansion, then release."""
    release_start_frame = sewing_delay_frames + sewing_ramp_frames * assembly_phase_count
    if body_animation_end_frame is not None:
        release_start_frame = max(release_start_frame, body_animation_end_frame)
    return 1.0 - sewing_schedule_progress(frame, release_start_frame, release_frames)


def run(args: argparse.Namespace) -> dict[str, object]:
    validate_arguments(args)
    source_report_path = resolve_path(args.source_report)
    material_coordinates_path = resolve_path(args.material_coordinates)
    output_dir = resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = source_paths(source_report_path)
    if args.initial_mesh is not None:
        inputs["initial_mesh"] = resolve_path(args.initial_mesh)
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))

    material_surface = load_obj_surface(inputs["physical_mesh"])
    initial_surface = load_obj_surface(inputs["initial_mesh"])
    if not np.array_equal(material_surface.faces, initial_surface.faces):
        raise ValueError("Initial drape does not match the material surface topology.")
    if len(material_surface.vertices) != len(initial_surface.vertices):
        raise ValueError("Initial drape does not match the material vertex count.")
    panel_vertices_cm = load_material_coordinates(
        material_coordinates_path,
        len(material_surface.vertices),
        material_surface.faces,
    )
    oriented_faces, oriented_panel_faces, reversed_triangle_count = orient_material_triangles(
        material_surface.faces,
        material_surface.faces,
        panel_vertices_cm,
    )
    body_vertices_target_m, body_faces = load_obj_geometry(inputs["body_mesh"])
    body_animation_start_path = (
        resolve_path(args.body_start_source)
        if args.body_start_source is not None
        else None
    )
    body_vertices_start_m = body_vertices_target_m.copy()
    body_animation_start_mode: str | None = None
    if body_animation_start_path is not None:
        body_vertices_start_m, body_start_faces = load_obj_geometry(
            body_animation_start_path
        )
        if body_vertices_start_m.shape != body_vertices_target_m.shape:
            raise ValueError(
                "Animated start and target bodies do not share stable vertex topology."
            )
        if not np.array_equal(body_start_faces, body_faces):
            raise ValueError(
                "Animated start and target bodies do not share stable face topology."
            )
        body_animation_start_mode = "source-mesh"
    elif args.body_start_radial_scale is not None:
        body_vertices_start_m = create_radially_scaled_body(
            body_vertices_target_m,
            args.body_start_radial_scale,
        )
        body_animation_start_mode = "radial-scale"
    body_animation_enabled = body_animation_start_mode is not None
    body_vertices_m = body_vertices_start_m.copy()
    projected_explicit_m, explicit_projection = project_outside_body(
        initial_surface.vertices * 0.01,
        body_vertices_m,
        body_faces,
        args.initial_body_clearance_cm * 0.01,
    )
    named_seam_links = load_named_seam_links(
        inputs["segmentation"],
        len(material_surface.vertices),
    )
    seam_links = [(first, second) for _, first, second in named_seam_links]
    vertex_owners = load_panel_vertex_owners(
        inputs["panel_index_map"],
        len(material_surface.vertices),
    )
    panel_top_anchors: list[SewingAnchor] = []
    shoulder_seam_groups: set[str] = set()
    if args.seam_topology_mode == "explicit-progressive":
        panel_top_anchors, shoulder_seam_groups = build_anatomical_sewing_anchors(
            named_seam_links,
            vertex_owners,
            panel_vertices_cm,
            projected_explicit_m * 100.0,
        )
    seam_assembly_phases = classify_seam_assembly_phases(
        named_seam_links,
        vertex_owners,
        panel_vertices_cm,
    )
    sewing_assembly_phase_count = (
        int(seam_assembly_phases.max()) + 1 if len(seam_assembly_phases) else 0
    )
    explicit_seam_metrics = evaluate_seams(projected_explicit_m * 100.0, seam_links)
    if args.seam_topology_mode == "explicit-progressive":
        identity = np.arange(len(material_surface.vertices), dtype=np.int32)
        simulation_surface = WeldedSurface(
            vertices=projected_explicit_m * 100.0,
            faces=oriented_faces,
            old_to_new=identity,
            components=tuple((int(index),) for index in identity),
        )
        welded_projection = {
            "projected_vertex_count": 0,
            "initial_minimum_signed_clearance_cm": explicit_projection[
                "final_minimum_signed_clearance_cm"
            ],
            "final_minimum_signed_clearance_cm": explicit_projection[
                "final_minimum_signed_clearance_cm"
            ],
            "maximum_projection_shift_cm": 0.0,
            "projection_skipped_for_explicit_panels": True,
        }
    else:
        simulation_surface = weld_surface(
            projected_explicit_m * 100.0,
            oriented_faces,
            seam_links,
        )
        explicit_seams_are_closed = (
            explicit_seam_metrics["maximum_seam_separation_cm"] is not None
            and explicit_seam_metrics["maximum_seam_separation_cm"] <= 1.0e-6
        )
        if explicit_seams_are_closed:
            projected_welded_m = simulation_surface.vertices * 0.01
            welded_projection = {
                "projected_vertex_count": 0,
                "initial_minimum_signed_clearance_cm": explicit_projection[
                    "final_minimum_signed_clearance_cm"
                ],
                "final_minimum_signed_clearance_cm": explicit_projection[
                    "final_minimum_signed_clearance_cm"
                ],
                "maximum_projection_shift_cm": 0.0,
                "projection_skipped_for_closed_seams": True,
            }
        else:
            projected_welded_m, welded_projection = project_outside_body(
                simulation_surface.vertices * 0.01,
                body_vertices_m,
                body_faces,
                args.initial_body_clearance_cm * 0.01,
            )
        simulation_surface = WeldedSurface(
            vertices=projected_welded_m * 100.0,
            faces=simulation_surface.faces,
            old_to_new=simulation_surface.old_to_new,
            components=simulation_surface.components,
        )
    if args.seam_topology_mode == "explicit-progressive":
        collision_topology_ids = np.empty(len(simulation_surface.vertices), dtype=np.int32)
        for component_index, component in enumerate(
            build_components(len(simulation_surface.vertices), seam_links)
        ):
            collision_topology_ids[np.asarray(component, dtype=np.int32)] = component_index
    else:
        collision_topology_ids = np.arange(len(simulation_surface.vertices), dtype=np.int32)
    rest_lengths = load_rest_lengths(inputs["rest_lengths"], len(material_surface.vertices))

    cloth_vertices_m = simulation_surface.vertices * 0.01
    panel_vertices_m = panel_vertices_cm * 0.01

    wp.init()
    device = wp.get_device(args.device)
    if not device.is_cuda:
        raise RuntimeError("Patterna Style3D proof requires a CUDA device.")

    initial_body_collisions, initial_self_collisions = count_intersections(
        cloth_vertices_m,
        simulation_surface.faces,
        body_vertices_m,
        body_faces,
        args.device,
        collision_topology_ids,
    )
    if args.seam_topology_mode == "explicit-progressive" and (
        initial_body_collisions > 0 or initial_self_collisions > 0
    ):
        raise ValueError(
            "Explicit Style3D sewing requires a collision-clean initial layout; "
            f"found {initial_body_collisions} body and "
            f"{initial_self_collisions} self intersections."
        )

    builder = newton.ModelBuilder(up_axis=newton.Axis.Y)
    SolverStyle3D.register_custom_attributes(builder)
    style3d.add_cloth_mesh(
        builder,
        pos=wp.vec3(0.0, 0.0, 0.0),
        rot=wp.quat_identity(),
        vel=wp.vec3(0.0, 0.0, 0.0),
        panel_verts=panel_vertices_m.tolist(),
        panel_indices=oriented_panel_faces.tolist(),
        vertices=cloth_vertices_m.tolist(),
        indices=simulation_surface.faces.tolist(),
        density=args.density_kg_m2,
        scale=1.0,
        particle_radius=args.body_contact_radius_cm * 0.01,
        tri_aniso_ke=wp.vec3(
            args.weft_stiffness,
            args.warp_stiffness,
            args.shear_stiffness,
        ),
        edge_aniso_ke=wp.vec3(args.bend_weft, args.bend_warp, args.bend_bias),
        tri_kd=2.0e-6,
        edge_kd=2.0e-6,
        validate_mesh=True,
        label="Patterna garment",
    )
    body_index = builder.add_body()
    body_collision_source = Mesh(body_vertices_m, body_faces.reshape(-1))
    builder.add_shape_mesh(
        body=body_index,
        mesh=body_collision_source,
    )
    model = builder.finalize(device=device)
    model.soft_contact_radius = args.body_contact_radius_cm * 0.01
    model.soft_contact_margin = args.body_contact_margin_cm * 0.01
    model.soft_contact_ke = args.body_contact_stiffness
    model.soft_contact_kd = 1.0e-5
    model.soft_contact_mu = args.body_friction
    model.set_gravity((0.0, -9.81, 0.0))

    initial_seam_rest_lengths_m: np.ndarray | None = None
    seam_stiffnesses_np: np.ndarray | None = None
    same_panel_seam_link_count = 0
    if args.seam_topology_mode == "explicit-progressive":
        initial_seam_rest_lengths_m = np.asarray(
            [
                np.linalg.norm(cloth_vertices_m[first] - cloth_vertices_m[second])
                for first, second in seam_links
            ],
            dtype=np.float32,
        )
        same_panel_seam_mask = np.asarray(
            [
                vertex_owners[first] == vertex_owners[second]
                for first, second in seam_links
            ],
            dtype=bool,
        )
        same_panel_seam_link_count = int(np.count_nonzero(same_panel_seam_mask))
        seam_stiffnesses_np = np.where(
            same_panel_seam_mask,
            args.dart_seam_stiffness,
            args.seam_stiffness,
        ).astype(np.float32)
        solver = PatternaStyle3DSewingSolver(
            model,
            seam_links,
            initial_seam_rest_lengths_m,
            seam_stiffness=args.seam_stiffness,
            seam_stiffnesses=seam_stiffnesses_np,
            velocity_retention=args.velocity_retention_per_substep,
            iterations=args.nonlinear_iterations,
            linear_iterations=args.linear_iterations,
        )
    else:
        solver = SolverStyle3D(
            model,
            iterations=args.nonlinear_iterations,
            linear_iterations=args.linear_iterations,
        )
    if solver.collision is None:
        raise RuntimeError("Style3D collision handling is unexpectedly disabled.")
    solver.collision.radius = args.self_contact_thickness_cm * 0.01
    solver.collision.stiff_vf = args.self_contact_vf_stiffness
    solver.collision.stiff_ee = args.self_contact_ee_stiffness
    solver.collision.stiff_ef = args.self_contact_ef_stiffness

    body_projection_points = wp.array(
        body_vertices_m.astype(np.float32),
        dtype=wp.vec3,
        device=device,
    )
    body_projection_indices = wp.array(
        body_faces.reshape(-1),
        dtype=int,
        device=device,
    )
    body_projection_mesh = wp.Mesh(body_projection_points, body_projection_indices)
    if body_collision_source.mesh is None:
        raise RuntimeError("Newton did not finalize the animated body collision mesh.")
    hard_body_correction_count = wp.zeros(1, dtype=int, device=device)
    cloth_surface_edges_np = surface_edges(simulation_surface.faces)
    vertex_edge_offsets_np, incident_edge_indices_np = build_vertex_edge_adjacency(
        len(cloth_vertices_m),
        cloth_surface_edges_np,
    )
    cloth_surface_edges = wp.array(
        cloth_surface_edges_np,
        dtype=int,
        device=device,
    )
    vertex_edge_offsets = wp.array(
        vertex_edge_offsets_np,
        dtype=int,
        device=device,
    )
    incident_edge_indices = wp.array(
        incident_edge_indices_np,
        dtype=int,
        device=device,
    )
    edge_corrections = wp.zeros(
        len(cloth_surface_edges_np),
        dtype=wp.vec3,
        device=device,
    )
    edge_corrected_positions = wp.empty(
        len(cloth_vertices_m),
        dtype=wp.vec3,
        device=device,
    )
    edge_corrected_velocities = wp.empty(
        len(cloth_vertices_m),
        dtype=wp.vec3,
        device=device,
    )
    hard_body_edge_correction_count = wp.zeros(1, dtype=int, device=device)
    sewing_anchor_indices_np = np.asarray(
        [anchor.vertex_index for anchor in panel_top_anchors],
        dtype=np.int32,
    )
    sewing_anchor_indices = wp.array(
        sewing_anchor_indices_np,
        dtype=int,
        device=device,
    )
    sewing_anchor_heights_np = (
        np.asarray(
            [anchor.target_height_cm * 0.01 for anchor in panel_top_anchors],
            dtype=np.float32,
        )
        if len(sewing_anchor_indices_np)
        else np.empty(0, dtype=np.float32)
    )
    sewing_anchor_heights = wp.array(
        sewing_anchor_heights_np,
        dtype=float,
        device=device,
    )

    state_0 = model.state()
    state_1 = model.state()
    control = model.control()
    collision_pipeline = newton.CollisionPipeline(model)
    contacts = collision_pipeline.contacts()
    solver.rebuild_bvh(state_0)

    frame_dt = 1.0 / 60.0
    simulation_dt = frame_dt / args.substeps
    static_streak = 0
    static_reached = False
    completed_frames = 0
    maximum_displacement_cm = 0.0
    mean_displacement_cm = 0.0
    p999_displacement_cm = 0.0
    non_static_vertices = len(cloth_vertices_m)
    final_sewing_progress = (
        0.0 if args.seam_topology_mode == "explicit-progressive" else 1.0
    )
    final_anchor_strength = (
        1.0 if args.seam_topology_mode == "explicit-progressive" else 0.0
    )
    final_body_animation_progress = (
        0.0 if body_animation_enabled else 1.0
    )
    body_animation_end_frame = (
        args.body_animation_delay_frames + args.body_animation_frames
        if body_animation_enabled
        else None
    )
    simulation_start = time.perf_counter()
    for frame in range(args.frames):
        if body_animation_enabled:
            animation_frame = frame - args.body_animation_delay_frames
            previous_body_vertices_m = body_vertices_m
            if animation_frame < 0:
                body_vertices_m = body_vertices_start_m.copy()
                final_body_animation_progress = 0.0
            else:
                body_vertices_m, final_body_animation_progress = (
                    interpolate_animated_body(
                        body_vertices_start_m,
                        body_vertices_target_m,
                        animation_frame,
                        args.body_animation_frames,
                    )
                )
            body_velocity_m_s = (
                body_vertices_m - previous_body_vertices_m
            ) / frame_dt
            body_points_f32 = body_vertices_m.astype(np.float32)
            body_collision_source.mesh.points.assign(body_points_f32)
            body_collision_source.mesh.velocities.assign(
                body_velocity_m_s.astype(np.float32)
            )
            body_collision_source.mesh.refit()
            body_projection_points.assign(body_points_f32)
            body_projection_mesh.refit()
            model.bvh_refit_shapes(state_0)
        if initial_seam_rest_lengths_m is not None:
            link_progress = np.asarray(
                [
                    sewing_schedule_progress(
                        frame,
                        args.sewing_ramp_delay_frames
                        + int(phase) * args.sewing_ramp_frames,
                        args.sewing_ramp_frames,
                    )
                    for phase in seam_assembly_phases
                ],
                dtype=np.float32,
            )
            target_length_m = args.seam_rest_length_cm * 0.01
            solver.set_seam_rest_lengths(
                initial_seam_rest_lengths_m
                + (target_length_m - initial_seam_rest_lengths_m) * link_progress
            )
            final_sewing_progress = float(np.min(link_progress))
            final_anchor_strength = sewing_anchor_strength(
                frame,
                args.sewing_ramp_delay_frames,
                args.sewing_ramp_frames,
                sewing_assembly_phase_count,
                args.sewing_anchor_release_frames,
                body_animation_end_frame,
            )
        frame_start = state_0.particle_q.numpy()
        hard_clearance_active = (
            args.hard_body_clearance_cm > 0.0
            and (
                args.hard_body_clearance_mode == "continuous"
                or args.seam_topology_mode != "explicit-progressive"
                or final_sewing_progress < 1.0
            )
        )
        for _ in range(args.substeps):
            state_0.clear_forces()
            collision_pipeline.collide(state_0, contacts)
            solver.step(state_0, state_1, control, contacts, simulation_dt)
            if hard_clearance_active:
                wp.launch(
                    enforce_body_clearance_kernel,
                    dim=len(cloth_vertices_m),
                    inputs=[
                        state_1.particle_q,
                        state_1.particle_qd,
                        body_projection_mesh.id,
                        args.hard_body_clearance_cm * 0.01,
                    ],
                    outputs=[hard_body_correction_count],
                    device=device,
                )
            if len(sewing_anchor_indices_np) and final_anchor_strength > 0.0:
                wp.launch(
                    enforce_vertical_sewing_anchors_kernel,
                    dim=len(sewing_anchor_indices_np),
                    inputs=[
                        state_1.particle_q,
                        state_1.particle_qd,
                        sewing_anchor_indices,
                        sewing_anchor_heights,
                        final_anchor_strength,
                    ],
                    device=device,
                )
            state_0, state_1 = state_1, state_0
        if (
            hard_clearance_active
            and args.hard_body_edge_clearance_cm > 0.0
            and args.hard_body_edge_passes > 0
        ):
            for _ in range(args.hard_body_edge_passes):
                wp.launch(
                    compute_body_edge_clearance_corrections_kernel,
                    dim=len(cloth_surface_edges_np),
                    inputs=[
                        state_0.particle_q,
                        cloth_surface_edges,
                        body_projection_mesh.id,
                        args.hard_body_edge_clearance_cm * 0.01,
                    ],
                    outputs=[edge_corrections, hard_body_edge_correction_count],
                    device=device,
                )
                wp.launch(
                    apply_body_edge_clearance_corrections_kernel,
                    dim=len(cloth_vertices_m),
                    inputs=[
                        state_0.particle_q,
                        state_0.particle_qd,
                        vertex_edge_offsets,
                        incident_edge_indices,
                        edge_corrections,
                    ],
                    outputs=[edge_corrected_positions, edge_corrected_velocities],
                    device=device,
                )
                state_0.particle_q.assign(edge_corrected_positions)
                state_0.particle_qd.assign(edge_corrected_velocities)
                wp.launch(
                    enforce_body_clearance_kernel,
                    dim=len(cloth_vertices_m),
                    inputs=[
                        state_0.particle_q,
                        state_0.particle_qd,
                        body_projection_mesh.id,
                        args.hard_body_clearance_cm * 0.01,
                    ],
                    outputs=[hard_body_correction_count],
                    device=device,
                )
        frame_end = state_0.particle_q.numpy()
        if not np.isfinite(frame_end).all():
            completed_frames = frame + 1
            static_streak = 0
            break
        displacement_cm = np.linalg.norm(frame_end - frame_start, axis=1) * 100.0
        maximum_displacement_cm = float(np.max(displacement_cm))
        mean_displacement_cm = float(np.mean(displacement_cm))
        p999_displacement_cm = float(np.percentile(displacement_cm, 99.9))
        l1_displacement_cm = np.sum(np.abs(frame_end - frame_start), axis=1) * 100.0
        non_static_vertices = int(np.count_nonzero(l1_displacement_cm > args.static_threshold_cm))
        static_frame = (
            mean_displacement_cm <= args.static_mean_threshold_cm
            and p999_displacement_cm <= args.static_p999_threshold_cm
        )
        static_streak = static_streak + 1 if static_frame else 0
        completed_frames = frame + 1
        if (
            final_sewing_progress >= 1.0
            and final_body_animation_progress >= 1.0
            and completed_frames >= args.minimum_frames
            and static_streak >= args.static_consecutive_frames
        ):
            static_reached = True
            break
    simulation_seconds = time.perf_counter() - simulation_start

    final_simulation_m = state_0.particle_q.numpy().astype(np.float64)
    final_expanded_cm = expand_welded_positions(
        final_simulation_m * 100.0,
        simulation_surface.old_to_new,
    )
    finite_positions = bool(np.isfinite(final_simulation_m).all())
    body_intersection_edges, self_intersection_edges = find_intersection_edges(
        final_simulation_m,
        simulation_surface.faces,
        body_vertices_m,
        body_faces,
        args.device,
        collision_topology_ids,
    )
    body_collisions = len(body_intersection_edges)
    self_collisions = len(self_intersection_edges)
    seam_metrics = evaluate_seams(final_expanded_cm, seam_links)
    strain_metrics = evaluate_strain(
        final_expanded_cm,
        rest_lengths,
        args.max_edge_strain,
    )

    accepted, rejection_reasons = evaluate_style3d_acceptance(
        finite_positions=finite_positions,
        static_equilibrium_reached=static_reached,
        body_collisions=body_collisions,
        self_collisions=self_collisions,
        seam_metrics=seam_metrics,
        strain_metrics=strain_metrics,
        max_seam_separation_cm=args.max_seam_separation_cm,
        max_p95_edge_strain=args.max_p95_edge_strain,
        max_p999_edge_strain=args.max_p999_edge_strain,
        max_p9999_edge_strain=args.max_p9999_edge_strain,
        max_high_strain_edge_fraction=args.max_high_strain_edge_fraction,
    )

    expanded_output = output_dir / "patterna_style3d_sim.obj"
    physical_output = output_dir / "patterna_style3d_physical.obj"
    report_output = output_dir / "patterna_style3d_report.json"
    (
        render_faces,
        spatial_orientation_report,
        spatially_reoriented_triangle_count,
    ) = orient_spatial_panels_outward(
        oriented_faces,
        final_expanded_cm * 0.01,
        vertex_owners,
        body_vertices_target_m,
        body_faces,
    )
    write_expanded_obj(
        inputs["physical_mesh"],
        expanded_output,
        final_expanded_cm,
        render_faces,
    )
    physical_render_faces = (
        render_faces
        if len(final_simulation_m) == len(final_expanded_cm)
        else simulation_surface.faces
    )
    write_physical_obj(
        physical_output,
        final_simulation_m * 100.0,
        physical_render_faces,
    )

    solver_files = [
        Path(inspect.getfile(SolverStyle3D)),
        Path(inspect.getfile(style3d.add_cloth_mesh)),
    ]
    if args.seam_topology_mode == "explicit-progressive":
        solver_files.append(Path(inspect.getfile(PatternaStyle3DSewingSolver)))
    report: dict[str, object] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "accepted": accepted,
        "rejection_reasons": rejection_reasons,
        "finite_positions": finite_positions,
        "source_report_path": str(source_report_path),
        "source_report_sha256": sha256_file(source_report_path),
        "source_report_accepted": bool(source_report.get("accepted", False)),
        "material_surface_path": str(inputs["physical_mesh"]),
        "material_surface_sha256": sha256_file(inputs["physical_mesh"]),
        "material_coordinates_path": str(material_coordinates_path),
        "material_coordinates_sha256": sha256_file(material_coordinates_path),
        "initial_surface_path": str(inputs["initial_mesh"]),
        "initial_surface_sha256": sha256_file(inputs["initial_mesh"]),
        "body_mesh_path": str(inputs["body_mesh"]),
        "body_mesh_sha256": sha256_file(inputs["body_mesh"]),
        "body_mesh_source_units": "meters",
        "body_start_source_path": (
            str(body_animation_start_path)
            if body_animation_start_path is not None
            else None
        ),
        "body_start_source_sha256": (
            sha256_file(body_animation_start_path)
            if body_animation_start_path is not None
            else None
        ),
        "body_animation_start_mode": body_animation_start_mode,
        "body_start_radial_scale": (
            args.body_start_radial_scale
            if body_animation_start_mode == "radial-scale"
            else None
        ),
        "body_animation_delay_frames": (
            args.body_animation_delay_frames
            if body_animation_enabled
            else None
        ),
        "body_animation_frames": (
            args.body_animation_frames
            if body_animation_enabled
            else None
        ),
        "body_animation_progress": final_body_animation_progress,
        "body_animation_completed": final_body_animation_progress >= 1.0,
        "body_vertex_count": len(body_vertices_target_m),
        "body_face_count": len(body_faces),
        "panel_ownership_path": str(inputs["segmentation"]),
        "panel_ownership_sha256": sha256_file(inputs["segmentation"]),
        "rest_lengths_path": str(inputs["rest_lengths"]),
        "rest_lengths_sha256": sha256_file(inputs["rest_lengths"]),
        "panel_index_map_path": str(inputs["panel_index_map"]),
        "panel_index_map_sha256": sha256_file(inputs["panel_index_map"]),
        "newton_version": newton.__version__,
        "warp_version": wp.__version__,
        "device": str(device),
        "solver": (
            "tools.patterna_style3d_sewing.PatternaStyle3DSewingSolver"
            if args.seam_topology_mode == "explicit-progressive"
            else "newton.solvers.SolverStyle3D"
        ),
        "solver_files": {str(path): sha256_file(path) for path in solver_files},
        "adapter_implementation_path": str(Path(__file__).resolve()),
        "adapter_implementation_sha256": sha256_file(Path(__file__).resolve()),
        "solver_formulation": "implicit-projective-dynamics-pcg-with-coupled-contact",
        "render_vertex_count": len(material_surface.vertices),
        "physical_vertex_count": len(simulation_surface.vertices),
        "welded_vertex_reduction": len(material_surface.vertices)
        - len(simulation_surface.vertices),
        "seam_topology_mode": args.seam_topology_mode,
        "physical_face_count": len(simulation_surface.faces),
        "mesh_resolution_cm": source_report.get("mesh_resolution_cm"),
        "pattern_specification_path": source_report.get("pattern_specification_path"),
        "pattern_specification_sha256": source_report.get(
            "pattern_specification_sha256"
        ),
        "reoriented_material_triangle_count": reversed_triangle_count,
        "spatially_reoriented_panel_count": sum(
            1
            for panel in spatial_orientation_report.values()
            if panel["flipped"]
        ),
        "spatially_reoriented_triangle_count": (
            spatially_reoriented_triangle_count
        ),
        "spatial_panel_orientation": spatial_orientation_report,
        "seam_component_count": sum(
            1 for component in simulation_surface.components if len(component) > 1
        ),
        "initial_body_collisions": initial_body_collisions,
        "initial_self_collisions": initial_self_collisions,
        "body_collisions": body_collisions,
        "self_collisions": self_collisions,
        "max_body_collisions": 0,
        "max_self_collisions": 0,
        "body_collision_rate": body_collisions / max(int(strain_metrics["evaluated_edge_count"]), 1),
        "self_collision_rate": self_collisions / max(int(strain_metrics["evaluated_edge_count"]), 1),
        "body_intersection_edge_samples": body_intersection_edges[:128].tolist(),
        "self_intersection_edge_samples": self_intersection_edges[:128].tolist(),
        "collision_gate_evaluated": True,
        "seam_closure_gate_evaluated": True,
        "static_equilibrium_reached": static_reached,
        "equilibrium_gate_evaluated": True,
        "completed_frames": completed_frames,
        "requested_frames": args.frames,
        "simulation_substeps": args.substeps,
        "nonlinear_iterations": args.nonlinear_iterations,
        "linear_iterations": args.linear_iterations,
        "velocity_retention_per_substep": (
            args.velocity_retention_per_substep
            if args.seam_topology_mode == "explicit-progressive"
            else None
        ),
        "self_contact_vf_stiffness": args.self_contact_vf_stiffness,
        "self_contact_ee_stiffness": args.self_contact_ee_stiffness,
        "self_contact_ef_stiffness": args.self_contact_ef_stiffness,
        "seam_stiffness": (
            args.seam_stiffness
            if args.seam_topology_mode == "explicit-progressive"
            else None
        ),
        "dart_seam_stiffness": (
            args.dart_seam_stiffness
            if args.seam_topology_mode == "explicit-progressive"
            else None
        ),
        "same_panel_seam_link_count": same_panel_seam_link_count,
        "seam_rest_length_cm": (
            args.seam_rest_length_cm
            if args.seam_topology_mode == "explicit-progressive"
            else None
        ),
        "initial_maximum_seam_rest_length_cm": (
            float(np.max(initial_seam_rest_lengths_m)) * 100.0
            if initial_seam_rest_lengths_m is not None
            else None
        ),
        "sewing_ramp_delay_frames": (
            args.sewing_ramp_delay_frames
            if args.seam_topology_mode == "explicit-progressive"
            else None
        ),
        "sewing_ramp_frames": (
            args.sewing_ramp_frames
            if args.seam_topology_mode == "explicit-progressive"
            else None
        ),
        "sewing_assembly_phase_count": (
            sewing_assembly_phase_count
            if args.seam_topology_mode == "explicit-progressive"
            else None
        ),
        "sewing_assembly_phase_link_counts": (
            {
                str(phase): int(np.count_nonzero(seam_assembly_phases == phase))
                for phase in range(sewing_assembly_phase_count)
            }
            if args.seam_topology_mode == "explicit-progressive"
            else None
        ),
        "sewing_anchor_release_frames": (
            args.sewing_anchor_release_frames
            if args.seam_topology_mode == "explicit-progressive"
            else None
        ),
        "final_sewing_anchor_strength": final_anchor_strength,
        "shoulder_seam_groups": sorted(shoulder_seam_groups),
        "sewing_vertical_anchor_vertex_count": len(panel_top_anchors),
        "sewing_vertical_anchor_vertices": [
            {
                "panel": anchor.panel_name,
                "vertex_index": anchor.vertex_index,
                "target_height_cm": anchor.target_height_cm,
                "initial_height_cm": anchor.initial_height_cm,
                "vertical_correction_cm": (
                    anchor.target_height_cm - anchor.initial_height_cm
                ),
                "source": anchor.source,
                "partner_panel": anchor.partner_panel_name,
            }
            for anchor in panel_top_anchors
        ],
        "sewing_settle_frames": (
            args.sewing_settle_frames
            if args.seam_topology_mode == "explicit-progressive"
            else None
        ),
        "sewing_schedule_progress": final_sewing_progress,
        "sewing_schedule_completed": final_sewing_progress >= 1.0,
        "static_consecutive_frames": args.static_consecutive_frames,
        "static_threshold_cm": args.static_threshold_cm,
        "non_static_percent": args.non_static_percent,
        "static_mean_threshold_cm": args.static_mean_threshold_cm,
        "static_p999_threshold_cm": args.static_p999_threshold_cm,
        "non_static_vertex_count": non_static_vertices,
        "maximum_displacement_cm": maximum_displacement_cm,
        "mean_displacement_cm": mean_displacement_cm,
        "ninety_ninth_point_ninth_percentile_displacement_cm": p999_displacement_cm,
        "simulation_seconds": simulation_seconds,
        "mean_frame_seconds": simulation_seconds / completed_frames,
        "fabric": {
            "density_kg_m2": args.density_kg_m2,
            "physical_thickness_cm": args.cloth_thickness_cm,
            "self_contact_thickness_cm": args.self_contact_thickness_cm,
            "body_contact_radius_cm": args.body_contact_radius_cm,
            "collision_particle_radius_cm": args.body_contact_radius_cm,
            "body_contact_margin_cm": args.body_contact_margin_cm,
            "initial_body_clearance_cm": args.initial_body_clearance_cm,
            "hard_body_clearance_cm": args.hard_body_clearance_cm,
            "hard_body_edge_clearance_cm": args.hard_body_edge_clearance_cm,
            "body_friction": args.body_friction,
            "weft_stiffness": args.weft_stiffness,
            "warp_stiffness": args.warp_stiffness,
            "shear_stiffness": args.shear_stiffness,
            "bend_weft": args.bend_weft,
            "bend_warp": args.bend_warp,
            "bend_bias": args.bend_bias,
        },
        "explicit_body_clearance_projection": explicit_projection,
        "welded_body_clearance_projection": welded_projection,
        "hard_body_projection_correction_count": int(
            hard_body_correction_count.numpy()[0]
        ),
        "hard_body_edge_projection_passes_per_frame": args.hard_body_edge_passes,
        "hard_body_edge_projection_correction_count": int(
            hard_body_edge_correction_count.numpy()[0]
        ),
        "hard_body_projection_release_mode": (
            "released-after-sewing-ramp"
            if args.seam_topology_mode == "explicit-progressive"
            and args.hard_body_clearance_cm > 0.0
            and args.hard_body_clearance_mode == "during-sewing"
            else "continuous"
            if args.hard_body_clearance_cm > 0.0
            else "disabled"
        ),
        **seam_metrics,
        "max_seam_separation_cm": args.max_seam_separation_cm,
        **strain_metrics,
        "material_rest_length_edge_count": strain_metrics["evaluated_edge_count"],
        "reference_geometry_edge_count": 0,
        "excluded_edge_count": 0,
        "peak_edge_strain_gate_mode": "reported-only-resolution-singularity",
        "max_ninety_fifth_percentile_edge_strain_ratio": args.max_p95_edge_strain,
        "max_ninety_ninth_point_ninth_percentile_edge_strain_ratio": args.max_p999_edge_strain,
        "max_ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio": args.max_p9999_edge_strain,
        "max_high_strain_edge_fraction": args.max_high_strain_edge_fraction,
        "output_mesh_path": str(expanded_output),
        "output_mesh_sha256": sha256_file(expanded_output),
        "physical_output_mesh_path": str(physical_output),
        "physical_output_mesh_sha256": sha256_file(physical_output),
    }
    report_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = run(parse_arguments())
    print(json.dumps(report, indent=2))
    return 0 if report["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
