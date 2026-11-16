#!/usr/bin/env python3
"""Create a deterministic exact-topology garment arrangement candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any

import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import coo_matrix, diags, lil_matrix
from scipy.sparse.linalg import factorized
from scipy.spatial.transform import Rotation

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.revision_bundle import canonical_json, sha256_file, verify_bundle


ARRANGEMENT_SCHEMA = "patterna.exact-triangle-arrangement/1.0"
MANIFEST_SCHEMA = "patterna.exact-triangle-arrangement-manifest/1.0"
SUPPORTED_ARCHETYPE = "adaptive-female-crew-neck-14-panel-v1"
FIXED_PANEL_IDS = {"front-torso-panel", "back-torso-panel"}


def role_path(bundle_directory: Path, manifest: dict[str, Any], role: str) -> Path:
    matches = [entry for entry in manifest["inputs"] if entry.get("role") == role]
    if len(matches) != 1:
        raise ValueError(f"Source bundle must contain exactly one {role} input.")
    return bundle_directory / matches[0]["bundlePath"]


def source_placement_points(
    vertices: list[dict[str, Any]],
    translation: list[float],
    rotation_degrees: list[float],
) -> np.ndarray:
    if len(translation) != 3 or len(rotation_degrees) != 3:
        raise ValueError("Panel placement requires three translation and rotation values.")
    x_angle, y_angle, z_angle = np.radians(rotation_degrees)
    cx, sx = math.cos(x_angle), math.sin(x_angle)
    cy, sy = math.cos(y_angle), math.sin(y_angle)
    cz, sz = math.cos(z_angle), math.sin(z_angle)
    result = np.empty((len(vertices), 3), dtype=np.float64)
    for index, vertex in enumerate(vertices):
        x = float(vertex["x"])
        y = float(vertex["y"])
        after_x_x = x
        after_x_y = y * cx
        after_x_z = y * sx
        after_y_x = after_x_x * cy + after_x_z * sy
        after_y_y = after_x_y
        after_y_z = -after_x_x * sy + after_x_z * cy
        world_x = after_y_x * cz - after_y_y * sz + float(translation[0])
        world_vertical = after_y_x * sz + after_y_y * cz + float(translation[1])
        world_depth = after_y_z + float(translation[2])
        # The source bundle collider and downstream cloth workers use Y-up.
        # The WinUI compiler's legacy arrangement document uses Z-up, so its
        # output ordering must not leak into this solver-neutral artifact.
        result[index] = (world_x, world_vertical, world_depth)
    return result


def build_constraints(
    panels: list[dict[str, Any]],
    seams: list[dict[str, Any]],
    segmentation_path: Path,
    panel_index_map_path: Path,
) -> list[dict[str, Any]]:
    total_vertices = sum(len(panel["vertices"]) for panel in panels)
    rows = segmentation_path.read_text(encoding="utf-8").splitlines()
    if len(rows) != total_vertices:
        raise ValueError(
            f"Authoritative seams contain {len(rows)} rows for {total_vertices} vertices."
        )
    panel_index_map = json.loads(panel_index_map_path.read_text(encoding="utf-8"))
    if panel_index_map.get("schema_version") != "patterna.style3d-panel-index-map/1.0":
        raise ValueError("Unsupported authoritative panel index map schema.")
    panel_by_source = {str(panel["sourcePanelName"]): panel for panel in panels}
    global_owners: list[tuple[str, int] | None] = [None] * total_vertices
    for mapped_panel in panel_index_map.get("panels", []):
        source_name = str(mapped_panel.get("source_panel_name", ""))
        panel = panel_by_source.get(source_name)
        indices = mapped_panel.get("vertex_indices")
        if panel is None or not isinstance(indices, list):
            raise ValueError(f"Panel index map contains an unknown panel: {source_name}")
        if len(indices) != len(panel["vertices"]):
            raise ValueError(f"Panel index map count changed for {source_name}.")
        for local_index, raw_global_index in enumerate(indices):
            global_index = int(raw_global_index)
            if global_index < 0 or global_index >= total_vertices:
                raise ValueError(f"Panel index map has an invalid global index: {global_index}")
            if global_owners[global_index] is not None:
                raise ValueError(f"Panel index map repeats global index {global_index}.")
            global_owners[global_index] = (str(panel["panelId"]), local_index)
    if any(owner is None for owner in global_owners):
        raise ValueError("Panel index map does not own every exact source vertex.")
    members: dict[tuple[int, int], list[int]] = {}
    for global_index, row in enumerate(rows):
        for label in row.split(","):
            match = re.fullmatch(r"seam_link_([0-9]+)_([0-9]+)", label.strip())
            if match:
                key = (int(match.group(1)), int(match.group(2)))
                members.setdefault(key, []).append(global_index)
    if not members:
        raise ValueError("Authoritative seams contain no explicit seam links.")
    invalid = {key: value for key, value in members.items() if len(value) != 2}
    if invalid:
        raise ValueError(
            "Every authoritative seam link must own exactly two vertices: "
            + repr(list(sorted(invalid.items()))[:8])
        )
    seam_by_ordinal = {index: seam for index, seam in enumerate(seams)}
    panel_by_id = {str(panel["panelId"]): panel for panel in panels}
    counts: dict[int, int] = {}
    for seam_ordinal, sample_ordinal in members:
        counts[seam_ordinal] = max(counts.get(seam_ordinal, 0), sample_ordinal + 1)
    constraints: list[dict[str, Any]] = []
    for (seam_ordinal, sample_ordinal), global_indices in sorted(members.items()):
        seam = seam_by_ordinal.get(seam_ordinal)
        if seam is None:
            raise ValueError(f"Authoritative seam link references unknown stitch {seam_ordinal}.")
        first_owner = global_owners[global_indices[0]]
        second_owner = global_owners[global_indices[1]]
        assert first_owner is not None and second_owner is not None
        expected = {str(seam["panelA"]), str(seam["panelB"])}
        if {first_owner[0], second_owner[0]} != expected:
            raise ValueError(
                f"Authoritative seam stitch-{seam_ordinal} does not match panel ownership."
            )
        if seam["panelA"] == seam["panelB"]:
            panel = panel_by_id[str(seam["panelA"])]
            edge_a = set(panel["edgeVertexIndices"][seam["edgeA"]])
            edge_b = set(panel["edgeVertexIndices"][seam["edgeB"]])
            candidates = (first_owner[1], second_owner[1])
            if candidates[0] in edge_a and candidates[1] in edge_b:
                vertex_a, vertex_b = candidates
            elif candidates[1] in edge_a and candidates[0] in edge_b:
                vertex_a, vertex_b = candidates[1], candidates[0]
            else:
                raise ValueError(
                    f"Internal seam stitch-{seam_ordinal} has ambiguous edge ownership."
                )
        else:
            by_panel = {first_owner[0]: first_owner[1], second_owner[0]: second_owner[1]}
            vertex_a = by_panel[seam["panelA"]]
            vertex_b = by_panel[seam["panelB"]]
        count = counts[seam_ordinal]
        constraints.append(
            {
                "constraintId": f"stitch-{seam_ordinal}:{sample_ordinal}",
                "seamId": f"stitch-{seam_ordinal}",
                "seamOrdinal": seam_ordinal,
                "sampleOrdinal": sample_ordinal,
                "sourcePosition": sample_ordinal / max(count - 1, 1),
                "sideA": {
                    "kind": "vertex",
                    "panelId": seam["panelA"],
                    "vertexIndex": vertex_a,
                    "sourceEdgeId": seam["edgeA"],
                },
                "sideB": {
                    "kind": "vertex",
                    "panelId": seam["panelB"],
                    "vertexIndex": vertex_b,
                    "sourceEdgeId": seam["edgeB"],
                },
                "targetDistanceCm": 0.0,
            }
        )
    return constraints


def rigid_panel_fit(
    panel_ids: list[str],
    initial: list[np.ndarray],
    constraints: list[dict[str, Any]],
) -> tuple[list[np.ndarray], dict[str, Any]]:
    panel_index = {panel_id: index for index, panel_id in enumerate(panel_ids)}
    moving = [panel_id for panel_id in panel_ids if panel_id not in FIXED_PANEL_IDS]
    moving_index = {panel_id: index for index, panel_id in enumerate(moving)}
    centers = [np.mean(points, axis=0) for points in initial]

    constraints_by_seam: dict[str, list[dict[str, Any]]] = {}
    for constraint in constraints:
        constraints_by_seam.setdefault(constraint["seamId"], []).append(constraint)
    fit_constraints: list[dict[str, Any]] = []
    for seam_constraints in constraints_by_seam.values():
        sample_count = min(10, len(seam_constraints))
        selected = {
            round(index * (len(seam_constraints) - 1) / (sample_count - 1))
            for index in range(sample_count)
        }
        fit_constraints.extend(seam_constraints[index] for index in sorted(selected))

    sample_rows: list[tuple[int, int, int, int]] = []
    for constraint in fit_constraints:
        side_a = constraint["sideA"]
        side_b = constraint["sideB"]
        sample_rows.append(
            (
                panel_index[side_a["panelId"]],
                int(side_a["vertexIndex"]),
                panel_index[side_b["panelId"]],
                int(side_b["vertexIndex"]),
            )
        )

    def transform_point(panel: int, vertex: int, values: np.ndarray) -> np.ndarray:
        panel_id = panel_ids[panel]
        point = initial[panel][vertex]
        variable = moving_index.get(panel_id)
        if variable is None:
            return point
        offset = variable * 6
        rotation = Rotation.from_rotvec(values[offset : offset + 3])
        translation = values[offset + 3 : offset + 6]
        return rotation.apply(point - centers[panel]) + centers[panel] + translation

    def residual(values: np.ndarray) -> np.ndarray:
        seam_residuals = np.concatenate(
            [
                transform_point(panel_a, vertex_a, values)
                - transform_point(panel_b, vertex_b, values)
                for panel_a, vertex_a, panel_b, vertex_b in sample_rows
            ]
        )
        regularization = values * 0.002
        return np.concatenate((seam_residuals, regularization))

    start = np.zeros(len(moving) * 6, dtype=np.float64)
    seam_coordinate_count = len(sample_rows) * 3
    sparsity = lil_matrix(
        (seam_coordinate_count + len(start), len(start)),
        dtype=np.int8,
    )
    for sample_index, (panel_a, _, panel_b, _) in enumerate(sample_rows):
        for panel in (panel_a, panel_b):
            variable = moving_index.get(panel_ids[panel])
            if variable is not None:
                sparsity[sample_index * 3 : sample_index * 3 + 3, variable * 6 : variable * 6 + 6] = 1
    for index in range(len(start)):
        sparsity[seam_coordinate_count + index, index] = 1
    solution = least_squares(
        residual,
        start,
        method="trf",
        jac_sparsity=sparsity.tocsr(),
        tr_solver="lsmr",
        max_nfev=80,
        ftol=1.0e-11,
        xtol=1.0e-11,
        gtol=1.0e-11,
    )
    arranged: list[np.ndarray] = []
    for index, panel_id in enumerate(panel_ids):
        variable = moving_index.get(panel_id)
        if variable is None:
            arranged.append(initial[index].copy())
            continue
        offset = variable * 6
        rotation = Rotation.from_rotvec(solution.x[offset : offset + 3])
        translation = solution.x[offset + 3 : offset + 6]
        arranged.append(
            rotation.apply(initial[index] - centers[index])
            + centers[index]
            + translation
        )
    return arranged, {
        "method": "bounded-rigid-panel-least-squares-v1",
        "fixedPanelIds": sorted(FIXED_PANEL_IDS),
        "functionEvaluations": int(solution.nfev),
        "fittedConstraintCount": len(fit_constraints),
        "publishedConstraintCount": len(constraints),
        "terminationStatus": int(solution.status),
        "terminationMessage": str(solution.message),
        "cost": float(solution.cost),
        "optimality": float(solution.optimality),
    }


def developable_seam_fit(
    panels: list[dict[str, Any]],
    rigid: list[np.ndarray],
    constraints: list[dict[str, Any]],
    *,
    iterations: int = 12,
    seam_weight: float = 60.0,
    anchor_weight: float = 0.02,
) -> tuple[list[np.ndarray], dict[str, Any]]:
    offsets: dict[str, int] = {}
    offset = 0
    for panel, points in zip(panels, rigid):
        offsets[str(panel["panelId"])] = offset
        offset += len(points)
    reference = np.concatenate(rigid, axis=0)
    edge_set: set[tuple[int, int]] = set()
    for panel in panels:
        panel_offset = offsets[str(panel["panelId"])]
        for triangle in panel["triangles"]:
            indices = [panel_offset + int(value) for value in triangle]
            for first, second in ((0, 1), (1, 2), (2, 0)):
                edge_set.add(tuple(sorted((indices[first], indices[second]))))
    edges = np.asarray(sorted(edge_set), dtype=np.int32)
    first_indices = edges[:, 0]
    second_indices = edges[:, 1]
    reference_edges = reference[first_indices] - reference[second_indices]
    if np.any(np.linalg.norm(reference_edges, axis=1) <= 1.0e-8):
        raise ValueError("Developable fitting source contains a degenerate material edge.")

    target_sums = np.zeros_like(reference)
    target_counts = np.zeros(len(reference), dtype=np.int32)
    initial_gaps: list[float] = []
    for constraint in constraints:
        side_a = constraint["sideA"]
        side_b = constraint["sideB"]
        index_a = offsets[str(side_a["panelId"])] + int(side_a["vertexIndex"])
        index_b = offsets[str(side_b["panelId"])] + int(side_b["vertexIndex"])
        target = 0.5 * (reference[index_a] + reference[index_b])
        target_sums[index_a] += target
        target_sums[index_b] += target
        target_counts[index_a] += 1
        target_counts[index_b] += 1
        initial_gaps.append(float(np.linalg.norm(reference[index_a] - reference[index_b])))
    constrained = target_counts > 0
    targets = np.zeros_like(reference)
    targets[constrained] = target_sums[constrained] / target_counts[constrained, None]

    rows = np.concatenate((first_indices, second_indices, first_indices, second_indices))
    columns = np.concatenate((first_indices, second_indices, second_indices, first_indices))
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
        shape=(len(reference), len(reference)),
    ).tocsc()
    weights = target_counts.astype(np.float64) * seam_weight + anchor_weight
    solve = factorized(laplacian + diags(weights, format="csc"))
    current = reference.copy()
    for _ in range(iterations):
        current_edges = current[first_indices] - current[second_indices]
        covariance = np.zeros((len(reference), 3, 3), dtype=np.float64)
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
        right_hand = np.zeros_like(reference)
        np.add.at(right_hand, first_indices, desired_edges)
        np.add.at(right_hand, second_indices, -desired_edges)
        right_hand += anchor_weight * reference
        right_hand[constrained] += (
            seam_weight * target_counts[constrained, None] * targets[constrained]
        )
        current = np.column_stack(
            [solve(right_hand[:, coordinate]) for coordinate in range(3)]
        )
    if not np.isfinite(current).all():
        raise ValueError("Developable fitting produced non-finite positions.")
    current_lengths = np.linalg.norm(
        current[first_indices] - current[second_indices], axis=1
    )
    reference_lengths = np.linalg.norm(reference_edges, axis=1)
    strains = np.abs(current_lengths / reference_lengths - 1.0)
    output = []
    for panel in panels:
        panel_offset = offsets[str(panel["panelId"])]
        count = len(panel["vertices"])
        output.append(current[panel_offset : panel_offset + count].copy())
    return output, {
        "method": "global-exact-topology-arap-seam-fit-v1",
        "iterationCount": iterations,
        "seamConstraintWeight": seam_weight,
        "anchorWeight": anchor_weight,
        "initialMaximumSeamSeparationCm": max(initial_gaps),
        "maximumEdgeStrainRatio": float(np.max(strains)),
        "p95EdgeStrainRatio": float(np.percentile(strains, 95.0)),
    }


def create_candidate(bundle_directory: Path, output_directory: Path) -> dict[str, Any]:
    bundle_directory = bundle_directory.resolve(strict=True)
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(
            f"Arrangement artifacts are immutable; output already exists: {output_directory}"
        )
    source_manifest = verify_bundle(bundle_directory)
    if source_manifest["schemaVersion"] != "patterna.revision-bundle/1.2":
        raise ValueError("Exact arrangement requires a source-only revision bundle 1.2.")
    if source_manifest["contract"]["garmentArchetype"] != SUPPORTED_ARCHETYPE:
        raise ValueError(
            "Unsupported garment archetype: "
            + source_manifest["contract"]["garmentArchetype"]
        )

    mesh_path = role_path(bundle_directory, source_manifest, "panelMesh")
    panels_path = role_path(bundle_directory, source_manifest, "panels")
    seams_path = role_path(bundle_directory, source_manifest, "seams")
    panel_index_map_path = role_path(bundle_directory, source_manifest, "panelIndexMap")
    mesh = json.loads(mesh_path.read_text(encoding="utf-8"))
    source = json.loads(panels_path.read_text(encoding="utf-8"))
    if mesh.get("schemaVersion") != "patterna.garmentcode-pattern-mesh/1.0":
        raise ValueError("Unsupported exact panel-mesh schema.")
    raw_placements = source.get("pattern", {}).get("panels")
    if not isinstance(raw_placements, dict):
        raise ValueError("Authoritative panels contain no source placement map.")
    panels = mesh.get("panels")
    seams = mesh.get("seams")
    if not isinstance(panels, list) or len(panels) != 14 or not isinstance(seams, list):
        raise ValueError("The supported archetype requires exactly 14 panels and authored seams.")

    panel_ids = [str(panel["panelId"]) for panel in panels]
    if len(set(panel_ids)) != len(panel_ids) or not FIXED_PANEL_IDS.issubset(panel_ids):
        raise ValueError("Panel IDs must be unique and contain both fixed torso panels.")
    initial: list[np.ndarray] = []
    for panel in panels:
        placement = raw_placements.get(panel["sourcePanelName"])
        if not isinstance(placement, dict):
            raise ValueError(
                f"No authored placement exists for {panel['sourcePanelName']}."
            )
        initial.append(
            source_placement_points(
                panel["vertices"],
                placement.get("translation", []),
                placement.get("rotation", []),
            )
        )
    constraints = build_constraints(panels, seams, seams_path, panel_index_map_path)
    rigid, rigid_optimization = rigid_panel_fit(panel_ids, initial, constraints)
    arranged, developable_optimization = developable_seam_fit(
        panels,
        rigid,
        constraints,
    )
    positions = np.concatenate(arranged, axis=0)
    offsets: list[int] = []
    offset = 0
    panel_records: list[dict[str, Any]] = []
    for panel, points in zip(panels, arranged):
        offsets.append(offset)
        material = [[float(vertex["x"]), float(vertex["y"])] for vertex in panel["vertices"]]
        record = {
            "panelId": panel["panelId"],
            "pieceId": panel["pieceId"],
            "sourcePanelName": panel["sourcePanelName"],
            "vertexOffset": offset,
            "vertexCount": len(points),
            "triangleCount": len(panel["triangles"]),
            "triangles": panel["triangles"],
            "edgeVertexIndices": panel["edgeVertexIndices"],
            "materialPositionsCm": material,
            "sourceMap": {
                "vertexIndices": list(range(len(points))),
                "triangleIndices": list(range(len(panel["triangles"]))),
            },
        }
        panel_records.append(record)
        offset += len(points)

    worker_path = Path(__file__).resolve()
    document = {
        "schemaVersion": ARRANGEMENT_SCHEMA,
        "sourceBundleId": source_manifest["bundleId"],
        "sourcePanelMeshSha256": sha256_file(mesh_path),
        "sourcePanelsSha256": sha256_file(panels_path),
        "sourceSeamsSha256": sha256_file(seams_path),
        "sourcePanelIndexMapSha256": sha256_file(panel_index_map_path),
        "workerSha256": sha256_file(worker_path),
        "garmentArchetype": SUPPORTED_ARCHETYPE,
        "units": "cm",
        "claims": {"accepted": False},
        "method": {
            "rigid": rigid_optimization,
            "developable": developable_optimization,
        },
        "panels": panel_records,
        "constraints": constraints,
    }

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_directory.name}-", dir=output_directory.parent)
    )
    try:
        positions_path = temporary / "positions.npy"
        np.save(positions_path, positions, allow_pickle=False)
        document_path = temporary / "arrangement.json"
        document_path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        identity = {
            "schemaVersion": MANIFEST_SCHEMA,
            "sourceBundleId": source_manifest["bundleId"],
            "claims": {"accepted": False},
            "files": [
                {
                    "path": "arrangement.json",
                    "byteLength": document_path.stat().st_size,
                    "sha256": sha256_file(document_path),
                },
                {
                    "path": "positions.npy",
                    "byteLength": positions_path.stat().st_size,
                    "sha256": sha256_file(positions_path),
                },
            ],
        }
        arrangement_id = hashlib.sha256(canonical_json(identity)).hexdigest()
        manifest = {**identity, "arrangementId": arrangement_id}
        (temporary / "arrangement-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output_directory)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    manifest = create_candidate(arguments.bundle, arguments.output_directory)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
