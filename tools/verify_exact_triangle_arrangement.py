#!/usr/bin/env python3
"""Independently verify an exact-topology Patterna arrangement artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import trimesh
import warp as wp

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.exact_triangle_arrangement import ARRANGEMENT_SCHEMA, MANIFEST_SCHEMA, role_path
from tools.prefit_newton_style3d import (
    find_intersection_edges,
    find_self_intersection_edge_face_pairs,
)
from tools.revision_bundle import canonical_json, sha256_file, verify_bundle
from tools.triangle_surface_clearance import prove_surface_clearance


VERIFICATION_SCHEMA = "patterna.arrangement-verification/1.0"


def read_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            vertices.append([float(value) for value in line.split()[1:4]])
        elif line.startswith("f "):
            indices = [int(value.split("/")[0]) - 1 for value in line.split()[1:]]
            if len(indices) != 3:
                raise ValueError("Arrangement verification requires triangulated OBJ input.")
            faces.append(indices)
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int32)
    if points.ndim != 2 or points.shape[1] != 3 or triangles.ndim != 2:
        raise ValueError(f"OBJ contains no valid triangle surface: {path}")
    if float(np.ptp(points[:, 1])) < 10.0:
        points *= 100.0
    return points, triangles


def verify_artifact_manifest(directory: Path) -> dict[str, Any]:
    manifest_path = directory / "arrangement-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != MANIFEST_SCHEMA:
        raise ValueError("Unsupported arrangement manifest schema.")
    if manifest.get("claims") != {"accepted": False}:
        raise ValueError("An arrangement producer cannot claim acceptance.")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Arrangement manifest contains no files.")
    declared = {"arrangement-manifest.json"}
    for entry in files:
        relative = entry.get("path")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ValueError("Arrangement files require relative paths.")
        path = (directory / relative).resolve(strict=True)
        path.relative_to(directory)
        if path.stat().st_size != entry.get("byteLength"):
            raise ValueError(f"Arrangement file size changed: {relative}")
        if sha256_file(path) != entry.get("sha256"):
            raise ValueError(f"Arrangement file hash changed: {relative}")
        declared.add(path.relative_to(directory).as_posix())
    actual = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
    }
    if actual != declared:
        raise ValueError("Arrangement artifact file set changed.")
    identity = {
        "schemaVersion": manifest["schemaVersion"],
        "sourceBundleId": manifest["sourceBundleId"],
        "claims": manifest["claims"],
        "files": files,
    }
    expected_id = hashlib.sha256(canonical_json(identity)).hexdigest()
    if manifest.get("arrangementId") != expected_id:
        raise ValueError("Arrangement identity does not match its manifest.")
    return manifest


def percentile(values: np.ndarray, amount: float) -> float:
    return float(np.percentile(values, amount)) if len(values) else 0.0


SLEEVE_WEAR_PANELS = {
    "left": ("left-sleeve-b-panel", "left-sleeve-f-panel"),
    "right": ("right-sleeve-b-panel", "right-sleeve-f-panel"),
}
SLEEVE_WEAR_REACH_FRACTION = 0.30
SLEEVE_WEAR_COVERAGE_DEGREES = 300.0
ARM_FIT_BAND_CM = (30.0, 50.0)
SHOULDER_STATION_CM = 20.5


def fit_collider_arm_axis(
    body_positions_cm: np.ndarray, sign: float
) -> tuple[np.ndarray, np.ndarray] | None:
    """Least-squares arm axis through collider section centroids.

    The band starts outboard of the torso so the centroids describe the arm
    alone. Returns an axis point at the shoulder station and a unit direction.
    """
    centroids = []
    for station in np.arange(ARM_FIT_BAND_CM[0], ARM_FIT_BAND_CM[1] + 0.5, 2.0):
        band = np.abs(sign * body_positions_cm[:, 0] - station) <= 1.0
        selected = body_positions_cm[band]
        if len(selected) >= 8:
            centroids.append(selected.mean(axis=0))
    if len(centroids) < 5:
        return None
    points = np.asarray(centroids)
    xs = points[:, 0]
    slope_y, intercept_y = np.polyfit(xs, points[:, 1], 1)
    slope_z, intercept_z = np.polyfit(xs, points[:, 2], 1)
    base_x = sign * SHOULDER_STATION_CM
    base = np.array(
        [base_x, slope_y * base_x + intercept_y, slope_z * base_x + intercept_z]
    )
    direction = np.array([sign, slope_y * sign, slope_z * sign])
    direction /= np.linalg.norm(direction)
    return base, direction


def sleeve_wear_issues(
    positions: np.ndarray,
    vertex_owners: list[str],
    artifact_panels: list[dict],
    body_positions_cm: np.ndarray,
) -> list[str]:
    """A closed sleeve wadded at the shoulder is not a worn sleeve.

    Each side must reach along the collider's own fitted arm axis and must
    encircle that axis. Without this gate an arrangement with every seam
    closed and no intersections would pass while the sleeves sit in a clump
    beside the deltoid.
    """
    owners = np.asarray(vertex_owners)
    issues: list[str] = []
    material_length = {}
    for panel in artifact_panels:
        xs = [point[0] for point in panel["materialPositionsCm"]]
        material_length[str(panel["panelId"])] = max(xs) - min(xs)
    for side, panel_ids in SLEEVE_WEAR_PANELS.items():
        sign = 1.0 if side == "left" else -1.0
        axis = fit_collider_arm_axis(body_positions_cm, sign)
        if axis is None:
            issues.append(f"the collider has no {side} arm band to test against")
            continue
        base, direction = axis
        side_masks = [owners == panel_id for panel_id in panel_ids]
        combined = side_masks[0] | side_masks[1]
        along = (positions - base[None, :]) @ direction
        for panel_id, mask in zip(panel_ids, side_masks):
            if not mask.any():
                issues.append(f"{panel_id} owns no vertices")
                continue
            # Zero gravity leaves a worn sleeve bunched loosely, so the reach
            # expectation is deliberately modest; the encirclement test below
            # separates a worn tube from a wad beside the arm.
            reach = float(np.max(along[mask]))
            required = SLEEVE_WEAR_REACH_FRACTION * material_length[panel_id]
            if reach < required:
                issues.append(
                    f"{panel_id} reaches {reach:.1f} cm along the arm axis;"
                    f" needs {required:.1f} cm"
                )
        station = 5.0
        slab = combined & (np.abs(along - station) <= 3.0)
        if slab.sum() < 8:
            issues.append(f"the {side} sleeve has no material at the arm station")
            continue
        helper = np.array([0.0, 0.0, 1.0])
        first = np.cross(direction, helper)
        first /= np.linalg.norm(first)
        second = np.cross(direction, first)
        local = positions[slab] - (base + station * direction)[None, :]
        angles = np.degrees(np.arctan2(local @ second, local @ first))
        angles = np.sort(np.mod(angles, 360.0))
        gaps = np.diff(np.concatenate([angles, angles[:1] + 360.0]))
        coverage = 360.0 - float(gaps.max())
        if coverage < SLEEVE_WEAR_COVERAGE_DEGREES:
            issues.append(
                f"the {side} sleeve covers {coverage:.0f} degrees around the"
                f" arm; needs {SLEEVE_WEAR_COVERAGE_DEGREES:.0f}"
            )
    return issues


def minimum_vertex_clearance_cm(
    body_mesh: trimesh.Trimesh,
    positions_cm: np.ndarray,
    chunk_size: int = 1024,
) -> float:
    maximum_signed_distance = -float("inf")
    for start in range(0, len(positions_cm), chunk_size):
        distances = trimesh.proximity.signed_distance(
            body_mesh,
            positions_cm[start : start + chunk_size],
        )
        maximum_signed_distance = max(
            maximum_signed_distance,
            float(np.max(distances)),
        )
    return -maximum_signed_distance


def gate(name: str, passed: bool, actual: Any, required: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual, "required": required}


def verify_arrangement(
    bundle_directory: Path,
    arrangement_directory: Path,
    output_path: Path,
    device: str,
) -> dict[str, Any]:
    bundle_directory = bundle_directory.resolve(strict=True)
    arrangement_directory = arrangement_directory.resolve(strict=True)
    source_manifest = verify_bundle(bundle_directory)
    artifact_manifest = verify_artifact_manifest(arrangement_directory)
    if artifact_manifest["sourceBundleId"] != source_manifest["bundleId"]:
        raise ValueError("Arrangement artifact names a different source bundle.")

    document_path = arrangement_directory / "arrangement.json"
    positions_path = arrangement_directory / "positions.npy"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    if document.get("schemaVersion") != ARRANGEMENT_SCHEMA:
        raise ValueError("Unsupported arrangement document schema.")
    if document.get("sourceBundleId") != source_manifest["bundleId"]:
        raise ValueError("Arrangement document names a different source bundle.")
    positions = np.load(positions_path, allow_pickle=False)
    if positions.ndim != 2 or positions.shape[1] != 3 or not np.isfinite(positions).all():
        raise ValueError("Arrangement positions must be a finite N by 3 array.")

    mesh_path = role_path(bundle_directory, source_manifest, "panelMesh")
    source_mesh = json.loads(mesh_path.read_text(encoding="utf-8"))
    source_panels = source_mesh["panels"]
    artifact_panels = document.get("panels")
    if not isinstance(artifact_panels, list) or len(artifact_panels) != len(source_panels):
        raise ValueError("Arrangement panel count does not match the source.")

    faces: list[list[int]] = []
    material_positions: list[list[float]] = []
    identity_issues: list[str] = []
    panel_orientation_issues: list[str] = []
    vertex_owners: list[str] = []
    face_owners: list[str] = []
    edge_set: set[tuple[int, int]] = set()
    for source_panel, artifact_panel in zip(source_panels, artifact_panels):
        offset = int(artifact_panel["vertexOffset"])
        count = int(artifact_panel["vertexCount"])
        if artifact_panel.get("panelId") != source_panel.get("panelId"):
            identity_issues.append(f"panel order or ID changed at offset {offset}")
        if count != len(source_panel["vertices"]):
            identity_issues.append(f"vertex count changed for {source_panel['panelId']}")
        if artifact_panel.get("triangles") != source_panel.get("triangles"):
            identity_issues.append(f"triangle topology changed for {source_panel['panelId']}")
        expected_material = [
            [float(vertex["x"]), float(vertex["y"])]
            for vertex in source_panel["vertices"]
        ]
        if artifact_panel.get("materialPositionsCm") != expected_material:
            identity_issues.append(f"material coordinates changed for {source_panel['panelId']}")
        source_map = artifact_panel.get("sourceMap", {})
        if source_map.get("vertexIndices") != list(range(count)):
            identity_issues.append(f"vertex source map changed for {source_panel['panelId']}")
        if source_map.get("triangleIndices") != list(range(len(source_panel["triangles"]))):
            identity_issues.append(f"triangle source map changed for {source_panel['panelId']}")
        material_positions.extend(expected_material)
        panel_faces = np.asarray(source_panel["triangles"], dtype=np.int32) + offset
        faces.extend(panel_faces.tolist())
        vertex_owners.extend([str(source_panel["panelId"])] * count)
        face_owners.extend([str(source_panel["panelId"])] * len(panel_faces))
        normals = np.cross(
            positions[panel_faces[:, 1]] - positions[panel_faces[:, 0]],
            positions[panel_faces[:, 2]] - positions[panel_faces[:, 0]],
        )
        lengths = np.linalg.norm(normals, axis=1)
        valid = lengths > 1.0e-12
        if np.any(valid):
            # Orientation means winding consistency: every interior edge must
            # be traversed in opposite directions by its two triangles. The
            # earlier mean-normal test silently assumed a near-flat panel and
            # failed legitimately wrapped arrangements, so it tested staging
            # flatness rather than the contract's "local inversions".
            directed_edges: dict[tuple[int, int], int] = {}
            for triangle in panel_faces:
                for first, second in ((0, 1), (1, 2), (2, 0)):
                    key = (int(triangle[first]), int(triangle[second]))
                    directed_edges[key] = directed_edges.get(key, 0) + 1
            winding_issues = 0
            for (a, b), occurrences in directed_edges.items():
                if occurrences > 1:
                    winding_issues += occurrences - 1
                reverse = directed_edges.get((b, a), 0)
                if reverse > 1:
                    winding_issues += reverse - 1
            if winding_issues:
                panel_orientation_issues.append(
                    f"{source_panel['panelId']} has {winding_issues} winding violations"
                )
        for triangle in panel_faces:
            for first, second in ((0, 1), (1, 2), (2, 0)):
                edge_set.add(tuple(sorted((int(triangle[first]), int(triangle[second])))))

    faces_array = np.asarray(faces, dtype=np.int32)
    material_array = np.asarray(material_positions, dtype=np.float64)
    if len(positions) != len(material_array):
        identity_issues.append("global position count changed")
    triangle_cross = np.cross(
        positions[faces_array[:, 1]] - positions[faces_array[:, 0]],
        positions[faces_array[:, 2]] - positions[faces_array[:, 0]],
    )
    triangle_areas = np.linalg.norm(triangle_cross, axis=1) * 0.5
    degenerate_count = int(np.count_nonzero(triangle_areas < 0.001))

    edges = np.asarray(sorted(edge_set), dtype=np.int32)
    current_lengths = np.linalg.norm(
        positions[edges[:, 0]] - positions[edges[:, 1]], axis=1
    )
    material_lengths = np.linalg.norm(
        material_array[edges[:, 0]] - material_array[edges[:, 1]], axis=1
    )
    strain = np.abs(current_lengths / material_lengths - 1.0)

    seam_separations: list[float] = []
    for constraint in document.get("constraints", []):
        side_a = constraint["sideA"]
        side_b = constraint["sideB"]
        panel_a = next(panel for panel in artifact_panels if panel["panelId"] == side_a["panelId"])
        panel_b = next(panel for panel in artifact_panels if panel["panelId"] == side_b["panelId"])
        index_a = int(panel_a["vertexOffset"]) + int(side_a["vertexIndex"])
        index_b = int(panel_b["vertexOffset"]) + int(side_b["vertexIndex"])
        seam_separations.append(float(np.linalg.norm(positions[index_a] - positions[index_b])))
    seam_array = np.asarray(seam_separations, dtype=np.float64)

    body_path = role_path(bundle_directory, source_manifest, "collider")
    body_positions_cm, body_faces = read_obj(body_path)
    wp.init()
    body_edges, self_edges = find_intersection_edges(
        positions * 0.01,
        faces_array,
        body_positions_cm * 0.01,
        body_faces,
        device,
    )
    diagnostic_self_edges, diagnostic_self_faces = find_self_intersection_edge_face_pairs(
        positions * 0.01,
        faces_array,
        device,
    )
    intersection_pairs: dict[str, int] = {}
    for edge, face_index in zip(diagnostic_self_edges, diagnostic_self_faces):
        edge_panels = sorted({vertex_owners[int(index)] for index in edge})
        edge_owner = "+".join(edge_panels)
        face_owner = face_owners[int(face_index)]
        key = " <-> ".join(sorted((edge_owner, face_owner)))
        intersection_pairs[key] = intersection_pairs.get(key, 0) + 1
    maximum_strain_index = int(np.argmax(strain))
    maximum_strain_edge = edges[maximum_strain_index]
    body_mesh = trimesh.Trimesh(
        vertices=body_positions_cm,
        faces=body_faces,
        process=False,
        validate=False,
    )
    minimum_vertex_clearance = minimum_vertex_clearance_cm(body_mesh, positions)
    wear_issues = sleeve_wear_issues(
        positions, vertex_owners, artifact_panels, body_positions_cm
    )
    continuous_clearance = (
        {
            "passed": False,
            "requiredMinimum": 0.25,
            "measuredDistance": 0.0,
            "provenLowerBound": None,
            "closestTrianglePair": None,
            "testedCandidatePairs": 0,
            "method": "not evaluated because the surfaces intersect",
        }
        if len(body_edges) > 0
        else prove_surface_clearance(
            positions,
            faces_array,
            body_positions_cm,
            body_faces,
            0.25,
        )
    )

    gates = [
        gate("identity", not identity_issues, identity_issues, "exact source round trip"),
        gate("clothBodyIntersections", len(body_edges) == 0, len(body_edges), "0"),
        gate("clothSelfIntersections", len(self_edges) == 0, len(self_edges), "0"),
        gate("minimumVertexBodyClearanceCm", minimum_vertex_clearance >= 0.25, minimum_vertex_clearance, ">= 0.25"),
        gate("minimumTriangleAreaCm2", float(np.min(triangle_areas)) >= 0.001, float(np.min(triangle_areas)), ">= 0.001"),
        gate("degenerateTriangleCount", degenerate_count == 0, degenerate_count, "0"),
        gate("panelOrientation", not panel_orientation_issues, panel_orientation_issues, "consistent"),
        gate("sleevesWornOnArms", not wear_issues, wear_issues, "sleeves extend along both arms"),
        gate("maximumSeamSeparationCm", len(seam_array) > 0 and float(np.max(seam_array)) <= 2.0, float(np.max(seam_array)) if len(seam_array) else None, "<= 2.0"),
        gate("maximumEdgeStrainRatio", float(np.max(strain)) <= 2.0, float(np.max(strain)), "<= 2.0"),
        gate("p95EdgeStrainRatio", percentile(strain, 95.0) <= 0.25, percentile(strain, 95.0), "<= 0.25"),
        gate(
            "continuousBodyClearanceCm",
            continuous_clearance["passed"],
            continuous_clearance,
            ">= 0.25 exact threshold proof",
        ),
    ]
    accepted = all(item["passed"] for item in gates)
    report_without_id = {
        "schemaVersion": VERIFICATION_SCHEMA,
        "sourceBundleId": source_manifest["bundleId"],
        "arrangementId": artifact_manifest["arrangementId"],
        "verifierSha256": sha256_file(Path(__file__).resolve()),
        "accepted": accepted,
        "gates": gates,
        "metrics": {
            "vertexCount": len(positions),
            "triangleCount": len(faces_array),
            "constraintCount": len(seam_array),
            "maximumSeamSeparationCm": float(np.max(seam_array)) if len(seam_array) else None,
            "p95SeamSeparationCm": percentile(seam_array, 95.0),
            "maximumEdgeStrainRatio": float(np.max(strain)),
            "p95EdgeStrainRatio": percentile(strain, 95.0),
            "bodyIntersectionEdgeCount": len(body_edges),
            "selfIntersectionEdgeCount": len(self_edges),
            "minimumVertexBodyClearanceCm": minimum_vertex_clearance,
            "continuousBodyClearance": continuous_clearance,
            "minimumTriangleAreaCm2": float(np.min(triangle_areas)),
            "maximumStrainEdge": {
                "vertices": maximum_strain_edge.tolist(),
                "panels": sorted(
                    {vertex_owners[int(index)] for index in maximum_strain_edge}
                ),
                "strainRatio": float(strain[maximum_strain_index]),
            },
            "selfIntersectionPairCounts": dict(
                sorted(
                    intersection_pairs.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ),
        },
    }
    verification_id = hashlib.sha256(canonical_json(report_without_id)).hexdigest()
    report = {**report_without_id, "verificationId": verification_id}
    output_path = output_path.resolve()
    if output_path.exists():
        raise FileExistsError(f"Verification reports are immutable: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--arrangement", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", default="cuda:0")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    report = verify_arrangement(
        arguments.bundle,
        arguments.arrangement,
        arguments.output,
        arguments.device,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
