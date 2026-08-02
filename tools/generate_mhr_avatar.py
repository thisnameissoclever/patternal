#!/usr/bin/env python3
"""Generate a Patterna avatar from Meta's Momentum Human Rig TorchScript model.

MHR uses centimeters with X horizontal, Y vertical, and Z depth. Patterna's
GarmentCode collision contract uses the same coordinate convention. A second
OBJ is emitted in Blender meters with Z vertical for deterministic previews.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = REPO_ROOT / ".runtime/mhr-v1.0.1/assets/mhr_model.pt"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts/mhr-avatar-proof-v1"
IDENTITY_COEFFICIENT_COUNT = 45
MODEL_PARAMETER_COUNT = 204
FACE_EXPRESSION_COUNT = 72


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--identity-json",
        type=Path,
        help="Optional JSON array containing 45 MHR identity coefficients.",
    )
    parser.add_argument(
        "--identity-coefficient",
        action="append",
        default=[],
        metavar="INDEX=VALUE",
        help="Override one MHR identity coefficient. May be supplied repeatedly.",
    )
    parser.add_argument(
        "--target-height-cm",
        type=float,
        help="Uniformly scale the generated identity to this standing height.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_identity(path: Path | None) -> np.ndarray:
    if path is None:
        return np.zeros(IDENTITY_COEFFICIENT_COUNT, dtype=np.float32)
    values = np.asarray(json.loads(path.read_text(encoding="utf-8")), dtype=np.float32)
    if values.shape != (IDENTITY_COEFFICIENT_COUNT,):
        raise ValueError(
            f"MHR identity must contain {IDENTITY_COEFFICIENT_COUNT} values, "
            f"received shape {values.shape}."
        )
    if not np.isfinite(values).all():
        raise ValueError("MHR identity contains a non-finite value.")
    return values


def apply_identity_overrides(
    identity: np.ndarray, overrides: list[str]
) -> np.ndarray:
    result = identity.copy()
    for override in overrides:
        try:
            index_text, value_text = override.split("=", maxsplit=1)
            index = int(index_text)
            value = float(value_text)
        except ValueError as error:
            raise ValueError(
                f"Invalid MHR identity override {override!r}; expected INDEX=VALUE."
            ) from error
        if index < 0 or index >= IDENTITY_COEFFICIENT_COUNT:
            raise ValueError(f"MHR identity coefficient index is out of range: {index}")
        if not np.isfinite(value):
            raise ValueError("MHR identity override must be finite.")
        result[index] = value
    return result


def evaluate_model(
    model_path: Path, identity: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    model = torch.jit.load(str(model_path), map_location="cpu")
    model.eval()
    identity_tensor = torch.from_numpy(identity).reshape(1, -1)
    model_parameters = torch.zeros((1, MODEL_PARAMETER_COUNT), dtype=torch.float32)
    expressions = torch.zeros((1, FACE_EXPRESSION_COUNT), dtype=torch.float32)
    with torch.no_grad():
        vertices, _ = model(identity_tensor, model_parameters, expressions, True)

    mesh = model.character_torch.mesh
    return (
        vertices[0].cpu().numpy().astype(np.float64),
        mesh.faces.cpu().numpy().astype(np.int64),
        mesh.texcoords.cpu().numpy().astype(np.float64),
        mesh.texcoord_faces.cpu().numpy().astype(np.int64),
    )


def write_obj(
    path: Path,
    vertices: np.ndarray,
    faces: np.ndarray,
    texture_coordinates: np.ndarray,
    texture_faces: np.ndarray,
    *,
    reverse_winding: bool,
) -> None:
    if faces.shape != texture_faces.shape:
        raise ValueError("MHR position and texture face arrays do not match.")
    order = (2, 1, 0) if reverse_winding else (0, 1, 2)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        output.write("# Patterna MHR LOD1 body\n")
        for x, y, z in vertices:
            output.write(f"v {x:.9f} {y:.9f} {z:.9f}\n")
        for u, v in texture_coordinates:
            output.write(f"vt {u:.9f} {v:.9f}\n")
        for face, texture_face in zip(faces, texture_faces, strict=True):
            corners = [
                f"{int(face[index]) + 1}/{int(texture_face[index]) + 1}"
                for index in order
            ]
            output.write("f " + " ".join(corners) + "\n")


def to_blender_meters(vertices_cm: np.ndarray) -> np.ndarray:
    """Map MHR X-right/Y-up/Z-back centimeters to Blender Z-up meters."""
    converted = vertices_cm[:, (0, 2, 1)].copy() / 100.0
    converted[:, 1] *= -1.0
    return converted


def scale_to_height(vertices_cm: np.ndarray, target_height_cm: float | None) -> np.ndarray:
    if target_height_cm is None:
        return vertices_cm
    if not np.isfinite(target_height_cm) or target_height_cm <= 0.0:
        raise ValueError("MHR target height must be a positive finite value.")
    current_height = float(vertices_cm[:, 1].max() - vertices_cm[:, 1].min())
    if current_height <= 0.0:
        raise ValueError("MHR body has no measurable standing height.")
    return vertices_cm * (target_height_cm / current_height)


def main() -> None:
    args = parse_args()
    model_path = args.model.resolve()
    output_directory = args.output_directory.resolve()
    identity_path = args.identity_json.resolve() if args.identity_json else None
    if not model_path.is_file():
        raise FileNotFoundError(f"MHR TorchScript model not found: {model_path}")

    identity = apply_identity_overrides(
        load_identity(identity_path), args.identity_coefficient
    )
    vertices_cm, faces, texture_coordinates, texture_faces = evaluate_model(
        model_path, identity
    )
    vertices_cm = scale_to_height(vertices_cm, args.target_height_cm)
    if vertices_cm.shape != (18439, 3):
        raise ValueError(f"Unexpected MHR LOD1 vertex shape: {vertices_cm.shape}")
    if not np.isfinite(vertices_cm).all():
        raise ValueError("MHR generated non-finite vertex coordinates.")

    output_directory.mkdir(parents=True, exist_ok=True)
    collision_path = output_directory / "avatar-mhr-garmentcode-cm.obj"
    preview_path = output_directory / "avatar-mhr-blender-m.obj"
    identity_output_path = output_directory / "identity-coefficients.json"
    report_path = output_directory / "avatar-report.json"

    write_obj(
        collision_path,
        vertices_cm,
        faces,
        texture_coordinates,
        texture_faces,
        reverse_winding=False,
    )
    write_obj(
        preview_path,
        to_blender_meters(vertices_cm),
        faces,
        texture_coordinates,
        texture_faces,
        reverse_winding=False,
    )
    identity_output_path.write_text(
        json.dumps(identity.tolist(), indent=2) + "\n", encoding="utf-8"
    )

    minimum = vertices_cm.min(axis=0)
    maximum = vertices_cm.max(axis=0)
    report = {
        "schemaVersion": "patterna.mhr-avatar-proof/1.0",
        "status": "generated-not-measurement-fitted",
        "source": {
            "name": "Meta Momentum Human Rig",
            "version": "1.0.1",
            "lod": 1,
            "modelPath": str(model_path),
            "modelSha256": sha256(model_path),
        },
        "topology": {
            "vertexCount": int(vertices_cm.shape[0]),
            "triangleCount": int(faces.shape[0]),
            "textureCoordinateCount": int(texture_coordinates.shape[0]),
        },
        "boundsCm": {
            "minimum": minimum.tolist(),
            "maximum": maximum.tolist(),
            "height": float(maximum[1] - minimum[1]),
        },
        "identity": {
            "coefficientCount": IDENTITY_COEFFICIENT_COUNT,
            "minimum": float(identity.min()),
            "maximum": float(identity.max()),
            "l2Norm": float(np.linalg.norm(identity)),
        },
        "requestedHeightCm": args.target_height_cm,
        "outputs": {
            "collisionObj": str(collision_path),
            "collisionObjSha256": sha256(collision_path),
            "previewObj": str(preview_path),
            "previewObjSha256": sha256(preview_path),
            "identityJson": str(identity_output_path),
        },
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
