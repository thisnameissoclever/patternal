#!/usr/bin/env python3
"""Fit an Anny female body to Patterna circuits, depths, and torso landmarks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import anny
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq
import torch
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anny_parametric_fit import optimize_native_controls
from mesh_torso_arcs import _central_torso_loop, measure_torso_arc_section


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_PHENOTYPE = {
    "gender": 1.0,
    "age": 0.67,
    "muscle": 0.12,
    "weight": 0.30,
    "height": 0.50,
    "proportions": 0.52,
    "cupsize": 0.72,
    "firmness": 1.0,
    "african": 0.72,
    "asian": 0.08,
    "caucasian": 0.20,
}
BASE_LOCAL_CHANGES = {
    "breast-trans-up": 1.0,
    "breast-volume-vert-up": 0.8,
    "breast-dist-incr": 0.0,
    "breast-point-incr": -0.15,
    "measure-underbust-circ-incr": 0.0,
    "measure-waist-circ-incr": 1.0,
    "measure-bust-circ-incr": 1.0,
    "hip-scale-depth-incr": 1.6,
    "l-upperarm-scale-horiz-incr": -0.4,
    "r-upperarm-scale-horiz-incr": -0.4,
    "l-upperarm-scale-depth-incr": -0.4,
    "r-upperarm-scale-depth-incr": -0.4,
}
STATION_OFFSETS_CM = {
    "hip": -18.0,
    "abdomen": -7.0,
    "waist": 0.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scaled_to_height(
    vertices: np.ndarray,
    target_height_cm: float,
    measurement_indices: np.ndarray | None = None,
) -> np.ndarray:
    result = np.asarray(vertices, dtype=np.float64).copy()
    measured = result if measurement_indices is None else result[measurement_indices]
    height = float(np.ptp(measured[:, 2]))
    if height <= 0.0 or target_height_cm <= 0.0:
        raise ValueError("Anny body height must be positive")
    result *= (target_height_cm / 100.0) / height
    scaled_measured = (
        result if measurement_indices is None else result[measurement_indices]
    )
    result[:, 2] -= float(scaled_measured[:, 2].min())
    return result


def y_up_mesh(vertices: np.ndarray, faces: np.ndarray) -> trimesh.Trimesh:
    converted = np.column_stack((vertices[:, 0], vertices[:, 2], vertices[:, 1]))
    return trimesh.Trimesh(vertices=converted, faces=faces, process=False)


def section_loop(vertices: np.ndarray, faces: np.ndarray, height_m: float) -> np.ndarray:
    section = y_up_mesh(vertices, faces).section(
        plane_origin=np.asarray([0.0, height_m, 0.0]),
        plane_normal=np.asarray([0.0, 1.0, 0.0]),
    )
    if section is None:
        raise RuntimeError(f"No Anny torso surface crosses {height_m * 100.0:.3f} cm")
    return _central_torso_loop(section)


def closed_perimeter_cm(points: np.ndarray) -> float:
    values = np.asarray(points, dtype=float)
    if np.linalg.norm(values[0] - values[-1]) > 1.0e-9:
        values = np.vstack((values, values[0]))
    return float(np.linalg.norm(np.diff(values, axis=0), axis=1).sum() * 100.0)


def find_breast_stations(
    vertices: np.ndarray,
    faces: np.ndarray,
    waist_height_m: float,
) -> tuple[float, float, dict[str, object]]:
    mesh = y_up_mesh(vertices, faces)
    offsets = np.arange(7.0, 23.6, 0.5)
    circuits = np.asarray([
        measure_torso_arc_section(
            mesh,
            waist_height_m * 100.0 + float(offset),
            front_is_positive_depth=False,
        ).circumference_cm
        for offset in offsets
    ])
    rises = np.diff(circuits)
    root_index = int(np.argmax(rises))
    root_offset_cm = float(offsets[root_index])
    bust_domain = np.where((offsets >= root_offset_cm + 3.0) & (offsets <= 23.0))[0]
    bust_index = int(bust_domain[np.argmax(circuits[bust_domain])])
    bust_offset_cm = float(offsets[bust_index])
    return root_offset_cm, bust_offset_cm, {
        "sampleOffsetsCm": offsets.tolist(),
        "sampleCircuitsCm": circuits.tolist(),
        "largestRootRiseCm": float(rises[root_index]),
        "rootOffsetCm": root_offset_cm,
        "bustOffsetCm": bust_offset_cm,
    }


def body_face_indices(faces: np.ndarray) -> np.ndarray:
    """Return the single largest connected face component."""

    groups = trimesh.graph.connected_components(
        trimesh.graph.face_adjacency(faces),
        nodes=np.arange(len(faces)),
        min_len=1,
    )
    if not groups:
        raise RuntimeError("Anny generated no connected surface components")
    return np.asarray(max(groups, key=len), dtype=np.int64)


def compact_surface(
    vertices: np.ndarray,
    faces: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compact one surface while preserving its original vertex-index mapping."""

    source_indices = np.unique(faces.reshape(-1))
    remap = np.full(len(vertices), -1, dtype=np.int64)
    remap[source_indices] = np.arange(len(source_indices), dtype=np.int64)
    return vertices[source_indices], remap[faces], source_indices


