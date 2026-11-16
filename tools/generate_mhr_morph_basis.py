#!/usr/bin/env python3
"""Generate a compact, hash-bound real-time morph basis for the packaged MHR body."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any

import numpy as np
import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.fit_mhr_identity import build_topologies, load_targets, scaled_to_height
from tools.fit_mhr_local_profile import (
    evaluate_measurements,
    fit_local_measurements,
    normalize_arm_forward_sweep,
    normalize_upper_arm_length,
    scaled_skeleton_state,
)
SCHEMA_VERSION = "patterna.mhr-morph-basis/1.0"
DISPLAY_AVATAR_SCHEMA = "patterna.display-avatar-glb/1.0"
VERTEX_MATCH_LIMIT_M = 0.000005

PARAMETERS: tuple[dict[str, Any], ...] = (
    {"avatarKey": "chest", "target": "bustCircumference", "minimum": 90.0, "maximum": 130.0},
    {"avatarKey": "chestDepth", "target": "bustDepth", "minimum": 24.0, "maximum": 36.0},
    {"avatarKey": "underBust", "target": "underbustCircumference", "minimum": 70.0, "maximum": 105.0},
    {"avatarKey": "underBustDepth", "target": "underbustDepth", "minimum": 18.0, "maximum": 29.0},
    {"avatarKey": "waist", "target": "waistCircumference", "minimum": 65.0, "maximum": 110.0},
    {"avatarKey": "waistDepth", "target": "waistDepth", "minimum": 16.0, "maximum": 28.0},
    {"avatarKey": "abdomenCirc", "target": "abdomenCircumference", "minimum": 70.0, "maximum": 120.0},
    {"avatarKey": "abdomenDepth", "target": "abdomenDepth", "minimum": 17.0, "maximum": 31.0},
    {"avatarKey": "hip", "target": "hipCircumference", "minimum": 90.0, "maximum": 135.0},
    {"avatarKey": "hipDepth", "target": "hipDepth", "minimum": 22.0, "maximum": 36.0},
    {
        "avatarKey": "upperArmCirc",
        "avatarSourceKeys": ["upperArmCircL", "upperArmCircR"],
        "aggregation": "mean",
        "target": "upperArmCircumference",
        "minimum": 22.0,
        "maximum": 40.0,
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--identity-json", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=32)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    if len(payload) < 20:
        raise ValueError("MHR GLB is too short.")
    magic, version, declared_length = struct.unpack_from("<4sII", payload)
    if magic != b"glTF" or version != 2 or declared_length != len(payload):
        raise ValueError("MHR GLB header is invalid.")
    document: dict[str, Any] | None = None
    binary: bytes | None = None
    offset = 12
    while offset < len(payload):
        length, chunk_type = struct.unpack_from("<II", payload, offset)
        offset += 8
        chunk = payload[offset : offset + length]
        offset += length
        if chunk_type == 0x4E4F534A:
            document = json.loads(chunk.decode("utf-8").rstrip("\x00 "))
        elif chunk_type == 0x004E4942:
            binary = chunk
    if document is None or binary is None:
        raise ValueError("MHR GLB must contain JSON and binary chunks.")
    return document, binary


def read_float_accessor(
    document: dict[str, Any], binary: bytes, accessor_index: int
) -> np.ndarray:
    accessor = document["accessors"][accessor_index]
    if accessor.get("componentType") != 5126 or accessor.get("type") != "VEC3":
        raise ValueError("MHR body POSITION accessor must be FLOAT VEC3.")
    view = document["bufferViews"][accessor["bufferView"]]
    stride = int(view.get("byteStride", 12))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    values = np.empty((int(accessor["count"]), 3), dtype=np.float64)
    for index in range(len(values)):
        values[index] = struct.unpack_from("<fff", binary, start + index * stride)
    return values


def glb_body_positions(
    document: dict[str, Any], binary: bytes, body_node_name: str
) -> np.ndarray:
    node = next(
        (candidate for candidate in document["nodes"] if candidate.get("name") == body_node_name),
        None,
    )
    if node is None or "mesh" not in node:
        raise ValueError(f"MHR GLB has no body mesh node named {body_node_name}.")
    primitives = document["meshes"][node["mesh"]].get("primitives", [])
    if len(primitives) != 1:
        raise ValueError("MHR morph contract requires one body primitive.")
    return read_float_accessor(document, binary, primitives[0]["attributes"]["POSITION"])


def spatial_key(point: np.ndarray) -> tuple[int, int, int]:
    return tuple(int(round(float(value) * 10_000.0)) for value in point)


def map_glb_vertices(
    glb_positions_m: np.ndarray, fitted_vertices_cm: np.ndarray
) -> tuple[np.ndarray, float]:
    fitted_m = fitted_vertices_cm / 100.0
    buckets: dict[tuple[int, int, int], list[int]] = {}
    for index, point in enumerate(fitted_m):
        buckets.setdefault(spatial_key(point), []).append(index)
    mapping = np.empty(len(glb_positions_m), dtype=np.int64)
    maximum_error = 0.0
    for index, point in enumerate(glb_positions_m):
        key = spatial_key(point)
        candidates = [
            candidate
            for offset in itertools.product((-1, 0, 1), repeat=3)
            for candidate in buckets.get(
                (key[0] + offset[0], key[1] + offset[1], key[2] + offset[2]),
                [],
            )
        ]
        if not candidates:
            raise ValueError(f"MHR GLB vertex {index} has no fitted-source match.")
        distances = np.linalg.norm(fitted_m[candidates] - point, axis=1)
        best = int(np.argmin(distances))
        mapping[index] = candidates[best]
        maximum_error = max(maximum_error, float(distances[best]))
    if maximum_error > VERTEX_MATCH_LIMIT_M:
        raise ValueError(
            f"MHR GLB vertex mapping drift {maximum_error:.9f} m exceeds {VERTEX_MATCH_LIMIT_M:.9f} m."
        )
    return mapping, maximum_error


def display_delta(
    delta_m: np.ndarray, display_yaw_degrees: float
) -> np.ndarray:
    yaw = math.radians(display_yaw_degrees)
    cosine = math.cos(yaw)
    sine = math.sin(yaw)
    result = np.empty_like(delta_m, dtype=np.float32)
    result[:, 0] = (delta_m[:, 0] * cosine + delta_m[:, 2] * sine) * 2.0
    result[:, 1] = delta_m[:, 1] * 2.0
    result[:, 2] = (-delta_m[:, 0] * sine + delta_m[:, 2] * cosine) * 2.0
    return result


def fit_target(
    normalized_vertices_cm: np.ndarray,
    faces: np.ndarray,
    targets: dict[str, float],
    iterations: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    fitted, report = fit_local_measurements(
        normalized_vertices_cm,
        faces,
        targets,
        iterations=iterations,
    )
    if report["status"] != "accepted":
        rejected = report["acceptance"]["rejectedMeasurements"]
        raise ValueError(f"MHR morph endpoint failed its fit gate: {rejected}")
    return fitted, report


def main() -> None:
    args = parse_args()
    profile_path = args.profile.resolve()
    model_path = args.model.resolve()
    identity_path = args.identity_json.resolve()
    geometry_path = args.geometry.resolve()
    manifest_path = args.manifest.resolve()
    output_path = args.output.resolve()
    if args.iterations < 1:
        raise ValueError("MHR morph generation requires at least one iteration.")

    display_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if display_manifest.get("schemaVersion") != DISPLAY_AVATAR_SCHEMA:
        raise ValueError("MHR display manifest has an unsupported schema.")
    target_height_cm, baseline_targets = load_targets(profile_path)
    identity = np.asarray(json.loads(identity_path.read_text(encoding="utf-8")), dtype=np.float32)
    if identity.shape != (45,) or not np.isfinite(identity).all():
        raise ValueError("MHR morph identity must contain 45 finite coefficients.")

    model = torch.jit.load(str(model_path), map_location="cpu")
    model.eval()
    with torch.no_grad():
        vertices, skeleton_state = model(
            torch.from_numpy(identity).reshape(1, -1),
            torch.zeros((1, 204), dtype=torch.float32),
            torch.zeros((1, 72), dtype=torch.float32),
            True,
        )
    source_vertices_cm = vertices[0].cpu().numpy().astype(np.float64)
    fitted_rig_state = scaled_skeleton_state(
        skeleton_state[0].cpu().numpy(), source_vertices_cm, target_height_cm
    )
    scaled = scaled_to_height(vertices, target_height_cm)[0].cpu().numpy().astype(np.float64)
    faces = model.character_torch.mesh.faces.cpu().numpy().astype(np.int64)
    swept, fitted_rig_state, sweep_report = normalize_arm_forward_sweep(
        scaled, fitted_rig_state
    )
    normalized, _, length_report = normalize_upper_arm_length(swept, fitted_rig_state)
    if not sweep_report["accepted"] or not length_report["accepted"]:
        raise ValueError("MHR anatomy normalization failed before morph generation.")

    baseline_vertices, baseline_report = fit_target(
        normalized, faces, baseline_targets, args.iterations
    )
    document, binary = read_glb(geometry_path)
    glb_positions_m = glb_body_positions(
        document, binary, str(display_manifest["primaryBodyNode"])
    )
    glb_to_source, mapping_error_m = map_glb_vertices(
        glb_positions_m, baseline_vertices
    )
    topologies = build_topologies(normalized, faces)
    baseline_measurements = evaluate_measurements(baseline_vertices, topologies)
    yaw = float(display_manifest["displayYawDegrees"])

    binary_parts: list[np.ndarray] = []
    parameter_reports: list[dict[str, Any]] = []
    float_offset = 0
    for contract in PARAMETERS:
        target_name = str(contract["target"])
        baseline_value = float(baseline_targets[target_name])
        endpoint_reports: dict[str, Any] = {}
        endpoint_offsets: dict[str, int] = {}
        for endpoint_name, endpoint_value in (
            ("minimum", float(contract["minimum"])),
            ("maximum", float(contract["maximum"])),
        ):
            targets = dict(baseline_targets)
            targets[target_name] = endpoint_value
            endpoint_vertices, endpoint_report = fit_target(
                normalized, faces, targets, args.iterations
            )
            source_delta_m = (endpoint_vertices - baseline_vertices) / 100.0
            glb_delta = source_delta_m[glb_to_source]
            transformed = display_delta(glb_delta, yaw).reshape(-1)
            endpoint_offsets[endpoint_name] = float_offset
            float_offset += int(transformed.size)
            binary_parts.append(transformed)
            measured = evaluate_measurements(endpoint_vertices, topologies)
            endpoint_reports[endpoint_name] = {
                "requestedCm": endpoint_value,
                "measuredCm": measured[target_name],
                "absoluteResidualCm": abs(measured[target_name] - endpoint_value),
                "maximumSurfaceDeltaCm": float(
                    np.linalg.norm(endpoint_vertices - baseline_vertices, axis=1).max()
                ),
                "fitIterations": endpoint_report["iterationsCompleted"],
            }
        parameter_reports.append(
            {
                **contract,
                "baseline": baseline_value,
                "minimumFloatOffset": endpoint_offsets["minimum"],
                "maximumFloatOffset": endpoint_offsets["maximum"],
                "floatCount": int(len(glb_positions_m) * 3),
                "endpoints": endpoint_reports,
            }
        )

    payload = np.concatenate(binary_parts).astype("<f4", copy=False).tobytes()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_bytes(payload)
    temporary_path.replace(output_path)

    basis = {
        "schemaVersion": SCHEMA_VERSION,
        "accepted": False,
        "previewOnly": True,
        "validationScope": "independent endpoint interpolation for declared measurements only; compound behavior is unproven",
        "file": output_path.name,
        "bytes": len(payload),
        "sha256": sha256(output_path),
        "floatEncoding": "little-endian-float32",
        "vertexCount": int(len(glb_positions_m)),
        "sourceVertexCount": int(len(baseline_vertices)),
        "floatsPerEndpoint": int(len(glb_positions_m) * 3),
        "baselineHeightCm": target_height_cm,
        "baseGeometrySha256": sha256(geometry_path),
        "baseProfileSha256": sha256(profile_path),
        "identitySha256": sha256(identity_path),
        "modelSha256": sha256(model_path),
        "maximumGlbVertexMappingErrorM": mapping_error_m,
        "baselineMaximumMeasurementResidualCm": max(
            abs(baseline_measurements[name] - target)
            for name, target in baseline_targets.items()
        ),
        "parameters": parameter_reports,
        "limitations": [
            "parameters are interpolated independently and combined additively",
            "values outside each declared preview range are not represented",
            "hair, eyes, and modesty assets receive height scaling but not local body fitting",
            "preview acceptance does not prove cloth, product appearance, or a simulation collider",
        ],
    }
    display_manifest["morphBasis"] = basis
    display_manifest["openGates"] = [
        "real-time MHR morph preview is not a revision-specific fitted collider"
        if gate == "measurement edits do not yet rebuild this MHR family in the packaged app"
        else gate
        for gate in display_manifest.get("openGates", [])
    ]
    manifest_temporary_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    manifest_temporary_path.write_text(
        json.dumps(display_manifest, indent=2) + "\n", encoding="utf-8"
    )
    manifest_temporary_path.replace(manifest_path)
    print(json.dumps(basis, indent=2))


if __name__ == "__main__":
    main()
