#!/usr/bin/env python3
"""Apply bounded topology-preserving measurement corrections to an MHR identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.fit_mhr_identity import (
    SECTION_SPECS,
    build_topologies,
    load_targets,
    measurement_acceptance,
    predict_measurements,
    scaled_to_height,
)
from tools.generate_mhr_avatar import to_blender_meters, write_obj
from tools.mhr_anthropometry import (
    SectionTopology,
    section_extent_cm,
    section_perimeter_cm,
    section_points_cm,
)


TORSO_SIGMA_RATIOS = {
    "hip": 0.035,
    "abdomen": 0.026,
    "waist": 0.020,
    "underbust": 0.016,
    "bust": 0.024,
}
DEFAULT_UPPER_ARM_LENGTH_RATIO = 0.17
DEFAULT_ARM_FORWARD_SWEEP_DEGREES = 20.0
MHR_ARM_JOINTS = {
    "right": {"shoulder": 39, "elbow": 40, "descendants": range(40, 74)},
    "left": {"shoulder": 75, "elbow": 76, "descendants": range(76, 110)},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--identity-json", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=32)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_measurements(
    vertices_cm: np.ndarray, topologies: list[SectionTopology]
) -> dict[str, float]:
    batch = torch.from_numpy(vertices_cm[None]).double()
    return {
        name: float(value.item())
        for name, value in predict_measurements(batch, topologies).items()
    }


def _smooth_edge(values: np.ndarray) -> np.ndarray:
    clamped = np.clip(values, 0.0, 1.0)
    return clamped * clamped * (3.0 - 2.0 * clamped)


def apply_torso_station(
    vertices_cm: np.ndarray,
    topology: SectionTopology,
    *,
    target_circumference_cm: float,
    target_depth_cm: float,
    sigma_ratio: float,
) -> None:
    batch = torch.from_numpy(vertices_cm[None]).double()
    points = section_points_cm(batch, topology)[0].numpy().reshape(-1, 3)
    current_depth = float(section_extent_cm(batch, topology, axis=2).item())
    if current_depth <= 0.0:
        raise ValueError(f"MHR {topology.name} depth is not positive.")
    floor = float(vertices_cm[:, 1].min())
    height = float(vertices_cm[:, 1].max() - floor)
    plane = floor + topology.height_ratio * height
    sigma = sigma_ratio * height
    vertical_weight = np.exp(-0.5 * ((vertices_cm[:, 1] - plane) / sigma) ** 2)

    half_width = float(np.max(np.abs(points[:, 0])))
    core_width = half_width * 1.08
    outer_width = max(core_width + 1.0, half_width * 1.42)
    lateral_weight = _smooth_edge(
        (outer_width - np.abs(vertices_cm[:, 0])) / (outer_width - core_width)
    )
    weights = vertical_weight * lateral_weight

    depth_center = 0.5 * (float(points[:, 2].min()) + float(points[:, 2].max()))
    depth_factor = float(np.clip(target_depth_cm / current_depth, 0.96, 1.04))
    vertices_cm[:, 2] = depth_center + (vertices_cm[:, 2] - depth_center) * (
        1.0 + (depth_factor - 1.0) * weights
    )

    updated_batch = torch.from_numpy(vertices_cm[None]).double()
    current_circumference = float(
        section_perimeter_cm(updated_batch, topology).item()
    )
    if current_circumference <= 0.0:
        raise ValueError(f"MHR {topology.name} circumference is not positive.")
    width_factor = float(
        np.clip(target_circumference_cm / current_circumference, 0.96, 1.04)
    )
    vertices_cm[:, 0] *= 1.0 + (width_factor - 1.0) * weights


def _arm_centerline(
    vertices_cm: np.ndarray,
    side: int,
    minimum_abs_x: float,
    minimum_y: float,
) -> tuple[np.ndarray, np.ndarray]:
    side_mask = (
        (vertices_cm[:, 0] * side >= minimum_abs_x)
        & (vertices_cm[:, 1] >= minimum_y)
    )
    side_points = vertices_cm[side_mask]
    if side_points.shape[0] < 100:
        raise ValueError("MHR arm centerline has too few vertices.")
    absolute_x = np.abs(side_points[:, 0])
    minimum = float(absolute_x.min())
    maximum = float(absolute_x.max())
    edges = np.linspace(minimum, maximum, 49)
    centers = 0.5 * (edges[:-1] + edges[1:])
    y_values: list[float] = []
    z_values: list[float] = []
    valid_centers: list[float] = []
    bins = np.clip(np.digitize(absolute_x, edges) - 1, 0, len(centers) - 1)
    for index, center in enumerate(centers):
        points = side_points[bins == index]
        if points.shape[0] < 8:
            continue
        valid_centers.append(float(center))
        y_values.append(float(np.median(points[:, 1])))
        z_values.append(float(np.median(points[:, 2])))
    if len(valid_centers) < 4:
        raise ValueError("MHR arm centerline could not be sampled.")
    query = np.abs(vertices_cm[:, 0])
    return (
        np.interp(query, valid_centers, y_values),
        np.interp(query, valid_centers, z_values),
    )


def upper_arm_weights(
    vertices_cm: np.ndarray,
    *,
    side: int,
    plane_x: float,
    sigma: float,
    minimum_abs_x: float,
    shoulder_root_abs_x: float,
    minimum_y: float,
    stature: float,
) -> np.ndarray:
    absolute_x = np.abs(vertices_cm[:, 0])
    shoulder_ramp = _smooth_edge(
        (absolute_x - shoulder_root_abs_x)
        / max(plane_x - shoulder_root_abs_x, 1.0)
    )
    distal_taper = np.exp(-0.5 * ((absolute_x - plane_x) / sigma) ** 2)
    weights = np.where(absolute_x <= plane_x, shoulder_ramp, distal_taper)
    height_ramp = _smooth_edge(
        (vertices_cm[:, 1] - minimum_y) / (0.05 * stature)
    )
    weights *= height_ramp
    weights *= (vertices_cm[:, 0] * side >= minimum_abs_x).astype(np.float64)
    return weights


def apply_upper_arm_station(
    vertices_cm: np.ndarray,
    topology: SectionTopology,
    *,
    target_circumference_cm: float,
) -> None:
    batch = torch.from_numpy(vertices_cm[None]).double()
    current = float(section_perimeter_cm(batch, topology).item())
    if current <= 0.0:
        raise ValueError("MHR upper-arm circumference is not positive.")
    factor = float(np.clip(target_circumference_cm / current, 0.94, 1.06))
    floor_x = float(vertices_cm[:, 0].min())
    span_x = float(vertices_cm[:, 0].max() - floor_x)
    plane_x = abs(floor_x + topology.height_ratio * span_x)
    stature = float(vertices_cm[:, 1].max() - vertices_cm[:, 1].min())
    floor_y = float(vertices_cm[:, 1].min())
    sigma = 0.055 * stature
    shoulder_root_abs_x = 0.12 * stature
    minimum_abs_x = max(0.105 * stature, plane_x - 1.8 * sigma)
    minimum_y = floor_y + 0.62 * stature
    for side in (-1, 1):
        center_y, center_z = _arm_centerline(
            vertices_cm, side, minimum_abs_x, minimum_y
        )
        weights = upper_arm_weights(
            vertices_cm,
            side=side,
            plane_x=plane_x,
            sigma=sigma,
            minimum_abs_x=minimum_abs_x,
            shoulder_root_abs_x=shoulder_root_abs_x,
            minimum_y=minimum_y,
            stature=stature,
        )
        local_factor = 1.0 + (factor - 1.0) * weights
        vertices_cm[:, 1] = center_y + (vertices_cm[:, 1] - center_y) * local_factor
        vertices_cm[:, 2] = center_z + (vertices_cm[:, 2] - center_z) * local_factor


def mesh_quality(
    original_vertices_cm: np.ndarray,
    fitted_vertices_cm: np.ndarray,
    faces: np.ndarray,
) -> dict[str, float | int | bool]:
    original_triangles = original_vertices_cm[faces]
    fitted_triangles = fitted_vertices_cm[faces]
    original_normals = np.cross(
        original_triangles[:, 1] - original_triangles[:, 0],
        original_triangles[:, 2] - original_triangles[:, 0],
    )
    fitted_normals = np.cross(
        fitted_triangles[:, 1] - fitted_triangles[:, 0],
        fitted_triangles[:, 2] - fitted_triangles[:, 0],
    )
    fitted_areas = 0.5 * np.linalg.norm(fitted_normals, axis=1)
    orientation_dot = np.einsum("ij,ij->i", original_normals, fitted_normals)
    flips = int(np.count_nonzero(orientation_dot <= 0.0))
    minimum_area = float(fitted_areas.min())
    finite = bool(np.isfinite(fitted_vertices_cm).all() and np.isfinite(fitted_areas).all())
    return {
        "finite": finite,
        "minimumTriangleAreaCm2": minimum_area,
        "orientationFlipCount": flips,
        "accepted": finite and minimum_area > 1.0e-6 and flips == 0,
    }


def scaled_skeleton_state(
    skeleton_state: np.ndarray,
    source_vertices_cm: np.ndarray,
    target_height_cm: float,
) -> np.ndarray:
    """Scale MHR global joint translations to the fitted body's stature."""
    state = np.asarray(skeleton_state, dtype=np.float64).copy()
    if state.ndim != 2 or state.shape[1] != 8 or state.shape[0] < 2:
        raise ValueError("MHR skeleton state must contain at least two 8-value joints.")
    if not np.isfinite(state).all():
        raise ValueError("MHR skeleton state contains a non-finite value.")
    source_height_cm = float(np.ptp(source_vertices_cm[:, 1]))
    if source_height_cm <= 0.0:
        raise ValueError("MHR source body has no measurable standing height.")
    state[:, :3] *= target_height_cm / source_height_cm
    return state


