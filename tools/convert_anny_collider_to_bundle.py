#!/usr/bin/env python3
"""Convert an accepted Anny worker collider into the revision-bundle frame.

The Anny worker writes its collision mesh in centimeters, Z-up, with the floor
at z=0 and the anatomical front along ``frontSign * y``. Revision bundles carry
their collider in meters, Y-up, with the floor at y=0 and the anatomical front
along +z. The map ``(x, y, z) -> (x, z, frontSign * y) / 100`` is a rotation
with determinant +1, so triangle winding and surface orientation are preserved
and no vertex is moved relative to any other.

The conversion reads the Anny output through its own immutable manifest, so it
cannot silently consume a stale or unverified mesh. It produces geometry only
and makes no acceptance claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-output", type=Path)
    parser.add_argument(
        "--posed-collider",
        type=Path,
        help="A posed collider written by pose_anny_dressing_body.py.",
    )
    parser.add_argument("--pose-report", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("v "):
                parts = line.split()
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif line.startswith("f "):
                parts = line.split()
                faces.append([int(part.split("/")[0]) - 1 for part in parts[1:4]])
    return np.asarray(vertices, dtype=np.float64), np.asarray(faces, dtype=np.int64)


def role_file(worker_output: Path, manifest: dict, role: str) -> Path:
    matches = [entry for entry in manifest["files"] if entry.get("role") == role]
    if len(matches) != 1:
        raise ValueError(f"The worker output must contain exactly one {role}.")
    entry = matches[0]
    path = worker_output / entry["bundlePath"]
    if path.stat().st_size != entry["byteLength"]:
        raise ValueError(f"Worker output {role} byte length changed.")
    if sha256_file(path) != entry["sha256"]:
        raise ValueError(f"Worker output {role} hash changed.")
    return path


def main() -> int:
    arguments = parse_arguments()
    if arguments.posed_collider is not None:
        if arguments.pose_report is None:
            raise ValueError("A posed collider requires its pose report.")
        pose_report = json.loads(
            arguments.pose_report.resolve(strict=True).read_text(encoding="utf-8")
        )
        if pose_report.get("schemaVersion") != "patterna.anny-dressing-pose/1.0":
            raise ValueError("Unsupported dressing pose report schema.")
        collider_path = arguments.posed_collider.resolve(strict=True)
        if sha256_file(collider_path) != pose_report["outputSha256"]:
            raise ValueError("The posed collider does not match its pose report.")
        source_identity = {
            "poseReportSourceRun": pose_report["sourceWorkerRun"],
            "poseTargetElevationDegrees": pose_report["targetElevationDegrees"],
        }
        landmarks_path = (
            Path(pose_report["sourceWorkerRun"]) / "landmarks.json"
        )
        front_sign = float(
            json.loads(landmarks_path.read_text(encoding="utf-8"))["frontSign"]
        )
    else:
        worker_output = arguments.worker_output.resolve(strict=True)
        manifest = json.loads(
            (worker_output / "avatar-worker-output-manifest.json").read_text(encoding="utf-8")
        )
        if manifest["claims"]["producerAccepted"] is not False:
            raise ValueError("A producer-accepted avatar output is not expected here.")
        collider_path = role_file(worker_output, manifest, "collisionMesh")
        landmarks = json.loads(
            role_file(worker_output, manifest, "landmarks").read_text(encoding="utf-8")
        )
        front_sign = float(landmarks["frontSign"])
        source_identity = {"sourceOutputId": manifest["outputId"]}
    if front_sign not in (1.0, -1.0):
        raise ValueError("The landmarks front sign must be exactly +1 or -1.")

    vertices, faces = read_obj(collider_path)
    converted = np.column_stack(
        [
            vertices[:, 0],
            vertices[:, 2],
            front_sign * vertices[:, 1],
        ]
    ) * 0.01

    floor = float(converted[:, 1].min())
    if abs(floor) > 1.0e-9:
        converted[:, 1] -= floor

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Patterna Anny collider in revision-bundle frame (Y-up meters)\n")
        for vertex in converted:
            stream.write(f"v {vertex[0]:.9g} {vertex[1]:.9g} {vertex[2]:.9g}\n")
        for face in faces:
            stream.write(f"f {face[0] + 1} {face[1] + 1} {face[2] + 1}\n")

    report = {
        "schemaVersion": "patterna.anny-collider-conversion/1.0",
        "claims": {"accepted": False, "colliderAccepted": False},
        **source_identity,
        "sourceColliderSha256": sha256_file(collider_path),
        "frontSign": front_sign,
        "transform": "(x, y, z) centimeters Z-up maps to (x, z, frontSign * y) / 100 meters Y-up",
        "determinant": 1.0,
        "vertexCount": int(converted.shape[0]),
        "triangleCount": int(faces.shape[0]),
        "boundsMeters": {
            "minimum": [float(value) for value in converted.min(axis=0)],
            "maximum": [float(value) for value in converted.max(axis=0)],
        },
        "statureMeters": float(converted[:, 1].max() - converted[:, 1].min()),
        "outputSha256": sha256_file(arguments.output),
    }
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "statureMeters": round(report["statureMeters"], 4),
                "vertices": report["vertexCount"],
                "triangles": report["triangleCount"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
