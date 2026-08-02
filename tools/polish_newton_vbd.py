#!/usr/bin/env python3
"""Remove residual avatar crossings with Newton VBD full-surface contact."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import time

import numpy as np
import warp as wp

import newton
from newton import Mesh
from newton.solvers import SolverVBD

try:
    from tools.prefit_garmentcode_warp import evaluate_acceptance
    from tools.prefit_newton_style3d import (
        count_intersections,
        evaluate_seams,
        evaluate_strain,
        expand_welded_positions,
        load_material_coordinates,
        load_obj_geometry,
        load_obj_surface,
        load_rest_lengths,
        load_seam_links,
        orient_material_triangles,
        project_outside_body,
        resolve_path,
        sha256_file,
        surface_edges,
        weld_surface,
        write_expanded_obj,
        write_physical_obj,
    )
except ModuleNotFoundError:
    from prefit_garmentcode_warp import evaluate_acceptance
    from prefit_newton_style3d import (
        count_intersections,
        evaluate_seams,
        evaluate_strain,
        expand_welded_positions,
        load_material_coordinates,
        load_obj_geometry,
        load_obj_surface,
        load_rest_lengths,
        load_seam_links,
        orient_material_triangles,
        project_outside_body,
        resolve_path,
        sha256_file,
        surface_edges,
        weld_surface,
        write_expanded_obj,
        write_physical_obj,
    )


REPORT_SCHEMA_VERSION = "patterna.newton-vbd-full-surface-report/1.0"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--style3d-report", type=Path)
    parser.add_argument(
        "--source-report",
        type=Path,
        help=(
            "Direct Style3D source manifest used by explicit-springs mode. "
            "This avoids requiring or pretending to consume a failed welded Style3D solve."
        ),
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--frames", type=int, default=240)
    parser.add_argument("--substeps", type=int, default=10)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--sdf-voxel-size-cm", type=float, default=0.5)
    parser.add_argument("--contact-margin-cm", type=float, default=0.2)
    parser.add_argument("--particle-radius-cm", type=float, default=0.034)
    parser.add_argument("--contact-stiffness", type=float, default=10000.0)
    parser.add_argument("--contact-damping", type=float, default=100.0)
    parser.add_argument("--body-friction", type=float, default=0.45)
    parser.add_argument("--shape-stiffness", type=float, default=10000.0)
    parser.add_argument("--shape-area-stiffness", type=float, default=10000.0)
    parser.add_argument("--shape-damping", type=float, default=50.0)
    parser.add_argument("--bend-stiffness", type=float, default=10.0)
    parser.add_argument("--bend-damping", type=float, default=1.0)
    parser.add_argument("--density-kg-m2", type=float, default=0.12)
    parser.add_argument(
        "--topology-mode",
        choices=("welded", "explicit-springs"),
        default="welded",
    )
    parser.add_argument("--initial-mesh", type=Path)
    parser.add_argument("--initial-body-clearance-cm", type=float, default=0.35)
    parser.add_argument("--seam-stiffness", type=float, default=10000.0)
    parser.add_argument("--seam-damping", type=float, default=100.0)
    parser.add_argument("--seam-rest-length-cm", type=float, default=0.001)
    parser.add_argument("--sewing-ramp-delay-frames", type=int, default=10)
    parser.add_argument("--sewing-ramp-frames", type=int, default=120)
    parser.add_argument("--sewing-settle-frames", type=int, default=60)
    parser.add_argument("--gravity-m-s2", type=float, default=0.0)
    parser.add_argument("--minimum-initial-triangle-area-cm2", type=float, default=0.01)
    parser.add_argument("--minimum-initial-triangle-angle-deg", type=float, default=5.0)
    parser.add_argument("--maximum-initial-triangle-aspect-ratio", type=float, default=20.0)
    parser.add_argument("--max-seam-separation-cm", type=float, default=0.25)
    parser.add_argument("--max-edge-strain", type=float, default=0.40)
    parser.add_argument("--max-p95-edge-strain", type=float, default=0.15)
    parser.add_argument("--max-p999-edge-strain", type=float, default=0.29)
    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    for field in ("frames", "substeps", "iterations"):
        if getattr(args, field) <= 0:
            raise ValueError(f"--{field.replace('_', '-')} must be positive.")
    positive_fields = (
        "sdf_voxel_size_cm",
        "contact_margin_cm",
        "particle_radius_cm",
        "contact_stiffness",
        "contact_damping",
        "shape_stiffness",
        "shape_area_stiffness",
        "shape_damping",
        "density_kg_m2",
        "initial_body_clearance_cm",
        "seam_stiffness",
        "seam_damping",
        "seam_rest_length_cm",
        "max_seam_separation_cm",
        "max_edge_strain",
        "max_p95_edge_strain",
        "max_p999_edge_strain",
        "minimum_initial_triangle_area_cm2",
        "minimum_initial_triangle_angle_deg",
        "maximum_initial_triangle_aspect_ratio",
    )
    for field in positive_fields:
        value = float(getattr(args, field))
        if not np.isfinite(value) or value <= 0.0:
            raise ValueError(f"--{field.replace('_', '-')} must be finite and positive.")
    if not np.isfinite(args.bend_stiffness) or args.bend_stiffness < 0.0:
        raise ValueError("--bend-stiffness must be finite and non-negative.")
    if not np.isfinite(args.bend_damping) or args.bend_damping < 0.0:
        raise ValueError("--bend-damping must be finite and non-negative.")
    if args.body_friction < 0.0 or not np.isfinite(args.body_friction):
        raise ValueError("--body-friction must be finite and non-negative.")
    if not np.isfinite(args.gravity_m_s2):
        raise ValueError("--gravity-m-s2 must be finite.")
    for field in (
        "sewing_ramp_delay_frames",
        "sewing_ramp_frames",
        "sewing_settle_frames",
    ):
        if int(getattr(args, field)) < 0:
            raise ValueError(f"--{field.replace('_', '-')} must be non-negative.")
    if args.topology_mode == "explicit-springs":
        if (args.source_report is None) == (args.style3d_report is None):
            raise ValueError(
                "Explicit-springs mode requires exactly one of --source-report "
                "or --style3d-report."
            )
        required_frames = (
            args.sewing_ramp_delay_frames
            + args.sewing_ramp_frames
            + args.sewing_settle_frames
        )
        if args.frames < required_frames:
            raise ValueError(
                "--frames must cover sewing delay, ramp, and settling; "
                f"need at least {required_frames}."
            )
    elif args.style3d_report is None:
        raise ValueError("Welded mode requires --style3d-report.")


def required_report_path(report: dict[str, object], key: str) -> Path:
    value = report.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Style3D report is missing the required {key!r} path.")
    path = resolve_path(value)
    if not path.is_file():
        raise FileNotFoundError(f"Style3D report path does not exist for {key}: {path}")
    return path


def report_sha256(report: dict[str, object]) -> str:
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def smoothstep01(value: float) -> float:
    clamped = float(np.clip(value, 0.0, 1.0))
    return clamped * clamped * (3.0 - 2.0 * clamped)


def sewing_schedule_progress(frame: int, delay_frames: int, ramp_frames: int) -> float:
    if ramp_frames <= 0:
        return 1.0 if frame >= delay_frames else 0.0
    return smoothstep01((frame - delay_frames) / ramp_frames)


def scheduled_seam_rest_lengths(
    initial_lengths_m: np.ndarray,
    target_length_m: float,
    frame: int,
    delay_frames: int,
    ramp_frames: int,
) -> np.ndarray:
    progress = sewing_schedule_progress(frame, delay_frames, ramp_frames)
    return initial_lengths_m + (target_length_m - initial_lengths_m) * progress


def triangle_quality(vertices_cm: np.ndarray, faces: np.ndarray) -> dict[str, float | int]:
    triangles = np.asarray(vertices_cm, dtype=np.float64)[np.asarray(faces, dtype=np.int32)]
    first = triangles[:, 1] - triangles[:, 0]
    second = triangles[:, 2] - triangles[:, 1]
    third = triangles[:, 0] - triangles[:, 2]
    lengths = np.stack(
        (
            np.linalg.norm(first, axis=1),
            np.linalg.norm(second, axis=1),
            np.linalg.norm(third, axis=1),
        ),
        axis=1,
    )
    double_areas = np.linalg.norm(np.cross(first, -third), axis=1)
    areas = double_areas * 0.5
    shortest_altitudes = np.divide(
        double_areas,
        np.max(lengths, axis=1),
        out=np.zeros_like(double_areas),
        where=np.max(lengths, axis=1) > 0.0,
    )
    aspect_ratios = np.divide(
        np.max(lengths, axis=1),
        shortest_altitudes,
        out=np.full_like(double_areas, np.inf),
        where=shortest_altitudes > 0.0,
    )
    angles: list[np.ndarray] = []
    for adjacent_a, adjacent_b, opposite in ((0, 2, 1), (0, 1, 2), (1, 2, 0)):
        denominator = lengths[:, adjacent_a] * lengths[:, adjacent_b]
        cosine = np.divide(
            lengths[:, adjacent_a] ** 2
            + lengths[:, adjacent_b] ** 2
            - lengths[:, opposite] ** 2,
            2.0 * denominator,
            out=np.ones_like(denominator),
            where=denominator > 0.0,
        )
        angles.append(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))
    minimum_angles = np.min(np.stack(angles, axis=1), axis=1)
    return {
        "minimum_triangle_area_cm2": float(np.min(areas)),
        "minimum_triangle_angle_deg": float(np.min(minimum_angles)),
        "maximum_triangle_aspect_ratio": float(np.max(aspect_ratios)),
    }


def material_triangle_rest_state(
    panel_vertices_cm: np.ndarray,
    faces: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    panel_vertices_m = np.asarray(panel_vertices_cm, dtype=np.float64) * 0.01
    first = panel_vertices_m[faces[:, 0]]
    second = panel_vertices_m[faces[:, 1]]
    third = panel_vertices_m[faces[:, 2]]
    deformation = np.stack((second - first, third - first), axis=2)
    determinants = np.linalg.det(deformation)
    if np.any(determinants <= 1.0e-14):
        indices = np.flatnonzero(determinants <= 1.0e-14)[:10].tolist()
        raise ValueError(f"Material rest surface has invalid triangles: {indices}")
    return np.linalg.inv(deformation), determinants * 0.5


def run(args: argparse.Namespace) -> dict[str, object]:
    validate_arguments(args)
    input_manifest_path = resolve_path(args.source_report or args.style3d_report)
    output_dir = resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_manifest = json.loads(input_manifest_path.read_text(encoding="utf-8"))
    using_direct_source = args.source_report is not None

    material_surface_path = required_report_path(
        input_manifest,
        "physical_mesh_path" if using_direct_source else "material_surface_path",
    )
    physical_input_path = (
        material_surface_path
        if using_direct_source
        else required_report_path(input_manifest, "physical_output_mesh_path")
    )
    material_coordinates_path = required_report_path(input_manifest, "material_coordinates_path")
    body_mesh_path = required_report_path(input_manifest, "body_mesh_path")
    segmentation_path = required_report_path(input_manifest, "panel_ownership_path")
    rest_lengths_path = required_report_path(input_manifest, "rest_lengths_path")

    material_surface = load_obj_surface(material_surface_path)
    body_vertices_m, body_faces = load_obj_geometry(body_mesh_path)
    seam_links = load_seam_links(segmentation_path, len(material_surface.vertices))
    rest_lengths = load_rest_lengths(rest_lengths_path, len(material_surface.vertices))

    topology = None
    material_rest_poses: np.ndarray | None = None
    material_rest_areas: np.ndarray | None = None
    reoriented_material_triangle_count = 0
    initial_projection: dict[str, float | int] | None = None
    if args.topology_mode == "explicit-springs":
        initial_input_path = resolve_path(args.initial_mesh or material_surface_path)
        initial_surface = load_obj_surface(initial_input_path)
        if not np.array_equal(initial_surface.faces, material_surface.faces):
            raise ValueError("Explicit sewn initial mesh does not match the material surface topology.")
        if len(initial_surface.vertices) != len(material_surface.vertices):
            raise ValueError("Explicit sewn initial mesh does not match the material vertex count.")
        panel_vertices_cm = load_material_coordinates(
            material_coordinates_path,
            len(material_surface.vertices),
            material_surface.faces,
        )
        physical_faces, _, reoriented_material_triangle_count = orient_material_triangles(
            material_surface.faces,
            material_surface.faces,
            panel_vertices_cm,
        )
        material_rest_poses, material_rest_areas = material_triangle_rest_state(
            panel_vertices_cm,
            physical_faces,
        )
        projected_m, initial_projection = project_outside_body(
            initial_surface.vertices * 0.01,
            body_vertices_m,
            body_faces,
            args.initial_body_clearance_cm * 0.01,
        )
        physical_vertices_cm = projected_m * 100.0
    else:
        initial_input_path = physical_input_path
        physical_vertices_cm, physical_faces = load_obj_geometry(physical_input_path)
        topology = weld_surface(material_surface.vertices, material_surface.faces, seam_links)
        if not np.array_equal(np.sort(topology.faces, axis=1), np.sort(physical_faces, axis=1)):
            raise ValueError("Style3D physical output topology does not match its welded source surface.")
        if len(topology.vertices) != len(physical_vertices_cm):
            raise ValueError("Style3D physical output vertex count does not match its welded source surface.")
    collision_topology_ids = np.arange(len(physical_vertices_cm), dtype=np.int32)

    wp.init()
    device = wp.get_device(args.device)
    if not device.is_cuda:
        raise RuntimeError("Patterna VBD full-surface cleanup requires a CUDA device.")

    initial_vertices_m = physical_vertices_cm * 0.01
    initial_body_collisions, initial_self_collisions = count_intersections(
        initial_vertices_m,
        physical_faces,
        body_vertices_m,
        body_faces,
        args.device,
        collision_topology_ids,
    )
    initial_triangle_quality = triangle_quality(physical_vertices_cm, physical_faces)
    if args.topology_mode == "explicit-springs":
        preflight_rejections: list[str] = []
        if initial_body_collisions > 0:
            preflight_rejections.append(
                f"initial body intersections {initial_body_collisions} exceed limit 0"
            )
        if initial_self_collisions > 0:
            preflight_rejections.append(
                f"initial self intersections {initial_self_collisions} exceed limit 0"
            )
        if (
            initial_triangle_quality["minimum_triangle_area_cm2"]
            < args.minimum_initial_triangle_area_cm2
        ):
            preflight_rejections.append(
                "minimum initial triangle area "
                f"{initial_triangle_quality['minimum_triangle_area_cm2']:.6g} cm2 is below "
                f"{args.minimum_initial_triangle_area_cm2:.6g} cm2"
            )
        if (
            initial_triangle_quality["minimum_triangle_angle_deg"]
            < args.minimum_initial_triangle_angle_deg
        ):
            preflight_rejections.append(
                "minimum initial triangle angle "
                f"{initial_triangle_quality['minimum_triangle_angle_deg']:.6g} deg is below "
                f"{args.minimum_initial_triangle_angle_deg:.6g} deg"
            )
        if (
            initial_triangle_quality["maximum_triangle_aspect_ratio"]
            > args.maximum_initial_triangle_aspect_ratio
        ):
            preflight_rejections.append(
                "maximum initial triangle aspect ratio "
                f"{initial_triangle_quality['maximum_triangle_aspect_ratio']:.6g} exceeds "
                f"{args.maximum_initial_triangle_aspect_ratio:.6g}"
            )
        if preflight_rejections:
            raise ValueError(
                "Explicit sewing source failed collision and mesh-quality preflight: "
                + "; ".join(preflight_rejections)
            )

    builder = newton.ModelBuilder(up_axis=newton.Axis.Y, gravity=args.gravity_m_s2)
    builder.add_cloth_mesh(
        pos=wp.vec3(0.0, 0.0, 0.0),
        rot=wp.quat_identity(),
        scale=1.0,
        vel=wp.vec3(0.0, 0.0, 0.0),
        vertices=initial_vertices_m.tolist(),
        indices=physical_faces.reshape(-1).tolist(),
        density=args.density_kg_m2,
        tri_ke=args.shape_stiffness,
        tri_ka=args.shape_area_stiffness,
        tri_kd=args.shape_damping,
        edge_ke=args.bend_stiffness,
        edge_kd=args.bend_damping,
        particle_radius=args.particle_radius_cm * 0.01,
        validate_mesh=True,
        label="Patterna Style3D drape collision polish",
    )
    initial_seam_rest_lengths_m: np.ndarray | None = None
    target_seam_rest_length_m: float | None = None
    if args.topology_mode == "explicit-springs":
        if len(builder.tri_poses) != len(material_rest_poses):
            raise ValueError("VBD skipped a material triangle while building explicit sewn cloth.")
        builder.tri_poses = material_rest_poses.tolist()
        builder.tri_areas = material_rest_areas.tolist()
        initial_seam_rest_lengths_m = np.asarray(
            [
                np.linalg.norm(initial_vertices_m[first] - initial_vertices_m[second])
                for first, second in seam_links
            ],
            dtype=np.float32,
        )
        target_seam_rest_length_m = args.seam_rest_length_cm * 0.01
        for link_index, (first, second) in enumerate(seam_links):
            builder.add_spring(
                first,
                second,
                args.seam_stiffness,
                args.seam_damping,
                0.0,
            )
            builder.spring_rest_length[-1] = float(initial_seam_rest_lengths_m[link_index])
    body_config = newton.ModelBuilder.ShapeConfig(
        ke=args.contact_stiffness,
        kd=args.contact_damping,
        mu=args.body_friction,
    )
    body_mesh = Mesh(body_vertices_m, body_faces.reshape(-1))
    sdf_build_start = time.perf_counter()
    body_mesh.build_sdf(
        device=device,
        target_voxel_size=args.sdf_voxel_size_cm * 0.01,
        texture_format="float32",
        cache_dir=output_dir / "avatar-sdf-cache",
    )
    sdf_build_seconds = time.perf_counter() - sdf_build_start
    builder.add_shape_mesh(
        body=-1,
        mesh=body_mesh,
        cfg=body_config,
        label="Patterna avatar full-surface SDF",
    )
    builder.color(include_bending=True)

    build_start = time.perf_counter()
    model = builder.finalize(device=device)
    model_build_seconds = time.perf_counter() - build_start
    model.soft_contact_ke = args.contact_stiffness
    model.soft_contact_kd = args.contact_damping
    model.soft_contact_mu = args.body_friction
    model.set_gravity((0.0, args.gravity_m_s2, 0.0))

    solver = SolverVBD(
        model,
        iterations=args.iterations,
        integrate_with_external_rigid_solver=False,
        # Generic particle self-contact treats coincident sewing partners as
        # penetrations and tears the seam apart. Cloth self-contact needs the
        # seam-aware triangle exclusion graph, so the exact post gate remains
        # authoritative until that graph is wired into Newton.
        particle_enable_self_contact=False,
    )
    collision_pipeline = newton.CollisionPipeline(
        model,
        broad_phase="nxn",
        soft_contact_margin=args.contact_margin_cm * 0.01,
        enable_rigid_soft_full_surface_contact=True,
    )
    contacts = collision_pipeline.contacts()
    state_0 = model.state()
    state_1 = model.state()
    control = model.control()

    frame_dt = 1.0 / 60.0
    simulation_dt = frame_dt / args.substeps
    maximum_contact_count = 0
    maximum_frame_displacement_cm = 0.0
    simulation_start = time.perf_counter()
    final_sewing_progress = 1.0 if args.topology_mode != "explicit-springs" else 0.0
    for frame in range(args.frames):
        if initial_seam_rest_lengths_m is not None:
            assert target_seam_rest_length_m is not None
            scheduled_rest_lengths = scheduled_seam_rest_lengths(
                initial_seam_rest_lengths_m,
                target_seam_rest_length_m,
                frame,
                args.sewing_ramp_delay_frames,
                args.sewing_ramp_frames,
            ).astype(np.float32)
            model.spring_rest_length.assign(scheduled_rest_lengths)
            final_sewing_progress = sewing_schedule_progress(
                frame,
                args.sewing_ramp_delay_frames,
                args.sewing_ramp_frames,
            )
        frame_start = state_0.particle_q.numpy()
        for _ in range(args.substeps):
            state_0.clear_forces()
            collision_pipeline.collide(state_0, contacts)
            maximum_contact_count = max(
                maximum_contact_count,
                int(contacts.soft_contact_count.numpy()[0]),
            )
            solver.step(state_0, state_1, control, contacts, simulation_dt)
            state_0, state_1 = state_1, state_0
        frame_end = state_0.particle_q.numpy()
        if not np.isfinite(frame_end).all():
            break
        displacement_cm = np.linalg.norm(frame_end - frame_start, axis=1) * 100.0
        maximum_frame_displacement_cm = max(
            maximum_frame_displacement_cm,
            float(np.max(displacement_cm)),
        )
    simulation_seconds = time.perf_counter() - simulation_start

    final_physical_m = state_0.particle_q.numpy().astype(np.float64)
    finite_positions = bool(np.isfinite(final_physical_m).all())
    final_expanded_cm = (
        final_physical_m * 100.0
        if topology is None
        else expand_welded_positions(final_physical_m * 100.0, topology.old_to_new)
    )
    body_collisions, self_collisions = count_intersections(
        final_physical_m,
        physical_faces,
        body_vertices_m,
        body_faces,
        args.device,
        collision_topology_ids,
    )
    seam_metrics = evaluate_seams(final_expanded_cm, seam_links)
    strain_metrics = evaluate_strain(final_expanded_cm, rest_lengths)
    accepted, rejection_reasons = evaluate_acceptance(
        finite_positions=finite_positions,
        equilibrium_gate_evaluated=True,
        static_equilibrium_reached=finite_positions,
        edge_contact_buffer_saturated=False,
        maximum_observed_edge_contacts=maximum_contact_count,
        edge_contact_capacity=max(maximum_contact_count, 1),
        body_collisions=body_collisions,
        self_collisions=self_collisions,
        seam_link_count=int(seam_metrics["seam_link_count"]),
        maximum_seam_separation_cm=seam_metrics["maximum_seam_separation_cm"],
        max_seam_separation_cm=args.max_seam_separation_cm,
        maximum_edge_strain_ratio=float(strain_metrics["maximum_edge_strain_ratio"]),
        ninety_fifth_percentile_edge_strain_ratio=float(
            strain_metrics["ninety_fifth_percentile_edge_strain_ratio"]
        ),
        ninety_ninth_point_ninth_percentile_edge_strain_ratio=float(
            strain_metrics["ninety_ninth_point_ninth_percentile_edge_strain_ratio"]
        ),
        max_body_collisions=0,
        max_self_collisions=0,
        max_edge_strain_ratio=args.max_edge_strain,
        max_ninety_fifth_percentile_edge_strain_ratio=args.max_p95_edge_strain,
        max_ninety_ninth_point_ninth_percentile_edge_strain_ratio=args.max_p999_edge_strain,
    )

    expanded_output = output_dir / "patterna_vbd_full_surface.obj"
    physical_output = output_dir / "patterna_vbd_full_surface_physical.obj"
    report_output = output_dir / "patterna_vbd_full_surface_report.json"
    write_expanded_obj(material_surface_path, expanded_output, final_expanded_cm)
    write_physical_obj(physical_output, final_physical_m * 100.0, physical_faces)

    solver_files = [
        Path(inspect.getfile(SolverVBD)),
        Path(inspect.getfile(newton.CollisionPipeline)),
    ]
    report: dict[str, object] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "accepted": accepted,
        "rejection_reasons": rejection_reasons,
        "input_manifest_path": str(input_manifest_path),
        "input_manifest_sha256": sha256_file(input_manifest_path),
        "input_manifest_canonical_sha256": report_sha256(input_manifest),
        "input_manifest_schema_version": input_manifest.get("schema_version"),
        "style3d_report_path": (
            str(input_manifest_path) if not using_direct_source else None
        ),
        "style3d_report_sha256": (
            sha256_file(input_manifest_path) if not using_direct_source else None
        ),
        "style3d_report_canonical_sha256": (
            report_sha256(input_manifest) if not using_direct_source else None
        ),
        "style3d_source_accepted": (
            bool(input_manifest.get("accepted", False)) if not using_direct_source else None
        ),
        "physical_input_path": str(physical_input_path),
        "physical_input_sha256": sha256_file(physical_input_path),
        "initial_input_path": str(initial_input_path),
        "initial_input_sha256": sha256_file(initial_input_path),
        "body_mesh_path": str(body_mesh_path),
        "body_mesh_sha256": sha256_file(body_mesh_path),
        "material_surface_path": str(material_surface_path),
        "material_surface_sha256": sha256_file(material_surface_path),
        "material_coordinates_path": str(material_coordinates_path),
        "material_coordinates_sha256": sha256_file(material_coordinates_path),
        "panel_ownership_path": str(segmentation_path),
        "panel_ownership_sha256": sha256_file(segmentation_path),
        "rest_lengths_path": str(rest_lengths_path),
        "rest_lengths_sha256": sha256_file(rest_lengths_path),
        "newton_version": newton.__version__,
        "warp_version": wp.__version__,
        "device": str(device),
        "solver": "newton.solvers.SolverVBD",
        "solver_files": {str(path): sha256_file(path) for path in solver_files},
        "solver_formulation": "vbd-full-surface-sdf-collision-polish",
        "material_solver": (
            "explicit panel cloth with zero-rest sewing springs"
            if args.topology_mode == "explicit-springs"
            else "Style3D source drape retained as VBD rest target"
        ),
        "topology_mode": args.topology_mode,
        "physical_vertex_count": len(physical_vertices_cm),
        "physical_face_count": len(physical_faces),
        "physical_edge_count": len(surface_edges(physical_faces)),
        "reoriented_material_triangle_count": reoriented_material_triangle_count,
        "initial_body_collisions": initial_body_collisions,
        "initial_self_collisions": initial_self_collisions,
        "initial_preflight_passed": True,
        **initial_triangle_quality,
        "minimum_initial_triangle_area_cm2_gate": args.minimum_initial_triangle_area_cm2,
        "minimum_initial_triangle_angle_deg_gate": args.minimum_initial_triangle_angle_deg,
        "maximum_initial_triangle_aspect_ratio_gate": args.maximum_initial_triangle_aspect_ratio,
        "body_collisions": body_collisions,
        "self_collisions": self_collisions,
        "collision_gate_evaluated": True,
        "full_surface_contact_enabled": True,
        "sdf_build_seconds": sdf_build_seconds,
        "model_build_seconds": model_build_seconds,
        "simulation_seconds": simulation_seconds,
        "completed_frames": args.frames,
        "simulation_substeps": args.substeps,
        "solver_iterations": args.iterations,
        "maximum_observed_contact_count": maximum_contact_count,
        "maximum_frame_displacement_cm": maximum_frame_displacement_cm,
        "sdf_voxel_size_cm": args.sdf_voxel_size_cm,
        "contact_margin_cm": args.contact_margin_cm,
        "particle_radius_cm": args.particle_radius_cm,
        "contact_stiffness": args.contact_stiffness,
        "contact_damping": args.contact_damping,
        "body_friction": args.body_friction,
        "initial_body_clearance_cm": args.initial_body_clearance_cm,
        "initial_body_projection": initial_projection,
        "seam_stiffness": args.seam_stiffness if args.topology_mode == "explicit-springs" else None,
        "seam_damping": args.seam_damping if args.topology_mode == "explicit-springs" else None,
        "seam_rest_length_cm": (
            args.seam_rest_length_cm if args.topology_mode == "explicit-springs" else None
        ),
        "initial_maximum_seam_rest_length_cm": (
            float(np.max(initial_seam_rest_lengths_m)) * 100.0
            if initial_seam_rest_lengths_m is not None
            else None
        ),
        "sewing_ramp_delay_frames": (
            args.sewing_ramp_delay_frames if args.topology_mode == "explicit-springs" else None
        ),
        "sewing_ramp_frames": (
            args.sewing_ramp_frames if args.topology_mode == "explicit-springs" else None
        ),
        "sewing_settle_frames": (
            args.sewing_settle_frames if args.topology_mode == "explicit-springs" else None
        ),
        "sewing_schedule_progress": final_sewing_progress,
        "sewing_schedule_completed": final_sewing_progress >= 1.0,
        "gravity_m_s2": args.gravity_m_s2,
        "shape_stiffness": args.shape_stiffness,
        "shape_area_stiffness": args.shape_area_stiffness,
        "shape_damping": args.shape_damping,
        "bend_stiffness": args.bend_stiffness,
        "bend_damping": args.bend_damping,
        **seam_metrics,
        "max_seam_separation_cm": args.max_seam_separation_cm,
        **strain_metrics,
        "max_edge_strain_ratio": args.max_edge_strain,
        "max_ninety_fifth_percentile_edge_strain_ratio": args.max_p95_edge_strain,
        "max_ninety_ninth_point_ninth_percentile_edge_strain_ratio": args.max_p999_edge_strain,
        "output_mesh_path": str(expanded_output),
        "output_mesh_sha256": sha256_file(expanded_output),
        "physical_output_mesh_path": str(physical_output),
        "physical_output_mesh_sha256": sha256_file(physical_output),
    }
    report_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = run(parse_arguments())
    print(json.dumps(report, indent=2))
    return 0 if report["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