def export_obj_preserving_vertices(
    path: Path,
    vertices: np.ndarray,
    faces: np.ndarray,
) -> None:
    """Write an OBJ without dropping unreferenced stable-topology vertices."""

    with path.open("w", encoding="utf-8", newline="\n") as output:
        output.write("# Patterna Anny stable-topology body\n")
        for x, y, z in vertices:
            output.write(f"v {x:.9f} {y:.9f} {z:.9f}\n")
        for a, b, c in faces:
            output.write(f"f {int(a) + 1} {int(b) + 1} {int(c) + 1}\n")


def breast_landmark_metrics(
    vertices: np.ndarray,
    faces: np.ndarray,
    root_height_m: float,
    bust_height_m: float,
) -> dict[str, float]:
    """Measure breast apices and the root recess from detected anatomy.

    Anny faces toward negative Y. The previous implementation used fixed
    whole-body height ratios inherited from another topology, so it sampled
    the abdomen instead of the inframammary root.
    """

    apices: list[np.ndarray] = []
    root_heights_m: list[float] = []
    root_reliefs_cm: list[float] = []
    root_curve_depths_cm: list[float] = []
    for side in (-1.0, 1.0):
        side_x = vertices[:, 0] * side
        breast_mask = (
            (side_x >= 0.035)
            & (side_x <= 0.18)
            & (vertices[:, 2] >= root_height_m - 0.005)
            & (vertices[:, 2] <= bust_height_m + 0.035)
        )
        candidates = vertices[breast_mask]
        if len(candidates) < 20:
            raise RuntimeError("Could not isolate an Anny breast surface")
        apex = candidates[int(np.argmin(candidates[:, 1]))]
        apices.append(apex)

        def front_y_at(height_m: float) -> float:
            loop = section_loop(vertices, faces, height_m)
            local = loop[np.abs(loop[:, 0] - apex[0]) <= 0.014]
            if len(local) < 2:
                raise RuntimeError("Could not sample the Anny breast-root profile")
            return float(np.min(local[:, 2]))

        root_candidates_m = np.arange(
            root_height_m - 0.018,
            root_height_m + 0.011,
            0.0025,
        )
        root_profile_y = np.asarray([
            front_y_at(float(height)) for height in root_candidates_m
        ])
        detected_root_index = int(np.argmax(root_profile_y))
        detected_root_height_m = float(root_candidates_m[detected_root_index])
        root_heights_m.append(detected_root_height_m)
        root_front_y = float(root_profile_y[detected_root_index])
        lower_pole_front_y = front_y_at(detected_root_height_m + 0.020)
        below_root_front_y = front_y_at(detected_root_height_m - 0.020)
        root_reliefs_cm.append((root_front_y - float(apex[1])) * 100.0)
        expected_root_y = 0.5 * (lower_pole_front_y + below_root_front_y)
        root_curve_depths_cm.append((root_front_y - expected_root_y) * 100.0)

    left, right = sorted(apices, key=lambda point: float(point[0]))
    return {
        "bustSeparationCm": float((right[0] - left[0]) * 100.0),
        "bustApexHeightCm": float((left[2] + right[2]) * 50.0),
        "bustApexHeightFromRootCm": float(
            (((left[2] + right[2]) * 0.5) - np.mean(root_heights_m)) * 100.0
        ),
        "detectedUnderbustRootHeightCm": float(np.mean(root_heights_m) * 100.0),
        "underbustRootReliefCm": float(np.mean(root_reliefs_cm)),
        "underbustRootReliefLeftCm": root_reliefs_cm[0],
        "underbustRootReliefRightCm": root_reliefs_cm[1],
        "underbustRootCurveDepthCm": float(np.mean(root_curve_depths_cm)),
        "underbustRootCurveDepthLeftCm": root_curve_depths_cm[0],
        "underbustRootCurveDepthRightCm": root_curve_depths_cm[1],
    }


