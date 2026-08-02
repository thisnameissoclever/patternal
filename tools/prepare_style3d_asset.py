#!/usr/bin/env python3
"""Fit a complete Newton Style3D garment asset to Patterna's measured body."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import newton.usd
import newton.utils
import numpy as np
from pxr import Usd
import trimesh
from trimesh.ray.ray_triangle import RayMeshIntersector


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_obj_geometry(path: Path) -> tuple[np.ndarray, np.ndarray]:
    mesh = trimesh.load(path, process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"Expected one triangle mesh in {path}.")
    if not mesh.is_watertight:
        raise ValueError("The target body must be watertight.")
    return np.asarray(mesh.vertices, dtype=np.float64), np.asarray(mesh.faces, dtype=np.int32)


def load_style3d_asset(
    garment_name: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, Path, Path]:
    asset_root = Path(newton.utils.download_asset("style3d"))
    garment_path = asset_root / "garments" / f"{garment_name}.usd"
    garment_stage = Usd.Stage.Open(str(garment_path))
    garment_prim = garment_stage.GetPrimAtPath(
        f"/Root/{garment_name}/Root_Garment"
    )
    garment_mesh, garment_uv_indices = newton.usd.get_mesh(
        garment_prim,
        load_uvs=True,
        preserve_facevarying_uvs=True,
        return_uv_indices=True,
    )
    avatar_path = asset_root / "avatars" / "Female.usd"
    avatar_stage = Usd.Stage.Open(str(avatar_path))
    avatar_prim = avatar_stage.GetPrimAtPath(
        "/Root/Female/Root_SkinnedMesh_Avatar_0_Sub_2"
    )
    avatar_mesh = newton.usd.get_mesh(avatar_prim)
    return (
        np.asarray(garment_mesh.vertices, dtype=np.float64),
        np.asarray(garment_mesh.indices, dtype=np.int32).reshape(-1, 3),
        np.asarray(garment_mesh.uvs, dtype=np.float64) * 1.0e-3,
        np.asarray(garment_uv_indices, dtype=np.int32).reshape(-1, 3),
        np.asarray(avatar_mesh.vertices, dtype=np.float64),
        np.asarray(avatar_mesh.indices, dtype=np.int32).reshape(-1, 3),
        garment_path,
        avatar_path,
    )


def body_axis_z(vertices: np.ndarray, sample_y: np.ndarray) -> np.ndarray:
    body = np.asarray(vertices, dtype=np.float64)
    height = float(np.ptp(body[:, 1]))
    half_band = height / 90.0
    central_limit = max(0.12, float(np.percentile(np.abs(body[:, 0]), 45)))
    result = np.empty(len(sample_y), dtype=np.float64)
    for index, y_value in enumerate(sample_y):
        distance = np.abs(body[:, 1] - y_value)
        selected = (distance <= half_band) & (np.abs(body[:, 0]) <= central_limit)
        if np.count_nonzero(selected) < 12:
            nearest = np.argpartition(distance, min(63, len(distance) - 1))[:64]
            selected_values = body[nearest, 2]
        else:
            selected_values = body[selected, 2]
        lower, upper = np.percentile(selected_values, [8.0, 92.0])
        result[index] = (lower + upper) * 0.5
    return result


def outer_ray_support(
    vertices: np.ndarray,
    faces: np.ndarray,
    origins: np.ndarray,
    directions: np.ndarray,
) -> np.ndarray:
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    locations, ray_indices, _ = RayMeshIntersector(mesh).intersects_location(
        origins,
        directions,
        multiple_hits=True,
    )
    supports = np.full(len(origins), -np.inf, dtype=np.float64)
    if len(locations):
        distances = np.einsum(
            "ij,ij->i",
            locations - origins[ray_indices],
            directions[ray_indices],
        )
        valid = distances > 1.0e-6
        np.maximum.at(supports, ray_indices[valid], distances[valid])
    if np.any(~np.isfinite(supports)):
        missing = np.flatnonzero(~np.isfinite(supports))
        body = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        closest, distance, _ = trimesh.proximity.closest_point(body, origins[missing])
        radial = np.einsum(
            "ij,ij->i",
            closest - origins[missing],
            directions[missing],
        )
        supports[missing] = np.maximum(radial, distance)
    if not np.isfinite(supports).all() or np.any(supports <= 0.0):
        raise RuntimeError("Could not evaluate a positive body support radius.")
    return supports


def fit_garment_to_body(
    garment_vertices: np.ndarray,
    source_body_vertices: np.ndarray,
    source_body_faces: np.ndarray,
    target_body_vertices: np.ndarray,
    target_body_faces: np.ndarray,
    minimum_clearance_m: float,
) -> tuple[np.ndarray, dict[str, float]]:
    source_min_y = float(np.min(source_body_vertices[:, 1]))
    source_height = float(np.ptp(source_body_vertices[:, 1]))
    target_min_y = float(np.min(target_body_vertices[:, 1]))
    target_height = float(np.ptp(target_body_vertices[:, 1]))
    normalized_y = (garment_vertices[:, 1] - source_min_y) / source_height
    target_y = target_min_y + normalized_y * target_height

    source_axis = body_axis_z(source_body_vertices, garment_vertices[:, 1])
    source_offset_x = garment_vertices[:, 0]
    source_offset_z = garment_vertices[:, 2] - source_axis
    source_radius = np.hypot(source_offset_x, source_offset_z)
    directions = np.column_stack(
        (
            source_offset_x / source_radius,
            np.zeros(len(source_radius), dtype=np.float64),
            source_offset_z / source_radius,
        )
    )
    source_origins = np.column_stack(
        (np.zeros(len(source_axis)), garment_vertices[:, 1], source_axis)
    )
    source_support = outer_ray_support(
        source_body_vertices,
        source_body_faces,
        source_origins,
        directions,
    )

    target_axis = body_axis_z(target_body_vertices, target_y)
    target_origins = np.column_stack(
        (np.zeros(len(target_axis)), target_y, target_axis)
    )
    target_support = outer_ray_support(
        target_body_vertices,
        target_body_faces,
        target_origins,
        directions,
    )
    scale = target_height / source_height
    source_clearance = source_radius - source_support
    retained_clearance = np.maximum(source_clearance * scale, minimum_clearance_m)
    target_radius = target_support + retained_clearance
    fitted = target_origins + directions * target_radius[:, np.newaxis]
    fitted[:, 1] = target_y
    return fitted, {
        "fit_mode": "cylindrical",
        "source_body_height_m": source_height,
        "target_body_height_m": target_height,
        "minimum_source_clearance_m": float(np.min(source_clearance)),
        "minimum_retained_clearance_m": float(np.min(retained_clearance)),
        "median_retained_clearance_m": float(np.median(retained_clearance)),
        "maximum_retained_clearance_m": float(np.max(retained_clearance)),
    }


def fit_garment_uniformly(
    garment_vertices: np.ndarray,
    source_body_vertices: np.ndarray,
    target_body_vertices: np.ndarray,
    target_body_faces: np.ndarray,
    minimum_clearance_m: float,
    mirror_depth: bool,
) -> tuple[np.ndarray, dict[str, float | str]]:
    source_min_y = float(np.min(source_body_vertices[:, 1]))
    source_height = float(np.ptp(source_body_vertices[:, 1]))
    target_min_y = float(np.min(target_body_vertices[:, 1]))
    target_height = float(np.ptp(target_body_vertices[:, 1]))
    scale_y = target_height / source_height

    garment_min_y = float(np.min(garment_vertices[:, 1]))
    garment_max_y = float(np.max(garment_vertices[:, 1]))
    target_garment_min_y = target_min_y + (garment_min_y - source_min_y) * scale_y
    target_garment_max_y = target_min_y + (garment_max_y - source_min_y) * scale_y
    source_band = (
        (source_body_vertices[:, 1] >= garment_min_y)
        & (source_body_vertices[:, 1] <= garment_max_y)
    )
    target_band = (
        (target_body_vertices[:, 1] >= target_garment_min_y)
        & (target_body_vertices[:, 1] <= target_garment_max_y)
    )
    source_x = np.percentile(source_body_vertices[source_band, 0], [1.0, 99.0])
    target_x = np.percentile(target_body_vertices[target_band, 0], [1.0, 99.0])
    scale_x = float(np.ptp(target_x) / np.ptp(source_x))

    source_torso = source_band & (np.abs(source_body_vertices[:, 0]) <= 0.24)
    target_torso = target_band & (np.abs(target_body_vertices[:, 0]) <= 0.30)
    source_z = np.percentile(source_body_vertices[source_torso, 2], [2.0, 98.0])
    target_z = np.percentile(target_body_vertices[target_torso, 2], [2.0, 98.0])
    source_z_center = float(np.mean(source_z))
    target_z_center = float(np.mean(target_z))
    scale_z = float(np.ptp(target_z) / np.ptp(source_z))

    fitted = garment_vertices.copy()
    fitted[:, 0] *= scale_x
    fitted[:, 1] = target_min_y + (fitted[:, 1] - source_min_y) * scale_y
    depth_sign = -1.0 if mirror_depth else 1.0
    fitted[:, 2] = target_z_center + depth_sign * (fitted[:, 2] - source_z_center) * scale_z

    target_body = trimesh.Trimesh(
        vertices=target_body_vertices,
        faces=target_body_faces,
        process=False,
    )
    closest, _, _ = trimesh.proximity.closest_point(target_body, fitted)
    signed = trimesh.proximity.signed_distance(target_body, fitted)
    selected = signed > -minimum_clearance_m
    if np.any(selected):
        direction = fitted[selected] - closest[selected]
        inside = signed[selected] >= 0.0
        direction[inside] *= -1.0
        length = np.linalg.norm(direction, axis=1)
        valid = length > 1.0e-12
        direction[valid] /= length[valid, np.newaxis]
        direction[~valid] = np.array([0.0, 0.0, 1.0])
        fitted[selected] = closest[selected] + direction * minimum_clearance_m
    return fitted, {
        "fit_mode": "uniform",
        "source_body_height_m": source_height,
        "target_body_height_m": target_height,
        "scale_x": scale_x,
        "scale_y": scale_y,
        "scale_z": scale_z,
        "depth_sign": depth_sign,
        "source_z_center_m": source_z_center,
        "target_z_center_m": target_z_center,
        "projected_vertex_count": int(np.count_nonzero(selected)),
        "minimum_clearance_m": minimum_clearance_m,
    }


def write_obj(
    path: Path,
    vertices_m: np.ndarray,
    faces: np.ndarray,
    material_vertices_m: np.ndarray,
    material_faces: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Patterna fitted Newton Style3D production garment",
        "o PatternaStyle3DGarment",
    ]
    lines.extend(
        f"v {vertex[0] * 100.0:.9f} {vertex[1] * 100.0:.9f} {vertex[2] * 100.0:.9f}"
        for vertex in vertices_m
    )
    lines.extend(
        f"vt {coordinate[0]:.9f} {coordinate[1]:.9f}"
        for coordinate in material_vertices_m
    )
    for face, material_face in zip(faces, material_faces, strict=True):
        corners = [
            f"{int(face[index]) + 1}/{int(material_face[index]) + 1}"
            for index in range(3)
        ]
        lines.append("f " + " ".join(corners))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--garment", default="Women_Sweatshirt")
    parser.add_argument("--target-body", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum-clearance-cm", type=float, default=0.35)
    parser.add_argument(
        "--fit-mode",
        choices=("uniform", "cylindrical"),
        default="uniform",
    )
    parser.add_argument(
        "--no-mirror-depth",
        action="store_false",
        dest="mirror_depth",
    )
    parser.add_argument(
        "--material-scale",
        type=float,
        default=0.0,
        help="Uniform flat-pattern scale. Zero preserves fitted surface area automatically.",
    )
    parser.set_defaults(mirror_depth=True)
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    target_body_path = args.target_body.resolve()
    output_path = args.output.resolve()
    (
        garment_vertices,
        garment_faces,
        material_vertices,
        material_faces,
        source_body_vertices,
        source_body_faces,
        garment_path,
        avatar_path,
    ) = load_style3d_asset(args.garment)
    target_body_vertices, target_body_faces = load_obj_geometry(target_body_path)
    if args.fit_mode == "cylindrical":
        fitted_vertices, fit_metrics = fit_garment_to_body(
            garment_vertices,
            source_body_vertices,
            source_body_faces,
            target_body_vertices,
            target_body_faces,
            args.minimum_clearance_cm * 0.01,
        )
    else:
        fitted_vertices, fit_metrics = fit_garment_uniformly(
            garment_vertices,
            source_body_vertices,
            target_body_vertices,
            target_body_faces,
            args.minimum_clearance_cm * 0.01,
            args.mirror_depth,
        )
    source_triangles = garment_vertices[garment_faces]
    fitted_triangles = fitted_vertices[garment_faces]
    source_area = 0.5 * np.linalg.norm(
        np.cross(
            source_triangles[:, 1] - source_triangles[:, 0],
            source_triangles[:, 2] - source_triangles[:, 0],
        ),
        axis=1,
    ).sum()
    fitted_area = 0.5 * np.linalg.norm(
        np.cross(
            fitted_triangles[:, 1] - fitted_triangles[:, 0],
            fitted_triangles[:, 2] - fitted_triangles[:, 0],
        ),
        axis=1,
    ).sum()
    material_scale = (
        args.material_scale
        if args.material_scale > 0.0
        else float(np.sqrt(fitted_area / source_area))
    )
    material_vertices = material_vertices * material_scale
    write_obj(
        output_path,
        fitted_vertices,
        garment_faces,
        material_vertices,
        material_faces,
    )
    report = {
        "schema_version": "patterna.style3d-asset-fit/1.0",
        "garment": args.garment,
        "fit_mode": args.fit_mode,
        "mirror_depth": args.mirror_depth,
        "garment_asset": str(garment_path),
        "garment_asset_sha256": sha256_file(garment_path),
        "source_avatar_asset": str(avatar_path),
        "source_avatar_asset_sha256": sha256_file(avatar_path),
        "target_body": str(target_body_path),
        "target_body_sha256": sha256_file(target_body_path),
        "output": str(output_path),
        "output_sha256": sha256_file(output_path),
        "vertex_count": len(fitted_vertices),
        "face_count": len(garment_faces),
        "material_vertex_count": len(material_vertices),
        "minimum_clearance_cm": args.minimum_clearance_cm,
        "material_scale": material_scale,
        "source_surface_area_m2": float(source_area),
        "fitted_surface_area_m2": float(fitted_area),
        "fit": fit_metrics,
    }
    report_path = output_path.with_suffix(".fit-report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
