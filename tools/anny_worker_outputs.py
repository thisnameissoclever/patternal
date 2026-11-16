"""Output-stage artifact production for the Anny avatar worker.

Consumes the fitted body and produces every raw artifact the immutable
avatar-worker output requires: display mesh, watertight collision mesh,
display-to-collider map, control application report, landmarks, measurements,
collider registration evidence, rejection list, and the thirteen fixed review
renders through a fresh Blender process. Every file keeps producer acceptance
false; wrapping into the immutable output happens in ``avatar_worker_output``.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import numpy as np


DECLARED_TOLERANCES_CM = {
    "circumference": 1.5,
    "distance": 1.5,
    "length": 1.5,
    "height": 1.5,
    "depth": 1.5,
    "width": 1.5,
    "projection": 1.0,
    "arc-length": 2.0,
    "stature": 1.0,
}


def vertex_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    normals = np.zeros_like(vertices)
    triangles = vertices[faces]
    face_normals = np.cross(
        triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    )
    for corner in range(3):
        np.add.at(normals, faces[:, corner], face_normals)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0.0] = 1.0
    return normals / lengths


def write_obj(
    path: Path,
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    material_name: str,
) -> None:
    normals = vertex_normals(vertices, faces)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Patterna Anny worker artifact (Z-up centimeters, floor at z=0)\n")
        stream.write(f"usemtl {material_name}\n")
        for vertex in vertices:
            stream.write(f"v {vertex[0]:.8f} {vertex[1]:.8f} {vertex[2]:.8f}\n")
        for normal in normals:
            stream.write(f"vn {normal[0]:.6f} {normal[1]:.6f} {normal[2]:.6f}\n")
        for face in faces:
            a, b, c = (int(index) + 1 for index in face)
            stream.write(f"f {a}//{a} {b}//{b} {c}//{c}\n")


def connected_component_labels(vertex_count: int, faces: np.ndarray) -> np.ndarray:
    """Union-find vertex component labels without scipy."""
    parent = np.arange(vertex_count, dtype=np.int64)

    def find(index: int) -> int:
        root = index
        while parent[root] != root:
            root = parent[root]
        while parent[index] != root:
            parent[index], index = root, parent[index]
        return root

    for a, b, c in faces:
        ra, rb, rc = find(int(a)), find(int(b)), find(int(c))
        parent[rb] = ra
        parent[find(int(rc))] = find(int(ra))
    labels = np.fromiter((find(int(i)) for i in range(vertex_count)), dtype=np.int64)
    return labels


def edge_manifold_watertight(faces: np.ndarray) -> bool:
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    edges = np.sort(edges, axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return bool((counts == 2).all())


def signed_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    triangles = vertices[faces]
    return float(
        np.einsum(
            "ij,ij->i",
            triangles[:, 0],
            np.cross(triangles[:, 1], triangles[:, 2]),
        ).sum()
        / 6.0
    )


def largest_component(vertices: np.ndarray, faces: np.ndarray):
    labels = connected_component_labels(len(vertices), faces)
    component_ids, component_sizes = np.unique(labels, return_counts=True)
    body_label = component_ids[int(np.argmax(component_sizes))]
    keep_vertices = np.flatnonzero(labels == body_label)
    remap = -np.ones(len(vertices), dtype=np.int64)
    remap[keep_vertices] = np.arange(keep_vertices.size)
    face_keep = (labels[faces[:, 0]] == body_label)
    body_faces = remap[faces[face_keep]]
    body_vertices = vertices[keep_vertices]
    if signed_volume(body_vertices, body_faces) < 0.0:
        body_faces = body_faces[:, ::-1].copy()
    return {
        "componentCount": int(component_ids.size),
        "vertices": body_vertices,
        "faces": body_faces,
        "displayVertexIndices": keep_vertices,
        "watertight": edge_manifold_watertight(body_faces),
    }


def produce_outputs(
    *,
    output: Path,
    vertices_cm: np.ndarray,
    faces: np.ndarray,
    bone_labels: list[str],
    bone_heads_cm: np.ndarray,
    context: dict[str, Any],
    fit_report: dict[str, Any],
    control_map: dict[str, Any],
    source_rows: dict[str, dict[str, Any]],
    identity: dict[str, str],
    blender_path: Path,
    render_script: Path,
) -> dict[str, Any]:
    floor = float(vertices_cm[:, 2].min())
    display_vertices = vertices_cm.copy()
    display_vertices[:, 2] -= floor
    heads = bone_heads_cm.copy()
    heads[:, 2] -= floor

    display_path = output / "display-mesh.obj"
    write_obj(display_path, display_vertices, faces, material_name="anny-body")

    body = largest_component(display_vertices, faces)
    collider_path = output / "collision-mesh.obj"
    write_obj(
        collider_path,
        np.asarray(body["vertices"], dtype=np.float64),
        np.asarray(body["faces"], dtype=np.int64),
        material_name="anny-collider",
    )

    display_to_collider = [int(index) for index in body["displayVertexIndices"]]
    collider_map = {
        "schemaVersion": "patterna.anny-display-collider-map/1.0",
        **identity,
        "displayVertexCount": int(display_vertices.shape[0]),
        "colliderVertexCount": int(body["vertices"].shape[0]),
        "colliderTriangleCount": int(body["faces"].shape[0]),
        "colliderIsWatertight": body["watertight"],
        "displayVertexForColliderVertex": display_to_collider,
        "claims": {"accepted": False},
    }
    (output / "display-to-collider-map.json").write_text(
        json.dumps(collider_map) + "\n", encoding="utf-8"
    )

    marks = context["marks"]
    landmark_positions = {
        label: [float(value) for value in heads[index]]
        for index, label in enumerate(bone_labels)
    }
    stations_cm = {
        name: {"heightCm": float(entry["heightCm"]) - floor}
        for name, entry in context["stations"].items()
        if "heightCm" in entry
    }
    landmarks = {
        "schemaVersion": "patterna.anny-worker-landmarks/1.0",
        **identity,
        "convention": "Z-up centimeters, floor at z=0, front is positive Y times frontSign",
        "frontSign": context["front"],
        "rig": {"boneCount": len(bone_labels), "boneHeadsCm": landmark_positions},
        "stations": stations_cm,
        "bustApexVertices": {
            "left": int(context["apex_left"]),
            "right": int(context["apex_right"]),
        },
        "pose": "anny rest pose declared as the balanced neutral stance",
        "claims": {"accepted": False},
    }
    (output / "landmarks.json").write_text(
        json.dumps(landmarks, indent=2) + "\n", encoding="utf-8"
    )

    measurements_rows = []
    rejections = []
    for name, objective in fit_report["objectives"].items():
        measure = name.split("|", 1)[0]
        tolerance = DECLARED_TOLERANCES_CM.get(measure, 1.5)
        error = objective["predictedCm"] - objective["targetCm"]
        measurements_rows.append(
            {
                "objective": name,
                "predictedCm": objective["predictedCm"],
                "targetCm": objective["targetCm"],
                "errorCm": error,
                "declaredToleranceCm": tolerance,
                "withinTolerance": abs(error) <= tolerance,
                "sourceKeys": objective["sourceKeys"],
                "targets": objective["targets"],
            }
        )
        if abs(error) > tolerance:
            rejections.append(
                {
                    "kind": "measurement-outside-declared-tolerance",
                    "objective": name,
                    "errorCm": error,
                    "declaredToleranceCm": tolerance,
                }
            )
    measurements = {
        "schemaVersion": "patterna.anny-worker-measurements/1.0",
        **identity,
        "declaredTolerancesCm": DECLARED_TOLERANCES_CM,
        "rows": measurements_rows,
        "claims": {"accepted": False},
    }
    (output / "measurements.json").write_text(
        json.dumps(measurements, indent=2) + "\n", encoding="utf-8"
    )

    registration = {
        "schemaVersion": "patterna.anny-collider-registration/1.0",
        **identity,
        "method": (
            "The collision mesh is the largest connected component of the exact"
            " display mesh with unchanged vertex positions, so shared vertices"
            " register exactly."
        ),
        "sharedVertexMaximumDeviationCm": 0.0,
        "displayComponentCount": body["componentCount"],
        "colliderIsWatertight": body["watertight"],
        "claims": {"accepted": False},
    }
    (output / "collider-registration.json").write_text(
        json.dumps(registration, indent=2) + "\n", encoding="utf-8"
    )

    fitted = fit_report["fittedParameters"]
    applied_direct_phenotype = fit_report["directPhenotype"]
    applied_direct_local = fit_report["directLocalChanges"]
    control_rows = []
    for row in control_map["controls"]:
        key = row["key"]
        source = source_rows[key]
        entry: dict[str, Any] = {
            "key": key,
            "sourceKind": source["sourceKind"],
            "sourceValue": source["sourceValue"],
            "sourceUnit": source["sourceUnit"],
            "status": row["status"],
        }
        if row["status"] == "mapped":
            target = row["target"]
            transform = target["transform"]
            applied: dict[str, Any] = {
                "family": target["family"],
                "key": target["key"],
                "transformKind": transform["kind"],
            }
            if transform["kind"] == "linear-direct":
                store = (
                    applied_direct_phenotype
                    if target["family"] == "phenotype"
                    else applied_direct_local
                )
                applied["appliedValue"] = store[target["key"]]
            else:
                label = f"{target['family']}:{target['key']}"
                applied["appliedValue"] = fitted.get(label)
                applied["additionalAppliedValues"] = {
                    f"{target['family']}:{extra}": fitted.get(
                        f"{target['family']}:{extra}"
                    )
                    for extra in transform["objective"].get("additionalTargetKeys", [])
                }
                objective_id = "|".join(
                    (
                        transform["objective"]["measure"],
                        transform["objective"]["station"],
                    )
                )
                matched = [
                    row_m
                    for row_m in measurements_rows
                    if row_m["objective"].split("::")[0] == objective_id
                    and key in row_m["sourceKeys"]
                ]
                if matched:
                    applied["objective"] = matched[0]["objective"]
                    applied["predictedCm"] = matched[0]["predictedCm"]
                    applied["withinDeclaredTolerance"] = matched[0]["withinTolerance"]
            entry["target"] = applied
        else:
            entry["unsupportedReason"] = row["unsupportedReason"]
        control_rows.append(entry)
    control_report = {
        "schemaVersion": "patterna.avatar-control-application/1.0",
        **identity,
        "controlMapId": control_map["controlMapId"],
        "controls": control_rows,
        "claims": {"accepted": False},
    }
    (output / "control-application-report.json").write_text(
        json.dumps(control_report, indent=2) + "\n", encoding="utf-8"
    )

    rejection_list = {
        "schemaVersion": "patterna.avatar-worker-rejections/1.0",
        **identity,
        "producerAccepted": False,
        "rejections": rejections,
    }
    (output / "rejection-list.json").write_text(
        json.dumps(rejection_list, indent=2) + "\n", encoding="utf-8"
    )

    render_landmarks = {
        label: landmark_positions[label]
        for label in (
            "head", "wrist.L", "wrist.R", "upperarm01.L", "upperarm01.R",
            "foot.L", "foot.R",
        )
    }
    for station in ("bust", "waist", "hip"):
        render_landmarks[station] = [
            0.0,
            0.0,
            stations_cm[station]["heightCm"],
        ]
    scale = 0.01  # Blender renders in meters for sane lighting distances.
    render_marks_m = {
        key: [value[0] * scale, value[1] * scale, value[2] * scale]
        for key, value in render_landmarks.items()
    }
    display_m_path = output / "display-mesh-meters.obj"
    write_obj(
        display_m_path,
        display_vertices * scale,
        faces,
        material_name="anny-body",
    )
    marks_path = output / "render-landmarks.json"
    marks_path.write_text(json.dumps(render_marks_m) + "\n", encoding="utf-8")
    renders_dir = output / "renders"
    completed = subprocess.run(
        [
            str(blender_path),
            "--background",
            "--factory-startup",
            "--python",
            str(render_script),
            "--",
            "--mesh",
            str(display_m_path),
            "--output-directory",
            str(renders_dir),
            "--landmarks",
            str(marks_path),
        ],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Blender render worker failed:\n"
            + completed.stdout[-2000:]
            + completed.stderr[-2000:]
        )

    return {
        "displayMesh": display_path.name,
        "collisionMesh": collider_path.name,
        "watertight": body["watertight"],
        "rejections": len(rejections),
        "rendersDirectory": renders_dir.name,
    }