def breast_apex_vertex_indices(
    vertices: np.ndarray,
    root_height_m: float,
    bust_height_m: float,
) -> tuple[int, int]:
    """Return stable source indices for the left and right breast apices."""

    result: list[int] = []
    for side in (-1.0, 1.0):
        side_coordinate = vertices[:, 0] * side
        candidate_indices = np.flatnonzero(
            (side_coordinate >= 0.035)
            & (side_coordinate <= 0.18)
            & (vertices[:, 2] >= root_height_m - 0.005)
            & (vertices[:, 2] <= bust_height_m + 0.035)
        )
        if len(candidate_indices) < 20:
            raise RuntimeError("Could not locate stable Anny breast apex indices")
        result.append(int(candidate_indices[np.argmin(vertices[candidate_indices, 1])]))
    return tuple(sorted(result, key=lambda index: float(vertices[index, 0])))


def solve_station_transform(
    loop: np.ndarray,
    target_circuit_cm: float,
    target_depth_cm: float,
) -> tuple[float, float, float, dict[str, float]]:
    points = np.asarray(loop, dtype=np.float64)
    depth_center = float((points[:, 2].min() + points[:, 2].max()) * 0.5)
    current_depth_cm = float(np.ptp(points[:, 2]) * 100.0)
    if current_depth_cm <= 0.0:
        raise ValueError("Anny torso section has no front-to-back depth")
    depth_scale = target_depth_cm / current_depth_cm

    def perimeter(width_scale: float) -> float:
        transformed = points.copy()
        transformed[:, 0] *= width_scale
        transformed[:, 2] = depth_center + (transformed[:, 2] - depth_center) * depth_scale
        return closed_perimeter_cm(transformed)

    width_scale = float(brentq(
        lambda value: perimeter(value) - target_circuit_cm,
        0.25,
        2.5,
    ))
    return width_scale, depth_scale, depth_center, {
        "sourceCircuitCm": closed_perimeter_cm(points),
        "targetCircuitCm": target_circuit_cm,
        "sourceDepthCm": current_depth_cm,
        "targetDepthCm": target_depth_cm,
        "widthScale": width_scale,
        "depthScale": depth_scale,
        "depthCenterM": depth_center,
    }


def apply_torso_cage(
    vertices: np.ndarray,
    faces: np.ndarray,
    stations_m: dict[str, float],
    targets: dict[str, tuple[float, float]],
    eligible_vertices: np.ndarray,
) -> tuple[np.ndarray, dict[str, object]]:
    ordered_names = sorted(stations_m, key=stations_m.get)
    transforms: dict[str, dict[str, float]] = {}
    widths: list[float] = []
    depths: list[float] = []
    centers: list[float] = []
    heights: list[float] = []
    for name in ordered_names:
        circuit_cm, depth_cm = targets[name]
        width, depth, center, evidence = solve_station_transform(
            section_loop(vertices, faces, stations_m[name]),
            circuit_cm,
            depth_cm,
        )
        heights.append(stations_m[name])
        widths.append(width)
        depths.append(depth)
        centers.append(center)
        transforms[name] = evidence

    lower = heights[0] - 0.20
    upper = heights[-1] + 0.10
    knots = np.asarray([lower, *heights, upper], dtype=float)
    width_curve = CubicSpline(knots, [1.0, *widths, 1.0], bc_type="natural")
    depth_curve = CubicSpline(knots, [1.0, *depths, 1.0], bc_type="natural")
    center_curve = CubicSpline(
        knots,
        [centers[0], *centers, centers[-1]],
        bc_type="natural",
    )
    result = vertices.copy()
    z = result[:, 2]
    torso = (
        (z >= lower)
        & (z <= upper)
        & eligible_vertices
    )
    local_z = z[torso]
    local_center = center_curve(local_z)
    result[torso, 0] *= width_curve(local_z)
    result[torso, 1] = local_center + (
        result[torso, 1] - local_center
    ) * depth_curve(local_z)
    displacement_cm = np.linalg.norm(result - vertices, axis=1) * 100.0
    return result, {
        "method": "topology-landmarked smooth anisotropic torso cage",
        "stationTransforms": transforms,
        "affectedVertexCount": int(np.count_nonzero(torso)),
        "maximumDisplacementCm": float(displacement_cm.max()),
    }


