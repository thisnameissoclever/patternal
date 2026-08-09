#!/usr/bin/env python3
"""Fit MHR's learned body identity coordinates to Patterna measurements."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.mhr_anthropometry import (
    SectionTopology,
    build_section_topology,
    section_extent_cm,
    section_perimeter_cm,
)


DEFAULT_MODEL = REPO_ROOT / ".runtime/mhr-v1.0.1/assets/mhr_model.pt"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts/mhr-avatar-fitted-v1"
SECTION_SPECS = (
    ("hip", 0.55, "hip", "hipDepth"),
    ("abdomen", 0.61, "abdomenCirc", "abdomenDepth"),
    ("waist", 0.68, "waist", "waistDepth"),
    ("underbust", 0.70, "underBust", "underBustDepth"),
    ("bust", 0.74, "chest", "chestDepth"),
)
UPPER_ARM_SECTION_RATIO = 0.74


def measurement_tolerance_cm(name: str) -> float:
    return 1.0 if name.endswith("Circumference") else 0.75


def measurement_acceptance(
    predictions: dict[str, torch.Tensor | float], targets: dict[str, float]
) -> dict[str, object]:
    residuals: dict[str, dict[str, float | bool]] = {}
    for name, target in targets.items():
        prediction_value = predictions[name]
        actual = (
            float(prediction_value.item())
            if isinstance(prediction_value, torch.Tensor)
            else float(prediction_value)
        )
        tolerance = measurement_tolerance_cm(name)
        absolute_error = abs(actual - target)
        residuals[name] = {
            "targetCm": target,
            "actualCm": actual,
            "signedErrorCm": actual - target,
            "absoluteErrorCm": absolute_error,
            "toleranceCm": tolerance,
            "accepted": absolute_error <= tolerance,
        }
    rejected = [name for name, result in residuals.items() if not result["accepted"]]
    return {
        "status": "accepted" if not rejected else "rejected",
        "rejectedMeasurements": rejected,
        "measurements": residuals,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--initial-identity-json", type=Path)
    parser.add_argument("--stages", type=int, default=10)
    parser.add_argument("--steps-per-stage", type=int, default=80)
    parser.add_argument("--learning-rate", type=float, default=0.035)
    parser.add_argument("--regularization", type=float, default=0.025)
    return parser.parse_args()


def load_targets(profile_path: Path) -> tuple[float, dict[str, float]]:
    document = json.loads(profile_path.read_text(encoding="utf-8"))
    measurements = document.get("measurements")
    if not isinstance(measurements, dict):
        raise ValueError("Patterna avatar profile has no measurement dictionary.")
    height = float(measurements["height"])
    targets: dict[str, float] = {}
    for name, _, circumference_key, depth_key in SECTION_SPECS:
        targets[f"{name}Circumference"] = float(measurements[circumference_key])
        targets[f"{name}Depth"] = float(measurements[depth_key])
    targets["upperArmCircumference"] = 0.5 * (
        float(measurements["upperArmCircL"])
        + float(measurements["upperArmCircR"])
    )
    if height <= 0.0 or any(value <= 0.0 for value in targets.values()):
        raise ValueError("MHR fit targets must be positive measurements in centimeters.")
    return height, targets


def scaled_to_height(vertices_cm: torch.Tensor, target_height_cm: float) -> torch.Tensor:
    current_height = vertices_cm[:, :, 1].amax(dim=1) - vertices_cm[:, :, 1].amin(dim=1)
    return vertices_cm * (target_height_cm / current_height)[:, None, None]


def build_topologies(vertices_cm: np.ndarray, faces: np.ndarray) -> list[SectionTopology]:
    torso_topologies = [
        build_section_topology(
            vertices_cm,
            faces,
            name=name,
            height_ratio=height_ratio,
        )
        for name, height_ratio, _, _ in SECTION_SPECS
    ]
    torso_topologies.append(
        build_section_topology(
            vertices_cm,
            faces,
            name="upperArm",
            height_ratio=UPPER_ARM_SECTION_RATIO,
            section_axis=0,
            require_centered=False,
        )
    )
    return torso_topologies


def predict_measurements(
    vertices_cm: torch.Tensor, topologies: list[SectionTopology]
) -> dict[str, torch.Tensor]:
    result: dict[str, torch.Tensor] = {}
    for topology in topologies:
        result[f"{topology.name}Circumference"] = section_perimeter_cm(
            vertices_cm, topology
        )
        if topology.section_axis == 1:
            result[f"{topology.name}Depth"] = section_extent_cm(
                vertices_cm, topology, axis=2
            )
    return result


def loss_for_predictions(
    predictions: dict[str, torch.Tensor],
    targets: dict[str, float],
    body_coefficients: torch.Tensor,
    regularization: float,
) -> torch.Tensor:
    measurement_losses = []
    for name, target in targets.items():
        tolerance = measurement_tolerance_cm(name)
        measurement_losses.append(((predictions[name] - target) / tolerance).square())
    measurement_loss = torch.stack(measurement_losses).mean()
    return measurement_loss + regularization * body_coefficients.square().mean()


def fit(
    model: torch.jit.ScriptModule,
    faces: np.ndarray,
    *,
    target_height_cm: float,
    targets: dict[str, float],
    stages: int,
    steps_per_stage: int,
    learning_rate: float,
    regularization: float,
    initial_identity: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, object]]:
    if stages < 1 or steps_per_stage < 1:
        raise ValueError("MHR fitting requires positive stage and step counts.")
    if initial_identity is None:
        initial_body = torch.zeros((1, 20), dtype=torch.float32)
    else:
        values = np.asarray(initial_identity, dtype=np.float32)
        if values.shape != (45,) or not np.isfinite(values).all():
            raise ValueError("Initial MHR identity must contain 45 finite coefficients.")
        initial_body = torch.from_numpy(values[:20]).reshape(1, 20).clone()
    body_coefficients = torch.nn.Parameter(initial_body)
    optimizer = torch.optim.Adam([body_coefficients], lr=learning_rate)
    zeros_head_and_hands = torch.zeros((1, 25), dtype=torch.float32)
    model_parameters = torch.zeros((1, 204), dtype=torch.float32)
    expressions = torch.zeros((1, 72), dtype=torch.float32)
    history: list[dict[str, object]] = []
    topologies: list[SectionTopology] = []
    best_loss = float("inf")
    best_stage = 0
    best_body_coefficients = body_coefficients.detach().clone()
    best_predictions: dict[str, float] = {}

    for stage in range(stages):
        with torch.no_grad():
            identity = torch.cat((body_coefficients, zeros_head_and_hands), dim=1)
            vertices, _ = model(identity, model_parameters, expressions, True)
            scaled = scaled_to_height(vertices, target_height_cm)
            topologies = build_topologies(scaled[0].cpu().numpy(), faces)

        for _ in range(steps_per_stage):
            optimizer.zero_grad(set_to_none=True)
            identity = torch.cat((body_coefficients, zeros_head_and_hands), dim=1)
            vertices, _ = model(identity, model_parameters, expressions, True)
            scaled = scaled_to_height(vertices, target_height_cm)
            predictions = predict_measurements(scaled, topologies)
            loss = loss_for_predictions(
                predictions, targets, body_coefficients, regularization
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_([body_coefficients], max_norm=50.0)
            optimizer.step()
            with torch.no_grad():
                body_coefficients.clamp_(-3.0, 3.0)

        with torch.no_grad():
            identity = torch.cat((body_coefficients, zeros_head_and_hands), dim=1)
            vertices, _ = model(identity, model_parameters, expressions, True)
            scaled = scaled_to_height(vertices, target_height_cm)
            topologies = build_topologies(scaled[0].cpu().numpy(), faces)
            predictions = predict_measurements(scaled, topologies)
            stage_loss = loss_for_predictions(
                predictions, targets, body_coefficients, regularization
            )
            stage_loss_value = float(stage_loss.item())
            stage_predictions = {
                name: float(value.item()) for name, value in predictions.items()
            }
            if stage_loss_value < best_loss:
                best_loss = stage_loss_value
                best_stage = stage + 1
                best_body_coefficients = body_coefficients.detach().clone()
                best_predictions = stage_predictions
            history.append(
                {
                    "stage": stage + 1,
                    "loss": stage_loss_value,
                    "coefficientMinimum": float(body_coefficients.min().item()),
                    "coefficientMaximum": float(body_coefficients.max().item()),
                    "predictionsCm": stage_predictions,
                    "acceptance": measurement_acceptance(stage_predictions, targets),
                }
            )
            print(json.dumps(history[-1]))

    identity = torch.cat((best_body_coefficients, zeros_head_and_hands), dim=1)
    saturated = [
        index
        for index, value in enumerate(best_body_coefficients[0].tolist())
        if abs(value) >= 2.999
    ]
    acceptance = measurement_acceptance(best_predictions, targets)
    return identity[0].detach().cpu().numpy(), {
        "status": acceptance["status"],
        "selectedStage": best_stage,
        "bestLoss": best_loss,
        "finalLoss": history[-1]["loss"],
        "selectedPredictionsCm": best_predictions,
        "saturatedBodyCoefficientIndices": saturated,
        "acceptance": acceptance,
        "history": history,
    }


def main() -> None:
    args = parse_args()
    profile_path = args.profile.resolve()
    model_path = args.model.resolve()
    output_directory = args.output_directory.resolve()
    target_height_cm, targets = load_targets(profile_path)
    initial_identity = (
        np.asarray(
            json.loads(args.initial_identity_json.resolve().read_text(encoding="utf-8")),
            dtype=np.float32,
        )
        if args.initial_identity_json
        else None
    )
    model = torch.jit.load(str(model_path), map_location="cpu")
    model.eval()
    faces = model.character_torch.mesh.faces.cpu().numpy().astype(np.int64)
    identity, evidence = fit(
        model,
        faces,
        target_height_cm=target_height_cm,
        targets=targets,
        stages=args.stages,
        steps_per_stage=args.steps_per_stage,
        learning_rate=args.learning_rate,
        regularization=args.regularization,
        initial_identity=initial_identity,
    )

    output_directory.mkdir(parents=True, exist_ok=True)
    identity_path = output_directory / "identity-coefficients.json"
    report_path = output_directory / "identity-fit-report.json"
    identity_path.write_text(json.dumps(identity.tolist(), indent=2) + "\n", encoding="utf-8")
    report = {
        "schemaVersion": "patterna.mhr-identity-fit/1.0",
        "sourceProfile": str(profile_path),
        "initialIdentity": (
            str(args.initial_identity_json.resolve()) if args.initial_identity_json else None
        ),
        "model": str(model_path),
        "targetHeightCm": target_height_cm,
        "targetsCm": targets,
        "identityCoefficientCount": int(identity.shape[0]),
        "bodyCoefficientBounds": {
            "minimum": float(identity[:20].min()),
            "maximum": float(identity[:20].max()),
        },
        **evidence,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote fitted MHR identity to {identity_path}")


if __name__ == "__main__":
    main()
