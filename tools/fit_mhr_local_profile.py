#!/usr/bin/env python3
"""Apply bounded topology-preserving measurement corrections to an MHR identity."""

from __future__ import annotations

import argparse
import hashlib
import json
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
        vertices, _ = model(
            torch.from_numpy(identity).reshape(1, -1),
            torch.zeros((1, 204), dtype=torch.float32),
            torch.zeros((1, 72), dtype=torch.float32),
            True,
        )
        vertices = scaled_to_height(vertices, target_height_cm)
    source_vertices = vertices[0].cpu().numpy().astype(np.float64)
    mesh = model.character_torch.mesh
    faces = mesh.faces.cpu().numpy().astype(np.int64)
    texture_coordinates = mesh.texcoords.cpu().numpy().astype(np.float64)
    texture_faces = mesh.texcoord_faces.cpu().numpy().astype(np.int64)
    fitted_vertices, evidence = fit_local_measurements(
        source_vertices, faces, targets, iterations=args.iterations
    )

    output_directory.mkdir(parents=True, exist_ok=True)
    collision_path = output_directory / "avatar-mhr-local-fit-garmentcode-cm.obj"
    preview_path = output_directory / "avatar-mhr-local-fit-blender-m.obj"
    report_path = output_directory / "local-fit-report.json"
    write_obj(
        collision_path,
        fitted_vertices,
        faces,
        texture_coordinates,
        texture_faces,
        reverse_winding=False,
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
        },
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