def cage_eligible_vertices(model: object) -> np.ndarray:
    """Exclude arm and hand vertices by their dominant rig influence."""

    weights = model.vertex_bone_weights.detach().cpu().numpy()
    indices = model.vertex_bone_indices.detach().cpu().numpy()
    dominant_slots = np.argmax(weights, axis=1)
    dominant_bones = indices[np.arange(len(indices)), dominant_slots]
    labels = list(model.bone_labels)
    blocked_fragments = (
        "clavicle",
        "shoulder",
        "upperarm",
        "lowerarm",
        "wrist",
        "finger",
        "metacarpal",
    )
    return np.asarray([
        not any(fragment in labels[int(bone)].lower() for fragment in blocked_fragments)
        for bone in dominant_bones
    ])


def semantic_segmentation(
    model: object,
    source_indices: np.ndarray,
) -> dict[str, list[int]]:
    """Transfer Anny rig semantics to the compact collision surface."""

    weights = model.vertex_bone_weights.detach().cpu().numpy()[source_indices]
    indices = model.vertex_bone_indices.detach().cpu().numpy()[source_indices]
    dominant_slots = np.argmax(weights, axis=1)
    dominant_bones = indices[np.arange(len(indices)), dominant_slots]
    labels = list(model.bone_labels)
    result = {
        "body": [],
        "left_arm": [],
        "right_arm": [],
        "left_leg": [],
        "right_leg": [],
        "face_internal": [],
    }
    for compact_index, bone_index in enumerate(dominant_bones):
        bone = labels[int(bone_index)].lower()
        side = "left" if bone.endswith(".l") else "right" if bone.endswith(".r") else None
        if side and any(token in bone for token in ("upperarm", "lowerarm", "wrist", "finger", "metacarpal")):
            result[f"{side}_arm"].append(compact_index)
        elif side and any(token in bone for token in ("upperleg", "lowerleg", "foot", "toe")):
            result[f"{side}_leg"].append(compact_index)
        elif "tongue" in bone:
            result["face_internal"].append(compact_index)
        else:
            result["body"].append(compact_index)
    return result


def measure_output(
    vertices: np.ndarray,
    faces: np.ndarray,
    stations_m: dict[str, float],
    targets: dict[str, tuple[float, float]],
) -> dict[str, object]:
    mesh = y_up_mesh(vertices, faces)
    sections: dict[str, object] = {}
    accepted = True
    for name, height_m in stations_m.items():
        measurement = measure_torso_arc_section(
            mesh,
            height_m * 100.0,
            front_is_positive_depth=False,
        )
        loop = section_loop(vertices, faces, height_m)
        depth_cm = float(np.ptp(loop[:, 2]) * 100.0)
        target_circuit, target_depth = targets[name]
        circuit_residual = measurement.circumference_cm - target_circuit
        depth_residual = depth_cm - target_depth
        accepted = accepted and abs(circuit_residual) <= 0.35 and abs(depth_residual) <= 0.35
        sections[name] = {
            **measurement.to_dict(),
            "depthCm": depth_cm,
            "targetCircumferenceCm": target_circuit,
            "targetDepthCm": target_depth,
            "circumferenceResidualCm": circuit_residual,
            "depthResidualCm": depth_residual,
        }
    landmarks = breast_landmark_metrics(
        vertices,
        faces,
        stations_m["underbust"],
        stations_m["bust"],
    )
    return {"sections": sections, "breastLandmarks": landmarks, "accepted": accepted}


