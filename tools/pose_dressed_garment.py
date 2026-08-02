#!/usr/bin/env python3
"""Transfer an accepted body pose onto an already-draped garment surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

try:
    from tools.pose_mpfb_body import arm_weights
except ModuleNotFoundError:
    from pose_mpfb_body import arm_weights


REPORT_SCHEMA_VERSION = "patterna.dressed-garment-pose/1.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_obj(path: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if line.startswith("v "):
            values = line.split()
            if len(values) < 4:
                raise ValueError(f"Invalid OBJ vertex line: {line}")
            vertices.append([float(values[1]), float(values[2]), float(values[3])])
        elif line.startswith("f "):
            indices = [int(value.split("/", 1)[0]) - 1 for value in line.split()[1:]]
            if len(indices) != 3:
                raise ValueError("Dressed pose transfer requires triangulated OBJ faces.")
            faces.append(indices)
    vertex_array = np.asarray(vertices, dtype=np.float64)
    face_array = np.asarray(faces, dtype=np.int64)
    if vertex_array.ndim != 2 or vertex_array.shape[1] != 3:
        raise ValueError("OBJ contains no valid vertices.")
    if face_array.ndim != 2 or face_array.shape[1] != 3:
        raise ValueError("OBJ contains no valid triangle faces.")
    if not np.isfinite(vertex_array).all():
        raise ValueError("OBJ contains a non-finite vertex coordinate.")
    return vertex_array, face_array, lines


def write_obj(path: Path, lines: list[str], vertices: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    vertex_index = 0
    output: list[str] = []
    for line in lines:
        if line.startswith("v "):
            x, y, z = vertices[vertex_index]
            output.append(f"v {x:.9f} {y:.9f} {z:.9f}")
            vertex_index += 1
        else:
            output.append(line)
    if vertex_index != len(vertices):
        raise ValueError("OBJ vertex rewrite did not preserve vertex count.")
    path.write_text("\n".join(output) + "\n", encoding="utf-8", newline="\n")


def structural_edge_strain(
    original: np.ndarray,
    posed: np.ndarray,
    faces: np.ndarray,
    excluded_vertex_indices: np.ndarray | None = None,
) -> tuple[float, float, float, list[int], int]:
    edges = np.concatenate(
        (faces[:, (0, 1)], faces[:, (1, 2)], faces[:, (2, 0)]),
        axis=0,
    )
    edges.sort(axis=1)
    edges = np.unique(edges, axis=0)
    before_exclusion = len(edges)
    if excluded_vertex_indices is not None and len(excluded_vertex_indices) > 0:
        excluded = np.zeros(len(original), dtype=bool)
        excluded[excluded_vertex_indices] = True
        edges = edges[~(excluded[edges[:, 0]] | excluded[edges[:, 1]])]
    original_lengths = np.linalg.norm(
        original[edges[:, 1]] - original[edges[:, 0]], axis=1
    )
    valid = original_lengths > 1.0e-8
    posed_lengths = np.linalg.norm(
        posed[edges[valid, 1]] - posed[edges[valid, 0]], axis=1
    )
    strain = np.abs((posed_lengths / original_lengths[valid]) - 1.0)
    maximum_index = int(np.argmax(strain))
    return (
        float(np.max(strain)),
        float(np.percentile(strain, 95.0)),
        float(np.percentile(strain, 99.9)),
        [int(value) for value in edges[valid][maximum_index]],
        before_exclusion - len(edges),
    )


def transfer_body_displacement(
    garment_vertices_cm: np.ndarray,
    source_body_m: np.ndarray,
    posed_body_m: np.ndarray,
    *,
    neighbors: int = 4,
    chunk_size: int = 256,
) -> tuple[np.ndarray, dict[str, float | int]]:
    if source_body_m.shape != posed_body_m.shape:
        raise ValueError("Source and posed bodies do not share stable topology.")
    if not 1 <= neighbors <= source_body_m.shape[0]:
        raise ValueError("Neighbor count is outside the body vertex range.")
    if chunk_size < 1:
        raise ValueError("Chunk size must be positive.")

    garment_m = garment_vertices_cm / 100.0
    body_displacement_m = posed_body_m - source_body_m
    posed_garment_m = garment_m.copy()
    nearest_distances: list[np.ndarray] = []

    for start in range(0, len(garment_m), chunk_size):
        stop = min(start + chunk_size, len(garment_m))
        points = garment_m[start:stop]
        delta = points[:, None, :] - source_body_m[None, :, :]
        distance_squared = np.einsum("ijk,ijk->ij", delta, delta)
        indices = np.argpartition(distance_squared, neighbors - 1, axis=1)[:, :neighbors]
        selected_distance_squared = np.take_along_axis(distance_squared, indices, axis=1)
        selected_distances = np.sqrt(np.maximum(selected_distance_squared, 0.0))
        inverse_distance = 1.0 / np.maximum(selected_distances, 1.0e-6)
        weights = inverse_distance / np.sum(inverse_distance, axis=1, keepdims=True)
        selected_displacement = body_displacement_m[indices]
        transferred = np.sum(selected_displacement * weights[:, :, None], axis=1)
        posed_garment_m[start:stop] += transferred
        nearest_distances.append(np.min(selected_distances, axis=1))

    all_nearest = np.concatenate(nearest_distances)
    displacement_cm = np.linalg.norm(posed_garment_m - garment_m, axis=1) * 100.0
    evidence: dict[str, float | int] = {
        "neighbors": neighbors,
        "maximum_nearest_body_distance_cm": float(np.max(all_nearest) * 100.0),
        "ninety_fifth_percentile_nearest_body_distance_cm": float(
            np.percentile(all_nearest, 95.0) * 100.0
        ),
        "affected_vertex_count": int(np.count_nonzero(displacement_cm > 0.01)),
        "maximum_displacement_cm": float(np.max(displacement_cm)),
    }
    return posed_garment_m * 100.0, evidence


def rotate_about_garmentcode_z(
    vertices_cm: np.ndarray,
    pivot_cm: np.ndarray,
    angle_radians: float,
) -> np.ndarray:
    """Apply the MPFB Y-axis rotation after x,y,z -> x,z,y conversion."""
    x = vertices_cm[:, 0] - pivot_cm[0]
    y = vertices_cm[:, 1] - pivot_cm[1]
    cosine = math.cos(angle_radians)
    sine = math.sin(angle_radians)
    rotated = vertices_cm.copy()
    rotated[:, 0] = pivot_cm[0] + x * cosine + y * sine
    rotated[:, 1] = pivot_cm[1] - x * sine + y * cosine
    return rotated


def interpolate_body_field(
    garment_vertices_cm: np.ndarray,
    source_body_m: np.ndarray,
    fields: list[np.ndarray],
    *,
    neighbors: int,
    chunk_size: int = 256,
) -> tuple[list[np.ndarray], np.ndarray]:
    garment_m = garment_vertices_cm / 100.0
    interpolated = [np.zeros(len(garment_m), dtype=np.float64) for _ in fields]
    nearest_distance = np.zeros(len(garment_m), dtype=np.float64)
    for start in range(0, len(garment_m), chunk_size):
        stop = min(start + chunk_size, len(garment_m))
        points = garment_m[start:stop]
        delta = points[:, None, :] - source_body_m[None, :, :]
        distance_squared = np.einsum("ijk,ijk->ij", delta, delta)
        indices = np.argpartition(distance_squared, neighbors - 1, axis=1)[:, :neighbors]
        selected_distance_squared = np.take_along_axis(distance_squared, indices, axis=1)
        selected_distances = np.sqrt(np.maximum(selected_distance_squared, 0.0))
        inverse_distance = 1.0 / np.maximum(selected_distances, 1.0e-6)
        weights = inverse_distance / np.sum(inverse_distance, axis=1, keepdims=True)
        nearest_distance[start:stop] = np.min(selected_distances, axis=1)
        for field_index, field in enumerate(fields):
            interpolated[field_index][start:stop] = np.sum(
                field[indices] * weights,
                axis=1,
            )
    return interpolated, nearest_distance


def transfer_rig_pose(
    garment_vertices_cm: np.ndarray,
    source_body_m: np.ndarray,
    rig_weights: dict[str, object],
    body_pose_report: dict[str, object],
    garment_labels: list[str] | None = None,
    *,
    neighbors: int = 16,
) -> tuple[np.ndarray, dict[str, object]]:
    lowering_degrees = float(body_pose_report["arm_lowering_degrees"])
    side_definitions = (
        (".L", "positive_x_arm", 1.0),
        (".R", "negative_x_arm", -1.0),
    )
    body_fields: list[np.ndarray] = []
    for suffix, _, _ in side_definitions:
        raw_weights = np.asarray(
            arm_weights(len(source_body_m), rig_weights, suffix),
            dtype=np.float64,
        )
        body_fields.append(raw_weights * raw_weights * (3.0 - 2.0 * raw_weights))

    garment_fields, nearest_distance = interpolate_body_field(
        garment_vertices_cm,
        source_body_m,
        body_fields,
        neighbors=neighbors,
    )
    posed = garment_vertices_cm.copy()
    side_evidence: dict[str, object] = {}
    report_sides = body_pose_report.get("sides")
    if not isinstance(report_sides, dict):
        raise ValueError("Body pose report has no side evidence.")
    for definition, influence in zip(side_definitions, garment_fields, strict=True):
        suffix, label, direction = definition
        side = report_sides.get(label)
        if not isinstance(side, dict):
            raise ValueError(f"Body pose report has no {label} evidence.")
        raw_pivot = np.asarray(side["shoulder_pivot_m"], dtype=np.float64)
        # The body preparation stage converts raw MPFB x,y,z into
        # GarmentCode x,z,y coordinates.
        pivot_cm = raw_pivot[[0, 2, 1]] * 100.0
        panel_vertex_count = 0
        if garment_labels is not None:
            if len(garment_labels) != len(garment_vertices_cm):
                raise ValueError("Garment labels do not match garment vertices.")
            side_token = "left" if suffix == ".L" else "right"
            panel_mask = np.asarray(
                [
                    (
                        f"{side_token}_sleeve" in garment_label.lower()
                        or f"sl_{side_token}_cuff" in garment_label.lower()
                    )
                    for garment_label in garment_labels
                ],
                dtype=bool,
            )
            stitch_mask = np.asarray(
                ["stitch" in garment_label.lower() for garment_label in garment_labels],
                dtype=bool,
            )
            influence = influence.copy()
            influence[~(panel_mask | stitch_mask)] = 0.0
            influence[panel_mask] = 1.0
            panel_vertex_count = int(np.count_nonzero(panel_mask))
        angle = math.radians(lowering_degrees) * direction
        rotated = rotate_about_garmentcode_z(posed, pivot_cm, angle)
        posed += (rotated - posed) * influence[:, None]
        side_evidence[label] = {
            "rig_suffix": suffix,
            "shoulder_pivot_cm": pivot_cm.tolist(),
            "maximum_influence": float(np.max(influence)),
            "affected_vertex_count": int(np.count_nonzero(influence > 0.001)),
            "rigid_panel_vertex_count": panel_vertex_count,
        }

    displacement_cm = np.linalg.norm(posed - garment_vertices_cm, axis=1)
    evidence: dict[str, object] = {
        "neighbors": neighbors,
        "maximum_nearest_body_distance_cm": float(np.max(nearest_distance) * 100.0),
        "ninety_fifth_percentile_nearest_body_distance_cm": float(
            np.percentile(nearest_distance, 95.0) * 100.0
        ),
        "affected_vertex_count": int(np.count_nonzero(displacement_cm > 0.01)),
        "maximum_displacement_cm": float(np.max(displacement_cm)),
        "sides": side_evidence,
    }
    return posed, evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--garment", type=Path, required=True)
    parser.add_argument("--source-body", type=Path, required=True)
    parser.add_argument("--posed-body", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-warp-report", type=Path, required=True)
    parser.add_argument("--posed-body-report", type=Path, required=True)
    parser.add_argument("--body-pose-report", type=Path, required=True)
    parser.add_argument("--rig-weights", type=Path, required=True)
    parser.add_argument("--garment-segmentation", type=Path, required=True)
    parser.add_argument("--neighbors", type=int, default=16)
    args = parser.parse_args()

    garment_path = args.garment.resolve()
    source_body_path = args.source_body.resolve()
    posed_body_path = args.posed_body.resolve()
    output_path = args.output.resolve()
    source_warp_report_path = args.source_warp_report.resolve()
    posed_body_report_path = args.posed_body_report.resolve()
    body_pose_report_path = args.body_pose_report.resolve()
    rig_weights_path = args.rig_weights.resolve()
    garment_segmentation_path = args.garment_segmentation.resolve()
    for path in (
        garment_path,
        source_body_path,
        posed_body_path,
        source_warp_report_path,
        posed_body_report_path,
        body_pose_report_path,
        rig_weights_path,
        garment_segmentation_path,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    source_warp_report = json.loads(
        source_warp_report_path.read_text(encoding="utf-8")
    )
    if not source_warp_report.get("accepted"):
        raise ValueError("Source garment Warp report is rejected.")
    reported_source_body_hash = source_warp_report.get("body_mesh_sha256")
    if reported_source_body_hash != sha256(source_body_path):
        raise ValueError("Source Warp report does not match the rest-pose body OBJ.")
    reported_garment_path = source_warp_report.get("output_mesh")
    if not isinstance(reported_garment_path, str) or (
        Path(reported_garment_path).resolve() != garment_path
    ):
        raise ValueError("Source Warp report does not identify the supplied garment OBJ.")
    posed_body_report = json.loads(
        posed_body_report_path.read_text(encoding="utf-8")
    )
    if not posed_body_report.get("accepted"):
        raise ValueError("Posed GarmentCode body report is rejected.")
    if posed_body_report.get("outputBodySha256") != sha256(posed_body_path):
        raise ValueError("Posed body report does not match the posed body OBJ.")
    body_pose_report = json.loads(body_pose_report_path.read_text(encoding="utf-8"))
    if not body_pose_report.get("accepted"):
        raise ValueError("Body pose report is rejected.")
    if posed_body_report.get("sourcePoseReportSha256") != sha256(body_pose_report_path):
        raise ValueError("Posed body conversion report does not match the body pose report.")
    rig_weight_payload = json.loads(rig_weights_path.read_text(encoding="utf-8"))
    if body_pose_report.get("rig_weights_sha256") != sha256(rig_weights_path):
        raise ValueError("Body pose report does not match the rig weights.")

    garment, garment_faces, garment_lines = parse_obj(garment_path)
    source_body, source_body_faces, _ = parse_obj(source_body_path)
    posed_body, posed_body_faces, _ = parse_obj(posed_body_path)
    if not np.array_equal(source_body_faces, posed_body_faces):
        raise ValueError("Source and posed body faces do not share stable topology.")

    segmentation_labels = garment_segmentation_path.read_text(
        encoding="utf-8"
    ).splitlines()
    if len(segmentation_labels) != len(garment):
        raise ValueError("Garment segmentation does not match the garment vertices.")
    posed_garment, transfer = transfer_rig_pose(
        garment,
        source_body,
        rig_weight_payload,
        body_pose_report,
        segmentation_labels,
        neighbors=args.neighbors,
    )
    (
        maximum_strain,
        p95_strain,
        p999_strain,
        maximum_strain_edge,
        excluded_seam_edge_count,
    ) = structural_edge_strain(
        garment,
        posed_garment,
        garment_faces,
    )
    issues: list[str] = []
    if not np.isfinite(posed_garment).all():
        issues.append("Pose transfer produced non-finite garment vertices.")
    if transfer["ninety_fifth_percentile_nearest_body_distance_cm"] > 8.0:
        issues.append("Garment is too far from the body for stable pose transfer.")
    if maximum_strain > 0.20:
        issues.append("Pose transfer causes excessive peak structural strain.")
    if p999_strain > 0.08:
        issues.append("Pose transfer causes excessive distributed structural strain.")

    write_obj(output_path, garment_lines, posed_garment)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "accepted": not issues,
        "issues": issues,
        "method": "interpolated MPFB arm-rig transform transfer",
        "source_garment": str(garment_path),
        "source_garment_sha256": sha256(garment_path),
        "source_warp_report": str(source_warp_report_path),
        "source_warp_report_sha256": sha256(source_warp_report_path),
        "source_body": str(source_body_path),
        "source_body_sha256": sha256(source_body_path),
        "posed_body": str(posed_body_path),
        "posed_body_sha256": sha256(posed_body_path),
        "posed_body_report": str(posed_body_report_path),
        "posed_body_report_sha256": sha256(posed_body_report_path),
        "body_pose_report": str(body_pose_report_path),
        "body_pose_report_sha256": sha256(body_pose_report_path),
        "rig_weights": str(rig_weights_path),
        "rig_weights_sha256": sha256(rig_weights_path),
        "garment_segmentation": str(garment_segmentation_path),
        "garment_segmentation_sha256": sha256(garment_segmentation_path),
        "output_garment": str(output_path),
        "output_garment_sha256": sha256(output_path),
        "garment_vertex_count": int(garment.shape[0]),
        "garment_face_count": int(garment_faces.shape[0]),
        "body_vertex_count": int(source_body.shape[0]),
        "body_face_count": int(source_body_faces.shape[0]),
        "topology_preserved": True,
        "whole_surface_edge_validation": True,
        "transfer": transfer,
        "maximum_transfer_edge_strain_ratio": maximum_strain,
        "maximum_transfer_strain_edge_vertices": maximum_strain_edge,
        "maximum_transfer_strain_edge_labels": [
            segmentation_labels[index] for index in maximum_strain_edge
        ],
        "excluded_seam_edge_count": excluded_seam_edge_count,
        "ninety_fifth_percentile_transfer_edge_strain_ratio": p95_strain,
        "ninety_ninth_point_ninth_percentile_transfer_edge_strain_ratio": p999_strain,
    }
    report_path = output_path.with_suffix(".pose-report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
