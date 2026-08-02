#!/usr/bin/env python3
"""Create a topology-preserving relaxed MPFB body for posed cloth simulation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


ARM_BONE_TOKENS = (
    "upperarm",
    "lowerarm",
    "wrist",
    "metacarpal",
    "finger",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_obj(path: Path) -> tuple[list[list[float]], list[str]]:
    vertices: list[list[float]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if not line.startswith("v "):
            continue
        values = line.split()
        if len(values) < 4:
            raise ValueError(f"Invalid OBJ vertex line: {line}")
        vertex = [float(values[1]), float(values[2]), float(values[3])]
        if not all(math.isfinite(value) for value in vertex):
            raise ValueError("OBJ contains a non-finite vertex coordinate.")
        vertices.append(vertex)
    if not vertices:
        raise ValueError("OBJ contains no vertices.")
    return vertices, lines


def write_obj(path: Path, lines: list[str], vertices: list[list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    vertex_index = 0
    output: list[str] = []
    for line in lines:
        if line.startswith("v "):
            x, y, z = vertices[vertex_index]
            output.append(f"v {x:.9f} {y:.9f} {z:.9f}")
            vertex_index += 1
        else:
            output.append(line)
    if vertex_index != len(vertices):
        raise ValueError("OBJ vertex rewrite did not preserve vertex count.")
    path.write_text("\n".join(output) + "\n", encoding="utf-8", newline="\n")


def arm_weights(
    vertex_count: int,
    weight_payload: dict[str, Any],
    suffix: str,
) -> list[float]:
    weights = [0.0] * vertex_count
    source = weight_payload.get("weights")
    if not isinstance(source, dict):
        raise ValueError("MPFB rig weight file has no weights object.")
    for bone_name, entries in source.items():
        lower_name = str(bone_name).lower()
        if not str(bone_name).endswith(suffix) or not any(
            token in lower_name for token in ARM_BONE_TOKENS
        ):
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, list) or len(entry) != 2:
                continue
            vertex_index = int(entry[0])
            if 0 <= vertex_index < vertex_count:
                weights[vertex_index] += float(entry[1])
    return [min(1.0, max(0.0, value)) for value in weights]


def shoulder_pivot(
    vertices: list[list[float]],
    weights: list[float],
) -> list[float]:
    candidates = [
        vertex
        for vertex, weight in zip(vertices, weights, strict=True)
        if 0.1 <= weight <= 0.5
    ]
    if len(candidates) < 2:
        raise ValueError("Rig weights do not expose a stable shoulder transition band.")
    return [
        sum(vertex[axis] for vertex in candidates) / len(candidates)
        for axis in range(3)
    ]


def rotate_about_y(
    vertex: list[float],
    pivot: list[float],
    angle_radians: float,
) -> list[float]:
    x = vertex[0] - pivot[0]
    z = vertex[2] - pivot[2]
    cosine = math.cos(angle_radians)
    sine = math.sin(angle_radians)
    return [
        pivot[0] + x * cosine + z * sine,
        vertex[1],
        pivot[2] - x * sine + z * cosine,
    ]


def pose_relaxed_arms(
    vertices: list[list[float]],
    weight_payload: dict[str, Any],
    lowering_degrees: float,
) -> tuple[list[list[float]], dict[str, object]]:
    if not -40.0 <= lowering_degrees <= 40.0:
        raise ValueError("Arm rotation must be from -40 through 40 degrees.")
    posed = [vertex.copy() for vertex in vertices]
    side_evidence: dict[str, object] = {}
    for suffix, label, direction in (
        (".L", "positive_x_arm", 1.0),
        (".R", "negative_x_arm", -1.0),
    ):
        weights = arm_weights(len(vertices), weight_payload, suffix)
        pivot = shoulder_pivot(vertices, weights)
        angle = math.radians(lowering_degrees) * direction
        affected = 0
        maximum_displacement = 0.0
        for index, weight in enumerate(weights):
            if weight <= 0.0:
                continue
            blend = weight * weight * (3.0 - 2.0 * weight)
            rotated = rotate_about_y(vertices[index], pivot, angle)
            next_vertex = [
                vertices[index][axis] +
                (rotated[axis] - vertices[index][axis]) * blend
                for axis in range(3)
            ]
            displacement = math.dist(vertices[index], next_vertex)
            maximum_displacement = max(maximum_displacement, displacement)
            posed[index] = next_vertex
            affected += 1
        side_evidence[label] = {
            "rig_suffix": suffix,
            "shoulder_pivot_m": pivot,
            "affected_vertex_count": affected,
            "maximum_displacement_m": maximum_displacement,
        }
    return posed, side_evidence


def bounds(vertices: list[list[float]]) -> list[list[float]]:
    return [
        [min(vertex[axis] for vertex in vertices) for axis in range(3)],
        [max(vertex[axis] for vertex in vertices) for axis in range(3)],
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rig-weights", type=Path, required=True)
    parser.add_argument("--source-fit-report", type=Path)
    parser.add_argument(
        "--arm-lowering-degrees",
        type=float,
        default=22.0,
        help=(
            "Rotate both arms downward from the MPFB rest pose. Negative "
            "values raise the arms for collision-safe garment dressing."
        ),
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_path = args.output.resolve()
    rig_weights_path = args.rig_weights.resolve()
    vertices, lines = parse_obj(input_path)
    weight_payload = json.loads(rig_weights_path.read_text(encoding="utf-8"))
    posed, side_evidence = pose_relaxed_arms(
        vertices,
        weight_payload,
        args.arm_lowering_degrees,
    )
    original_bounds = bounds(vertices)
    posed_bounds = bounds(posed)
    # The raw MPFB export is Z-up. The GarmentCode preparation stage performs
    # the later axis conversion into its Y-up simulation space.
    floor_delta = posed_bounds[0][2] - original_bounds[0][2]
    center_x = (posed_bounds[0][0] + posed_bounds[1][0]) * 0.5
    accepted = abs(floor_delta) <= 0.0001 and abs(center_x) <= 0.002
    issues: list[str] = []
    if abs(floor_delta) > 0.0001:
        issues.append("The pose moved the body's floor datum.")
    if abs(center_x) > 0.002:
        issues.append("The pose broke left-right body symmetry.")

    write_obj(output_path, lines, posed)
    pose_name = (
        "raised-arm-dressing"
        if args.arm_lowering_degrees < 0.0
        else "relaxed-stand"
        if args.arm_lowering_degrees > 0.0
        else "source-rest-pose"
    )
    report = {
        "schema_version": "patterna.mpfb-body-pose/1.0",
        "accepted": accepted,
        "issues": issues,
        "method": "MPFB default-rig weighted shoulder rotation",
        "pose": pose_name,
        "arm_lowering_degrees": args.arm_lowering_degrees,
        "arm_rotation_degrees": args.arm_lowering_degrees,
        "source_body": str(input_path),
        "source_body_sha256": sha256(input_path),
        "source_fit_report": (
            str(args.source_fit_report.resolve())
            if args.source_fit_report is not None
            else None
        ),
        "source_fit_report_sha256": (
            sha256(args.source_fit_report.resolve())
            if args.source_fit_report is not None
            else None
        ),
        "rig_weights": str(rig_weights_path),
        "rig_weights_sha256": sha256(rig_weights_path),
        "output_body": str(output_path),
        "output_body_sha256": sha256(output_path),
        "vertex_count": len(vertices),
        "topology_preserved": True,
        "source_bounds_m": original_bounds,
        "posed_bounds_m": posed_bounds,
        "floor_delta_m": floor_delta,
        "posed_center_x_m": center_x,
        "sides": side_evidence,
    }
    report_path = output_path.with_suffix(".pose-report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not accepted:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
