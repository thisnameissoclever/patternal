"""Differentiably fit Anny's native body controls to Patterna measurements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import torch

from mhr_anthropometry import (
    SectionTopology,
    build_section_topology,
    section_extent_cm,
    section_perimeter_cm,
)


@dataclass(frozen=True)
class ParameterSpec:
    initial: float
    minimum: float
    maximum: float
    regularization: float


PARAMETERS = {
    "local:measure-hips-circ-incr": ParameterSpec(0.0, -1.0, 1.0, 0.05),
    "local:hip-scale-horiz-incr": ParameterSpec(0.0, -1.0, 1.0, 0.08),
    "local:hip-scale-depth-incr": ParameterSpec(0.75, -1.0, 1.0, 0.08),
    "local:measure-waist-circ-incr": ParameterSpec(0.0, -1.0, 1.0, 0.05),
    "local:measure-underbust-circ-incr": ParameterSpec(0.0, -1.0, 1.0, 0.05),
    "local:measure-bust-circ-incr": ParameterSpec(0.75, -1.0, 1.0, 0.05),
    "local:breast-dist-incr": ParameterSpec(0.0, -1.0, 1.0, 0.04),
    "local:stomach-tone-incr": ParameterSpec(0.15, -1.0, 1.0, 0.10),
}


def scaled_to_height_cm(
    vertices: torch.Tensor,
    target_height_cm: float,
    measurement_vertex_indices: np.ndarray | None = None,
) -> torch.Tensor:
    """Scale batched Z-up Anny vertices to a requested standing height."""

    measured = (
        vertices
        if measurement_vertex_indices is None
        else vertices[:, measurement_vertex_indices, :]
    )
    floor = measured[:, :, 2].amin(dim=1)
    height = measured[:, :, 2].amax(dim=1) - floor
    scaled = vertices * (target_height_cm / height)[:, None, None]
    return scaled - torch.stack(
        (torch.zeros_like(floor), torch.zeros_like(floor), floor * target_height_cm / height),
        dim=1,
    )[:, None, :]


def parameter_values(parameters: Mapping[str, torch.Tensor]) -> dict[str, float]:
    return {name: float(value.detach().cpu().item()) for name, value in parameters.items()}


def split_model_parameters(
    parameters: Mapping[str, torch.Tensor],
    base_phenotype: Mapping[str, float],
    base_local_changes: Mapping[str, float],
) -> tuple[dict[str, float | torch.Tensor], dict[str, float | torch.Tensor]]:
    phenotype: dict[str, float | torch.Tensor] = dict(base_phenotype)
    local_changes: dict[str, float | torch.Tensor] = dict(base_local_changes)
    for name, value in parameters.items():
        family, key = name.split(":", 1)
        if family == "phenotype":
            phenotype[key] = value
        elif family == "local":
            local_changes[key] = value
        else:
            raise ValueError(f"Unsupported Anny parameter family: {family}")
    return phenotype, local_changes


def build_station_topologies(
    vertices_cm: np.ndarray,
    faces: np.ndarray,
    station_heights_cm: Mapping[str, float],
) -> dict[str, SectionTopology]:
    floor = float(vertices_cm[:, 2].min())
    height = float(np.ptp(vertices_cm[:, 2]))
    if height <= 0.0:
        raise ValueError("Anny reference body has no standing height")
    return {
        name: build_section_topology(
            vertices_cm,
            faces,
            name=name,
            height_ratio=(float(station_height) - floor) / height,
            section_axis=2,
        )
        for name, station_height in station_heights_cm.items()
    }


def predictions_cm(
    vertices_cm: torch.Tensor,
    topologies: Mapping[str, SectionTopology],
) -> dict[str, torch.Tensor]:
    result: dict[str, torch.Tensor] = {}
    for name, topology in topologies.items():
        result[f"{name}Circumference"] = section_perimeter_cm(vertices_cm, topology)
        result[f"{name}Depth"] = section_extent_cm(vertices_cm, topology, axis=1)
    return result


def optimize_native_controls(
    model: object,
    faces: np.ndarray,
    *,
    body_vertex_indices: np.ndarray,
    base_phenotype: Mapping[str, float],
    base_local_changes: Mapping[str, float],
    target_height_cm: float,
    station_heights_cm: Mapping[str, float],
    targets: Mapping[str, tuple[float, float]],
    breast_apex_vertex_indices: tuple[int, int],
    bust_separation_target_cm: float,
    stages: int = 5,
    steps_per_stage: int = 55,
    learning_rate: float = 0.035,
) -> tuple[np.ndarray, dict[str, float], dict[str, float], dict[str, object]]:
    """Optimize native semantic controls before any geometric residual fit."""

    if stages < 1 or steps_per_stage < 1:
        raise ValueError("Anny optimization requires positive stage and step counts")
    parameters = {
        name: torch.nn.Parameter(
            torch.tensor(spec.initial, dtype=model.dtype, device=model.device)
        )
        for name, spec in PARAMETERS.items()
    }
    optimizer = torch.optim.Adam(parameters.values(), lr=learning_rate)
    history: list[dict[str, object]] = []
    topologies: dict[str, SectionTopology] = {}

    for stage in range(stages):
        with torch.no_grad():
            phenotype, local_changes = split_model_parameters(
                parameters,
                base_phenotype,
                base_local_changes,
            )
            output = model(
                phenotype_kwargs=phenotype,
                local_changes_kwargs=local_changes,
            )
            scaled = scaled_to_height_cm(
                output["vertices"],
                target_height_cm,
                body_vertex_indices,
            )
            topologies = build_station_topologies(
                scaled[0].detach().cpu().numpy(),
                faces,
                station_heights_cm,
            )

        for _ in range(steps_per_stage):
            optimizer.zero_grad(set_to_none=True)
            phenotype, local_changes = split_model_parameters(
                parameters,
                base_phenotype,
                base_local_changes,
            )
            output = model(
                phenotype_kwargs=phenotype,
                local_changes_kwargs=local_changes,
            )
            scaled = scaled_to_height_cm(
                output["vertices"],
                target_height_cm,
                body_vertex_indices,
            )
            predicted = predictions_cm(scaled, topologies)
            losses: list[torch.Tensor] = []
            for station, (target_circuit, target_depth) in targets.items():
                losses.append(
                    ((predicted[f"{station}Circumference"] - target_circuit) / 0.75).square().mean()
                )
                losses.append(
                    ((predicted[f"{station}Depth"] - target_depth) / 0.55).square().mean()
                )
            left_apex, right_apex = breast_apex_vertex_indices
            bust_separation = (
                scaled[:, right_apex, 0] - scaled[:, left_apex, 0]
            ).abs()
            losses.append(
                ((bust_separation - bust_separation_target_cm) / 0.45).square().mean()
            )
            for name, parameter in parameters.items():
                spec = PARAMETERS[name]
                losses.append(
                    spec.regularization * (parameter - spec.initial).square()
                )
            loss = torch.stack(losses).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(parameters.values(), max_norm=25.0)
            optimizer.step()
            with torch.no_grad():
                for name, parameter in parameters.items():
                    spec = PARAMETERS[name]
                    parameter.clamp_(spec.minimum, spec.maximum)

        with torch.no_grad():
            phenotype, local_changes = split_model_parameters(
                parameters,
                base_phenotype,
                base_local_changes,
            )
            output = model(
                phenotype_kwargs=phenotype,
                local_changes_kwargs=local_changes,
            )
            scaled = scaled_to_height_cm(
                output["vertices"],
                target_height_cm,
                body_vertex_indices,
            )
            predicted = predictions_cm(scaled, topologies)
            history.append({
                "stage": stage + 1,
                "parameters": parameter_values(parameters),
                "predictionsCm": {
                    name: float(value.detach().cpu().item())
                    for name, value in predicted.items()
                },
            })

    phenotype, local_changes = split_model_parameters(
        parameters,
        base_phenotype,
        base_local_changes,
    )
    with torch.no_grad():
        final = model(
            phenotype_kwargs=phenotype,
            local_changes_kwargs=local_changes,
        )
        final_vertices_cm = scaled_to_height_cm(
            final["vertices"], target_height_cm, body_vertex_indices
        )[0].detach().cpu().numpy()
    final_phenotype = {
        name: float(value.detach().cpu().item()) if torch.is_tensor(value) else float(value)
        for name, value in phenotype.items()
    }
    final_local = {
        name: float(value.detach().cpu().item()) if torch.is_tensor(value) else float(value)
        for name, value in local_changes.items()
    }
    return final_vertices_cm / 100.0, final_phenotype, final_local, {
        "method": "differentiable optimization of Anny native semantic controls",
        "stages": stages,
        "stepsPerStage": steps_per_stage,
        "history": history,
    }