def main() -> None:
    args = parse_args()
    profile_path = args.profile.resolve()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    measurements = profile["measurements"]
    target_height_cm = float(measurements["height"])

    model = anny.create_fullbody_model(
        rig="default",
        topology="default",
        local_changes="default",
        triangulate_faces=True,
        all_phenotypes=True,
        extrapolate_phenotypes=True,
        remove_unattached_vertices=False,
    ).to(dtype=torch.float64)
    display_faces = model.faces.detach().cpu().numpy().astype(np.int64)
    body_component = body_face_indices(display_faces)
    body_faces = display_faces[body_component]
    body_source_indices = np.unique(body_faces.reshape(-1))
    with torch.no_grad():
        output = model(
            phenotype_kwargs=BASE_PHENOTYPE,
            local_changes_kwargs=BASE_LOCAL_CHANGES,
        )
    vertices = scaled_to_height(
        output["vertices"].squeeze(0).detach().cpu().numpy(),
        target_height_cm,
        body_source_indices,
    )
    anthropometry = anny.Anthropometry(model)
    waist_height_m = float(np.median(vertices[anthropometry.waist_vertex_indices, 2]))
    root_offset_cm, bust_offset_cm, station_search = find_breast_stations(
        vertices,
        body_faces,
        waist_height_m,
    )
    stations_m = {
        **{
            name: waist_height_m + offset_cm / 100.0
            for name, offset_cm in STATION_OFFSETS_CM.items()
        },
        "underbust": waist_height_m + root_offset_cm / 100.0,
        "bust": waist_height_m + bust_offset_cm / 100.0,
    }
    prefit_landmarks = breast_landmark_metrics(
        vertices,
        body_faces,
        stations_m["underbust"],
        stations_m["bust"],
    )
    stations_m["underbust"] = (
        float(prefit_landmarks["detectedUnderbustRootHeightCm"]) / 100.0
    )
    station_search["circuitRiseRootOffsetCm"] = station_search["rootOffsetCm"]
    station_search["rootOffsetCm"] = (
        stations_m["underbust"] - waist_height_m
    ) * 100.0
    station_search["rootRefinementMethod"] = (
        "least-projecting breast surface near the circuit-rise landmark"
    )
    targets = {
        "hip": (float(measurements["hip"]), float(measurements["hipDepth"])),
        "abdomen": (
            float(measurements["abdomenCirc"]),
            float(measurements["abdomenDepth"]),
        ),
        "waist": (float(measurements["waist"]), float(measurements["waistDepth"])),
        "underbust": (
            float(measurements["underBust"]),
            float(measurements["underBustDepth"]),
        ),
        "bust": (float(measurements["chest"]), float(measurements["chestDepth"])),
    }
    apex_vertex_indices = breast_apex_vertex_indices(
        vertices,
        stations_m["underbust"],
        stations_m["bust"],
    )
    vertices, fitted_phenotype, fitted_local_changes, native_fit_report = (
        optimize_native_controls(
            model,
            body_faces,
            body_vertex_indices=body_source_indices,
            base_phenotype=BASE_PHENOTYPE,
            base_local_changes=BASE_LOCAL_CHANGES,
            target_height_cm=target_height_cm,
            station_heights_cm={
                name: height_m * 100.0 for name, height_m in stations_m.items()
            },
            targets=targets,
            breast_apex_vertex_indices=apex_vertex_indices,
            bust_separation_target_cm=float(measurements["bustSeparation"]),
        )
    )
    waist_height_m = float(
        np.median(vertices[anthropometry.waist_vertex_indices, 2])
    )
    root_offset_cm, bust_offset_cm, station_search = find_breast_stations(
        vertices,
        body_faces,
        waist_height_m,
    )
    stations_m = {
        **{
            name: waist_height_m + offset_cm / 100.0
            for name, offset_cm in STATION_OFFSETS_CM.items()
        },
        "underbust": waist_height_m + root_offset_cm / 100.0,
        "bust": waist_height_m + bust_offset_cm / 100.0,
    }
    eligible_vertices = cage_eligible_vertices(model)
    first_fit, first_cage_report = apply_torso_cage(
        vertices,
        body_faces,
        stations_m,
        targets,
        eligible_vertices,
    )
    fitted, second_cage_report = apply_torso_cage(
        first_fit,
        body_faces,
        stations_m,
        targets,
        eligible_vertices,
    )
    cage_report = {
        "method": "two-pass topology-landmarked smooth anisotropic torso cage",
        "passes": [first_cage_report, second_cage_report],
        "maximumDisplacementFromBaseCm": float(
            np.linalg.norm(fitted - vertices, axis=1).max() * 100.0
        ),
    }
    measurements_report = measure_output(fitted, body_faces, stations_m, targets)
    height_cm = float(np.ptp(fitted[body_source_indices, 2]) * 100.0)
    display_path = output_dir / "body.obj"
    collision_path = output_dir / "body-collision.obj"
    topology_path = output_dir / "body-topology.obj"
    trimesh.Trimesh(
        vertices=fitted,
        faces=display_faces,
        process=False,
    ).export(display_path)
    collision_vertices, collision_faces, collision_source_indices = compact_surface(
        fitted,
        body_faces,
    )
    collision_mesh = trimesh.Trimesh(
        vertices=collision_vertices,
        faces=collision_faces,
        process=False,
    )
    collision_mesh.export(collision_path)
    segmentation = semantic_segmentation(model, collision_source_indices)
    segmentation_path = output_dir / "body-collision.segmentation.json"
    segmentation_path.write_text(
        json.dumps(segmentation, indent=2) + "\n",
        encoding="utf-8",
    )
    topology_vertex_count = int(body_faces.max()) + 1
    export_obj_preserving_vertices(
        topology_path,
        fitted[:topology_vertex_count],
        body_faces,
    )
    landmarks = measurements_report["breastLandmarks"]
    bust_separation_target_cm = float(measurements["bustSeparation"])
    bust_separation_residual_cm = (
        float(landmarks["bustSeparationCm"]) - bust_separation_target_cm
    )
    report = {
        "schemaVersion": "patterna.anny-profile-fit/1.0",
        "backend": "Anny 0.5 default topology",
        "backendLicense": "Apache-2.0 code and CC0 MPFB2 assets",
        "sourceProfile": str(profile_path),
        "sourceProfileSha256": sha256(profile_path),
        "outputBody": str(display_path),
        "outputBodySha256": sha256(display_path),
        "outputCollisionBody": str(collision_path),
        "outputCollisionBodySha256": sha256(collision_path),
        "outputCollisionSegmentation": str(segmentation_path),
        "outputCollisionSegmentationSha256": sha256(segmentation_path),
        "outputTopologyBody": str(topology_path),
        "outputTopologyBodySha256": sha256(topology_path),
        "vertexCount": int(len(fitted)),
        "faceCount": int(len(display_faces)),
        "collisionVertexCount": int(len(collision_vertices)),
        "collisionFaceCount": int(len(collision_faces)),
        "collisionConnectedComponents": int(
            len(collision_mesh.split(only_watertight=False))
        ),
        "collisionWatertight": bool(collision_mesh.is_watertight),
        "collisionSourceIndexMinimum": int(collision_source_indices.min()),
        "collisionSourceIndexMaximum": int(collision_source_indices.max()),
        "collisionSegmentationCounts": {
            name: len(indices) for name, indices in segmentation.items()
        },
        "topologyVertexCount": topology_vertex_count,
        "heightCm": height_cm,
        "targetHeightCm": target_height_cm,
        "heightResidualCm": height_cm - target_height_cm,
        "phenotype": fitted_phenotype,
        "localChanges": fitted_local_changes,
        "nativeParametricFit": native_fit_report,
        "waistLandmarkHeightCm": waist_height_m * 100.0,
        "stationHeightsCm": {name: value * 100.0 for name, value in stations_m.items()},
        "stationSearch": station_search,
        "cageFit": cage_report,
        "measurements": measurements_report,
        "bustSeparationTargetCm": bust_separation_target_cm,
        "bustSeparationResidualCm": bust_separation_residual_cm,
        "accepted": bool(
            measurements_report["accepted"]
            and abs(height_cm - target_height_cm) <= 0.05
            and float(station_search["largestRootRiseCm"]) >= 1.0
            and abs(bust_separation_residual_cm) <= 0.75
            and float(landmarks["bustApexHeightFromRootCm"]) >= 4.0
            and float(landmarks["underbustRootReliefCm"]) >= 2.0
            and float(landmarks["underbustRootCurveDepthCm"]) >= 0.30
            and collision_mesh.is_watertight
            and len(collision_mesh.split(only_watertight=False)) == 1
        ),
    }
    report_path = output_dir / "fit-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["accepted"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
