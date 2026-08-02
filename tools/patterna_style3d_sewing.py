"""Style3D cloth solver extension with explicit, progressively closing seams."""

from __future__ import annotations

import numpy as np
import warp as wp

from newton.solvers import SolverStyle3D
from newton._src.solvers.style3d.builder import PDMatrixBuilder
from newton._src.solvers.style3d.kernels import (
    accumulate_dragging_pd_diag_kernel,
    eval_bend_kernel,
    eval_drag_force_kernel,
    eval_stretch_kernel,
    init_rhs_kernel,
    init_step_kernel,
    nonlinear_step_kernel,
    prepare_jacobi_preconditioner_kernel,
    prepare_jacobi_preconditioner_no_contact_hessian_kernel,
    update_velocity,
)


@wp.kernel
def eval_seam_spring_kernel(
    positions: wp.array(dtype=wp.vec3),
    seam_indices: wp.array2d(dtype=wp.int32),
    seam_rest_lengths: wp.array(dtype=float),
    seam_stiffnesses: wp.array(dtype=float),
    forces: wp.array(dtype=wp.vec3),
):
    seam_index = wp.tid()
    first = seam_indices[seam_index, 0]
    second = seam_indices[seam_index, 1]
    delta = positions[second] - positions[first]
    length = wp.length(delta)
    if length > 1.0e-8:
        force = delta * (
            seam_stiffnesses[seam_index]
            * (length - seam_rest_lengths[seam_index])
            / length
        )
        wp.atomic_add(forces, first, force)
        wp.atomic_sub(forces, second, force)


@wp.kernel
def damp_velocity_kernel(
    velocities: wp.array(dtype=wp.vec3),
    retention: float,
):
    particle_index = wp.tid()
    velocities[particle_index] *= retention


def add_seam_matrix_constraints(
    builder: PDMatrixBuilder,
    seam_links: np.ndarray,
    stiffness: float | np.ndarray,
) -> None:
    """Add the positive semidefinite distance-spring approximation to the PD matrix."""
    stiffnesses = np.asarray(stiffness, dtype=np.float64)
    if stiffnesses.ndim == 0:
        stiffnesses = np.full(len(seam_links), float(stiffnesses), dtype=np.float64)
    if stiffnesses.shape != (len(seam_links),):
        raise ValueError("Seam stiffnesses must match the seam-pair count.")
    if not np.isfinite(stiffnesses).all() or np.any(stiffnesses <= 0.0):
        raise ValueError("Seam stiffnesses must be finite and positive.")
    counts = builder.counts.numpy()
    neighbors = builder.neighbors.numpy()
    values = builder.values.numpy()
    diags = builder.diags.numpy()

    for link_index, (raw_first, raw_second) in enumerate(seam_links):
        link_stiffness = float(stiffnesses[link_index])
        first = int(raw_first)
        second = int(raw_second)
        diags[first] += link_stiffness
        diags[second] += link_stiffness
        for row, column in ((first, second), (second, first)):
            matches = np.flatnonzero(neighbors[row, : counts[row]] == column)
            if len(matches):
                values[row, int(matches[0])] -= link_stiffness
                continue
            slot = int(counts[row])
            if slot >= builder.max_neighbors:
                raise ValueError(
                    f"Style3D seam matrix row {row} exceeds "
                    f"{builder.max_neighbors} neighbors."
                )
            neighbors[row, slot] = column
            values[row, slot] = -link_stiffness
            counts[row] += 1

    builder.counts.assign(counts)
    builder.neighbors.assign(neighbors)
    builder.values.assign(values)
    builder.diags.assign(diags)


