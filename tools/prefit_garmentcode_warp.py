#!/usr/bin/env python3
"""Run Patterna garment assembly through GarmentCode's Warp cloth solver."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pickle
import shutil
import struct
import sys
import time
import re

import numpy as np

try:
    from tools.patterna_shell_assembly import (
        assemble_body_aware_shell,
        load_obj_vertices_centimeters,
        set_current_geometry_rest_lengths,
    )
except ModuleNotFoundError:
    from patterna_shell_assembly import (
        assemble_body_aware_shell,
        load_obj_vertices_centimeters,
        set_current_geometry_rest_lengths,
    )


REPORT_SCHEMA_VERSION = "patterna.warp-prefit-report/2.6"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _append_length_prefixed_text(digest, value: str) -> None:
    encoded = value.encode("utf-8")
    digest.update(struct.pack("<Q", len(encoded)))
    digest.update(encoded)


def hash_physical_topology(vertex_count: int, faces: np.ndarray) -> str:
    """Hash ordered face connectivity independently from particle positions."""
    triangles = np.asarray(faces, dtype=np.int64)
    if vertex_count <= 0:
        raise ValueError("Physical topology requires at least one vertex.")
    if triangles.ndim != 2 or triangles.shape[1] != 3 or triangles.size == 0:
        raise ValueError("Physical topology requires an N by 3 triangle array.")
    if np.any(triangles < 0) or np.any(triangles >= vertex_count):
        raise ValueError("Physical topology contains an out-of-range vertex index.")

    digest = hashlib.sha256()
    digest.update(b"patterna.physical-topology/1\0")
    digest.update(struct.pack("<QQ", vertex_count, len(triangles)))
    digest.update(triangles.astype("<i8", copy=False).tobytes(order="C"))
    return digest.hexdigest()


def hash_surface_corner_mapping(
    texture_vertex_count: int,
    position_faces: np.ndarray,
    texture_faces: np.ndarray,
) -> str:
    """Hash the exact position-to-pattern-corner mapping of an OBJ surface."""
    positions = np.asarray(position_faces, dtype=np.int64)
    textures = np.asarray(texture_faces, dtype=np.int64)
    if texture_vertex_count <= 0:
        raise ValueError("Surface corner mapping requires texture vertices.")
    if positions.shape != textures.shape or positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError("Position and texture face arrays must be matching triangles.")
    if np.any(textures < 0) or np.any(textures >= texture_vertex_count):
        raise ValueError("Surface corner mapping contains an invalid texture index.")

    interleaved = np.stack((positions, textures), axis=-1)
    digest = hashlib.sha256()
    digest.update(b"patterna.surface-corner-mapping/1\0")
    digest.update(struct.pack("<QQ", texture_vertex_count, len(positions)))
    digest.update(interleaved.astype("<i8", copy=False).tobytes(order="C"))
    return digest.hexdigest()


def read_obj_topology(path: Path) -> dict[str, object]:
    """Read the ordered triangle and pattern-corner topology from an OBJ."""
    vertex_count = 0
    texture_vertex_count = 0
    position_faces: list[list[int]] = []
    texture_faces: list[list[int]] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("v "):
            vertex_count += 1
        elif line.startswith("vt "):
            texture_vertex_count += 1
        elif line.startswith("f "):
            corners = line.split()[1:]
            if len(corners) != 3:
                raise RuntimeError(f"Physical mesh contains a non-triangle face: {line}")
            position_face = []
            texture_face = []
            for corner in corners:
                fields = corner.split("/")
                if not fields[0] or len(fields) < 2 or not fields[1]:
                    raise RuntimeError(
                        "Physical mesh faces must contain position and texture indices."
                    )
                position_index = int(fields[0])
                texture_index = int(fields[1])
                if position_index <= 0 or texture_index <= 0:
                    raise RuntimeError(
                        "Physical mesh identity requires positive absolute OBJ indices."
                    )
                position_face.append(position_index - 1)
                texture_face.append(texture_index - 1)
            position_faces.append(position_face)
            texture_faces.append(texture_face)

    positions = np.asarray(position_faces, dtype=np.int64)
    textures = np.asarray(texture_faces, dtype=np.int64)
    return {
        "vertex_count": vertex_count,
        "texture_vertex_count": texture_vertex_count,
        "face_count": len(positions),
        "position_faces": positions,
        "texture_faces": textures,
        "topology_sha256": hash_physical_topology(vertex_count, positions),
        "surface_corner_mapping_sha256": hash_surface_corner_mapping(
            texture_vertex_count,
            positions,
            textures,
        ),
    }


def hash_material_rest_graph(
    material_rest_lengths: dict[tuple[int, int], float],
) -> tuple[str, int]:
    """Hash an undirected material-rest graph independently from dict ordering."""
    normalized: dict[tuple[int, int], float] = {}
    for raw_edge, raw_length in material_rest_lengths.items():
        if len(raw_edge) != 2:
            raise RuntimeError(f"Invalid material rest edge: {raw_edge!r}")
        first, second = sorted((int(raw_edge[0]), int(raw_edge[1])))
        length = float(raw_length)
        if first < 0 or first == second or not np.isfinite(length) or length <= 1.0e-6:
            raise RuntimeError(
                f"Invalid material rest entry {(first, second)}: {length!r}"
            )
        key = (first, second)
        if key in normalized and normalized[key] != length:
            raise RuntimeError(f"Conflicting material rest lengths for edge {key}.")
        normalized[key] = length

    if not normalized:
        raise RuntimeError("Material rest graph is empty.")
    digest = hashlib.sha256()
    digest.update(b"patterna.material-rest-graph/1\0")
    digest.update(struct.pack("<Q", len(normalized)))
    for (first, second), length in sorted(normalized.items()):
        digest.update(struct.pack("<QQd", first, second, length))
    return digest.hexdigest(), len(normalized)


def hash_seam_constraint_graph(
    topology_mode: str,
    surface_corner_mapping_sha256: str,
    seam_link_records: dict[str, tuple[int, int]],
) -> str:
    """Hash welded corner identity and explicit sewing links as one seam contract."""
    digest = hashlib.sha256()
    digest.update(b"patterna.seam-constraint-graph/1\0")
    _append_length_prefixed_text(digest, topology_mode)
    _append_length_prefixed_text(digest, surface_corner_mapping_sha256)
    digest.update(struct.pack("<Q", len(seam_link_records)))
    for label, raw_pair in sorted(seam_link_records.items()):
        first, second = sorted((int(raw_pair[0]), int(raw_pair[1])))
        if first < 0 or first == second:
            raise RuntimeError(f"Invalid seam constraint {label}: {raw_pair!r}")
        _append_length_prefixed_text(digest, label)
        digest.update(struct.pack("<QQ", first, second))
    return digest.hexdigest()


def implementation_identity(
    implementation_paths: dict[str, Path],
) -> tuple[str, dict[str, str]]:
    """Hash every source file that defines meshing and solver behavior."""
    file_hashes = {
        name: _sha256_file(path)
        for name, path in sorted(implementation_paths.items())
    }
    digest = hashlib.sha256()
    digest.update(b"patterna.solver-implementation/1\0")
    for name, file_hash in file_hashes.items():
        _append_length_prefixed_text(digest, name)
        _append_length_prefixed_text(digest, file_hash)
    return digest.hexdigest(), file_hashes


def _panel_slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return result or "panel"


def apply_body_aware_initial_arrangement(mesh, arrangement_path: Path) -> None:
    """Replace flat-slab placement with the compiler's measured sewn shell."""
    document = json.loads(arrangement_path.read_text(encoding="utf-8"))
    arranged_panels = {
        panel["panelId"]: panel for panel in document.get("panels", [])
    }
    if not arranged_panels:
        raise RuntimeError("The initial arrangement contains no panels.")

    target_sums = np.zeros((len(mesh.vertices), 3), dtype=float)
    target_counts = np.zeros(len(mesh.vertices), dtype=int)
    for panel_name in mesh.panelNames:
        panel_id = f"{_panel_slug(panel_name)}-panel"
        if panel_id not in arranged_panels:
            raise RuntimeError(
                f"The initial arrangement has no panel matching {panel_name}."
            )
        arranged_vertices = arranged_panels[panel_id].get("vertices", [])
        panel = mesh.panels[panel_name]
        if len(arranged_vertices) != len(panel.panel_vertices):
            raise RuntimeError(
                f"Initial arrangement panel {panel_id} has {len(arranged_vertices)} "
                f"vertices; the GarmentCode panel has {len(panel.panel_vertices)}."
            )
        for local_index, arranged in enumerate(arranged_vertices):
            if local_index < panel.n_stitches:
                global_index = mesh.verts_loc_glob[(panel_name, local_index)]
            else:
                global_index = local_index + panel.glob_offset - panel.n_stitches
            target_sums[global_index] += np.asarray(
                [arranged["x"], arranged["z"], arranged["y"]],
                dtype=float,
            )
            target_counts[global_index] += 1

    if np.any(target_counts == 0):
        missing = np.flatnonzero(target_counts == 0)
        raise RuntimeError(
            f"Initial arrangement did not map {len(missing)} GarmentCode vertices."
        )
    arranged = target_sums / target_counts[:, None]
    seam_links = getattr(mesh, "seam_links", [])
    if seam_links:
        parent = list(range(len(arranged)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        for first, second in seam_links:
            first_root = find(first)
            second_root = find(second)
            if first_root != second_root:
                parent[second_root] = first_root
        components: dict[int, list[int]] = {}
        for first, second in seam_links:
            components.setdefault(find(first), []).extend((first, second))
        for indices in components.values():
            unique_indices = sorted(set(indices))
            centroid = arranged[unique_indices].mean(axis=0)
            arranged[unique_indices] = centroid
    mesh.vertices = arranged.tolist()


def create_radially_scaled_body(
    target_vertices: np.ndarray,
    radial_scale: float,
) -> np.ndarray:
    """Create a topology-identical narrow mannequin for staged inflation."""
    target = np.asarray(target_vertices, dtype=float)
    if target.ndim != 2 or target.shape[1] != 3 or not np.isfinite(target).all():
        raise ValueError("Target body vertices must be a finite N by 3 array.")
    if not np.isfinite(radial_scale) or not 0.1 <= radial_scale < 1.0:
        raise ValueError("Body start radial scale must be between 0.1 and 1.0.")
    result = target.copy()
    result[:, 0] *= radial_scale
    result[:, 2] *= radial_scale
    return result


def load_obj_geometry(path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            values = line.split()
            vertices.append([float(values[1]), float(values[2]), float(values[3])])
        elif line.startswith("f "):
            indices = [int(value.split("/", 1)[0]) - 1 for value in line.split()[1:]]
            if len(indices) != 3:
                raise RuntimeError(f"Initial mesh is not triangulated: {path}")
            faces.append(indices)
    vertex_array = np.asarray(vertices, dtype=float)
    face_array = np.asarray(faces, dtype=int)
    if vertex_array.ndim != 2 or vertex_array.shape[1] != 3:
        raise RuntimeError(f"Initial mesh has no valid vertices: {path}")
    if face_array.ndim != 2 or face_array.shape[1] != 3:
        raise RuntimeError(f"Initial mesh has no valid faces: {path}")
    if not np.isfinite(vertex_array).all():
        raise RuntimeError(f"Initial mesh has non-finite vertices: {path}")
    return vertex_array, face_array


def apply_staged_initial_mesh(mesh, initial_mesh_path: Path) -> None:
    """Start from a dressed pose while preserving compiled garment topology."""
    vertices, faces = load_obj_geometry(initial_mesh_path)
    compiled_vertices = np.asarray(mesh.vertices, dtype=float)
    compiled_faces = np.asarray(mesh.faces, dtype=int)
    if vertices.shape != compiled_vertices.shape:
        raise RuntimeError(
            f"Staged initial mesh has {len(vertices)} vertices; the compiled "
            f"garment has {len(compiled_vertices)}."
        )
    if not np.array_equal(faces, compiled_faces):
        raise RuntimeError("Staged initial mesh does not match compiled garment faces.")
    mesh.vertices = vertices.tolist()


def apply_welded_staged_initial_mesh(
    mesh,
    pattern_path: Path,
    initial_mesh_path: Path,
    resolution_scale: float,
) -> None:
    """Transfer a collision-clean welded drape onto explicit material islands."""
    from pygarment.meshgen.boxmeshgen import BoxMesh

    vertices, faces = load_obj_geometry(initial_mesh_path)
    welded = BoxMesh(str(pattern_path), resolution_scale)
    welded.load(topology_mode="welded-bootstrap")
    welded_faces = np.asarray(welded.faces, dtype=int)
    if vertices.shape != np.asarray(welded.vertices, dtype=float).shape:
        raise RuntimeError(
            f"Welded staged mesh has {len(vertices)} vertices; the deterministic "
            f"welded topology has {len(welded.vertices)}."
        )
    if not np.array_equal(faces, welded_faces):
        raise RuntimeError(
            "Welded staged mesh does not match the deterministic welded topology."
        )

    transferred = np.asarray(mesh.vertices, dtype=float).copy()
    used_explicit_vertices = set(np.asarray(mesh.faces, dtype=int).reshape(-1).tolist())
    for explicit_index, locations in enumerate(mesh.verts_glob_loc):
        if len(locations) != 1:
            raise RuntimeError(
                "Explicit material topology must preserve one panel-local vertex "
                "per global vertex."
            )
        local = tuple(locations[0])
        welded_index = welded.verts_loc_glob.get(local)
        if welded_index is None:
            panel = welded.panels[local[0]]
            if local[1] >= panel.n_stitches:
                welded_index = local[1] + panel.glob_offset - panel.n_stitches
            elif explicit_index not in used_explicit_vertices:
                continue
            else:
                raise RuntimeError(
                    f"Welded staging topology is missing used local vertex {local}."
                )
        transferred[explicit_index] = vertices[welded_index]
    if not np.isfinite(transferred).all():
        raise RuntimeError("Transferred welded staging mesh contains non-finite vertices.")
    mesh.vertices = transferred.tolist()


def fit_panel_rigid_positions(
    source_vertices: np.ndarray,
    target_vertices: np.ndarray,
    panel_ids: list[str],
) -> tuple[np.ndarray, dict[str, float | int]]:
    """Fit each material panel to a dressed target without stretching it."""
    source = np.asarray(source_vertices, dtype=float)
    target = np.asarray(target_vertices, dtype=float)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 3:
        raise ValueError("Rigid panel fitting requires matching N by 3 vertex arrays.")
    if len(panel_ids) != len(source):
        raise ValueError("Rigid panel fitting requires one panel identity per vertex.")
    if not np.isfinite(source).all() or not np.isfinite(target).all():
        raise ValueError("Rigid panel fitting requires finite vertices.")

    fitted = source.copy()
    unique_panels = sorted(set(panel_ids))
    for panel in unique_panels:
        indices = np.asarray(
            [index for index, value in enumerate(panel_ids) if value == panel],
            dtype=int,
        )
        source_panel = source[indices]
        target_panel = target[indices]
        source_center = np.mean(source_panel, axis=0)
        target_center = np.mean(target_panel, axis=0)
        covariance = (source_panel - source_center).T @ (
            target_panel - target_center
        )
        left, _, right_transpose = np.linalg.svd(covariance)
        rotation = right_transpose.T @ left.T
        if np.linalg.det(rotation) < 0.0:
            right_transpose[-1, :] *= -1.0
            rotation = right_transpose.T @ left.T
        fitted[indices] = (
            (source_panel - source_center) @ rotation.T + target_center
        )

    target_distance = np.linalg.norm(fitted - target, axis=1)
    return fitted, {
        "panel_count": len(unique_panels),
        "target_root_mean_square_distance_cm": float(
            np.sqrt(np.mean(np.square(target_distance)))
        ),
        "maximum_target_distance_cm": float(target_distance.max(initial=0.0)),
    }


def apply_welded_rigid_panel_layout(
    mesh,
    pattern_path: Path,
    initial_mesh_path: Path,
    resolution_scale: float,
) -> dict[str, float | int]:
    """Place rest-shaped panels near a collision-clean welded drape."""
    from pygarment.meshgen.boxmeshgen import BoxMesh

    vertices, faces = load_obj_geometry(initial_mesh_path)
    welded = BoxMesh(str(pattern_path), resolution_scale)
    welded.load(topology_mode="welded-bootstrap")
    if vertices.shape != np.asarray(welded.vertices, dtype=float).shape:
        raise RuntimeError(
            f"Welded staged mesh has {len(vertices)} vertices; the deterministic "
            f"welded topology has {len(welded.vertices)}."
        )
    if not np.array_equal(faces, np.asarray(welded.faces, dtype=int)):
        raise RuntimeError(
            "Welded staged mesh does not match the deterministic welded topology."
        )

    target = np.asarray(mesh.vertices, dtype=float).copy()
    panel_ids: list[str] = []
    for explicit_index, locations in enumerate(mesh.verts_glob_loc):
        if len(locations) != 1:
            raise RuntimeError(
                "Rigid panel layout requires explicit one-panel material vertices."
            )
        local = tuple(locations[0])
        panel_ids.append(str(local[0]))
        welded_index = welded.verts_loc_glob.get(local)
        if welded_index is None:
            panel = welded.panels[local[0]]
            if local[1] >= panel.n_stitches:
                welded_index = local[1] + panel.glob_offset - panel.n_stitches
            else:
                raise RuntimeError(
                    f"Welded staging topology is missing local vertex {local}."
                )
        target[explicit_index] = vertices[welded_index]

    fitted, diagnostics = fit_panel_rigid_positions(
        np.asarray(mesh.vertices, dtype=float),
        target,
        panel_ids,
    )
    mesh.vertices = fitted.tolist()
    return diagnostics


def transfer_drape_by_panel_barycentric(
    source_mesh,
    target_mesh,
    source_vertices: np.ndarray,
) -> dict[str, float | int]:
    """Transfer a dressed surface between material meshes in panel space."""
    import igl

    source_vertices = np.asarray(source_vertices, dtype=float)
    if source_vertices.shape != np.asarray(source_mesh.vertices, dtype=float).shape:
        raise RuntimeError("Remesh source positions do not match source topology.")
    if set(source_mesh.panels) != set(target_mesh.panels):
        raise RuntimeError("Remesh source and target do not contain the same panels.")

    transferred = np.asarray(target_mesh.vertices, dtype=float).copy()
    maximum_material_distance = 0.0
    for panel_name in sorted(target_mesh.panels):
        source_panel = source_mesh.panels[panel_name]
        target_panel = target_mesh.panels[panel_name]
        source_material = np.column_stack(
            [
                np.asarray(source_panel.panel_vertices, dtype=float),
                np.zeros(len(source_panel.panel_vertices), dtype=float),
            ]
        )
        target_material = np.column_stack(
            [
                np.asarray(target_panel.panel_vertices, dtype=float),
                np.zeros(len(target_panel.panel_vertices), dtype=float),
            ]
        )
        source_faces = np.asarray(source_panel.panel_faces, dtype=np.int64)
        squared_distance, triangle_indices, closest = (
            igl.point_mesh_squared_distance(
                target_material,
                source_material,
                source_faces,
            )
        )
        maximum_material_distance = max(
            maximum_material_distance,
            float(np.sqrt(squared_distance).max(initial=0.0)),
        )
        triangles = source_faces[triangle_indices]
        barycentric = igl.barycentric_coordinates(
            closest,
            source_material[triangles[:, 0]],
            source_material[triangles[:, 1]],
            source_material[triangles[:, 2]],
        )
        source_global = np.asarray(
            [
                source_mesh.verts_loc_glob[(panel_name, local_index)]
                for local_index in range(len(source_panel.panel_vertices))
            ],
            dtype=int,
        )
        source_dressed = source_vertices[source_global]
        target_dressed = np.sum(
            source_dressed[triangles] * barycentric[:, :, None],
            axis=1,
        )
        target_global = np.asarray(
            [
                target_mesh.verts_loc_glob[(panel_name, local_index)]
                for local_index in range(len(target_panel.panel_vertices))
            ],
            dtype=int,
        )
        transferred[target_global] = target_dressed

    if not np.isfinite(transferred).all():
        raise RuntimeError("Panel-space remesh transfer produced non-finite vertices.")
    target_mesh.vertices = transferred.tolist()
    return {
        "panel_count": len(target_mesh.panels),
        "source_vertex_count": len(source_vertices),
        "target_vertex_count": len(transferred),
        "maximum_material_projection_distance_cm": maximum_material_distance,
    }


def apply_explicit_remeshed_initial_mesh(
    mesh,
    pattern_path: Path,
    initial_mesh_path: Path,
    source_resolution_scale: float,
    source_pattern_path: Path | None = None,
) -> dict[str, object]:
    """Transfer an explicit dressed surface to a new material resolution."""
    from pygarment.meshgen.boxmeshgen import BoxMesh

    vertices, faces = load_obj_geometry(initial_mesh_path)
    effective_source_pattern = source_pattern_path or pattern_path
    source = BoxMesh(str(effective_source_pattern), source_resolution_scale)
    source.load(topology_mode="explicit")
    if vertices.shape != np.asarray(source.vertices, dtype=float).shape:
        raise RuntimeError(
            f"Explicit remesh source has {len(vertices)} vertices; deterministic "
            f"source topology has {len(source.vertices)}."
        )
    if not np.array_equal(faces, np.asarray(source.faces, dtype=int)):
        raise RuntimeError(
            "Explicit remesh source does not match deterministic source topology."
        )
    diagnostics = transfer_drape_by_panel_barycentric(source, mesh, vertices)
    diagnostics["source_pattern_path"] = str(effective_source_pattern)
    diagnostics["source_pattern_sha256"] = hashlib.sha256(
        effective_source_pattern.read_bytes()
    ).hexdigest()
    return diagnostics


def transfer_positions_by_panel_identity(
    source_mesh,
    target_mesh,
    source_vertices: np.ndarray,
    max_weld_separation_cm: float,
) -> dict[str, float | int]:
    """Transfer a staged drape while collapsing only close sewn counterparts."""

    if not np.isfinite(max_weld_separation_cm) or max_weld_separation_cm <= 0.0:
        raise ValueError("Maximum staged weld separation must be positive and finite.")
    source_vertices = np.asarray(source_vertices, dtype=float)
    if source_vertices.shape != np.asarray(source_mesh.vertices, dtype=float).shape:
        raise RuntimeError("Staged source vertices do not match source material topology.")

    transferred = np.asarray(target_mesh.vertices, dtype=float).copy()
    welded_vertex_count = 0
    welded_source_vertex_count = 0
    separations: list[float] = []
    for target_index, locations in enumerate(target_mesh.verts_glob_loc):
        source_indices: list[int] = []
        for location in locations:
            source_index = source_mesh.verts_loc_glob.get(tuple(location))
            if source_index is None:
                raise RuntimeError(
                    "Staged source topology is missing panel-local vertex "
                    f"{tuple(location)!r}."
                )
            source_indices.append(int(source_index))
        if not source_indices:
            raise RuntimeError(
                f"Target vertex {target_index} has no panel-local ownership."
            )

        unique_source_indices = sorted(set(source_indices))
        positions = source_vertices[unique_source_indices]
        if len(unique_source_indices) > 1:
            pairwise = positions[:, None, :] - positions[None, :, :]
            maximum_separation = float(
                np.max(np.linalg.norm(pairwise, axis=2))
            )
            separations.append(maximum_separation)
            if maximum_separation > max_weld_separation_cm:
                raise RuntimeError(
                    "Refusing to weld a staged seam whose source vertices are "
                    f"{maximum_separation:.4f} cm apart; limit is "
                    f"{max_weld_separation_cm:.4f} cm."
                )
            welded_vertex_count += 1
            welded_source_vertex_count += len(unique_source_indices)
        transferred[target_index] = np.mean(positions, axis=0)

    if not np.isfinite(transferred).all():
        raise RuntimeError("Transferred staged topology contains non-finite vertices.")
    target_mesh.vertices = transferred.tolist()
    return {
        "welded_vertex_count": welded_vertex_count,
        "welded_source_vertex_count": welded_source_vertex_count,
        "maximum_input_separation_cm": max(separations, default=0.0),
        "mean_input_separation_cm": float(np.mean(separations)) if separations else 0.0,
    }


def apply_explicit_staged_initial_mesh(
    mesh,
    pattern_path: Path,
    initial_mesh_path: Path,
    resolution_scale: float,
    max_weld_separation_cm: float,
) -> dict[str, float | int]:
    """Transfer a closed explicit drape into continuous hybrid seam topology."""

    from pygarment.meshgen.boxmeshgen import BoxMesh

    vertices, faces = load_obj_geometry(initial_mesh_path)
    explicit = BoxMesh(str(pattern_path), resolution_scale)
    explicit.load(topology_mode="explicit")
    explicit_faces = np.asarray(explicit.faces, dtype=int)
    if vertices.shape != np.asarray(explicit.vertices, dtype=float).shape:
        raise RuntimeError(
            f"Explicit staged mesh has {len(vertices)} vertices; the deterministic "
            f"explicit topology has {len(explicit.vertices)}."
        )
    if not np.array_equal(faces, explicit_faces):
        raise RuntimeError(
            "Explicit staged mesh does not match the deterministic explicit topology."
        )
    return transfer_positions_by_panel_identity(
        explicit,
        mesh,
        vertices,
        max_weld_separation_cm,
    )


def evaluate_acceptance(
    *,
    finite_positions: bool,
    equilibrium_gate_evaluated: bool,
    static_equilibrium_reached: bool,
    edge_contact_buffer_saturated: bool,
    maximum_observed_edge_contacts: int,
    edge_contact_capacity: int,
    body_collisions: int | None,
    self_collisions: int | None,
    seam_link_count: int,
    maximum_seam_separation_cm: float | None,
    max_seam_separation_cm: float,
    maximum_edge_strain_ratio: float | None,
    ninety_fifth_percentile_edge_strain_ratio: float | None,
    ninety_ninth_point_ninth_percentile_edge_strain_ratio: float | None,
    max_body_collisions: int,
    max_self_collisions: int,
    max_edge_strain_ratio: float,
    max_ninety_fifth_percentile_edge_strain_ratio: float,
    max_ninety_ninth_point_ninth_percentile_edge_strain_ratio: float,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not finite_positions:
        reasons.append("solver output contains non-finite vertex positions")
    if not equilibrium_gate_evaluated:
        reasons.append("static-equilibrium gate was not evaluated")
    elif not static_equilibrium_reached:
        reasons.append("solver did not reach static equilibrium")
    if edge_contact_buffer_saturated:
        reasons.append(
            "edge contact buffer saturated at "
            f"{maximum_observed_edge_contacts} contacts with capacity "
            f"{edge_contact_capacity}"
        )
    if body_collisions is None or self_collisions is None:
        reasons.append("collision gate was not evaluated")
    else:
        if body_collisions > max_body_collisions:
            reasons.append(
                f"body intersections {body_collisions} exceed limit {max_body_collisions}"
            )
        if self_collisions > max_self_collisions:
            reasons.append(
                f"self intersections {self_collisions} exceed limit {max_self_collisions}"
            )
    if seam_link_count <= 0 or maximum_seam_separation_cm is None:
        reasons.append("explicit seam-closure gate was not evaluated")
    elif maximum_seam_separation_cm > max_seam_separation_cm:
        reasons.append(
            "maximum seam separation "
            f"{maximum_seam_separation_cm:.3f} cm exceeds limit "
            f"{max_seam_separation_cm:.3f} cm"
        )
    if (
        maximum_edge_strain_ratio is None
        or ninety_fifth_percentile_edge_strain_ratio is None
        or ninety_ninth_point_ninth_percentile_edge_strain_ratio is None
    ):
        reasons.append("edge-strain gate was not evaluated")
    else:
        if maximum_edge_strain_ratio > max_edge_strain_ratio:
            reasons.append(
                "peak edge strain "
                f"{maximum_edge_strain_ratio:.3f} exceeds limit "
                f"{max_edge_strain_ratio:.3f}"
            )
        if (
            ninety_fifth_percentile_edge_strain_ratio
            > max_ninety_fifth_percentile_edge_strain_ratio
        ):
            reasons.append(
                "95th-percentile edge strain "
                f"{ninety_fifth_percentile_edge_strain_ratio:.3f} exceeds limit "
                f"{max_ninety_fifth_percentile_edge_strain_ratio:.3f}"
            )
        if (
            ninety_ninth_point_ninth_percentile_edge_strain_ratio
            > max_ninety_ninth_point_ninth_percentile_edge_strain_ratio
        ):
            reasons.append(
                "99.9th-percentile edge strain "
                f"{ninety_ninth_point_ninth_percentile_edge_strain_ratio:.3f} exceeds limit "
                f"{max_ninety_ninth_point_ninth_percentile_edge_strain_ratio:.3f}"
            )
    return not reasons, reasons


def evaluate_static_quality(
    *,
    body_collisions: int | None,
    self_collisions: int | None,
    seam_link_count: int,
    maximum_seam_separation_cm: float | None,
    max_seam_separation_cm: float,
    maximum_edge_strain_ratio: float,
    ninety_fifth_percentile_edge_strain_ratio: float,
    ninety_ninth_point_ninth_percentile_edge_strain_ratio: float,
    max_body_collisions: int,
    max_self_collisions: int,
    max_edge_strain_ratio: float,
    max_ninety_fifth_percentile_edge_strain_ratio: float,
    max_ninety_ninth_point_ninth_percentile_edge_strain_ratio: float,
) -> list[str]:
    reasons: list[str] = []
    if body_collisions is None or self_collisions is None:
        reasons.append("collision gate was not evaluated")
    else:
        if body_collisions > max_body_collisions:
            reasons.append(f"{body_collisions} body intersections")
        if self_collisions > max_self_collisions:
            reasons.append(f"{self_collisions} self intersections")
    if seam_link_count <= 0 or maximum_seam_separation_cm is None:
        reasons.append("explicit seam closure unavailable")
    elif maximum_seam_separation_cm > max_seam_separation_cm:
        reasons.append(
            "maximum seam separation "
            f"{maximum_seam_separation_cm:.3f} cm"
        )
    if maximum_edge_strain_ratio > max_edge_strain_ratio:
        reasons.append(f"peak strain {maximum_edge_strain_ratio:.3f}")
    if (
        ninety_fifth_percentile_edge_strain_ratio
        > max_ninety_fifth_percentile_edge_strain_ratio
    ):
        reasons.append(
            "95th-percentile strain "
            f"{ninety_fifth_percentile_edge_strain_ratio:.3f}"
        )
    if (
        ninety_ninth_point_ninth_percentile_edge_strain_ratio
        > max_ninety_ninth_point_ninth_percentile_edge_strain_ratio
    ):
        reasons.append(
            "99.9th-percentile strain "
            f"{ninety_ninth_point_ninth_percentile_edge_strain_ratio:.3f}"
        )
    return reasons


def evaluate_seam_closure(
    vertices: np.ndarray,
    seam_links: list[tuple[int, int]],
) -> tuple[float | None, float | None, float | None, list[int] | None]:
    """Measure the physical gap across every explicit sewing correspondence."""
    if not seam_links:
        return None, None, None, None

    links = np.asarray(seam_links, dtype=int)
    if links.ndim != 2 or links.shape[1] != 2:
        raise RuntimeError("Explicit seam links must be vertex-index pairs.")
    if np.any(links < 0) or np.any(links >= len(vertices)):
        raise RuntimeError("Explicit seam link references a missing cloth vertex.")
    if np.any(links[:, 0] == links[:, 1]):
        raise RuntimeError("Explicit seam link endpoints must remain distinct.")

    separation = np.linalg.norm(
        vertices[links[:, 1]] - vertices[links[:, 0]],
        axis=1,
    )
    if not np.isfinite(separation).all():
        raise RuntimeError("Explicit seam closure contains non-finite distances.")
    maximum_index = int(np.argmax(separation))
    return (
        float(separation[maximum_index]),
        float(np.mean(separation)),
        float(np.percentile(separation, 95.0)),
        links[maximum_index].astype(int).tolist(),
    )


def interpolate_animated_body(
    start_vertices: np.ndarray,
    target_vertices: np.ndarray,
    frame: int,
    animation_frames: int,
) -> tuple[np.ndarray, float]:
    if start_vertices.shape != target_vertices.shape:
        raise ValueError("Animated body meshes do not share stable topology.")
    if animation_frames < 1:
        raise ValueError("Body animation requires at least one frame.")
    linear_progress = min(max((frame + 1) / animation_frames, 0.0), 1.0)
    smooth_progress = linear_progress * linear_progress * (3.0 - 2.0 * linear_progress)
    return (
        start_vertices + (target_vertices - start_vertices) * smooth_progress,
        smooth_progress,
    )


def evaluate_edge_strain(
    initial_vertices: np.ndarray,
    final_vertices: np.ndarray,
    faces: np.ndarray,
    material_rest_lengths: dict[tuple[int, int], float] | None = None,
) -> tuple[
    float,
    float,
    float,
    int,
    int,
    int,
    list[int],
    list[float],
    list[float],
]:
    triangle_edges = np.concatenate(
        (
            faces[:, (0, 1)],
            faces[:, (1, 2)],
            faces[:, (2, 0)],
        ),
        axis=0,
    )
    triangle_edges.sort(axis=1)
    edges = np.unique(triangle_edges, axis=0)
    rest_lengths = np.linalg.norm(
        initial_vertices[edges[:, 1]] - initial_vertices[edges[:, 0]],
        axis=1,
    )
    material_edge_count = 0
    if material_rest_lengths:
        for edge_index, (first, second) in enumerate(edges):
            key = (int(first), int(second))
            if key not in material_rest_lengths:
                continue
            material_length = float(material_rest_lengths[key])
            if not np.isfinite(material_length) or material_length <= 1.0e-6:
                raise RuntimeError(
                    f"Material rest length for edge {key} is invalid: "
                    f"{material_length!r}"
                )
            rest_lengths[edge_index] = material_length
            material_edge_count += 1
    valid_edges = rest_lengths > 1.0e-6
    if not np.any(valid_edges):
        raise RuntimeError("The garment mesh has no finite-length edges.")

    edges = edges[valid_edges]
    rest_lengths = rest_lengths[valid_edges]
    final_lengths = np.linalg.norm(
        final_vertices[edges[:, 1]] - final_vertices[edges[:, 0]],
        axis=1,
    )
    strain = np.abs((final_lengths / rest_lengths) - 1.0)
    maximum_index = int(np.argmax(strain))
    maximum_edge = edges[maximum_index]
    return (
        float(np.max(strain)),
        float(np.percentile(strain, 95.0)),
        float(np.percentile(strain, 99.9)),
        int(strain.size),
        material_edge_count,
        int(strain.size) - material_edge_count,
        [int(maximum_edge[0]), int(maximum_edge[1])],
        np.mean(initial_vertices[maximum_edge], axis=0).astype(float).tolist(),
        np.mean(final_vertices[maximum_edge], axis=0).astype(float).tolist(),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pattern",
        type=Path,
        default=Path("PatternaUnreal/SourceAssets/GarmentCode/PatternaFemaleCrewNeck.specification.json"),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("PatternaUnreal/SourceAssets/GarmentCode/PatternaWarpPrefit.yaml"),
    )
    parser.add_argument("--body", default="mean_female")
    parser.add_argument(
        "--body-obj",
        type=Path,
        help="Revision-specific GarmentCode body mesh. Requires the matching YAML and segmentation files.",
    )
    parser.add_argument("--body-measurements", type=Path)
    parser.add_argument("--body-segmentation", type=Path)
    parser.add_argument(
        "--body-start-obj",
        type=Path,
        help=(
            "Topology-identical starting body for collision-driven kinematic pose "
            "animation toward --body-obj."
        ),
    )
    parser.add_argument(
        "--body-animation-frames",
        type=int,
        default=0,
        help="Frames used to animate --body-start-obj into --body-obj.",
    )
    parser.add_argument(
        "--body-start-radial-scale",
        type=float,
        help=(
            "Create an in-memory narrow mannequin with identical topology, "
            "then inflate it toward the exact body."
        ),
    )
    parser.add_argument(
        "--body-animation-delay-frames",
        type=int,
        default=0,
        help="Assembly frames completed before mannequin inflation begins.",
    )
    parser.add_argument(
        "--initial-arrangement",
        type=Path,
        help="Compiler-generated body-aware sewn shell used as the solver start state.",
    )
    parser.add_argument(
        "--initial-mesh",
        type=Path,
        help="Topology-identical dressed mesh used as a staged pose start state.",
    )
    parser.add_argument(
        "--initial-welded-mesh",
        type=Path,
        help=(
            "Collision-clean welded drape transferred by panel-local identity "
            "onto explicit material topology."
        ),
    )
    parser.add_argument(
        "--initial-welded-rigid-layout",
        type=Path,
        help=(
            "Collision-clean welded drape used only to rigidly place each "
            "unstretched explicit material panel before progressive sewing."
        ),
    )
    parser.add_argument(
        "--initial-explicit-remesh",
        type=Path,
        help=(
            "Collision-clean explicit drape transferred in material panel space "
            "onto the selected mesh resolution."
        ),
    )
    parser.add_argument(
        "--initial-explicit-remesh-resolution",
        type=float,
        help="Mesh resolution in centimeters used by --initial-explicit-remesh.",
    )
    parser.add_argument(
        "--initial-explicit-source-pattern",
        type=Path,
        help=(
            "Pattern specification that owns the topology of "
            "--initial-explicit-remesh. Defaults to the target pattern."
        ),
    )
    parser.add_argument(
        "--initial-explicit-mesh",
        type=Path,
        help=(
            "Collision-clean explicit panel drape transferred by panel-local "
            "identity into the selected continuous seam topology."
        ),
    )
    parser.add_argument(
        "--assemble-body-shell",
        action="store_true",
        help=(
            "Initialize the cup-aware panels as a sewn shell around the exact "
            "body instead of detached placement slabs."
        ),
    )
    parser.add_argument(
        "--shell-clearance-cm",
        type=float,
        default=1.5,
        help="Radial clearance outside the measured torso for shell assembly.",
    )
    parser.add_argument(
        "--shell-bootstrap-rest",
        action="store_true",
        help=(
            "Use the assembled shell as a temporary rest pose for collision "
            "relaxation. This is a staging pass, not physical acceptance."
        ),
    )
    parser.add_argument(
        "--rest-lengths",
        type=Path,
        help="Original GarmentCode edge-length pickle paired with --initial-mesh.",
    )
    parser.add_argument(
        "--strain-reference-mesh",
        type=Path,
        help="Original box mesh used to evaluate full pattern-to-pose strain.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        help="Isolated output directory for this simulation revision.",
    )
    parser.add_argument("--frames", type=int, default=None)
    parser.add_argument(
        "--topology-mode",
        choices=("explicit", "hybrid-seams", "welded-bootstrap"),
        default="explicit",
        help="Garment topology used by this solver pass.",
    )
    parser.add_argument("--rebuild-mesh", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--count-collisions", action="store_true")
    parser.add_argument("--stop-when-static", action="store_true")
    parser.add_argument(
        "--max-seam-separation-cm",
        type=float,
        default=0.25,
        help="Maximum accepted distance between paired seam vertices in centimeters.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help=(
            "Warp execution device. 'auto' selects the first CUDA device and "
            "falls back to CPU only when no CUDA runtime is available."
        ),
    )
    return parser.parse_args()


def configure_warp_device(wp, requested_device: str):
    available_devices = list(wp.get_devices())
    if not available_devices:
        raise RuntimeError("Warp reported no execution devices.")

    if requested_device == "auto":
        selected_device = next(
            (device for device in available_devices if device.is_cuda),
            available_devices[0],
        )
    else:
        selected_device = next(
            (
                device
                for device in available_devices
                if str(device) == requested_device
            ),
            None,
        )
        if selected_device is None:
            available = ", ".join(str(device) for device in available_devices)
            raise RuntimeError(
                f"Requested Warp device {requested_device!r} is unavailable. "
                f"Available devices: {available}."
            )

    wp.set_device(selected_device)
    return selected_device, available_devices


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    garmentcode_root = repo_root / "third_party" / "GarmentCode"
    pattern_path = (repo_root / args.pattern).resolve() if not args.pattern.is_absolute() else args.pattern
    config_path = (repo_root / args.config).resolve() if not args.config.is_absolute() else args.config
    explicit_body_paths = (
        args.body_obj,
        args.body_measurements,
        args.body_segmentation,
    )
    body_start_sources = (
        args.body_start_obj,
        args.body_start_radial_scale,
    )
    if sum(value is not None for value in body_start_sources) > 1:
        raise ValueError(
            "--body-start-obj and --body-start-radial-scale are mutually exclusive."
        )
    if (not any(value is not None for value in body_start_sources)) != (
        args.body_animation_frames == 0
    ):
        raise ValueError(
            "A body start source and positive --body-animation-frames value "
            "must be supplied together."
        )
    if args.body_animation_delay_frames < 0:
        raise ValueError("--body-animation-delay-frames cannot be negative.")
    if args.body_start_radial_scale is not None and not (
        0.1 <= args.body_start_radial_scale < 1.0
    ):
        raise ValueError("--body-start-radial-scale must be between 0.1 and 1.0.")
    staged_paths = (
        args.initial_mesh,
        args.rest_lengths,
        args.strain_reference_mesh,
    )
    if any(staged_paths) and not all(staged_paths):
        raise ValueError(
            "--initial-mesh, --rest-lengths, and --strain-reference-mesh "
            "must be supplied together."
        )
    initial_sources = (
        args.initial_arrangement,
        args.initial_mesh,
        args.initial_welded_mesh,
        args.initial_welded_rigid_layout,
        args.initial_explicit_remesh,
        args.initial_explicit_mesh,
        True if args.assemble_body_shell else None,
    )
    if sum(value is not None for value in initial_sources) > 1:
        raise ValueError("Initial arrangement and staged mesh sources are mutually exclusive.")
    if (args.initial_explicit_remesh is None) != (
        args.initial_explicit_remesh_resolution is None
    ):
        raise ValueError(
            "--initial-explicit-remesh and --initial-explicit-remesh-resolution "
            "must be supplied together."
        )
    if (
        args.initial_explicit_remesh_resolution is not None
        and (
            not np.isfinite(args.initial_explicit_remesh_resolution)
            or args.initial_explicit_remesh_resolution <= 0.0
        )
    ):
        raise ValueError("Explicit remesh source resolution must be positive and finite.")
    if (
        args.initial_explicit_source_pattern is not None
        and args.initial_explicit_remesh is None
    ):
        raise ValueError(
            "--initial-explicit-source-pattern requires --initial-explicit-remesh."
        )
    if not np.isfinite(args.max_seam_separation_cm) or args.max_seam_separation_cm <= 0:
        raise ValueError("--max-seam-separation-cm must be a positive finite value.")
    if not np.isfinite(args.shell_clearance_cm) or args.shell_clearance_cm <= 0:
        raise ValueError("--shell-clearance-cm must be a positive finite value.")
    if any(explicit_body_paths) and not all(explicit_body_paths):
        raise ValueError(
            "--body-obj, --body-measurements, and --body-segmentation must be supplied together."
        )
    if args.assemble_body_shell and not all(explicit_body_paths):
        raise ValueError(
            "--assemble-body-shell requires the exact body OBJ, measurements, "
            "and segmentation files."
        )
    if args.shell_bootstrap_rest and not args.assemble_body_shell:
        raise ValueError(
            "--shell-bootstrap-rest requires --assemble-body-shell."
        )
    body_obj_path = (
        (repo_root / args.body_obj).resolve()
        if args.body_obj is not None and not args.body_obj.is_absolute()
        else args.body_obj
    )
    body_measurements_path = (
        (repo_root / args.body_measurements).resolve()
        if args.body_measurements is not None and not args.body_measurements.is_absolute()
        else args.body_measurements
    )
    body_segmentation_path = (
        (repo_root / args.body_segmentation).resolve()
        if args.body_segmentation is not None and not args.body_segmentation.is_absolute()
        else args.body_segmentation
    )
    body_start_path = (
        (repo_root / args.body_start_obj).resolve()
        if args.body_start_obj is not None and not args.body_start_obj.is_absolute()
        else args.body_start_obj
    )
    output_directory = (
        (repo_root / args.output_directory).resolve()
        if args.output_directory is not None and not args.output_directory.is_absolute()
        else args.output_directory
    )
    initial_mesh_path = (
        (repo_root / args.initial_mesh).resolve()
        if args.initial_mesh is not None and not args.initial_mesh.is_absolute()
        else args.initial_mesh
    )
    initial_welded_mesh_path = (
        (repo_root / args.initial_welded_mesh).resolve()
        if args.initial_welded_mesh is not None
        and not args.initial_welded_mesh.is_absolute()
        else args.initial_welded_mesh
    )
    initial_welded_rigid_layout_path = (
        (repo_root / args.initial_welded_rigid_layout).resolve()
        if args.initial_welded_rigid_layout is not None
        and not args.initial_welded_rigid_layout.is_absolute()
        else args.initial_welded_rigid_layout
    )
    initial_explicit_remesh_path = (
        (repo_root / args.initial_explicit_remesh).resolve()
        if args.initial_explicit_remesh is not None
        and not args.initial_explicit_remesh.is_absolute()
        else args.initial_explicit_remesh
    )
    initial_explicit_source_pattern_path = (
        (repo_root / args.initial_explicit_source_pattern).resolve()
        if args.initial_explicit_source_pattern is not None
        and not args.initial_explicit_source_pattern.is_absolute()
        else args.initial_explicit_source_pattern
    )
    initial_explicit_mesh_path = (
        (repo_root / args.initial_explicit_mesh).resolve()
        if args.initial_explicit_mesh is not None
        and not args.initial_explicit_mesh.is_absolute()
        else args.initial_explicit_mesh
    )
    rest_lengths_path = (
        (repo_root / args.rest_lengths).resolve()
        if args.rest_lengths is not None and not args.rest_lengths.is_absolute()
        else args.rest_lengths
    )
    strain_reference_path = (
        (repo_root / args.strain_reference_mesh).resolve()
        if args.strain_reference_mesh is not None
        and not args.strain_reference_mesh.is_absolute()
        else args.strain_reference_mesh
    )

    if not pattern_path.is_file():
        raise FileNotFoundError(pattern_path)
    if not config_path.is_file():
        raise FileNotFoundError(config_path)
    for explicit_path in explicit_body_paths:
        if explicit_path is not None:
            resolved = (
                (repo_root / explicit_path).resolve()
                if not explicit_path.is_absolute()
                else explicit_path
            )
            if not resolved.is_file():
                raise FileNotFoundError(resolved)
    for staged_path in (
        initial_mesh_path,
        initial_welded_mesh_path,
        initial_welded_rigid_layout_path,
        initial_explicit_remesh_path,
        initial_explicit_source_pattern_path,
        rest_lengths_path,
        strain_reference_path,
    ):
        if staged_path is not None and not staged_path.is_file():
            raise FileNotFoundError(staged_path)
    if body_start_path is not None and not body_start_path.is_file():
        raise FileNotFoundError(body_start_path)

    sys.path.insert(0, str(garmentcode_root))
    os.chdir(garmentcode_root)

    import warp as wp
    from pygarment import data_config
    from pygarment.meshgen.boxmeshgen import BoxMesh
    from pygarment.meshgen.garment import Cloth
    from pygarment.meshgen.render.pythonrender import render_images
    from pygarment.meshgen.sim_config import PathCofig, SimConfig

    wp.init()
    selected_device, available_devices = configure_warp_device(wp, args.device)
    print(
        "Patterna Warp device: "
        f"requested={args.device}, selected={selected_device}, "
        f"available={[str(device) for device in available_devices]}"
    )
    props = data_config.Properties(str(config_path))
    sim_values = props["sim"]["config"]
    material_values = sim_values["material"]
    frame_count = args.frames if args.frames is not None else int(sim_values["max_sim_steps"])

    output_root = output_directory or (
        repo_root / "PatternaUnreal" / "Saved" / "Patterna" / "GarmentCodeWarp"
    )
    output_root.mkdir(parents=True, exist_ok=True)
    work_input = output_root / "input"
    work_input.mkdir(parents=True, exist_ok=True)
    garment_name = pattern_path.stem.removesuffix(".specification").removesuffix("_specification")
    expected_pattern = work_input / f"{garment_name}_specification.json"
    shutil.copyfile(pattern_path, expected_pattern)

    paths = PathCofig(
        in_element_path=work_input,
        out_path=output_root,
        in_name=garment_name,
        body_name=args.body,
        smpl_body=False,
        add_timestamp=False,
    )
    if body_obj_path is not None:
        paths.in_body_obj = body_obj_path
        paths.in_body_mes = body_measurements_path
        paths.body_seg = body_segmentation_path

    mesh = BoxMesh(paths.in_g_spec, sim_values["resolution_scale"])
    staged_seam_transfer = None
    shell_assembly = None
    shell_bootstrap_rest = None
    if args.rebuild_mesh or not paths.g_box_mesh.is_file():
        print(f"Generating seam-aware box mesh for {garment_name}")
        mesh.load(topology_mode=args.topology_mode)
        if args.initial_arrangement is not None:
            arrangement_path = args.initial_arrangement.resolve()
            if not arrangement_path.is_file():
                raise FileNotFoundError(
                    f"Initial arrangement not found: {arrangement_path}"
                )
            apply_body_aware_initial_arrangement(mesh, arrangement_path)
            print(f"Applied body-aware initial arrangement {arrangement_path}")
        elif initial_mesh_path is not None:
            apply_staged_initial_mesh(mesh, initial_mesh_path)
            print(f"Applied staged dressed initial mesh {initial_mesh_path}")
        elif initial_welded_mesh_path is not None:
            apply_welded_staged_initial_mesh(
                mesh,
                pattern_path,
                initial_welded_mesh_path,
                sim_values["resolution_scale"],
            )
            print(
                "Transferred welded dressed pose onto explicit material topology "
                f"from {initial_welded_mesh_path}"
            )
        elif initial_welded_rigid_layout_path is not None:
            staged_seam_transfer = apply_welded_rigid_panel_layout(
                mesh,
                pattern_path,
                initial_welded_rigid_layout_path,
                sim_values["resolution_scale"],
            )
            print(
                "Rigidly placed unstretched material panels around the dressed "
                f"target from {initial_welded_rigid_layout_path}: "
                f"{staged_seam_transfer}"
            )
        elif initial_explicit_remesh_path is not None:
            if args.topology_mode != "explicit":
                raise ValueError(
                    "--initial-explicit-remesh requires explicit target topology."
                )
            staged_seam_transfer = apply_explicit_remeshed_initial_mesh(
                mesh,
                pattern_path,
                initial_explicit_remesh_path,
                args.initial_explicit_remesh_resolution,
                initial_explicit_source_pattern_path,
            )
            print(
                "Transferred explicit dressed surface into the selected material "
                f"resolution from {initial_explicit_remesh_path}: "
                f"{staged_seam_transfer}"
            )
        elif initial_explicit_mesh_path is not None:
            if args.topology_mode == "explicit":
                raise ValueError(
                    "--initial-explicit-mesh requires hybrid-seams or "
                    "welded-bootstrap topology."
                )
            staged_seam_transfer = apply_explicit_staged_initial_mesh(
                mesh,
                pattern_path,
                initial_explicit_mesh_path,
                sim_values["resolution_scale"],
                args.max_seam_separation_cm,
            )
            print(
                "Transferred collision-clean explicit drape into "
                f"{args.topology_mode} topology from {initial_explicit_mesh_path}: "
                f"{staged_seam_transfer}"
            )
        elif args.assemble_body_shell:
            body_vertices_cm = load_obj_vertices_centimeters(body_obj_path)
            segmentation = json.loads(
                body_segmentation_path.read_text(encoding="utf-8")
            )
            torso_indices = np.asarray(segmentation.get("body", []), dtype=int)
            if torso_indices.size == 0:
                raise RuntimeError(
                    "Body segmentation contains no torso-owned vertices."
                )
            if int(np.max(torso_indices)) >= len(body_vertices_cm):
                raise RuntimeError(
                    "Body segmentation references vertices outside the body mesh."
                )
            shell_assembly = assemble_body_aware_shell(
                mesh,
                body_vertices_cm[torso_indices],
                clearance_cm=args.shell_clearance_cm,
            ).as_dict()
            if args.shell_bootstrap_rest:
                shell_bootstrap_rest = set_current_geometry_rest_lengths(mesh)
            print(f"Assembled body-aware sewn shell: {shell_assembly}")
            if shell_bootstrap_rest is not None:
                print(
                    "Rebased temporary shell rest lengths for staging: "
                    f"{shell_bootstrap_rest}"
                )
        mesh.serialize(paths, store_panels=False, uv_config=props["render"]["config"]["uv_texture"])
        if rest_lengths_path is not None:
            shutil.copyfile(rest_lengths_path, paths.g_orig_edge_len)
            print(f"Restored pattern edge lengths from {rest_lengths_path}")
    else:
        print(f"Reusing {paths.g_box_mesh}")

    config = SimConfig(sim_values)
    started = time.perf_counter()
    garment = Cloth(garment_name, config, paths, caching=False)
    construction_seconds = time.perf_counter() - started
    body_animation_start = None
    body_animation_target = None
    body_animation_start_mode = None
    if body_start_path is not None:
        body_animation_target = np.asarray(garment.v_body, dtype=float).copy()
        start_vertices, _, start_faces = garment.load_obj(body_start_path)
        start_vertices = np.asarray(start_vertices, dtype=float) * garment.b_scale
        if garment.shift_y:
            start_vertices[:, 1] += garment.shift_y
        if not np.array_equal(start_faces, np.asarray(garment.f_body, dtype=int)):
            raise RuntimeError(
                "Animated start and target bodies do not share stable face topology."
            )
        if start_vertices.shape != body_animation_target.shape:
            raise RuntimeError(
                "Animated start and target bodies do not share stable vertex topology."
            )
        body_animation_start = start_vertices
        body_animation_start_mode = "mesh"
        garment.set_body_vertices(body_animation_start)
        print(
            "Initialized collision-driven body animation from "
            f"{body_start_path} over {args.body_animation_frames} frames"
        )
    elif args.body_start_radial_scale is not None:
        body_animation_target = np.asarray(garment.v_body, dtype=float).copy()
        body_animation_start = create_radially_scaled_body(
            body_animation_target,
            args.body_start_radial_scale,
        )
        body_animation_start_mode = "radial-scale"
        garment.set_body_vertices(body_animation_start)
        print(
            "Initialized narrow mannequin inflation with radial scale "
            f"{args.body_start_radial_scale:.3f}, delay "
            f"{args.body_animation_delay_frames} frames, and duration "
            f"{args.body_animation_frames} frames"
        )
    initial = np.asarray(garment.current_verts).copy()
    initial_body_intersections = (
        garment.count_body_intersections() if args.count_collisions else None
    )
    initial_self_intersections = (
        garment.count_self_intersections() if args.count_collisions else None
    )
    initial_body_intersection_locations = (
        garment.locate_body_intersections() if args.count_collisions else []
    )
    strain_reference = initial
    if strain_reference_path is not None:
        strain_reference, reference_faces = load_obj_geometry(strain_reference_path)
        if strain_reference.shape != initial.shape:
            raise RuntimeError(
                "Strain reference mesh does not match the simulated garment vertices."
            )
        if not np.array_equal(reference_faces, np.asarray(garment.f_cloth, dtype=int)):
            raise RuntimeError(
                "Strain reference mesh does not match the simulated garment faces."
            )
    effective_rest_lengths_path = rest_lengths_path or Path(paths.g_orig_edge_len)
    if not effective_rest_lengths_path.is_file():
        raise RuntimeError(
            "Material-space edge rest lengths are required for full-surface "
            f"strain validation: {effective_rest_lengths_path}"
        )
    with effective_rest_lengths_path.open("rb") as source:
        loaded_rest_lengths = pickle.load(source)
    if not isinstance(loaded_rest_lengths, dict) or not loaded_rest_lengths:
        raise RuntimeError("Material-space edge rest lengths are empty or malformed.")
    material_rest_lengths = {
        tuple(sorted((int(edge[0]), int(edge[1])))): float(length)
        for edge, length in loaded_rest_lengths.items()
    }
    physical_mesh_path = Path(paths.g_box_mesh).resolve()
    panel_ownership_path = Path(paths.g_mesh_segmentation).resolve()
    physical_identity = read_obj_topology(physical_mesh_path)
    physical_faces = np.asarray(physical_identity["position_faces"], dtype=np.int64)
    if int(physical_identity["vertex_count"]) != len(garment.v_cloth_init) or not np.array_equal(
        physical_faces,
        np.asarray(garment.f_cloth, dtype=np.int64),
    ):
        raise RuntimeError(
            "Serialized physical mesh identity does not match the topology consumed by Warp."
        )
    ownership_vertex_count = len(
        panel_ownership_path.read_text(encoding="utf-8").splitlines()
    )
    if ownership_vertex_count != int(physical_identity["vertex_count"]):
        raise RuntimeError(
            "Panel ownership record count does not match the physical particle count."
        )
    material_rest_graph_sha256, material_rest_graph_edge_count = (
        hash_material_rest_graph(material_rest_lengths)
    )
    seam_constraint_graph_sha256 = hash_seam_constraint_graph(
        args.topology_mode,
        str(physical_identity["surface_corner_mapping_sha256"]),
        garment.seam_link_records,
    )
    implementation_paths = {
        "tools/prefit_garmentcode_warp.py": Path(__file__).resolve(),
        "third_party/GarmentCode/pygarment/meshgen/boxmeshgen.py": (
            garmentcode_root / "pygarment" / "meshgen" / "boxmeshgen.py"
        ),
        "third_party/GarmentCode/pygarment/meshgen/garment.py": (
            garmentcode_root / "pygarment" / "meshgen" / "garment.py"
        ),
        "third_party/GarmentCode/pygarment/meshgen/sim_config.py": (
            garmentcode_root / "pygarment" / "meshgen" / "sim_config.py"
        ),
    }
    solver_implementation_sha256, solver_implementation_files = (
        implementation_identity(implementation_paths)
    )
    mesher_implementation_sha256 = solver_implementation_files[
        "third_party/GarmentCode/pygarment/meshgen/boxmeshgen.py"
    ]
    edge_contact_capacity = int(garment.model.edge_contact_max)
    maximum_observed_edge_contacts = 0

    frame_seconds: list[float] = []
    static_equilibrium_reached = False
    max_body_collisions = int(sim_values["max_body_collisions"])
    max_self_collisions = int(sim_values["max_self_collisions"])
    max_edge_strain_ratio = float(sim_values["max_edge_strain_ratio"])
    max_ninety_fifth_percentile_edge_strain_ratio = float(
        sim_values["max_ninety_fifth_percentile_edge_strain_ratio"]
    )
    max_ninety_ninth_point_ninth_percentile_edge_strain_ratio = float(
        sim_values["max_ninety_ninth_point_ninth_percentile_edge_strain_ratio"]
    )
    seam_link_count = len(garment.seam_links)
    seam_bending_constraint_count = getattr(
        garment,
        "seam_bending_constraint_count",
        0,
    )
    for frame in range(frame_count):
        frame_started = time.perf_counter()
        garment.frame = frame
        if body_animation_start is not None and body_animation_target is not None:
            animation_frame = frame - args.body_animation_delay_frames
            if animation_frame < 0:
                animated_body = body_animation_start
                animation_progress = 0.0
            else:
                animated_body, animation_progress = interpolate_animated_body(
                    body_animation_start,
                    body_animation_target,
                    animation_frame,
                    args.body_animation_frames,
                )
            garment.set_body_vertices(animated_body)
        garment.run_frame()
        observed_edge_contacts = int(garment.model.edge_contact_count.numpy()[0])
        maximum_observed_edge_contacts = max(
            maximum_observed_edge_contacts,
            observed_edge_contacts,
        )
        elapsed = time.perf_counter() - frame_started
        frame_seconds.append(elapsed)
        print(f"Frame {frame + 1}/{frame_count}: {elapsed:.3f}s")
        if (
            args.stop_when_static
            and frame >= config.zero_gravity_steps
            and frame >= config.min_sim_steps
            and frame
            >= args.body_animation_delay_frames + args.body_animation_frames
        ):
            is_static, non_static_count = garment.is_static()
            if is_static:
                candidate_body_collisions = None
                candidate_self_collisions = None
                if args.count_collisions:
                    candidate_body_collisions = garment.count_body_intersections()
                    candidate_self_collisions = garment.count_self_intersections()
                candidate_vertices = np.asarray(garment.current_verts)
                (
                    candidate_maximum_seam_separation_cm,
                    _,
                    _,
                    _,
                ) = evaluate_seam_closure(candidate_vertices, garment.seam_links)
                (
                    candidate_peak_strain,
                    candidate_p95_strain,
                    candidate_p999_strain,
                    _,
                    _,
                    _,
                    _,
                    _,
                    _,
                ) = evaluate_edge_strain(
                    strain_reference,
                    candidate_vertices,
                    np.asarray(garment.f_cloth),
                    material_rest_lengths,
                )
                quality_reasons = evaluate_static_quality(
                    body_collisions=candidate_body_collisions,
                    self_collisions=candidate_self_collisions,
                    seam_link_count=seam_link_count,
                    maximum_seam_separation_cm=(
                        candidate_maximum_seam_separation_cm
                    ),
                    max_seam_separation_cm=args.max_seam_separation_cm,
                    maximum_edge_strain_ratio=candidate_peak_strain,
                    ninety_fifth_percentile_edge_strain_ratio=candidate_p95_strain,
                    ninety_ninth_point_ninth_percentile_edge_strain_ratio=(
                        candidate_p999_strain
                    ),
                    max_body_collisions=max_body_collisions,
                    max_self_collisions=max_self_collisions,
                    max_edge_strain_ratio=max_edge_strain_ratio,
                    max_ninety_fifth_percentile_edge_strain_ratio=(
                        max_ninety_fifth_percentile_edge_strain_ratio
                    ),
                    max_ninety_ninth_point_ninth_percentile_edge_strain_ratio=(
                        max_ninety_ninth_point_ninth_percentile_edge_strain_ratio
                    ),
                )
                if not quality_reasons:
                    static_equilibrium_reached = True
                    print(
                        "Accepted static equilibrium reached with "
                        f"{non_static_count} moving vertices"
                    )
                    break
                print(
                    "Velocity is static but physical acceptance is still pending: "
                    + ", ".join(quality_reasons)
                )

    garment.save_frame(save_v_norms=False)
    final = np.asarray(garment.current_verts)
    output_mesh_path = Path(paths.g_sim).resolve()
    output_identity = read_obj_topology(output_mesh_path)
    if (
        int(output_identity["vertex_count"]) != int(physical_identity["vertex_count"])
        or int(output_identity["face_count"]) != int(physical_identity["face_count"])
        or str(output_identity["topology_sha256"])
        != str(physical_identity["topology_sha256"])
        or str(output_identity["surface_corner_mapping_sha256"])
        != str(physical_identity["surface_corner_mapping_sha256"])
    ):
        raise RuntimeError(
            "Warp output changed the physical topology or pattern-corner mapping."
        )
    displacement = np.linalg.norm(final - initial, axis=1)
    body_collisions = garment.count_body_intersections() if args.count_collisions else None
    self_collisions = garment.count_self_intersections() if args.count_collisions else None
    segmentation_labels = paths.g_mesh_segmentation.read_text(encoding="utf-8").splitlines()
    for location in initial_body_intersection_locations:
        location["vertex_labels"] = [
            segmentation_labels[index] for index in location["vertices"]
        ]
    self_intersection_locations = (
        garment.locate_self_intersections() if args.count_collisions else []
    )
    for location in self_intersection_locations:
        location["vertex_labels"] = [
            segmentation_labels[index] for index in location["vertices"]
        ]
        face_index = location["face_index"]
        face_vertices = [int(value) for value in garment.f_cloth[face_index]]
        location["face_vertices"] = face_vertices
        location["face_vertex_labels"] = [
            segmentation_labels[index] for index in face_vertices
        ]
    cloth_vertex_count = int(final.shape[0])
    body_vertex_count = int(np.asarray(garment.v_body).shape[0])
    body_face_count = int(np.asarray(garment.f_body).shape[0])
    body_collision_rate = (
        float(body_collisions) / cloth_vertex_count
        if body_collisions is not None and cloth_vertex_count > 0
        else None
    )
    self_collision_rate = (
        float(self_collisions) / cloth_vertex_count
        if self_collisions is not None and cloth_vertex_count > 0
        else None
    )
    finite_positions = bool(np.isfinite(final).all())
    maximum_seam_separation_cm = None
    mean_seam_separation_cm = None
    ninety_fifth_percentile_seam_separation_cm = None
    maximum_seam_separation_edge_vertices = None
    if finite_positions:
        (
            maximum_seam_separation_cm,
            mean_seam_separation_cm,
            ninety_fifth_percentile_seam_separation_cm,
            maximum_seam_separation_edge_vertices,
        ) = evaluate_seam_closure(final, garment.seam_links)
    maximum_edge_strain_ratio = None
    ninety_fifth_percentile_edge_strain_ratio = None
    ninety_ninth_point_ninth_percentile_edge_strain_ratio = None
    evaluated_edge_count = 0
    material_rest_length_edge_count = 0
    reference_geometry_edge_count = 0
    maximum_strain_edge_vertices = None
    maximum_strain_initial_midpoint_cm = None
    maximum_strain_final_midpoint_cm = None
    if finite_positions:
        (
            maximum_edge_strain_ratio,
            ninety_fifth_percentile_edge_strain_ratio,
            ninety_ninth_point_ninth_percentile_edge_strain_ratio,
            evaluated_edge_count,
            material_rest_length_edge_count,
            reference_geometry_edge_count,
            maximum_strain_edge_vertices,
            maximum_strain_initial_midpoint_cm,
            maximum_strain_final_midpoint_cm,
        ) = evaluate_edge_strain(
            strain_reference,
            final,
            np.asarray(garment.f_cloth),
            material_rest_lengths,
        )
    maximum_strain_panel_labels = (
        sorted(
            {
                segmentation_labels[index]
                for index in maximum_strain_edge_vertices
            }
        )
        if maximum_strain_edge_vertices is not None
        else []
    )
    maximum_seam_separation_panel_labels = (
        sorted(
            {
                segmentation_labels[index]
                for index in maximum_seam_separation_edge_vertices
            }
        )
        if maximum_seam_separation_edge_vertices is not None
        else []
    )
    collision_gate_evaluated = body_collisions is not None and self_collisions is not None
    edge_contact_buffer_saturated = (
        maximum_observed_edge_contacts >= edge_contact_capacity
    )
    accepted, rejection_reasons = evaluate_acceptance(
        finite_positions=finite_positions,
        equilibrium_gate_evaluated=args.stop_when_static,
        static_equilibrium_reached=static_equilibrium_reached,
        edge_contact_buffer_saturated=edge_contact_buffer_saturated,
        maximum_observed_edge_contacts=maximum_observed_edge_contacts,
        edge_contact_capacity=edge_contact_capacity,
        body_collisions=body_collisions,
        self_collisions=self_collisions,
        seam_link_count=seam_link_count,
        maximum_seam_separation_cm=maximum_seam_separation_cm,
        max_seam_separation_cm=args.max_seam_separation_cm,
        maximum_edge_strain_ratio=maximum_edge_strain_ratio,
        ninety_fifth_percentile_edge_strain_ratio=(
            ninety_fifth_percentile_edge_strain_ratio
        ),
        ninety_ninth_point_ninth_percentile_edge_strain_ratio=(
            ninety_ninth_point_ninth_percentile_edge_strain_ratio
        ),
        max_body_collisions=max_body_collisions,
        max_self_collisions=max_self_collisions,
        max_edge_strain_ratio=max_edge_strain_ratio,
        max_ninety_fifth_percentile_edge_strain_ratio=(
            max_ninety_fifth_percentile_edge_strain_ratio
        ),
        max_ninety_ninth_point_ninth_percentile_edge_strain_ratio=(
            max_ninety_ninth_point_ninth_percentile_edge_strain_ratio
        ),
    )
    render_error = None
    if args.render:
        try:
            render_images(paths, garment.v_body, garment.f_body, props["render"]["config"])
        except Exception as exc:
            render_error = f"{type(exc).__name__}: {exc}"
            print(f"Legacy OpenGL renderer unavailable: {render_error}")
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "garment_topology_mode": args.topology_mode,
        "pattern_specification_path": str(expected_pattern.resolve()),
        "pattern_specification_sha256": _sha256_file(expected_pattern.resolve()),
        "mesh_resolution_cm": float(sim_values["resolution_scale"]),
        "physical_mesh_path": str(physical_mesh_path),
        "physical_mesh_sha256": _sha256_file(physical_mesh_path),
        "physical_topology_sha256": physical_identity["topology_sha256"],
        "physical_vertex_count": physical_identity["vertex_count"],
        "physical_face_count": physical_identity["face_count"],
        "texture_vertex_count": physical_identity["texture_vertex_count"],
        "welded_vertex_reduction": (
            int(physical_identity["texture_vertex_count"])
            - int(physical_identity["vertex_count"])
        ),
        "surface_corner_mapping_sha256": physical_identity[
            "surface_corner_mapping_sha256"
        ],
        "panel_ownership_path": str(panel_ownership_path),
        "panel_ownership_sha256": _sha256_file(panel_ownership_path),
        "panel_ownership_vertex_count": ownership_vertex_count,
        "seam_constraint_graph_sha256": seam_constraint_graph_sha256,
        "material_rest_graph_sha256": material_rest_graph_sha256,
        "material_rest_graph_edge_count": material_rest_graph_edge_count,
        "mesher_implementation_sha256": mesher_implementation_sha256,
        "solver_implementation_sha256": solver_implementation_sha256,
        "solver_implementation_files": solver_implementation_files,
        "accepted": accepted,
        "finite_positions": finite_positions,
        "equilibrium_gate_evaluated": args.stop_when_static,
        "static_equilibrium_reached": static_equilibrium_reached,
        "edge_contact_buffer_saturated": edge_contact_buffer_saturated,
        "maximum_observed_edge_contacts": maximum_observed_edge_contacts,
        "edge_contact_capacity": edge_contact_capacity,
        "edge_contacts_per_spring": config.edge_contacts_per_spring,
        "collision_gate_evaluated": collision_gate_evaluated,
        "seam_closure_gate_evaluated": seam_link_count > 0,
        "rejection_reasons": rejection_reasons,
        "body": args.body,
        "body_mesh_path": str(paths.in_body_obj.resolve()),
        "body_mesh_sha256": hashlib.sha256(paths.in_body_obj.read_bytes()).hexdigest(),
        "body_measurements_path": str(paths.in_body_mes.resolve()),
        "body_measurements_sha256": hashlib.sha256(paths.in_body_mes.read_bytes()).hexdigest(),
        "body_segmentation_path": str(paths.body_seg.resolve()),
        "body_segmentation_sha256": hashlib.sha256(paths.body_seg.read_bytes()).hexdigest(),
        "body_animation_start_path": str(body_start_path) if body_start_path else None,
        "body_animation_start_mode": body_animation_start_mode,
        "body_animation_start_radial_scale": args.body_start_radial_scale,
        "body_animation_start_sha256": (
            hashlib.sha256(body_start_path.read_bytes()).hexdigest()
            if body_start_path else None
        ),
        "body_animation_frames": args.body_animation_frames,
        "body_animation_delay_frames": args.body_animation_delay_frames,
        "body_animation_completed": (
            body_animation_start is None
            or len(frame_seconds)
            >= args.body_animation_delay_frames + args.body_animation_frames
        ),
        "solver_config_path": str(config_path),
        "solver_config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "staged_initial_mesh_path": (
            str(
                initial_mesh_path
                or initial_welded_mesh_path
                or initial_welded_rigid_layout_path
                or initial_explicit_remesh_path
                or initial_explicit_mesh_path
            )
            if initial_mesh_path
            or initial_welded_mesh_path
            or initial_welded_rigid_layout_path
            or initial_explicit_remesh_path
            or initial_explicit_mesh_path
            else None
        ),
        "staged_initial_mesh_sha256": (
            hashlib.sha256(
                (
                    initial_mesh_path
                    or initial_welded_mesh_path
                    or initial_welded_rigid_layout_path
                    or initial_explicit_remesh_path
                    or initial_explicit_mesh_path
                ).read_bytes()
            ).hexdigest()
            if initial_mesh_path
            or initial_welded_mesh_path
            or initial_welded_rigid_layout_path
            or initial_explicit_remesh_path
            or initial_explicit_mesh_path
            else None
        ),
        "staged_initial_mesh_topology": (
            "explicit"
            if initial_mesh_path
            else "welded-bootstrap"
            if initial_welded_mesh_path
            else "welded-bootstrap-rigid-panel-fit"
            if initial_welded_rigid_layout_path
            else (
                "explicit-remesh-"
                f"{args.initial_explicit_remesh_resolution:g}-to-"
                f"{sim_values['resolution_scale']:g}"
            )
            if initial_explicit_remesh_path
            else "explicit-to-" + args.topology_mode
            if initial_explicit_mesh_path
            else None
        ),
        "staged_seam_transfer": staged_seam_transfer,
        "staged_source_pattern_path": (
            str(initial_explicit_source_pattern_path)
            if initial_explicit_source_pattern_path else None
        ),
        "staged_source_pattern_sha256": (
            hashlib.sha256(initial_explicit_source_pattern_path.read_bytes()).hexdigest()
            if initial_explicit_source_pattern_path else None
        ),
        "shell_assembly": shell_assembly,
        "shell_bootstrap_rest": shell_bootstrap_rest,
        "rest_lengths_path": str(effective_rest_lengths_path.resolve()),
        "rest_lengths_sha256": hashlib.sha256(
            effective_rest_lengths_path.read_bytes()
        ).hexdigest(),
        "strain_reference_mesh_path": (
            str(strain_reference_path) if strain_reference_path else None
        ),
        "strain_reference_mesh_sha256": (
            hashlib.sha256(strain_reference_path.read_bytes()).hexdigest()
            if strain_reference_path else None
        ),
        "fabric": {
            "thickness_cm": float(material_values["fabric_thickness"]),
            "density": float(material_values["fabric_density"]),
            "friction": float(material_values["fabric_friction"]),
            "edge_bending_stiffness": float(material_values["garment_edge_ke"]),
            "triangle_area_stiffness": float(material_values["garment_tri_ka"]),
            "triangle_shear_stiffness": float(material_values["garment_tri_ke"]),
            "structural_spring_stiffness": float(material_values["spring_ke"]),
            "structural_spring_damping": float(material_values["spring_kd"]),
            "seam_stiffness": float(material_values.get("sewing_ke", 50000000.0)),
            "seam_damping": float(material_values.get("sewing_kd", 100.0)),
        },
        "cloth_vertices": cloth_vertex_count,
        "body_vertices": body_vertex_count,
        "body_faces": body_face_count,
        "construction_seconds": construction_seconds,
        "requested_frames": frame_count,
        "completed_frames": len(frame_seconds),
        "simulation_substeps": int(config.sim_substeps),
        "solver_iterations": int(config.solver_iterations),
        "sewing_ramp_delay_frames": int(config.sewing_ramp_delay_frames),
        "sewing_ramp_frames": int(config.sewing_ramp_frames),
        "sewing_settle_frames": int(config.sewing_settle_frames),
        "sewing_schedule_progress": float(garment.sewing_progress),
        "sewing_schedule_completed": garment.sewing_progress >= 1.0,
        "seam_projection_enabled": bool(config.enable_seam_projection),
        "seam_projection_radius_cm": float(config.seam_projection_radius_cm),
        "seam_component_count": int(garment.seam_component_count),
        "mean_frame_seconds": float(np.mean(frame_seconds)) if frame_seconds else 0.0,
        "maximum_displacement_cm": float(displacement.max(initial=0.0)),
        "mean_displacement_cm": float(displacement.mean()) if displacement.size else 0.0,
        "body_collisions": body_collisions,
        "self_collisions": self_collisions,
        "initial_body_collisions": initial_body_intersections,
        "initial_self_collisions": initial_self_intersections,
        "initial_body_intersection_locations": initial_body_intersection_locations,
        "self_intersection_locations": self_intersection_locations,
        "max_body_collisions": max_body_collisions,
        "max_self_collisions": max_self_collisions,
        "seam_link_count": seam_link_count,
        "seam_bending_constraint_count": seam_bending_constraint_count,
        "maximum_seam_separation_cm": maximum_seam_separation_cm,
        "mean_seam_separation_cm": mean_seam_separation_cm,
        "ninety_fifth_percentile_seam_separation_cm": (
            ninety_fifth_percentile_seam_separation_cm
        ),
        "max_seam_separation_cm": args.max_seam_separation_cm,
        "maximum_seam_separation_edge_vertices": (
            maximum_seam_separation_edge_vertices
        ),
        "maximum_seam_separation_panel_labels": (
            maximum_seam_separation_panel_labels
        ),
        "evaluated_edge_count": evaluated_edge_count,
        "strain_reference_mode": "material-space-rest-lengths-with-geometry-fallback",
        "material_rest_length_edge_count": material_rest_length_edge_count,
        "reference_geometry_edge_count": reference_geometry_edge_count,
        "excluded_edge_count": 0,
        "excluded_seam_edge_count": 0,
        "maximum_strain_edge_vertices": maximum_strain_edge_vertices,
        "maximum_strain_panel_labels": maximum_strain_panel_labels,
        "maximum_strain_initial_midpoint_cm": maximum_strain_initial_midpoint_cm,
        "maximum_strain_final_midpoint_cm": maximum_strain_final_midpoint_cm,
        "maximum_edge_strain_ratio": maximum_edge_strain_ratio,
        "ninety_fifth_percentile_edge_strain_ratio": (
            ninety_fifth_percentile_edge_strain_ratio
        ),
        "ninety_ninth_point_ninth_percentile_edge_strain_ratio": (
            ninety_ninth_point_ninth_percentile_edge_strain_ratio
        ),
        "max_edge_strain_ratio": max_edge_strain_ratio,
        "max_ninety_fifth_percentile_edge_strain_ratio": (
            max_ninety_fifth_percentile_edge_strain_ratio
        ),
        "max_ninety_ninth_point_ninth_percentile_edge_strain_ratio": (
            max_ninety_ninth_point_ninth_percentile_edge_strain_ratio
        ),
        "body_collision_rate": body_collision_rate,
        "self_collision_rate": self_collision_rate,
        "output_mesh": str(output_mesh_path),
        "output_mesh_path": str(output_mesh_path),
        "output_mesh_sha256": _sha256_file(output_mesh_path),
        "output_topology_sha256": output_identity["topology_sha256"],
        "front_render": str(paths.render_path("front").resolve()) if args.render and render_error is None else None,
        "back_render": str(paths.render_path("back").resolve()) if args.render and render_error is None else None,
        "render_error": render_error,
        "requested_warp_device": args.device,
        "available_warp_devices": [str(device) for device in available_devices],
        "warp_device": str(selected_device),
    }
    report_path = paths.out_el / "patterna_warp_prefit_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
