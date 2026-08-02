#!/usr/bin/env python3
"""Fit CharMorph body controls to Patterna's editable circumference profile."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import least_squares
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charmorph_morphs import apply_controls, load_packed_morphs
from charmorph_profile_controls import (
    FIT_CONTROL_NAMES,
    FIT_CONTROL_BOUNDS,
    FIT_TARGET_NAMES,
    PATTERNA_FULL_BUST_CONTROLS,
    clamp_controls,
    measurement_targets,
)
from charmorph_supported_bust import (
    apply_supported_bust_shape,
    breast_vertex_indices,
    underbust_root_curvature_cm,
)
from mesh_torso_arcs import measure_torso_arc_section


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHARACTER_DIR = REPO_ROOT / "third_party" / "CharMorph-db" / "characters" / "mb_female"
DEFAULT_PROFILE = REPO_ROOT / "PatternaUnreal" / "SourceAssets" / "Avatar" / "PatternaFullBustDefault.avatar-profile.json"
DEFAULT_BASIS = "African"
STATION_RATIOS = {
    "hip": 0.505,
    "abdomen": 0.585,
    "waist": 0.660,
    "underbust": 0.682,
    "high_chest": 0.802,
}
BUST_RATIOS = (0.695, 0.705, 0.715, 0.725, 0.735)


def resolve(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def triangulate_quads(faces: np.ndarray) -> np.ndarray:
    if faces.ndim != 2:
        raise ValueError("CharMorph faces must be a two-dimensional array")
    if faces.shape[1] == 3:
        return faces.astype(np.int64, copy=True)
    if faces.shape[1] != 4:
        raise ValueError("CharMorph faces must contain triangles or quads")
    return np.vstack((faces[:, [0, 1, 2]], faces[:, [0, 2, 3]])).astype(np.int64)


def scaled_vertices(vertices: np.ndarray, target_height_cm: float) -> np.ndarray:
    result = vertices.astype(np.float64, copy=True)
    height = float(result[:, 2].max() - result[:, 2].min())
    if height <= 0.0 or target_height_cm <= 0.0:
        raise ValueError("CharMorph height must be positive")
    result *= (target_height_cm / 100.0) / height
    return result


def breast_landmark_metrics(vertices_z_up: np.ndarray) -> dict[str, float]:
    """Locate the two breast apices and the inframammary relief."""
    floor = float(vertices_z_up[:, 2].min())
    height = float(np.ptp(vertices_z_up[:, 2]))
    if height <= 0.0:
        raise ValueError("CharMorph height must be positive")
    apices: list[np.ndarray] = []
    fold_reliefs_cm: list[float] = []
    for side in (-1.0, 1.0):
        side_coordinate = vertices_z_up[:, 0] * side
        breast_mask = (
            (side_coordinate >= 0.035)
            & (side_coordinate <= 0.18)
            & (vertices_z_up[:, 2] >= floor + 0.69 * height)
            & (vertices_z_up[:, 2] <= floor + 0.77 * height)
        )
        candidates = vertices_z_up[breast_mask]
        if len(candidates) < 20:
            raise RuntimeError("Could not isolate a CharMorph breast surface")
        apex = candidates[int(np.argmin(candidates[:, 1]))]
        apices.append(apex)
        fold_mask = (
            (np.abs(vertices_z_up[:, 0] - apex[0]) <= 0.03)
            & (vertices_z_up[:, 2] >= floor + 0.658 * height)
            & (vertices_z_up[:, 2] <= floor + 0.676 * height)
        )
        fold = vertices_z_up[fold_mask]
        if len(fold) < 4:
            raise RuntimeError("Could not isolate a CharMorph inframammary root")
        fold_front_y = float(np.min(fold[:, 1]))
        fold_reliefs_cm.append((fold_front_y - float(apex[1])) * 100.0)
    left, right = sorted(apices, key=lambda point: float(point[0]))
    return {
        "bust_separation": float((right[0] - left[0]) * 100.0),
        "bust_apex_height_ratio": float(
            (((left[2] + right[2]) * 0.5) - floor) / height
        ),
        "underbust_fold_relief": float(np.mean(fold_reliefs_cm)),
        "underbust_fold_relief_left": fold_reliefs_cm[0],
        "underbust_fold_relief_right": fold_reliefs_cm[1],
    }


def circumference_metrics(
    vertices_z_up: np.ndarray,
    faces: np.ndarray,
) -> dict[str, float]:
    floor = float(vertices_z_up[:, 2].min())
    height_m = float(vertices_z_up[:, 2].max() - floor)
    converted = np.column_stack((
        vertices_z_up[:, 0],
        vertices_z_up[:, 2] - floor,
        vertices_z_up[:, 1],
    ))
    mesh = trimesh.Trimesh(vertices=converted, faces=faces, process=False)
    result = {
        name: measure_torso_arc_section(
            mesh,
            ratio * height_m * 100.0,
            front_is_positive_depth=False,
        ).circumference_cm
        for name, ratio in STATION_RATIOS.items()
    }
    landmarks = breast_landmark_metrics(vertices_z_up)
    result["bust"] = measure_torso_arc_section(
        mesh,
        landmarks["bust_apex_height_ratio"] * height_m * 100.0,
        front_is_positive_depth=False,
    ).circumference_cm
    result.update(landmarks)
    return result


def fit_controls(
    basis: np.ndarray,
    faces: np.ndarray,
    raw_morphs: dict,
    targets: dict[str, float],
    measurements: dict[str, object],
    target_height_cm: float,
    initial_controls: dict[str, float],
    max_evaluations: int,
) -> tuple[dict[str, float], dict[str, float], object]:
    names = FIT_CONTROL_NAMES
    initial = np.asarray([initial_controls[name] for name in names], dtype=float)
    lower = np.asarray([FIT_CONTROL_BOUNDS[name][0] for name in names], dtype=float)
    upper = np.asarray([FIT_CONTROL_BOUNDS[name][1] for name in names], dtype=float)
    cache: dict[tuple[float, ...], dict[str, float]] = {}

    def metrics_for(values: np.ndarray) -> dict[str, float]:
        key = tuple(np.round(values, 10))
        if key not in cache:
            controls = dict(initial_controls)
            controls.update(zip(names, values.tolist()))
            vertices, _ = apply_controls(basis, raw_morphs, controls)
            supported, _ = apply_supported_bust_shape(
                scaled_vertices(vertices, target_height_cm),
                raw_morphs,
                measurements,
            )
            cache[key] = circumference_metrics(
                supported,
                faces,
            )
        return cache[key]

    def residuals(values: np.ndarray) -> np.ndarray:
        metrics = metrics_for(values)
        measurement = np.asarray([
            (metrics[name] - targets[name]) / 1.0
            for name in FIT_TARGET_NAMES
        ])
        regularization = (values - initial) * 0.08
        return np.concatenate((measurement, regularization))

    solution = least_squares(
        residuals,
        initial,
        bounds=(lower, upper),
        max_nfev=max_evaluations,
        xtol=1.0e-5,
        ftol=1.0e-5,
        gtol=1.0e-5,
        verbose=1,
    )
    fitted = dict(initial_controls)
    fitted.update(zip(names, solution.x.tolist()))
    fitted = clamp_controls(fitted)
    return fitted, metrics_for(solution.x), solution


def enforce_closed_circuits(
    vertices: np.ndarray,
    faces: np.ndarray,
    targets: dict[str, float],
    *,
    iterations: int = 12,
) -> tuple[np.ndarray, dict[str, float], float]:
    """Apply bounded smooth radial corrections below the breast root."""
    corrected = vertices.astype(np.float64, copy=True)
    original = corrected.copy()
    floor = float(corrected[:, 2].min())
    height = float(corrected[:, 2].max() - floor)
    stations = {
        name: floor + ratio * height
        for name, ratio in STATION_RATIOS.items()
        if name in ("hip", "abdomen", "waist", "underbust")
    }
    sigma = {
        "hip": 0.024 * height,
        "abdomen": 0.018 * height,
        "waist": 0.014 * height,
        "underbust": 0.0075 * height,
    }
    for _ in range(iterations):
        metrics = circumference_metrics(corrected, faces)
        if max(abs(metrics[name] - targets[name]) for name in stations) <= 0.20:
            break
        for name, station in stations.items():
            measured = metrics[name]
            factor = float(np.clip(targets[name] / measured, 0.975, 1.025))
            vertical_weights = np.exp(
                -0.5 * ((corrected[:, 2] - station) / sigma[name]) ** 2
            )
            lateral_ratio = np.abs(corrected[:, 0]) / height
            lateral_weights = np.clip((0.25 - lateral_ratio) / 0.06, 0.0, 1.0)
            weights = vertical_weights * lateral_weights
            local_factor = 1.0 + (factor - 1.0) * weights
            corrected[:, 0] *= local_factor
            corrected[:, 1] *= local_factor
    final_metrics = circumference_metrics(corrected, faces)
    maximum_displacement_cm = float(
        np.linalg.norm(corrected - original, axis=1).max() * 100.0
    )
    return corrected, final_metrics, maximum_displacement_cm


def refine_bust_after_constraints(
    basis: np.ndarray,
    faces: np.ndarray,
    raw_morphs: dict,
    controls: dict[str, float],
    targets: dict[str, float],
    measurements: dict[str, object],
    target_height_cm: float,
) -> tuple[dict[str, float], np.ndarray, dict[str, float], float, object]:
    names = ("Torso_BreastMass", "Torso_BreastPosX", "Torso_BreastScaleY")
    initial = np.asarray([controls[name] for name in names], dtype=float)
    lower = np.asarray([FIT_CONTROL_BOUNDS[name][0] for name in names], dtype=float)
    upper = np.asarray([FIT_CONTROL_BOUNDS[name][1] for name in names], dtype=float)
    cache: dict[tuple[float, ...], tuple[np.ndarray, dict[str, float], float]] = {}

    def evaluate(values: np.ndarray) -> tuple[np.ndarray, dict[str, float], float]:
        key = tuple(np.round(values, 10))
        if key not in cache:
            candidate = dict(controls)
            candidate.update(zip(names, values.tolist()))
            morphed, _ = apply_controls(basis, raw_morphs, candidate)
            supported, _ = apply_supported_bust_shape(
                scaled_vertices(morphed, target_height_cm),
                raw_morphs,
                measurements,
            )
            cache[key] = enforce_closed_circuits(supported, faces, targets)
        return cache[key]

    def residual(values: np.ndarray) -> np.ndarray:
        _vertices, metrics, _maximum_displacement = evaluate(values)
        return np.asarray([
            metrics["bust"] - targets["bust"],
            metrics["bust_separation"] - targets["bust_separation"],
            *((values - initial) * 0.04),
        ])

    solution = least_squares(
        residual,
        initial,
        bounds=(lower, upper),
        max_nfev=24,
        xtol=1.0e-5,
        ftol=1.0e-5,
        gtol=1.0e-5,
    )
    fitted = dict(controls)
    fitted.update(zip(names, solution.x.tolist()))
    vertices, metrics, maximum_displacement = evaluate(solution.x)
    return fitted, vertices, metrics, maximum_displacement, solution


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--character-dir", type=Path, default=DEFAULT_CHARACTER_DIR)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--basis", default=DEFAULT_BASIS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--vertices", type=Path)
    parser.add_argument("--max-evaluations", type=int, default=80)
    args = parser.parse_args()
    if args.max_evaluations <= 0:
        raise ValueError("Maximum evaluation count must be positive")

    character_dir = resolve(args.character_dir)
    profile_path = resolve(args.profile)
    output_path = resolve(args.output)
    report_path = resolve(args.report) if args.report else output_path.with_suffix(".fit-report.json")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    targets = measurement_targets(profile)
    measurements = profile.get("measurements")
    if not isinstance(measurements, dict):
        raise ValueError("CharMorph fitting requires a measurements object")
    target_height_cm = float(profile["measurements"]["height"])

    basis_path = character_dir / "morphs" / "L1" / f"{args.basis}.npy"
    if not basis_path.is_file():
        raise FileNotFoundError(f"CharMorph basis not found: {basis_path}")
    faces_path = character_dir / "faces.npy"
    pack_path = character_dir / "morphs" / "L2_packed" / "__main__.npz"
    basis = np.load(basis_path).astype(np.float64)
    faces = triangulate_quads(np.load(faces_path))
    raw_morphs = load_packed_morphs(pack_path)
    controls, control_metrics, solution = fit_controls(
        basis,
        faces,
        raw_morphs,
        targets,
        measurements,
        target_height_cm,
        dict(PATTERNA_FULL_BUST_CONTROLS),
        args.max_evaluations,
    )
    controls, corrected, metrics, maximum_displacement_cm, bust_solution = (
        refine_bust_after_constraints(
            basis,
            faces,
            raw_morphs,
            controls,
            targets,
            measurements,
            target_height_cm,
        )
    )
    final_breast_indices = breast_vertex_indices(raw_morphs)
    final_root_half_width_m = float(
        np.clip(
            (targets["bust"] - targets["underbust"]) * 0.0028,
            0.065,
            0.095,
        )
        * (target_height_cm / 167.0)
    )
    final_root_curvature_cm = underbust_root_curvature_cm(
        corrected,
        final_breast_indices,
        final_root_half_width_m,
    )
    fitted_morphed, _ = apply_controls(basis, raw_morphs, controls)
    _supported, support_evidence = apply_supported_bust_shape(
        scaled_vertices(fitted_morphed, target_height_cm),
        raw_morphs,
        measurements,
    )
    residuals = {
        name: metrics[name] - targets[name]
        for name in targets
        if name in metrics
    }
    circuit_names = ("hip", "abdomen", "waist", "underbust", "bust")
    fitted_residuals = {name: residuals[name] for name in circuit_names}
    max_residual = max(abs(value) for value in fitted_residuals.values())
    bust_separation_residual = residuals["bust_separation"]
    accepted = bool(
        solution.success
        and bust_solution.success
        and max_residual <= 0.25
        and abs(bust_separation_residual) <= 1.0
        and maximum_displacement_cm <= 1.5
        and metrics["underbust_fold_relief"] >= 2.0
        and min(final_root_curvature_cm) >= 0.50
        and support_evidence.maximum_displacement_cm <= 3.5
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"replaceDefaults": True, "controls": controls}, indent=2) + "\n",
        encoding="utf-8",
    )
    vertices_path = resolve(args.vertices) if args.vertices else output_path.with_suffix(".vertices.npy")
    vertices_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(vertices_path, corrected.astype(np.float32))
    report = {
        "schemaVersion": "patterna.charmorph-fit/1.0",
        "accepted": accepted,
        "sourceProfile": str(profile_path),
        "sourceProfileSha256": sha256(profile_path),
        "sourcePack": str(pack_path),
        "sourcePackSha256": sha256(pack_path),
        "sourceBasis": str(basis_path),
        "sourceBasisName": args.basis,
        "sourceBasisSha256": sha256(basis_path),
        "targetHeightCm": target_height_cm,
        "targetsCm": targets,
        "measuredCm": metrics,
        "controlOnlyMeasuredCm": control_metrics,
        "residualsCm": residuals,
        "closedCircuitResidualsCm": fitted_residuals,
        "maximumAbsoluteResidualCm": max_residual,
        "toleranceCm": 0.25,
        "bustSeparationResidualCm": bust_separation_residual,
        "bustSeparationToleranceCm": 1.0,
        "surfaceConstraint": {
            "method": "bounded smooth radial circuits below the breast root",
            "maximumDisplacementCm": maximum_displacement_cm,
            "maximumAllowedDisplacementCm": 1.5,
            "preservesBreastSurface": True,
            "vertices": str(vertices_path),
            "verticesSha256": sha256(vertices_path),
        },
        "anatomicalLandmarks": {
            "bustApexHeightRatio": metrics["bust_apex_height_ratio"],
            "bustSeparationCm": metrics["bust_separation"],
            "bustSeparationTargetCm": targets["bust_separation"],
            "underbustFoldReliefCm": metrics["underbust_fold_relief"],
            "underbustFoldReliefLeftCm": metrics["underbust_fold_relief_left"],
            "underbustFoldReliefRightCm": metrics["underbust_fold_relief_right"],
            "minimumAcceptedFoldReliefCm": 2.0,
            "underbustRootCurvatureLeftCm": final_root_curvature_cm[0],
            "underbustRootCurvatureRightCm": final_root_curvature_cm[1],
            "minimumAcceptedRootCurvatureCm": 0.50,
        },
        "supportedBustSurface": support_evidence.to_dict(),
        "nonPlanarTapeMeasurements": {
            "high_chest": {
                "targetCm": targets["high_chest"],
                "diagnosticHorizontalSectionCm": metrics["high_chest"],
                "usedAsClosedFitConstraint": False,
            }
        },
        "optimizer": {
            "success": bool(solution.success),
            "status": int(solution.status),
            "message": str(solution.message),
            "evaluations": int(solution.nfev),
            "cost": float(solution.cost),
            "bustRefinementSuccess": bool(bust_solution.success),
            "bustRefinementEvaluations": int(bust_solution.nfev),
        },
        "controls": controls,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not accepted:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