def normalize_upper_arm_length(
    vertices_cm: np.ndarray,
    skeleton_state: np.ndarray,
    *,
    target_ratio: float = DEFAULT_UPPER_ARM_LENGTH_RATIO,
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    """Lengthen the default MHR upper arms and their rig branches together."""
    vertices = np.asarray(vertices_cm, dtype=np.float64).copy()
    state = np.asarray(skeleton_state, dtype=np.float64).copy()
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        raise ValueError("MHR upper-arm normalization requires finite 3D vertices.")
    if state.shape != (127, 8) or not np.isfinite(state).all():
        raise ValueError("MHR upper-arm normalization requires the 127-joint state.")
    stature = float(np.ptp(vertices[:, 1]))
    if stature <= 0.0 or not 0.16 <= target_ratio <= 0.23:
        raise ValueError("MHR upper-arm normalization target is outside the anatomy gate.")
    target_length = target_ratio * stature
    floor = float(vertices[:, 1].min())
    sides: dict[str, object] = {}

    for side_name, contract in MHR_ARM_JOINTS.items():
        shoulder = state[contract["shoulder"], :3].copy()
        elbow = state[contract["elbow"], :3].copy()
        vector = elbow - shoulder
        current_length = float(np.linalg.norm(vector))
        if current_length <= 0.0:
            raise ValueError(f"MHR {side_name} upper arm has no usable length.")
        direction = vector / current_length
        extension = max(0.0, target_length - current_length)
        delta = direction * extension
        side = 1.0 if side_name == "left" else -1.0
        projection = np.dot(vertices - shoulder, direction) / current_length
        longitudinal_weight = _smooth_edge(projection)
        lateral_weight = _smooth_edge(
            (np.abs(vertices[:, 0]) - 0.105 * stature) / (0.035 * stature)
        )
        height_weight = _smooth_edge(
            (vertices[:, 1] - (floor + 0.55 * stature)) / (0.08 * stature)
        )
        side_weight = (vertices[:, 0] * side > 0.0).astype(np.float64)
        weights = longitudinal_weight * lateral_weight * height_weight * side_weight
        vertices += weights[:, None] * delta[None, :]
        for joint_index in contract["descendants"]:
            state[joint_index, :3] += delta
        sides[side_name] = {
            "beforeCm": current_length,
            "afterCm": current_length + extension,
            "extensionCm": extension,
        }

    return vertices, state, {
        "accepted": all(
            side["afterCm"] / stature >= 0.16
            for side in sides.values()
        ),
        "method": "symmetric smooth upper-arm surface extension with matching MHR descendant-joint translation",
        "targetRatioToStature": target_ratio,
        "targetLengthCm": target_length,
        "sides": sides,
    }


def normalize_arm_forward_sweep(
    vertices_cm: np.ndarray,
    skeleton_state: np.ndarray,
    *,
    target_degrees: float = DEFAULT_ARM_FORWARD_SWEEP_DEGREES,
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    """Reduce excessive forward arm sweep while preserving bilateral symmetry."""
    vertices = np.asarray(vertices_cm, dtype=np.float64).copy()
    state = np.asarray(skeleton_state, dtype=np.float64).copy()
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        raise ValueError("MHR arm-sweep normalization requires finite 3D vertices.")
    if state.shape != (127, 8) or not np.isfinite(state).all():
        raise ValueError("MHR arm-sweep normalization requires the 127-joint state.")
    if not 0.0 <= target_degrees <= 25.0:
        raise ValueError("MHR arm-sweep target must remain inside the inspection-pose gate.")
    stature = float(np.ptp(vertices[:, 1]))
    floor = float(vertices[:, 1].min())
    sides: dict[str, object] = {}

    for side_name, contract in MHR_ARM_JOINTS.items():
        side = 1.0 if side_name == "left" else -1.0
        shoulder = state[contract["shoulder"], :3].copy()
        candidates = vertices[
            (vertices[:, 0] * side > 0.105 * stature)
            & (vertices[:, 1] > floor + 0.55 * stature)
        ]
        if len(candidates) < 100:
            raise ValueError(f"MHR {side_name} arm sweep has too few surface samples.")
        endpoint = candidates[int(np.argmax(np.linalg.norm(candidates - shoulder, axis=1)))]
        vector = endpoint - shoulder
        before_degrees = math.degrees(math.atan2(vector[2], abs(vector[0])))
        correction_degrees = max(0.0, before_degrees - target_degrees)
        angle = math.radians(correction_degrees * side)
        cosine = math.cos(angle)
        sine = math.sin(angle)

        relative = vertices - shoulder
        rotated = relative.copy()
        rotated[:, 0] = cosine * relative[:, 0] + sine * relative[:, 2]
        rotated[:, 2] = -sine * relative[:, 0] + cosine * relative[:, 2]
        lateral_weight = _smooth_edge(
            (np.abs(vertices[:, 0]) - 0.105 * stature) / (0.035 * stature)
        )
        height_weight = _smooth_edge(
            (vertices[:, 1] - (floor + 0.55 * stature)) / (0.08 * stature)
        )
        side_weight = (vertices[:, 0] * side > 0.0).astype(np.float64)
        weights = lateral_weight * height_weight * side_weight
        vertices += weights[:, None] * (shoulder + rotated - vertices)

        for joint_index in contract["descendants"]:
            joint_relative = state[joint_index, :3] - shoulder
            state[joint_index, 0] = shoulder[0] + cosine * joint_relative[0] + sine * joint_relative[2]
            state[joint_index, 2] = shoulder[2] - sine * joint_relative[0] + cosine * joint_relative[2]
        sides[side_name] = {
            "beforeDegrees": before_degrees,
            "targetDegrees": target_degrees,
            "rotationDegrees": correction_degrees,
        }

    return vertices, state, {
        "accepted": all(side["beforeDegrees"] - side["rotationDegrees"] <= 25.0 for side in sides.values()),
        "method": "symmetric smooth arm-surface yaw correction with matching MHR descendant-joint rotation",
        "targetAbsoluteForwardSweepDegrees": target_degrees,
        "sides": sides,
    }


def fit_local_measurements(
    vertices_cm: np.ndarray,
    faces: np.ndarray,
    targets: dict[str, float],
    *,
    iterations: int,
) -> tuple[np.ndarray, dict[str, object]]:
    if iterations < 1:
        raise ValueError("MHR local fitting requires at least one iteration.")
    original = vertices_cm.astype(np.float64, copy=True)
    corrected = original.copy()
    topologies = build_topologies(original, faces)
    topology_by_name = {topology.name: topology for topology in topologies}
    before = evaluate_measurements(original, topologies)
    history: list[dict[str, object]] = []

    for iteration in range(iterations):
        for name, _, circumference_key, depth_key in SECTION_SPECS:
            apply_torso_station(
                corrected,
                topology_by_name[name],
                target_circumference_cm=targets[f"{name}Circumference"],
                target_depth_cm=targets[f"{name}Depth"],
                sigma_ratio=TORSO_SIGMA_RATIOS[name],
            )
        apply_upper_arm_station(
            corrected,
            topology_by_name["upperArm"],
            target_circumference_cm=targets["upperArmCircumference"],
        )
        measured = evaluate_measurements(corrected, topologies)
        acceptance = measurement_acceptance(measured, targets)
        maximum_error = max(
            result["absoluteErrorCm"]
            for result in acceptance["measurements"].values()
        )
        history.append(
            {
                "iteration": iteration + 1,
                "status": acceptance["status"],
                "maximumAbsoluteErrorCm": maximum_error,
            }
        )
        if acceptance["status"] == "accepted":
            break

    after = evaluate_measurements(corrected, topologies)
    acceptance = measurement_acceptance(after, targets)
    displacements = np.linalg.norm(corrected - original, axis=1)
    quality = mesh_quality(original, corrected, faces)
    status = (
        "accepted"
        if acceptance["status"] == "accepted" and quality["accepted"]
        else "rejected"
    )
    return corrected, {
        "status": status,
        "method": "bounded smooth topology-preserving section correction",
        "iterationsRequested": iterations,
        "iterationsCompleted": len(history),
        "measurementsBeforeCm": before,
        "measurementsAfterCm": after,
        "acceptance": acceptance,
        "meshQuality": quality,
        "maximumDisplacementCm": float(displacements.max()),
        "rmsDisplacementCm": float(np.sqrt(np.mean(displacements**2))),
        "history": history,
    }


def main() -> None:
    args = parse_args()
    profile_path = args.profile.resolve()
    model_path = args.model.resolve()
    identity_path = args.identity_json.resolve()
    output_directory = args.output_directory.resolve()
    target_height_cm, targets = load_targets(profile_path)
    identity = np.asarray(
        json.loads(identity_path.read_text(encoding="utf-8")), dtype=np.float32
    )
    if identity.shape != (45,) or not np.isfinite(identity).all():
        raise ValueError("MHR local fit identity must contain 45 finite coefficients.")

    model = torch.jit.load(str(model_path), map_location="cpu")
    model.eval()
    with torch.no_grad():
        vertices, skeleton_state = model(
            torch.from_numpy(identity).reshape(1, -1),
            torch.zeros((1, 204), dtype=torch.float32),
            torch.zeros((1, 72), dtype=torch.float32),
            True,
        )
    unscaled_vertices = vertices[0].cpu().numpy().astype(np.float64)
    fitted_rig_state = scaled_skeleton_state(
        skeleton_state[0].cpu().numpy(),
        unscaled_vertices,
        target_height_cm,
    )
    vertices = scaled_to_height(vertices, target_height_cm)
    source_vertices = vertices[0].cpu().numpy().astype(np.float64)
    mesh = model.character_torch.mesh
    faces = mesh.faces.cpu().numpy().astype(np.int64)
    texture_coordinates = mesh.texcoords.cpu().numpy().astype(np.float64)
    texture_faces = mesh.texcoord_faces.cpu().numpy().astype(np.int64)
    sweep_vertices, fitted_rig_state, sweep_normalization = normalize_arm_forward_sweep(
        source_vertices,
        fitted_rig_state,
    )
    normalized_vertices, fitted_rig_state, length_normalization = normalize_upper_arm_length(
        sweep_vertices,
        fitted_rig_state,
    )
    fitted_vertices, evidence = fit_local_measurements(
        normalized_vertices, faces, targets, iterations=args.iterations
    )
    overall_quality = mesh_quality(source_vertices, fitted_vertices, faces)
    if (
        not sweep_normalization["accepted"]
        or not length_normalization["accepted"]
        or not overall_quality["accepted"]
    ):
        evidence["status"] = "rejected"
    evidence["anatomyNormalization"] = {
        "armForwardSweep": sweep_normalization,
        "upperArmLength": length_normalization,
    }
    evidence["overallMeshQuality"] = overall_quality
    total_displacements = np.linalg.norm(fitted_vertices - source_vertices, axis=1)
    evidence["maximumTotalDisplacementCm"] = float(total_displacements.max())
    evidence["rmsTotalDisplacementCm"] = float(
        np.sqrt(np.mean(total_displacements**2))
    )

    output_directory.mkdir(parents=True, exist_ok=True)
    collision_path = output_directory / "avatar-mhr-local-fit-garmentcode-cm.obj"
    preview_path = output_directory / "avatar-mhr-local-fit-blender-m.obj"
    rig_state_path = output_directory / "mhr-rig-state.json"
    report_path = output_directory / "local-fit-report.json"
    write_obj(
        collision_path,
        fitted_vertices,
        faces,
        texture_coordinates,
        texture_faces,
        reverse_winding=False,
    )
    rig_state = {
        "schemaVersion": "patterna.mhr-rig-state/1.0",
        "coordinateSystem": "MHR centimeters, X right, Y up, Z back",
        "jointCount": int(fitted_rig_state.shape[0]),
        "fbxBoneCount": int(fitted_rig_state.shape[0] - 1),
        "worldJointIndex": 0,
        "fbxBoneStateOffset": 1,
        "heightTargetCm": target_height_cm,
        "jointStates": fitted_rig_state.tolist(),
    }
    rig_state_path.write_text(
        json.dumps(rig_state, indent=2) + "\n",
        encoding="utf-8",
    )
    write_obj(
        preview_path,
        to_blender_meters(fitted_vertices),
        faces,
        texture_coordinates,
        texture_faces,
        reverse_winding=False,
    )
    report = {
        "schemaVersion": "patterna.mhr-local-fit/1.0",
        **evidence,
        "source": {
            "profile": str(profile_path),
            "profileSha256": sha256(profile_path),
            "model": str(model_path),
            "modelSha256": sha256(model_path),
            "identity": str(identity_path),
            "identitySha256": sha256(identity_path),
        },
        "topology": {
            "vertexCount": int(fitted_vertices.shape[0]),
            "triangleCount": int(faces.shape[0]),
        },
        "outputs": {
            "collisionObj": str(collision_path),
            "collisionObjSha256": sha256(collision_path),
            "previewObj": str(preview_path),
            "previewObjSha256": sha256(preview_path),
            "rigState": str(rig_state_path),
            "rigStateSha256": sha256(rig_state_path),
        },
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
