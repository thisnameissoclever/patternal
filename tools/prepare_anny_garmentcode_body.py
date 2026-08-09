#!/usr/bin/env python3
"""Prepare one accepted Anny body for GarmentCode drafting and cloth collision."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import ConvexHull
import trimesh
import yaml

from mesh_torso_arcs import (
    back_fraction_from_across_measurements,
    lateral_extrema_depth_cm,
    measure_torso_arc_section,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--avatar-body", type=Path, required=True)
    parser.add_argument("--fit-report", type=Path, required=True)
    parser.add_argument("--segmentation", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-body", type=Path, required=True)
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_mesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load(path, process=False, maintain_order=True)
    if not isinstance(mesh, trimesh.Trimesh):
        raise TypeError(f"Expected one mesh in {path}, received {type(mesh).__name__}")
    return mesh


def anny_to_garmentcode(vertices: np.ndarray) -> np.ndarray:
    """Convert Anny X/right, Y/back, Z/up to GarmentCode X, Y/up, Z/depth."""

    converted = np.column_stack((vertices[:, 0], vertices[:, 2], vertices[:, 1]))
    converted[:, 1] -= float(converted[:, 1].min())
    return converted


def averaged_measurement(measurements: dict[str, object], *names: str) -> float:
    values = [float(measurements[name]) for name in names if name in measurements]
    if not values or not np.isfinite(values).all() or min(values) <= 0.0:
        raise ValueError("Missing or invalid measurement: " + ", ".join(names))
    return float(np.mean(values))


def validate_segmentation(
    segmentation: dict[str, object],
    vertex_count: int,
) -> dict[str, list[int]]:
    expected = {
        "body",
        "left_arm",
        "right_arm",
        "left_leg",
        "right_leg",
        "face_internal",
    }
    if set(segmentation) != expected:
        raise ValueError("Anny collision segmentation has unexpected labels")
    normalized = {
        name: [int(index) for index in indices]
        for name, indices in segmentation.items()
        if isinstance(indices, list)
    }
    flattened = [index for indices in normalized.values() for index in indices]
    if sorted(flattened) != list(range(vertex_count)):
        raise ValueError("Anny collision segmentation is not a vertex partition")
    return normalized


def measure_armhole_front_fraction(
    mesh: trimesh.Trimesh,
    segmentation: dict[str, list[int]],
) -> tuple[float, dict[str, object]]:
    """Measure front/back armscye balance from each Anny arm-root interface.

    Dominant rig labels create a jagged topological boundary, so its raw edge
    sum is not a usable tape measurement. The planar convex envelope is stable
    enough to recover the front/back proportion while the editable armscye
    circumference remains the authority for the finished total length.
    """

    label_names = list(segmentation)
    labels = np.full(len(mesh.vertices), -1, dtype=np.int32)
    for label_index, name in enumerate(label_names):
        labels[np.asarray(segmentation[name], dtype=np.int32)] = label_index
    face_labels = np.empty(len(mesh.faces), dtype=np.int32)
    for face_index, face in enumerate(np.asarray(mesh.faces, dtype=np.int32)):
        values, counts = np.unique(labels[face], return_counts=True)
        face_labels[face_index] = int(values[np.argmax(counts)])

    body_label = label_names.index("body")
    per_side: dict[str, dict[str, float]] = {}
    fractions: list[float] = []
    for side_name in ("left_arm", "right_arm"):
        arm_label = label_names.index(side_name)
        interface_edges = np.asarray(
            [
                edge
                for adjacent_faces, edge in zip(
                    mesh.face_adjacency,
                    mesh.face_adjacency_edges,
                )
                if {
                    int(face_labels[int(adjacent_faces[0])]),
                    int(face_labels[int(adjacent_faces[1])]),
                }
                == {body_label, arm_label}
            ],
            dtype=np.int32,
        )
        if interface_edges.ndim != 2 or len(interface_edges) < 8:
            raise RuntimeError(f"Anny {side_name} has no usable arm-root boundary")
        points_cm = (
            np.asarray(mesh.vertices, dtype=float)[np.unique(interface_edges)] * 100.0
        )
        centered = points_cm - np.mean(points_cm, axis=0)
        _, _, axes = np.linalg.svd(centered, full_matrices=False)
        planar = centered @ axes[:2].T
        hull = ConvexHull(planar)
        ordered_2d = planar[hull.vertices]
        ordered_3d = points_cm[hull.vertices]
        next_2d = np.roll(ordered_2d, -1, axis=0)
        next_3d = np.roll(ordered_3d, -1, axis=0)
        lengths_cm = np.linalg.norm(ordered_2d - next_2d, axis=1)
        midpoint_depth_cm = 0.5 * (ordered_3d[:, 2] + next_3d[:, 2])
        center_depth_cm = float(np.mean(points_cm[:, 2]))
        front_length_cm = float(
            np.sum(lengths_cm[midpoint_depth_cm < center_depth_cm])
        )
        back_length_cm = float(
            np.sum(lengths_cm[midpoint_depth_cm >= center_depth_cm])
        )
        total_length_cm = front_length_cm + back_length_cm
        if total_length_cm <= 0.0:
            raise RuntimeError(f"Anny {side_name} arm-root envelope is degenerate")
        fraction = front_length_cm / total_length_cm
        if fraction < 0.40 or fraction > 0.60:
            raise RuntimeError(
                f"Anny {side_name} front armscye fraction is implausible: "
                f"{fraction:.4f}"
            )
        fractions.append(fraction)
        per_side[side_name] = {
            "frontEnvelopeLengthCm": front_length_cm,
            "backEnvelopeLengthCm": back_length_cm,
            "envelopeCircumferenceCm": total_length_cm,
            "frontFraction": fraction,
        }
    measured_fraction = float(np.mean(fractions))
    return measured_fraction, {
        "method": "dominant-rig arm-root planar convex envelope",
        "frontDirection": "negative GarmentCode Z",
        "frontFraction": measured_fraction,
        "sides": per_side,
    }


def front_landmark_vertex(
    mesh: trimesh.Trimesh,
    *,
    x_cm: float,
    height_cm: float,
) -> int:
    """Locate a requested landmark on Anny's negative-depth front surface."""

    vertices_cm = np.asarray(mesh.vertices, dtype=float) * 100.0
    height_distance = np.abs(vertices_cm[:, 1] - height_cm)
    near_height = height_distance <= 1.5
    if not np.any(near_height):
        raise RuntimeError("Anny surface has no vertices near a drafting landmark")
    available_x = vertices_cm[near_height, 0]
    clamped_x = float(np.clip(x_cm, available_x.min() + 0.2, available_x.max() - 0.2))
    near_landmark = near_height & (np.abs(vertices_cm[:, 0] - clamped_x) <= 1.6)
    candidates = np.flatnonzero(near_landmark)
    if len(candidates) < 2:
        raise RuntimeError("Anny surface has no front vertices near a drafting landmark")
    score = (
        np.abs(vertices_cm[candidates, 0] - clamped_x) * 0.15
        + height_distance[candidates] * 0.15
        + vertices_cm[candidates, 2]
    )
    return int(candidates[np.argmin(score)])