class PatternaStyle3DSewingSolver(SolverStyle3D):
    """Newton Style3D with explicit seam forces coupled into every nonlinear solve."""

    def __init__(
        self,
        model,
        seam_links: list[tuple[int, int]],
        seam_rest_lengths_m: np.ndarray,
        *,
        seam_stiffness: float,
        seam_stiffnesses: np.ndarray | None = None,
        velocity_retention: float = 1.0,
        iterations: int = 10,
        linear_iterations: int = 10,
    ) -> None:
        links = np.asarray(seam_links, dtype=np.int32)
        rest_lengths = np.asarray(seam_rest_lengths_m, dtype=np.float32)
        if links.ndim != 2 or links.shape[1] != 2 or len(links) == 0:
            raise ValueError("Explicit Style3D sewing requires at least one vertex pair.")
        if rest_lengths.shape != (len(links),):
            raise ValueError("Style3D seam rest lengths must match the seam-pair count.")
        if not np.isfinite(seam_stiffness) or seam_stiffness <= 0.0:
            raise ValueError("Style3D seam stiffness must be finite and positive.")
        link_stiffnesses = (
            np.full(len(links), float(seam_stiffness), dtype=np.float32)
            if seam_stiffnesses is None
            else np.asarray(seam_stiffnesses, dtype=np.float32)
        )
        if link_stiffnesses.shape != (len(links),):
            raise ValueError("Style3D seam stiffnesses must match the seam-pair count.")
        if not np.isfinite(link_stiffnesses).all() or np.any(link_stiffnesses <= 0.0):
            raise ValueError("Style3D seam stiffnesses must be finite and positive.")
        if (
            not np.isfinite(velocity_retention)
            or velocity_retention <= 0.0
            or velocity_retention > 1.0
        ):
            raise ValueError("Velocity retention must be in the interval (0, 1].")
        if not np.isfinite(rest_lengths).all() or np.any(rest_lengths < 0.0):
            raise ValueError("Style3D seam rest lengths must be finite and non-negative.")

        self._seam_links_host = links
        self._seam_stiffnesses_host = link_stiffnesses
        self.seam_stiffness = float(seam_stiffness)
        self.velocity_retention = float(velocity_retention)
        super().__init__(
            model,
            iterations=iterations,
            linear_iterations=linear_iterations,
        )
        self.seam_indices = wp.array2d(links, dtype=int, device=self.device)
        self.seam_rest_lengths = wp.array(rest_lengths, dtype=float, device=self.device)
        self.seam_stiffnesses = wp.array(
            link_stiffnesses,
            dtype=float,
            device=self.device,
        )

    def set_seam_rest_lengths(self, rest_lengths_m: np.ndarray) -> None:
        values = np.asarray(rest_lengths_m, dtype=np.float32)
        if values.shape != (len(self._seam_links_host),):
            raise ValueError("Updated seam rest lengths must match the seam-pair count.")
        if not np.isfinite(values).all() or np.any(values < 0.0):
            raise ValueError("Updated seam rest lengths must be finite and non-negative.")
        self.seam_rest_lengths.assign(values)

    def _precompute(self, model) -> None:
        if not hasattr(model, "style3d"):
            raise AttributeError("Style3D custom attributes are missing from the model.")
        matrix_builder = PDMatrixBuilder(model.particle_count, max_neighbor=40)
        matrix_builder.add_stretch_constraints(
            model.tri_indices.numpy().tolist(),
            model.tri_poses.numpy().tolist(),
            model.style3d.tri_aniso_ke.numpy().tolist(),
            model.tri_areas.numpy().tolist(),
        )
        matrix_builder.add_bend_constraints(
            model.edge_indices.numpy().tolist(),
            model.edge_bending_properties.numpy().tolist(),
            model.style3d.edge_rest_area.numpy().tolist(),
            model.style3d.edge_bending_cot.numpy().tolist(),
        )
        add_seam_matrix_constraints(
            matrix_builder,
            self._seam_links_host,
            self._seam_stiffnesses_host,
        )
        (
            self.pd_diags,
            self.pd_non_diags.num_nz,
            self.pd_non_diags.nz_ell,
        ) = matrix_builder.finalize(self.device)

    def step(self, state_in, state_out, control, contacts, dt: float) -> None:
        if self.collision is not None:
            self.collision.frame_begin(state_in.particle_q, state_in.particle_qd, dt)

        wp.launch(
            kernel=init_step_kernel,
            dim=self.model.particle_count,
            inputs=[
                dt,
                self.model.gravity,
                self.model.particle_world,
                state_in.particle_f,
                state_in.particle_qd,
                state_in.particle_q,
                self.x_prev,
                self.pd_diags,
                self.model.particle_mass,
                self.model.particle_flags,
            ],
            outputs=[self.x_inertia, self.static_A_diags, self.dx],
            device=self.device,
        )

        if self.enable_mouse_dragging:
            wp.launch(
                accumulate_dragging_pd_diag_kernel,
                dim=1,
                inputs=[
                    self.drag_spring_stiff,
                    self.drag_index,
                    self.drag_bary_coord,
                    self.model.tri_indices,
                    self.model.particle_flags,
                ],
                outputs=[self.static_A_diags],
                device=self.device,
            )

        for iteration in range(self.nonlinear_iterations):
            wp.launch(
                init_rhs_kernel,
                dim=self.model.particle_count,
                inputs=[
                    dt,
                    state_in.particle_q,
                    self.x_inertia,
                    self.model.particle_mass,
                ],
                outputs=[self.rhs],
                device=self.device,
            )
            wp.launch(
                eval_stretch_kernel,
                dim=len(self.model.tri_areas),
                inputs=[
                    state_in.particle_q,
                    self.model.tri_areas,
                    self.model.tri_poses,
                    self.model.tri_indices,
                    self.style3d.tri_aniso_ke,
                ],
                outputs=[self.rhs],
                device=self.device,
            )
            wp.launch(
                eval_bend_kernel,
                dim=len(self.style3d.edge_rest_area),
                inputs=[
                    state_in.particle_q,
                    self.style3d.edge_rest_area,
                    self.style3d.edge_bending_cot,
                    self.model.edge_indices,
                    self.model.edge_bending_properties,
                ],
                outputs=[self.rhs],
                device=self.device,
            )
            wp.launch(
                eval_seam_spring_kernel,
                dim=len(self._seam_links_host),
                inputs=[
                    state_in.particle_q,
                    self.seam_indices,
                    self.seam_rest_lengths,
                    self.seam_stiffnesses,
                ],
                outputs=[self.rhs],
                device=self.device,
            )

            if self.enable_mouse_dragging:
                wp.launch(
                    eval_drag_force_kernel,
                    dim=1,
                    inputs=[
                        self.drag_spring_stiff,
                        self.drag_index,
                        self.drag_pos,
                        self.drag_bary_coord,
                        self.model.tri_indices,
                        state_in.particle_q,
                    ],
                    outputs=[self.rhs],
                    device=self.device,
                )

            if self.collision is not None:
                self.collision.accumulate_contact_force(
                    dt,
                    iteration,
                    state_in,
                    state_out,
                    contacts,
                    self.rhs,
                    self.x_prev,
                    self.static_A_diags,
                )
                wp.launch(
                    prepare_jacobi_preconditioner_kernel,
                    dim=self.model.particle_count,
                    inputs=[
                        self.static_A_diags,
                        self.collision.contact_hessian_diagonal(),
                        self.model.particle_flags,
                    ],
                    outputs=[self.inv_A_diags],
                    device=self.device,
                )
            else:
                wp.launch(
                    prepare_jacobi_preconditioner_no_contact_hessian_kernel,
                    dim=self.model.particle_count,
                    inputs=[self.static_A_diags],
                    outputs=[self.inv_A_diags],
                    device=self.device,
                )

            self.linear_solver.solve(
                self.pd_non_diags,
                self.static_A_diags,
                self.dx if iteration == 0 else None,
                self.rhs,
                self.inv_A_diags,
                self.dx,
                self.linear_iterations,
                None if self.collision is None else self.collision.hessian_multiply,
            )
            if self.collision is not None:
                self.collision.linear_iteration_end(self.dx)
            wp.launch(
                nonlinear_step_kernel,
                dim=self.model.particle_count,
                inputs=[state_in.particle_q],
                outputs=[state_out.particle_q, self.dx],
                device=self.device,
            )
            state_in.particle_q.assign(state_out.particle_q)

        wp.launch(
            update_velocity,
            dim=self.model.particle_count,
            inputs=[dt, self.x_prev, state_out.particle_q],
            outputs=[state_out.particle_qd],
            device=self.device,
        )
        if self.velocity_retention < 1.0:
            wp.launch(
                damp_velocity_kernel,
                dim=self.model.particle_count,
                inputs=[state_out.particle_qd, self.velocity_retention],
                device=self.device,
            )
        if self.collision is not None:
            self.collision.frame_end(state_out.particle_q, state_out.particle_qd, dt)
