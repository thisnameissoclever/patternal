#!/usr/bin/env python3
"""Pose the fitted Anny body into a declared dressing stance and export it.

A garment is assembled around a body by staging flat panels beside it, so the
body must hold a stance that keeps the arms clear of the torso panels. Anny's
rest stance hangs the arms down and forward, straight through the plane where a
shirt's front panel stages, which is why the arrangement plan's own preflight
gates refuse to build against the rest body.

This tool re-evaluates the same fitted shape from an accepted avatar-worker
output, rotates each upper-arm bone until its axis reaches a declared stance,
and exports the posed collision surface. The shape parameters are unchanged:
only the pose differs, and the stance is searched against the resulting bone
geometry rather than guessed.

The stance is two angles, not one. Elevation is how far the arm rises above the
horizontal plane; azimuth is how far it swings forward of the line through both
shoulders. Solving elevation alone leaves the arm horizontal but still swung
forward wherever the rest pose left it, which is not a stance any garment is
drafted for, so both are driven to their targets together.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-run", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--target-elevation-degrees",
        type=float,
        default=0.0,
        help="Arm axis elevation above the horizontal plane.",
    )
    parser.add_argument(
        "--target-azimuth-degrees",
        type=float,
        default=0.0,
        help="Arm axis swing forward of the line through both shoulders.",
    )
    parser.add_argument(
        "--stance-tolerance-degrees",
        type=float,
        default=0.5,
        help="How close both stance angles must come to their targets.",
    )
    return parser.parse_args()


def install_network_guard() -> None:
    import socket

    def denied(*_args, **_kwargs):
        raise RuntimeError("Outbound network access is disabled for Anny posing.")

    class DeniedSocket(socket.socket):
        def connect(self, *args, **kwargs):
            return denied()

        def connect_ex(self, *args, **kwargs):
            return denied()

    socket.socket = DeniedSocket
    socket.create_connection = denied
    socket.getaddrinfo = denied


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    arguments = parse_arguments()
    cache_dir = arguments.cache_dir.resolve()
    os.environ["ANNY_CACHE_DIR"] = str(cache_dir / "anny")
    os.environ["WARP_CACHE_PATH"] = str(cache_dir / "warp")
    install_network_guard()

    import numpy as np
    import torch
    import anny

    repository_root = Path(__file__).resolve().parents[1]
    for entry in (str(repository_root), str(repository_root / "tools")):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    from anny_worker_outputs import largest_component

    fit_report = json.loads(
        (arguments.worker_run / "anny-fit-report.json").read_text(encoding="utf-8")
    )
    torch.manual_seed(int(fit_report["seed"]))
    model = anny.Anny(
        phenotypes="all", local_changes="all", facial_actions="all"
    ).to(dtype=torch.float64, device="cpu")
    bone_labels = [str(label) for label in model.bone_labels]

    phenotype = dict(fit_report["basePhenotype"])
    phenotype.update(fit_report["directPhenotype"])
    local: dict[str, float] = dict(fit_report["directLocalChanges"])
    for full, value in fit_report["fittedParameters"].items():
        family, label = full.split(":", 1)
        if family == "phenotype":
            phenotype[label] = value
        else:
            local[label] = value

    def evaluate(pose: torch.Tensor | None) -> dict:
        with torch.no_grad():
            output = model(
                pose_parameters=pose,
                phenotype_kwargs=phenotype,
                local_changes_kwargs=local,
            )
        # rest_bone_heads is pose-invariant, so the posed bone positions must
        # come from the pose transforms' translation column.
        posed_heads = (output["bone_poses"][0][:, :3, 3] * 100.0).numpy()
        return {
            "vertices": (output["vertices"][0] * 100.0).numpy(),
            "boneHeads": posed_heads,
        }

    def identity_pose() -> torch.Tensor:
        return torch.eye(4, dtype=torch.float64)[None, None].repeat(
            1, model.bone_count, 1, 1
        )

    def axis_angle_rotation(vector: np.ndarray) -> torch.Tensor:
        """Rodrigues rotation for an axis-angle vector, as a 4x4 bone pose."""
        matrix = torch.eye(4, dtype=torch.float64)
        angle = float(np.linalg.norm(vector))
        if angle < 1.0e-12:
            return matrix
        unit = vector / angle
        cross = np.array(
            [
                [0.0, -unit[2], unit[1]],
                [unit[2], 0.0, -unit[0]],
                [-unit[1], unit[0], 0.0],
            ]
        )
        rotation = (
            np.eye(3)
            + math.sin(angle) * cross
            + (1.0 - math.cos(angle)) * (cross @ cross)
        )
        matrix[:3, :3] = torch.tensor(rotation, dtype=torch.float64)
        return matrix

    # Anny's frame is Z-up with x across the shoulders and y along the body's
    # depth, so an arm's elevation is its rise out of the xy plane and its
    # azimuth is its swing off the x axis within that plane. The left arm runs
    # toward +x and the right toward -x, so the right side's lateral reference
    # is negated to keep both angles signed the same way.
    def arm_stance(bone_heads: np.ndarray, side: str) -> tuple[float, float]:
        shoulder = bone_heads[bone_labels.index(f"upperarm01.{side}")]
        wrist = bone_heads[bone_labels.index(f"wrist.{side}")]
        direction = wrist - shoulder
        lateral = direction[0] if side == "L" else -direction[0]
        horizontal = math.hypot(lateral, direction[1])
        elevation = math.degrees(math.atan2(direction[2], horizontal))
        azimuth = math.degrees(math.atan2(direction[1], lateral))
        return elevation, azimuth

    rest = evaluate(None)
    rest_stance = {side: arm_stance(rest["boneHeads"], side) for side in ("L", "R")}
    target = np.array(
        [arguments.target_elevation_degrees, arguments.target_azimuth_degrees]
    )

    def solve_arm(side: str) -> dict:
        """Gauss-Newton on the shoulder rotation until both angles hit target."""
        bone_index = bone_labels.index(f"upperarm01.{side}")

        def stance_for(vector: np.ndarray) -> np.ndarray:
            pose = identity_pose()
            pose[0, bone_index] = axis_angle_rotation(vector)
            return np.array(arm_stance(evaluate(pose)["boneHeads"], side))

        vector = np.zeros(3)
        stance = np.array(rest_stance[side])
        step = math.radians(4.0)
        history: list[dict] = []
        for _ in range(24):
            residual = target - stance
            if np.max(np.abs(residual)) < arguments.stance_tolerance_degrees:
                break
            jacobian = np.zeros((2, 3))
            for column in range(3):
                probe = vector.copy()
                probe[column] += step
                jacobian[:, column] = (stance_for(probe) - stance) / step
            # Three rotation parameters answer two angles, so take the
            # minimum-norm step and damp it: the smallest rotation that
            # satisfies the stance is the one that disturbs the shape least.
            normal = jacobian @ jacobian.T + 1.0e-6 * np.eye(2)
            delta = jacobian.T @ np.linalg.solve(normal, residual)
            magnitude = float(np.linalg.norm(delta))
            limit = math.radians(25.0)
            if magnitude > limit:
                delta *= limit / magnitude
            vector = vector + delta
            stance = stance_for(vector)
            history.append(
                {
                    "elevationDegrees": float(stance[0]),
                    "azimuthDegrees": float(stance[1]),
                }
            )
        residual = target - stance
        if np.max(np.abs(residual)) >= arguments.stance_tolerance_degrees:
            raise ValueError(
                f"The {side} arm stance did not converge: reached elevation "
                f"{stance[0]:.2f} and azimuth {stance[1]:.2f} degrees."
            )
        return {
            "boneIndex": bone_index,
            "rotationVectorRadians": [float(value) for value in vector],
            "rotationMagnitudeDegrees": math.degrees(float(np.linalg.norm(vector))),
            "achievedElevationDegrees": float(stance[0]),
            "achievedAzimuthDegrees": float(stance[1]),
            "iterations": len(history),
        }

    search = {side: solve_arm(side) for side in ("L", "R")}

    pose = identity_pose()
    for found in search.values():
        pose[0, found["boneIndex"]] = axis_angle_rotation(
            np.asarray(found["rotationVectorRadians"])
        )
    posed = evaluate(pose)
    vertices = posed["vertices"]
    floor = float(vertices[:, 2].min())
    vertices = vertices.copy()
    vertices[:, 2] -= floor
    faces = np.asarray(model.faces, dtype=np.int64)
    body = largest_component(vertices, faces)

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Patterna Anny dressing-pose collider (Z-up centimeters)\n")
        for vertex in body["vertices"]:
            stream.write(f"v {vertex[0]:.9g} {vertex[1]:.9g} {vertex[2]:.9g}\n")
        for face in body["faces"]:
            stream.write(f"f {face[0] + 1} {face[1] + 1} {face[2] + 1}\n")

    report = {
        "schemaVersion": "patterna.anny-dressing-pose/1.0",
        "claims": {"accepted": False, "colliderAccepted": False, "poseAccepted": False},
        "sourceWorkerRun": str(arguments.worker_run),
        "sourceMeshSha256": fit_report["meshSha256"],
        "targetElevationDegrees": arguments.target_elevation_degrees,
        "targetAzimuthDegrees": arguments.target_azimuth_degrees,
        "stanceToleranceDegrees": arguments.stance_tolerance_degrees,
        "restArmStanceDegrees": {
            side: {"elevation": values[0], "azimuth": values[1]}
            for side, values in rest_stance.items()
        },
        "search": search,
        "shapeParametersUnchanged": True,
        "posedVertexCount": int(body["vertices"].shape[0]),
        "posedTriangleCount": int(body["faces"].shape[0]),
        "watertight": body["watertight"],
        "componentCount": body["componentCount"],
        "outputSha256": sha256_file(arguments.output),
    }
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "restStance": {
                    side: [round(values[0], 1), round(values[1], 1)]
                    for side, values in rest_stance.items()
                },
                "achievedStance": {
                    side: [
                        round(found["achievedElevationDegrees"], 2),
                        round(found["achievedAzimuthDegrees"], 2),
                    ]
                    for side, found in search.items()
                },
                "watertight": body["watertight"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