def geodesic_graph_cm(mesh: trimesh.Trimesh):
    faces = np.asarray(mesh.faces, dtype=np.int64)
    edges = np.vstack((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    edges = np.sort(edges, axis=1)
    edges = np.unique(edges, axis=0)
    vertices_cm = np.asarray(mesh.vertices, dtype=float) * 100.0
    lengths = np.linalg.norm(
        vertices_cm[edges[:, 0]] - vertices_cm[edges[:, 1]],
        axis=1,
    )
    rows = np.concatenate((edges[:, 0], edges[:, 1]))
    columns = np.concatenate((edges[:, 1], edges[:, 0]))
    weights = np.concatenate((lengths, lengths))
    return coo_matrix(
        (weights, (rows, columns)),
        shape=(len(vertices_cm), len(vertices_cm)),
    ).tocsr()


def front_shoulder_height_cm(
    mesh: trimesh.Trimesh,
    *,
    x_cm: float,
    bust_height_cm: float,
) -> float:
    """Find the top of the shoulder surface at the princess seam X."""

    vertices_cm = np.asarray(mesh.vertices, dtype=float) * 100.0
    candidates = vertices_cm[
        (np.abs(vertices_cm[:, 0] - x_cm) <= 1.6)
        & (vertices_cm[:, 1] >= bust_height_cm + 8.0)
        & (vertices_cm[:, 1] <= bust_height_cm + 24.0)
        & (vertices_cm[:, 2] < 0.0)
    ]
    if len(candidates) < 3:
        raise RuntimeError("Could not locate the Anny shoulder surface")
    return float(candidates[:, 1].max())


def front_geodesic_ruler_cm(
    mesh: trimesh.Trimesh,
    graph,
    *,
    start_height_cm: float,
    end_height_cm: float,
    start_x_cm: float,
    end_x_cm: float,
) -> float:
    """Measure a princess ruler along the connected Anny body surface."""

    start = front_landmark_vertex(
        mesh,
        x_cm=start_x_cm,
        height_cm=start_height_cm,
    )
    end = front_landmark_vertex(
        mesh,
        x_cm=end_x_cm,
        height_cm=end_height_cm,
    )
    distance = float(dijkstra(graph, directed=False, indices=start)[end])
    if not math.isfinite(distance) or distance <= 0.0:
        raise RuntimeError("Anny surface geodesic ruler did not converge")
    return distance


def side_landmark_vertex(
    mesh: trimesh.Trimesh,
    torso_indices: np.ndarray,
    *,
    height_cm: float,
    side_seam_depth_cm: float,
) -> int:
    """Locate the right torso side seam at one horizontal body station."""

    vertices_cm = np.asarray(mesh.vertices, dtype=float) * 100.0
    indices = np.asarray(torso_indices, dtype=np.int32)
    points = vertices_cm[indices]
    height_distance = np.abs(points[:, 1] - height_cm)
    near_height = height_distance <= 1.5
    if not np.any(near_height):
        raise RuntimeError("Anny torso has no vertices near a side-seam landmark")
    lateral_extent = points[:, 0]
    maximum_lateral = float(np.max(lateral_extent[near_height]))
    candidates_mask = (
        near_height
        & (lateral_extent > 0.0)
        & (lateral_extent >= maximum_lateral * 0.72)
    )
    candidates = np.flatnonzero(candidates_mask)
    if len(candidates) < 2:
        raise RuntimeError("Anny torso has no usable right side-seam landmark")
    candidate_points = points[candidates]
    score = (
        np.abs(candidate_points[:, 2] - side_seam_depth_cm)
        + height_distance[candidates]
        + (maximum_lateral - candidate_points[:, 0]) * 0.08
    )
    return int(indices[candidates[int(np.argmin(score))]])


def side_geodesic_ruler_cm(
    mesh: trimesh.Trimesh,
    graph,
    torso_indices: np.ndarray,
    *,
    start_height_cm: float,
    end_height_cm: float,
    side_seam_depth_cm: float,
) -> float:
    """Measure one vertical side-seam section on the collision surface."""

    start = side_landmark_vertex(
        mesh,
        torso_indices,
        height_cm=start_height_cm,
        side_seam_depth_cm=side_seam_depth_cm,
    )
    end = side_landmark_vertex(
        mesh,
        torso_indices,
        height_cm=end_height_cm,
        side_seam_depth_cm=side_seam_depth_cm,
    )
    distance = float(dijkstra(graph, directed=False, indices=start)[end])
    if not math.isfinite(distance) or distance <= 0.0:
        raise RuntimeError("Anny side-seam surface ruler did not converge")
    # The source mesh rarely has a vertex exactly on a requested horizontal
    # drafting plane. Extend only the missing vertical interval so a sampled
    # ruler can never become shorter than the anatomical station interval.
    # Adding both endpoint errors would double-count a shared offset when two
    # nearby samples sit on the same side of their requested planes.
    vertices_cm = np.asarray(mesh.vertices, dtype=float) * 100.0
    requested_interval = abs(float(end_height_cm) - float(start_height_cm))
    sampled_interval = abs(
        float(vertices_cm[end, 1]) - float(vertices_cm[start, 1])
    )
    endpoint_extension = max(0.0, requested_interval - sampled_interval)
    return max(
        distance + endpoint_extension,
        requested_interval,
    )


def station_heights_cm(
    fit_report: dict[str, object],
    profile: dict[str, object],
) -> dict[str, float]:
    raw = fit_report.get("stationHeightsCm")
    measurements = profile.get("measurements")
    if not isinstance(raw, dict) or not isinstance(measurements, dict):
        raise ValueError("Anny fit and avatar profile need anatomical landmarks")
    stations = {
        name: float(raw[name])
        for name in ("hip", "abdomen", "waist", "underbust", "bust")
    }
    armhole_depth = averaged_measurement(
        measurements,
        "armholeDepthL",
        "armholeDepthR",
    )
    front_waist_length = float(measurements["frontWaistLength"])
    underarm = stations["waist"] + front_waist_length - armhole_depth
    if underarm <= stations["bust"] + 1.5:
        raise ValueError("Anny underarm landmark is not above the full bust")
    stations["underarmCircuit"] = underarm
    stations["upperTorsoCircuit"] = stations["bust"] + 0.65 * (
        underarm - stations["bust"]
    )
    stations["highBustTape"] = underarm + 1.5
    return stations


def build_drafting_body(
    collision_body: trimesh.Trimesh,
    profile: dict[str, object],
    stations: dict[str, float],
    torso_indices: np.ndarray,
) -> tuple[dict[str, float], dict[str, object]]:
    source_body = profile.get("body")
    measurements = profile.get("measurements")
    if not isinstance(source_body, dict) or not isinstance(measurements, dict):
        raise ValueError("Avatar profile must contain body and measurements objects")
    body = {str(key): float(value) for key, value in source_body.items()}
    sections = {
        name: measure_torso_arc_section(
            collision_body,
            height,
            front_is_positive_depth=False,
        )
        for name, height in stations.items()
        if name != "highBustTape"
    }
    high_bust_back_fraction = back_fraction_from_across_measurements(
        float(measurements["acrossFront"]),
        float(measurements["acrossBack"]),
    )
    bust_side_seam_depth_cm = lateral_extrema_depth_cm(
        collision_body,
        stations["bust"],
    )
    for station in ("bust", "upperTorsoCircuit", "underarmCircuit"):
        sections[station] = measure_torso_arc_section(
            collision_body,
            stations[station],
            front_is_positive_depth=False,
            side_seam_depth_cm=bust_side_seam_depth_cm,
        )

    body["high_bust"] = float(measurements["highChestCirc"])
    body["armscye_circumference"] = averaged_measurement(
        measurements,
        "armscyeCircL",
        "armscyeCircR",
    )
    body["patterna_requested_armhole_depth"] = averaged_measurement(
        measurements,
        "armholeDepthL",
        "armholeDepthR",
    )
    body["patterna_armscye_is_estimated"] = 1.0
    body["patterna_armhole_depth_is_estimated"] = 1.0
    body["back_width"] = float(body["bust"]) * sections["bust"].back_fraction
    body["waist_back_width"] = (
        float(body["waist"]) * sections["waist"].back_fraction
    )
    for station, key in (
        ("bust", "patterna_back_bust_fraction"),
        ("upperTorsoCircuit", "patterna_back_upper_torso_fraction"),
        ("underarmCircuit", "patterna_back_underarm_fraction"),
        ("underbust", "patterna_back_underbust_fraction"),
        ("waist", "patterna_back_waist_fraction"),
    ):
        body[key] = sections[station].back_fraction
    body["patterna_back_high_bust_tape_fraction"] = high_bust_back_fraction

    waist_height = stations["waist"]
    body["patterna_waist_level_world"] = waist_height
    body["patterna_side_seam_height_from_waist"] = (
        stations["underarmCircuit"] - waist_height
    )
    body["patterna_upper_torso_height_from_waist"] = (
        stations["upperTorsoCircuit"] - waist_height
    )
    body["patterna_high_bust_tape_height_from_waist"] = (
        stations["highBustTape"] - waist_height
    )
    body["patterna_bust_height_from_waist"] = stations["bust"] - waist_height
    body["patterna_underbust_height_from_waist"] = (
        stations["underbust"] - waist_height
    )
    body["patterna_full_bust_horizontal_circumference"] = (
        sections["bust"].circumference_cm
    )
    body["patterna_upper_torso_circumference"] = (
        sections["upperTorsoCircuit"].circumference_cm
    )
    body["patterna_underarm_circumference"] = (
        sections["underarmCircuit"].circumference_cm
    )

    bust_apex_half_cm = float(body["bust_points"]) / 2.0
    waist_princess_x_cm = bust_apex_half_cm * 0.78
    shoulder_half_cm = float(body["shoulder_w"]) / 2.0
    neck_half_cm = float(body["neck_w"]) * 0.42
    shoulder_princess_x_cm = min(
        shoulder_half_cm - max(2.5, shoulder_half_cm * 0.18),
        bust_apex_half_cm * 1.23,
    )
    shoulder_drop_cm = math.tan(math.radians(float(body["shoulder_incl"]))) * (
        shoulder_half_cm - neck_half_cm
    )
    shoulder_height_cm = front_shoulder_height_cm(
        collision_body,
        x_cm=shoulder_princess_x_cm,
        bust_height_cm=stations["bust"],
    )
    surface_graph = geodesic_graph_cm(collision_body)
    waist_to_underbust_cm = front_geodesic_ruler_cm(
        collision_body,
        surface_graph,
        start_height_cm=waist_height,
        end_height_cm=stations["underbust"],
        start_x_cm=waist_princess_x_cm,
        end_x_cm=bust_apex_half_cm,
    )
    underbust_to_bust_cm = front_geodesic_ruler_cm(
        collision_body,
        surface_graph,
        start_height_cm=stations["underbust"],
        end_height_cm=stations["bust"],
        start_x_cm=bust_apex_half_cm,
        end_x_cm=bust_apex_half_cm,
    )
    body["patterna_front_princess_waist_to_underbust_length"] = (
        waist_to_underbust_cm
    )
    body["patterna_front_princess_underbust_to_bust_length"] = (
        underbust_to_bust_cm
    )
    body["patterna_front_princess_contour_length"] = (
        waist_to_underbust_cm + underbust_to_bust_cm
    )
    body["patterna_front_princess_upper_contour_length"] = (
        front_geodesic_ruler_cm(
            collision_body,
            surface_graph,
            start_height_cm=stations["bust"],
            end_height_cm=shoulder_height_cm,
            start_x_cm=bust_apex_half_cm,
            end_x_cm=shoulder_princess_x_cm,
        )
    )
    side_waist_to_underbust_cm = side_geodesic_ruler_cm(
        collision_body,
        surface_graph,
        torso_indices,
        start_height_cm=waist_height,
        end_height_cm=stations["underbust"],
        side_seam_depth_cm=bust_side_seam_depth_cm,
    )
    side_underbust_to_upper_torso_cm = side_geodesic_ruler_cm(
        collision_body,
        surface_graph,
        torso_indices,
        start_height_cm=stations["underbust"],
        end_height_cm=stations["upperTorsoCircuit"],
        side_seam_depth_cm=bust_side_seam_depth_cm,
    )
    side_upper_torso_to_underarm_cm = side_geodesic_ruler_cm(
        collision_body,
        surface_graph,
        torso_indices,
        start_height_cm=stations["upperTorsoCircuit"],
        end_height_cm=stations["underarmCircuit"],
        side_seam_depth_cm=bust_side_seam_depth_cm,
    )
    body["patterna_side_waist_to_underbust_length"] = (
        side_waist_to_underbust_cm
    )
    body["patterna_side_underbust_to_upper_torso_length"] = (
        side_underbust_to_upper_torso_cm
    )
    body["patterna_side_upper_torso_to_underarm_length"] = (
        side_upper_torso_to_underarm_cm
    )
    torso_vertices_cm = (
        np.asarray(collision_body.vertices, dtype=float)[
            np.asarray(torso_indices, dtype=np.int32)
        ]
        * 100.0
    )
    dressing_band = torso_vertices_cm[
        (torso_vertices_cm[:, 1] >= waist_height - 1.0)
        & (torso_vertices_cm[:, 1] <= shoulder_height_cm + 2.0)
    ]
    if len(dressing_band) < 24:
        raise RuntimeError("Anny torso segmentation has no usable dressing band")
    body["patterna_front_depth_sign"] = -1.0
    body["patterna_front_staging_depth_cm"] = (
        float(np.min(dressing_band[:, 2])) - 2.0
    )
    body["patterna_back_staging_depth_cm"] = (
        float(np.max(dressing_band[:, 2])) + 2.0
    )
    return body, {
        "heightsCm": stations,
        "bustSideSeamDepthCm": bust_side_seam_depth_cm,
        "bustArcSplitMethod": (
            "full-bust lateral extrema continued through the underarm"
        ),
        "frontDirection": "negative GarmentCode Z",
        "highBustTapeDistribution": {
            "heightCm": stations["highBustTape"],
            "requestedCircumferenceCm": float(measurements["highChestCirc"]),
            "backFraction": high_bust_back_fraction,
            "source": "editable acrossFront and acrossBack measurements",
            "horizontalColliderSectionUsed": False,
        },
        "frontStagingDepthCm": body["patterna_front_staging_depth_cm"],
        "backStagingDepthCm": body["patterna_back_staging_depth_cm"],
        "princessRulerMethod": "shortest path on the exact collision surface",
        "princessRulerSegmentsCm": {
            "waistToUnderbust": waist_to_underbust_cm,
            "underbustToBust": underbust_to_bust_cm,
            "waistToBust": waist_to_underbust_cm + underbust_to_bust_cm,
        },
        "sideSeamRulerMethod": "shortest path on the exact collision surface",
        "sideSeamRulerSegmentsCm": {
            "waistToUnderbust": side_waist_to_underbust_cm,
            "underbustToUpperTorso": side_underbust_to_upper_torso_cm,
            "upperTorsoToUnderarm": side_upper_torso_to_underarm_cm,
        },
        "shoulderSurfaceHeightCm": shoulder_height_cm,
        "sections": {name: section.to_dict() for name, section in sections.items()},
    }


def main() -> None:
    args = parse_args()
    avatar_body_path = resolve(args.avatar_body)
    fit_report_path = resolve(args.fit_report)
    segmentation_path = resolve(args.segmentation)
    profile_path = resolve(args.profile)
    output_body_path = resolve(args.output_body)
    fit_report = json.loads(fit_report_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if not fit_report.get("accepted"):
        raise ValueError("Anny fit report must be accepted")
    if fit_report.get("sourceProfileSha256") != sha256(profile_path):
        raise ValueError("Anny fit report does not match the avatar profile")
    if fit_report.get("outputCollisionBodySha256") != sha256(avatar_body_path):
        raise ValueError("Anny fit report does not match the collision body")
    if fit_report.get("outputCollisionSegmentationSha256") != sha256(segmentation_path):
        raise ValueError("Anny fit report does not match the segmentation")

    source = load_mesh(avatar_body_path)
    converted_vertices = anny_to_garmentcode(
        np.asarray(source.vertices, dtype=float)
    )
    collision_body = trimesh.Trimesh(
        vertices=converted_vertices,
        faces=np.asarray(source.faces, dtype=np.int64),
        process=False,
        maintain_order=True,
    )
    collision_body.fix_normals(multibody=False)
    components = collision_body.split(only_watertight=False)
    if not collision_body.is_watertight or len(components) != 1:
        raise ValueError("Prepared Anny collision body must be one watertight surface")
    segmentation = validate_segmentation(
        json.loads(segmentation_path.read_text(encoding="utf-8")),
        len(collision_body.vertices),
    )
    front_armscye_fraction, armhole_balance_report = (
        measure_armhole_front_fraction(collision_body, segmentation)
    )
    stations = station_heights_cm(fit_report, profile)
    body_values, circuit_report = build_drafting_body(
        collision_body,
        profile,
        stations,
        np.asarray(segmentation["body"], dtype=np.int32),
    )
    body_values["patterna_front_armscye_fraction"] = front_armscye_fraction

    output_body_path.parent.mkdir(parents=True, exist_ok=True)
    collision_body.export(output_body_path)
    output_segmentation_path = output_body_path.with_suffix(".segmentation.json")
    output_measurements_path = output_body_path.with_suffix(".yaml")
    output_report_path = output_body_path.with_suffix(".report.json")
    output_segmentation_path.write_text(
        json.dumps(segmentation, indent=2) + "\n",
        encoding="utf-8",
    )
    output_measurements_path.write_text(
        yaml.safe_dump({"body": body_values}, sort_keys=True),
        encoding="utf-8",
    )
    height_cm = float(np.ptp(collision_body.vertices[:, 1]) * 100.0)
    requested_height_cm = float(profile["measurements"]["height"])
    report = {
        "schemaVersion": "patterna.anny-garmentcode-body/1.0",
        "sourceBody": str(avatar_body_path),
        "sourceBodySha256": sha256(avatar_body_path),
        "sourceFitReport": str(fit_report_path),
        "sourceFitReportSha256": sha256(fit_report_path),
        "sourceProfile": str(profile_path),
        "sourceProfileSha256": sha256(profile_path),
        "sourceSegmentation": str(segmentation_path),
        "sourceSegmentationSha256": sha256(segmentation_path),
        "outputBody": str(output_body_path),
        "outputBodySha256": sha256(output_body_path),
        "coordinateTransform": "Anny x,y,z to GarmentCode x,z,y; feet at y=0",
        "vertexCount": int(len(collision_body.vertices)),
        "faceCount": int(len(collision_body.faces)),
        "watertight": bool(collision_body.is_watertight),
        "connectedComponents": len(components),
        "heightCm": height_cm,
        "requestedHeightCm": requested_height_cm,
        "heightResidualCm": height_cm - requested_height_cm,
        "segmentationCounts": {
            name: len(indices) for name, indices in segmentation.items()
        },
        "segmentationSource": "Anny dominant rig influences",
        "anatomicalCircuits": circuit_report,
        "armholeBalance": armhole_balance_report,
        "accepted": bool(
            abs(height_cm - requested_height_cm) <= 0.15
            and collision_body.is_watertight
            and len(components) == 1
        ),
    }
    output_report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    if not report["accepted"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
