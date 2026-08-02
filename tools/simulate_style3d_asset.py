#!/usr/bin/env python3
"""Drape a complete Style3D garment asset on Patterna's measured avatar."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import newton
from newton import Mesh
from newton.solvers import SolverStyle3D, style3d
import numpy as np
import trimesh
import warp as wp


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_obj(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    material_vertices: list[list[float]] = []
    faces: list[list[int]] = []
    material_faces: list[list[int]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("v "):
            values = line.split()
            vertices.append([float(values[1]), float(values[2]), float(values[3])])
        elif line.startswith("vt "):
            values = line.split()
            material_vertices.append([float(values[1]), float(values[2])])
        elif line.startswith("f "):
            corners = line.split()[1:]
            if len(corners) != 3:
                raise ValueError("The Style3D garment must be triangulated.")
            physical_face: list[int] = []
            material_face: list[int] = []
            for corner in corners:
                parts = corner.split("/")
                physical_face.append(int(parts[0]) - 1)
                material_face.append(int(parts[1]) - 1)
            faces.append(physical_face)
            material_faces.append(material_face)
    arrays = (
        np.asarray(vertices, dtype=np.float64) * 0.01,
        np.asarray(faces, dtype=np.int32),
        np.asarray(material_vertices, dtype=np.float64),
        np.asarray(material_faces, dtype=np.int32),
    )
    if not all(len(array) for array in arrays):
        raise ValueError(f"Incomplete OBJ garment: {path}")
    return arrays


def load_body(path: Path) -> tuple[np.ndarray, np.ndarray]:
    mesh = trimesh.load(path, process=False)
    if not isinstance(mesh, trimesh.Trimesh) or not mesh.is_watertight:
        raise ValueError("The simulation body must be one watertight triangle mesh.")
    return (
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int32),
    )


def write_obj(
    template_path: Path,
    output_path: Path,
    vertices_m: np.ndarray,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    vertex_index = 0
    for raw_line in template_path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("v "):
            vertex = vertices_m[vertex_index] * 100.0
            lines.append(f"v {vertex[0]:.9f} {vertex[1]:.9f} {vertex[2]:.9f}")
            vertex_index += 1
        else:
            lines.append(raw_line)
    if vertex_index != len(vertices_m):
        raise ValueError("Template vertex count changed during simulation.")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--garment", required=True, type=Path)
    parser.add_argument("--body", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--minimum-frames", type=int, default=120)
    parser.add_argument("--substeps", type=int, default=10)
    parser.add_argument("--nonlinear-iterations", type=int, default=4)
    parser.add_argument("--linear-iterations", type=int, default=10)
    parser.add_argument("--static-consecutive-frames", type=int, default=15)
    parser.add_argument("--static-threshold-cm", type=float, default=0.01)
    parser.add_argument("--collision-radius-cm", type=float, default=0.20)
    parser.add_argument("--self-contact-radius-cm", type=float, default=0.07)
    parser.add_argument("--body-contact-stiffness", type=float, default=1000.0)
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict[str, object]:
    garment_path = args.garment.resolve()
    body_path = args.body.resolve()
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    vertices, faces, material_vertices, material_faces = load_obj(garment_path)
    body_vertices, body_faces = load_body(body_path)

    wp.init()
    device = wp.get_device(args.device)
    builder = newton.ModelBuilder(up_axis=newton.Axis.Y)
    SolverStyle3D.register_custom_attributes(builder)
    style3d.add_cloth_mesh(
        builder,
        pos=wp.vec3(0.0),
        rot=wp.quat_identity(),
        vel=wp.vec3(0.0),
        panel_verts=material_vertices.tolist(),
        panel_indices=material_faces.tolist(),
        vertices=vertices.tolist(),
        indices=faces.tolist(),
        density=0.18,
        particle_radius=args.collision_radius_cm * 0.01,
        tri_aniso_ke=wp.vec3(300.0, 300.0, 30.0),
        edge_aniso_ke=wp.vec3(2.0e-5, 1.0e-5, 5.0e-6),
        tri_kd=2.0e-6,
        edge_kd=2.0e-6,
        validate_mesh=True,
        label="Patterna Style3D production garment",
    )
    builder.add_shape_mesh(
        body=builder.add_body(),
        mesh=Mesh(body_vertices, body_faces.reshape(-1)),
    )
    model = builder.finalize(device=device)
    model.soft_contact_radius = args.collision_radius_cm * 0.01
    model.soft_contact_margin = 0.0035
    model.soft_contact_ke = args.body_contact_stiffness
    model.soft_contact_kd = 1.0e-5
    model.soft_contact_mu = 0.45
    model.set_gravity((0.0, -9.81, 0.0))
    solver = SolverStyle3D(
        model,
        iterations=args.nonlinear_iterations,
        linear_iterations=args.linear_iterations,
    )
    if solver.collision is None:
        raise RuntimeError("Style3D collision handling is disabled.")
    solver.collision.radius = args.self_contact_radius_cm * 0.01

    state_0 = model.state()
    state_1 = model.state()
    control = model.control()
    contacts = model.contacts()
    frame_dt = 1.0 / 60.0
    simulation_dt = frame_dt / args.substeps
    static_streak = 0
    static_reached = False
    completed_frames = 0
    maximum_displacement_cm = 0.0
    mean_displacement_cm = 0.0
    start = time.perf_counter()
    for frame in range(args.frames):
        frame_start = state_0.particle_q.numpy()
        for _ in range(args.substeps):
            state_0.clear_forces()
            model.collide(state_0, contacts)
            solver.step(state_0, state_1, control, contacts, simulation_dt)
            state_0, state_1 = state_1, state_0
        frame_end = state_0.particle_q.numpy()
        displacement_cm = np.linalg.norm(frame_end - frame_start, axis=1) * 100.0
        maximum_displacement_cm = float(np.max(displacement_cm))
        mean_displacement_cm = float(np.mean(displacement_cm))
        l1_cm = np.sum(np.abs(frame_end - frame_start), axis=1) * 100.0
        static_frame = np.count_nonzero(l1_cm > args.static_threshold_cm) <= len(l1_cm) * 0.05
        static_streak = static_streak + 1 if static_frame else 0
        completed_frames = frame + 1
        if completed_frames >= args.minimum_frames and static_streak >= args.static_consecutive_frames:
            static_reached = True
            break
    elapsed = time.perf_counter() - start
    final_vertices = state_0.particle_q.numpy().astype(np.float64)
    body_mesh = trimesh.Trimesh(vertices=body_vertices, faces=body_faces, process=False)
    vertex_signed = trimesh.proximity.signed_distance(body_mesh, final_vertices)
    triangle_centers = final_vertices[faces].mean(axis=1)
    center_signed = trimesh.proximity.signed_distance(body_mesh, triangle_centers)
    output_path = output_directory / "patterna-style3d-draped.obj"
    write_obj(garment_path, output_path, final_vertices)
    report = {
        "schema_version": "patterna.style3d-asset-drape/1.0",
        "garment": str(garment_path),
        "garment_sha256": sha256_file(garment_path),
        "body": str(body_path),
        "body_sha256": sha256_file(body_path),
        "output": str(output_path),
        "output_sha256": sha256_file(output_path),
        "device": str(device),
        "newton_version": newton.__version__,
        "warp_version": wp.__version__,
        "vertex_count": len(final_vertices),
        "face_count": len(faces),
        "completed_frames": completed_frames,
        "static_equilibrium_reached": static_reached,
        "maximum_displacement_cm": maximum_displacement_cm,
        "mean_displacement_cm": mean_displacement_cm,
        "simulation_seconds": elapsed,
        "inside_body_vertex_count": int(np.count_nonzero(vertex_signed > 0.0)),
        "inside_body_triangle_center_count": int(np.count_nonzero(center_signed > 0.0)),
        "minimum_vertex_clearance_cm": float(-np.max(vertex_signed) * 100.0),
        "collision_radius_cm": args.collision_radius_cm,
        "self_contact_radius_cm": args.self_contact_radius_cm,
        "body_contact_stiffness": args.body_contact_stiffness,
    }
    (output_directory / "patterna-style3d-drape-report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    print(json.dumps(run(parse_arguments()), indent=2))


if __name__ == "__main__":
    main()
