#!/usr/bin/env python3
"""Run Patterna's exact stitched garment bundle in the pinned PPF runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import re
import subprocess
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--source-report", required=True, type=Path)
    parser.add_argument("--garment-override", type=Path)
    parser.add_argument("--garment-override-report", type=Path)
    parser.add_argument("--body-override", type=Path)
    parser.add_argument("--body-override-report", type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--frames", type=int, default=240)
    parser.add_argument("--release-time-seconds", type=float, default=0.20)
    parser.add_argument("--dt", type=float, default=0.005)
    parser.add_argument("--stitch-stiffness", type=float, default=1.0)
    parser.add_argument("--stitch-length-factor", type=float, default=10.0)
    parser.add_argument("--direct-seam-capture-cm", type=float, default=5.0)
    parser.add_argument("--allow-spread-panel-research", action="store_true")
    parser.add_argument("--maximum-seam-phase", type=int, default=5)
    parser.add_argument("--body-contact-start-phase", type=int, default=0)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_obj(path: Path):
    import numpy as np

    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("v "):
            values = raw_line.split()
            vertices.append([float(values[1]), float(values[2]), float(values[3])])
        elif raw_line.startswith("f "):
            corners = raw_line.split()[1:]
            if len(corners) != 3:
                raise ValueError(f"PPF requires a triangulated OBJ: {path}")
            faces.append([int(corner.split("/")[0]) - 1 for corner in corners])
    vertex_array = np.asarray(vertices, dtype=np.float64)
    face_array = np.asarray(faces, dtype=np.int64)
    if vertex_array.ndim != 2 or vertex_array.shape[1] != 3 or not len(vertex_array):
        raise ValueError(f"OBJ has no usable vertices: {path}")
    if face_array.ndim != 2 or face_array.shape[1] != 3 or not len(face_array):
        raise ValueError(f"OBJ has no usable triangles: {path}")
    if face_array.min() < 0 or face_array.max() >= len(vertex_array):
        raise ValueError(f"OBJ has an out-of-range face index: {path}")
    if not np.isfinite(vertex_array).all():
        raise ValueError(f"OBJ has non-finite vertices: {path}")
    return vertex_array, face_array


def load_seam_links(path: Path, vertex_count: int) -> list[tuple[str, int, int]]:
    rows = path.read_text(encoding="utf-8").splitlines()
    if len(rows) != vertex_count:
        raise ValueError(
            f"Segmentation has {len(rows)} rows for {vertex_count} garment vertices."
        )
    members: dict[str, list[int]] = {}
    for vertex_index, row in enumerate(rows):
        for raw_label in row.split(","):
            label = raw_label.strip()
            if label.startswith("seam_link_"):
                members.setdefault(label, []).append(vertex_index)
    invalid = {
        label: indices
        for label, indices in members.items()
        if len(indices) != 2 or indices[0] == indices[1]
    }
    if invalid:
        raise ValueError(
            "Every authored seam link must identify two distinct vertices: "
            f"{list(sorted(invalid.items()))[:8]}"
        )
    return [
        (label, int(indices[0]), int(indices[1]))
        for label, indices in sorted(members.items())
    ]


def load_panel_owners(path: Path, vertex_count: int) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "patterna.style3d-panel-index-map/1.0":
        raise ValueError("Panel index map schema is not supported.")
    owners = [""] * vertex_count
    for raw_panel in document.get("panels", []):
        name = str(raw_panel.get("source_panel_name", "")).strip()
        indices = raw_panel.get("vertex_indices", [])
        if not name or not indices:
            raise ValueError("Panel index map contains an unnamed or empty panel.")
        for raw_index in indices:
            index = int(raw_index)
            if index < 0 or index >= vertex_count or owners[index]:
                raise ValueError(f"Panel index map has invalid ownership at vertex {index}.")
            owners[index] = name
    if any(not owner for owner in owners):
        raise ValueError("Panel index map does not own every garment vertex.")
    return owners


def stage_cross_panel_intersections(
    vertices_m,
    faces,
    panel_owners: list[str],
    intersection_finder,
    *,
    step_cm: float = 0.10,
    maximum_shift_cm: float = 1.00,
):
    """Rigidly separate intersecting panels without changing material shape."""
    import numpy as np

    original = np.asarray(vertices_m, dtype=np.float64)
    faces_array = np.asarray(faces, dtype=np.int64)
    face_owners = [panel_owners[int(face[0])] for face in faces_array]
    if any(
        panel_owners[int(vertex)] != face_owners[face_index]
        for face_index, face in enumerate(faces_array)
        for vertex in face
    ):
        raise ValueError("A garment triangle crosses panel ownership boundaries.")
    initial_pairs = list(intersection_finder(original, faces_array))
    intra_panel = [
        pair for pair in initial_pairs if face_owners[pair[0]] == face_owners[pair[1]]
    ]
    if intra_panel:
        raise ValueError(
            "Rigid staging cannot repair intersections within one panel: "
            f"{intra_panel[:8]}"
        )
    conflict_panels = sorted(
        {
            face_owners[face_index]
            for pair in initial_pairs
            for face_index in pair
        }
    )
    if not conflict_panels:
        return original.copy(), {
            "method": "rigid-radial-panel-separation",
            "initialIntersectionCount": 0,
            "finalIntersectionCount": 0,
            "maximumShiftCm": 0.0,
            "panelTranslationsCm": {},
        }

    panel_indices = {
        panel: np.asarray(
            [index for index, owner in enumerate(panel_owners) if owner == panel],
            dtype=np.int64,
        )
        for panel in conflict_panels
    }
    panel_directions: dict[str, np.ndarray] = {}
    for panel, indices in panel_indices.items():
        centroid = original[indices].mean(axis=0)
        lateral = float(centroid[0])
        depth = float(centroid[2])
        if abs(lateral) > 1e-6:
            direction = np.asarray(
                [np.sign(lateral), 0.0, 0.25 * (np.sign(depth) or 1.0)],
                dtype=np.float64,
            )
        else:
            direction = np.asarray([0.0, 0.0, np.sign(depth) or 1.0])
        panel_directions[panel] = direction / np.linalg.norm(direction)

    maximum_steps = int(round(maximum_shift_cm / step_cm))
    for step in range(1, maximum_steps + 1):
        distance_m = step * step_cm * 0.01
        staged = original.copy()
        for panel, indices in panel_indices.items():
            staged[indices] += distance_m * panel_directions[panel]
        remaining = list(intersection_finder(staged, faces_array))
        if not remaining:
            return staged, {
                "method": "rigid-radial-panel-separation",
                "initialIntersectionCount": len(initial_pairs),
                "finalIntersectionCount": 0,
                "maximumShiftCm": step * step_cm,
                "panelTranslationsCm": {
                    panel: (step * step_cm * direction).tolist()
                    for panel, direction in panel_directions.items()
                },
            }
    raise RuntimeError(
        "Rigid panel staging did not remove all intersections within "
        f"{maximum_shift_cm:.2f} cm."
    )


def stage_body_clearance(
    vertices_m,
    faces,
    panel_owners: list[str],
    body_vertices_m,
    violation_face_finder,
    self_intersection_finder,
    *,
    step_cm: float = 0.10,
    maximum_shift_cm: float = 1.00,
):
    """Rigidly move only body-clearance-violating panels radially outward."""
    import numpy as np

    staged = np.asarray(vertices_m, dtype=np.float64).copy()
    faces_array = np.asarray(faces, dtype=np.int64)
    body = np.asarray(body_vertices_m, dtype=np.float64)
    face_owners = [panel_owners[int(face[0])] for face in faces_array]
    body_center_xz = 0.5 * (
        body[:, (0, 2)].min(axis=0) + body[:, (0, 2)].max(axis=0)
    )
    translations = {
        name: np.zeros(3, dtype=np.float64) for name in sorted(set(panel_owners))
    }
    initial_violations = list(violation_face_finder(staged))
    violations = initial_violations
    maximum_steps = int(math.ceil(maximum_shift_cm / step_cm))
    for _ in range(maximum_steps):
        if not violations:
            break
        conflicting_panels = sorted({face_owners[index] for index in violations})
        for panel in conflicting_panels:
            indices = np.asarray(
                [index for index, owner in enumerate(panel_owners) if owner == panel],
                dtype=np.int64,
            )
            center_xz = staged[indices][:, (0, 2)].mean(axis=0)
            radial_xz = center_xz - body_center_xz
            length = float(np.linalg.norm(radial_xz))
            if length <= 1e-12:
                raise ValueError(f"Cannot derive a radial clearance direction for {panel}.")
            translation = np.asarray(
                [radial_xz[0] / length, 0.0, radial_xz[1] / length]
            ) * (step_cm * 0.01)
            staged[indices] += translation
            translations[panel] += translation
        intersections = list(self_intersection_finder(staged, faces_array))
        if intersections:
            raise ValueError(
                "Body-clearance staging introduced garment self-intersections: "
                f"{intersections[:8]}"
            )
        violations = list(violation_face_finder(staged))
    if violations:
        raise ValueError(
            f"Body-clearance staging still has {len(violations)} violations after "
            f"{maximum_shift_cm:.2f} cm."
        )
    return staged, {
        "method": "rigid-radial-body-clearance",
        "initialViolationCount": len(initial_violations),
        "finalViolationCount": len(violations),
        "clearanceThresholdCm": 0.25,
        "maximumShiftCm": max(
            (100.0 * float(np.linalg.norm(value)) for value in translations.values()),
            default=0.0,
        ),
        "panelTranslationsCm": {
            name: (100.0 * translation).tolist()
            for name, translation in translations.items()
            if float(np.linalg.norm(translation)) > 0.0
        },
    }


def stitch_arrays(seam_links: list[tuple[str, int, int]]):
    import numpy as np

    indices = np.asarray(
        [[first, second, second, second] for _, first, second in seam_links],
        dtype=np.int64,
    )
    weights = np.tile(
        np.asarray([[1.0, 1.0, 0.0, 0.0]], dtype=np.float64),
        (len(seam_links), 1),
    )
    return indices, weights


SEAM_PHASE_ORDER = (
    "internal-shaping",
    "detached-shells",
    "torso-shell",
    "finishing-bands",
    "neckline",
    "sleeve-caps",
)


def classify_seam_phase(first_panel: str, second_panel: str) -> str:
    """Return the construction phase for one authored seam link.

    The classification is deliberately based on semantic panel roles instead
    of generated seam-link numbers. The generated labels preserve identity,
    but they do not describe whether a link closes a dart, torso, cuff,
    neckline, or sleeve cap.
    """
    panels = (first_panel.lower(), second_panel.lower())
    if panels[0] == panels[1]:
        return "internal-shaping"

    has_torso = tuple("torso" in panel for panel in panels)
    has_sleeve = tuple("sleeve" in panel for panel in panels)
    has_cuff = tuple("cuff" in panel for panel in panels)
    has_collar = tuple("collar" in panel for panel in panels)

    if all(has_torso):
        return "torso-shell"
    if all(has_sleeve) or all(has_cuff) or all(has_collar):
        return "detached-shells"
    if any(has_sleeve) and any(has_cuff):
        return "finishing-bands"
    if any(has_collar) and any(has_torso):
        return "neckline"
    if any(has_sleeve) and any(has_torso):
        return "sleeve-caps"
    raise ValueError(
        "Authored seam link has no supported construction phase: "
        f"{first_panel} <-> {second_panel}"
    )


def seam_assembly_plan(
    vertices_m,
    seam_links: list[tuple[str, int, int]],
    panel_owners: list[str],
) -> dict[str, object]:
    """Summarize cumulative seam phases and their initial capture distances."""
    import numpy as np

    grouped: dict[str, list[tuple[str, int, int]]] = {
        phase: [] for phase in SEAM_PHASE_ORDER
    }
    for link in seam_links:
        _, first, second = link
        grouped[
            classify_seam_phase(panel_owners[first], panel_owners[second])
        ].append(link)

    vertices = np.asarray(vertices_m, dtype=np.float64)
    phases = []
    cumulative_count = 0
    for index, phase in enumerate(SEAM_PHASE_ORDER):
        links = grouped[phase]
        cumulative_count += len(links)
        distances_cm = np.asarray(
            [
                100.0 * np.linalg.norm(vertices[first] - vertices[second])
                for _, first, second in links
            ],
            dtype=np.float64,
        )
        phases.append(
            {
                "index": index,
                "name": phase,
                "linkCount": len(links),
                "cumulativeLinkCount": cumulative_count,
                "maximumInitialSeparationCm": (
                    float(distances_cm.max()) if len(distances_cm) else 0.0
                ),
                "meanInitialSeparationCm": (
                    float(distances_cm.mean()) if len(distances_cm) else 0.0
                ),
                "p95InitialSeparationCm": (
                    float(np.percentile(distances_cm, 95.0))
                    if len(distances_cm)
                    else 0.0
                ),
            }
        )
    if cumulative_count != len(seam_links):
        raise RuntimeError("Seam assembly plan did not classify every authored link.")
    return {
        "method": "cumulative-semantic-construction-phases",
        "phaseCount": len(phases),
        "authoredLinkCount": len(seam_links),
        "phases": phases,
    }


def active_seam_links_for_phase(
    seam_links: list[tuple[str, int, int]],
    panel_owners: list[str],
    maximum_phase_index: int,
) -> list[tuple[str, int, int]]:
    if maximum_phase_index < 0 or maximum_phase_index >= len(SEAM_PHASE_ORDER):
        raise ValueError(
            f"Maximum seam phase must be between 0 and {len(SEAM_PHASE_ORDER) - 1}."
        )
    allowed = set(SEAM_PHASE_ORDER[: maximum_phase_index + 1])
    return [
        link
        for link in seam_links
        if classify_seam_phase(
            panel_owners[link[1]],
            panel_owners[link[2]],
        )
        in allowed
    ]


def load_rest_lengths(path: Path, vertex_count: int) -> dict[tuple[int, int], float]:
    import numpy as np

    with path.open("rb") as stream:
        raw = pickle.load(stream)
    result: dict[tuple[int, int], float] = {}
    for raw_pair, raw_length in raw.items():
        first, second = int(raw_pair[0]), int(raw_pair[1])
        length = float(raw_length)
        if first < 0 or second < 0 or first >= vertex_count or second >= vertex_count:
            raise ValueError(f"Material rest edge is out of range: {(first, second)}")
        if not np.isfinite(length) or length <= 0.0:
            raise ValueError(f"Material rest edge has invalid length: {raw_pair}")
        result[(first, second)] = length
    if not result:
        raise ValueError("Material rest-length map is empty.")
    return result


def seam_metrics(vertices_m, seam_links: list[tuple[str, int, int]]) -> dict[str, object]:
    import numpy as np

    first = np.asarray([entry[1] for entry in seam_links], dtype=np.int64)
    second = np.asarray([entry[2] for entry in seam_links], dtype=np.int64)
    distances_cm = 100.0 * np.linalg.norm(vertices_m[first] - vertices_m[second], axis=1)
    maximum_index = int(np.argmax(distances_cm))
    return {
        "count": len(seam_links),
        "maximumSeparationCm": float(distances_cm[maximum_index]),
        "meanSeparationCm": float(np.mean(distances_cm)),
        "p95SeparationCm": float(np.percentile(distances_cm, 95.0)),
        "maximumSeparationLabel": seam_links[maximum_index][0],
        "maximumSeparationVertices": [int(first[maximum_index]), int(second[maximum_index])],
    }


def strain_metrics(vertices_m, rest_lengths_cm: dict[tuple[int, int], float]) -> dict[str, object]:
    import numpy as np

    ordered = list(rest_lengths_cm.items())
    first = np.asarray([pair[0] for pair, _ in ordered], dtype=np.int64)
    second = np.asarray([pair[1] for pair, _ in ordered], dtype=np.int64)
    rest_cm = np.asarray([length for _, length in ordered], dtype=np.float64)
    current_cm = 100.0 * np.linalg.norm(vertices_m[first] - vertices_m[second], axis=1)
    strain = np.abs(current_cm / rest_cm - 1.0)
    maximum_index = int(np.argmax(strain))
    high_count = int(np.count_nonzero(strain > 0.40))
    return {
        "edgeCount": len(strain),
        "maximumRatio": float(strain[maximum_index]),
        "p95Ratio": float(np.percentile(strain, 95.0)),
        "p999Ratio": float(np.percentile(strain, 99.9)),
        "p9999Ratio": float(np.percentile(strain, 99.99)),
        "highStrainThresholdRatio": 0.40,
        "highStrainEdgeCount": high_count,
        "highStrainEdgeFraction": high_count / len(strain),
        "maximumStrainVertices": list(ordered[maximum_index][0]),
    }


def triangle_area_metrics_cm2(vertices_cm, faces) -> dict[str, float | int]:
    import numpy as np

    vertices = np.asarray(vertices_cm, dtype=np.float64)
    triangles = vertices[np.asarray(faces, dtype=np.int64)]
    if vertices.shape[1] == 2:
        first = triangles[:, 1] - triangles[:, 0]
        second = triangles[:, 2] - triangles[:, 0]
        areas = 0.5 * np.abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0])
    elif vertices.shape[1] == 3:
        areas = 0.5 * np.linalg.norm(
            np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
            axis=1,
        )
    else:
        raise ValueError("Triangle vertices must have two or three coordinates.")
    if not len(areas) or not np.isfinite(areas).all():
        raise ValueError("Triangle areas are missing or non-finite.")
    return {
        "triangleCount": len(areas),
        "minimumAreaCm2": float(areas.min()),
        "p01AreaCm2": float(np.percentile(areas, 1.0)),
        "meanAreaCm2": float(areas.mean()),
    }


def cross_group_pairs(pairs, first_group_count: int) -> list[tuple[int, int]]:
    return [
        (int(first), int(second))
        for first, second in pairs
        if (first < first_group_count) != (second < first_group_count)
    ]


def cross_pair_details(
    pairs: list[tuple[int, int]],
    garment_face_count: int,
    garment_faces,
    panel_owners: list[str],
) -> list[dict[str, int | str]]:
    details = []
    for first, second in pairs:
        garment_face = first if first < garment_face_count else second
        body_face = second if first < garment_face_count else first
        details.append(
            {
                "garmentFaceIndex": int(garment_face),
                "bodyFaceIndex": int(body_face - garment_face_count),
                "panel": panel_owners[int(garment_faces[garment_face][0])],
            }
        )
    return details


def mapped_object_vertices(global_vertices, object_vertex_map):
    import numpy as np

    vertices = np.asarray(global_vertices)
    indices = np.asarray(object_vertex_map, dtype=np.int64)
    if indices.ndim != 1 or not len(indices):
        raise ValueError("PPF object vertex map must be a non-empty vector.")
    if indices.min() < 0 or indices.max() >= len(vertices):
        raise ValueError("PPF object vertex map contains an out-of-range index.")
    return vertices[indices]


def final_frame_indices(latest_frame_index: int) -> tuple[int, int]:
    if latest_frame_index < 1:
        raise ValueError("PPF requires at least an initial and one simulated snapshot.")
    return latest_frame_index - 1, latest_frame_index


def write_obj(template_path: Path, output_path: Path, vertices_cm) -> None:
    lines: list[str] = []
    vertex_index = 0
    for raw_line in template_path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("v "):
            vertex = vertices_cm[vertex_index]
            lines.append(f"v {vertex[0]:.9f} {vertex[1]:.9f} {vertex[2]:.9f}")
            vertex_index += 1
        else:
            lines.append(raw_line)
    if vertex_index != len(vertices_cm):
        raise ValueError("Template vertex count does not match PPF output.")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_gpu_identity() -> dict[str, str | None]:
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total,compute_cap",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        return {"query": "failed", "error": result.stderr.strip()}
    values = [value.strip() for value in result.stdout.strip().split(",")]
    return {
        "name": values[0] if len(values) > 0 else None,
        "driverVersion": values[1] if len(values) > 1 else None,
        "memoryMiB": values[2] if len(values) > 2 else None,
        "computeCapability": values[3] if len(values) > 3 else None,
    }


def prepare_runtime(runtime_root: Path) -> tuple[dict[str, object], Path]:
    manifest_path = runtime_root / "runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != "patterna.challenger-runtime/1.0":
        raise ValueError("PPF runtime manifest schema is not supported.")
    if manifest.get("name") != "PPF":
        raise ValueError("The selected challenger runtime is not PPF.")
    for relative_path, expected_hash in manifest.get("entrypoints", {}).items():
        entrypoint = runtime_root / relative_path
        if not entrypoint.is_file() or sha256(entrypoint) != expected_hash:
            raise ValueError(f"PPF entrypoint identity failed: {relative_path}")
    path_entries = [
        runtime_root / "python",
        runtime_root / "python" / "Scripts",
        runtime_root / "bin",
        runtime_root / "target" / "release",
        runtime_root / "mingit" / "cmd",
    ]
    os.environ["PATH"] = (
        os.pathsep.join(str(path) for path in path_entries)
        + os.pathsep
        + os.environ.get("PATH", "")
    )
    for path in path_entries:
        if path.is_dir() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(path))
    sys.path.insert(0, str(runtime_root))
    return manifest, manifest_path


def require_source_path(report: dict[str, object], key: str) -> Path:
    raw_path = report.get(key)
    raw_hash = report.get(f"{key.removesuffix('_path')}_sha256")
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError(f"Source report has no {key}.")
    path = Path(raw_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Source report input is missing: {path}")
    if not isinstance(raw_hash, str) or sha256(path) != raw_hash:
        raise ValueError(f"Source report hash does not match {key}: {path}")
    return path


def resolve_body_mesh(
    source_report: dict[str, object],
    body_override: Path | None,
    body_override_report: Path | None,
) -> tuple[Path, dict[str, object]]:
    canonical_body = require_source_path(source_report, "body_mesh_path")
    canonical_hash = sha256(canonical_body)
    if (body_override is None) != (body_override_report is None):
        raise ValueError("--body-override and --body-override-report must be supplied together.")
    if body_override is None or body_override_report is None:
        return canonical_body, {
            "canonicalBody": str(canonical_body),
            "canonicalBodySha256": canonical_hash,
            "collisionBody": str(canonical_body),
            "collisionBodySha256": canonical_hash,
            "collisionBodyOverride": False,
        }
    proxy_path = body_override.resolve()
    proxy_report_path = body_override_report.resolve()
    if not proxy_path.is_file() or not proxy_report_path.is_file():
        raise FileNotFoundError("Collision-body override or its report is missing.")
    proxy_report = json.loads(proxy_report_path.read_text(encoding="utf-8"))
    proxy_schema = proxy_report.get("schemaVersion")
    if proxy_schema not in {
        "patterna.body-collision-proxy/1.0",
        "patterna.ppf-dressing-body/1.0",
    }:
        raise ValueError("Collision-body override report schema is not supported.")
    if proxy_report.get("accepted") is not True:
        raise ValueError("Collision-body override report is not accepted.")
    lineage_key = (
        "sourceMeshSha256"
        if proxy_schema == "patterna.body-collision-proxy/1.0"
        else "canonicalBodySha256"
    )
    if proxy_report.get("inputs", {}).get(lineage_key) != canonical_hash:
        raise ValueError("Collision-body override was not derived from the canonical body.")
    proxy_hash = sha256(proxy_path)
    output_key = (
        "proxyMeshSha256"
        if proxy_schema == "patterna.body-collision-proxy/1.0"
        else "dressingBodySha256"
    )
    if proxy_report.get("outputs", {}).get(output_key) != proxy_hash:
        raise ValueError("Collision-body override hash does not match its report.")
    return proxy_path, {
        "canonicalBody": str(canonical_body),
        "canonicalBodySha256": canonical_hash,
        "collisionBody": str(proxy_path),
        "collisionBodySha256": proxy_hash,
        "collisionBodyOverride": True,
        "collisionBodyRole": (
            "accepted-full-size-proxy"
            if proxy_schema == "patterna.body-collision-proxy/1.0"
            else "temporary-reduced-dressing-body"
        ),
        "collisionBodyReport": str(proxy_report_path),
        "collisionBodyReportSha256": sha256(proxy_report_path),
    }


def resolve_garment_mesh(
    source_report: dict[str, object],
    source_report_path: Path,
    garment_override: Path | None,
    garment_override_report: Path | None,
) -> tuple[Path, dict[str, object]]:
    """Resolve a canonical source garment or one hash-bound prior PPF phase."""
    canonical_garment = require_source_path(source_report, "physical_mesh_path")
    canonical_hash = sha256(canonical_garment)
    if (garment_override is None) != (garment_override_report is None):
        raise ValueError(
            "--garment-override and --garment-override-report must be supplied "
            "together."
        )
    if garment_override is None or garment_override_report is None:
        return canonical_garment, {
            "canonicalGarment": str(canonical_garment),
            "canonicalGarmentSha256": canonical_hash,
            "simulationGarment": str(canonical_garment),
            "simulationGarmentSha256": canonical_hash,
            "simulationGarmentOverride": False,
        }

    override_path = garment_override.resolve()
    override_report_path = garment_override_report.resolve()
    if not override_path.is_file() or not override_report_path.is_file():
        raise FileNotFoundError("Garment override or its PPF report is missing.")
    override_report = json.loads(override_report_path.read_text(encoding="utf-8"))
    if override_report.get("schemaVersion") != "patterna.ppf-common-bundle/1.0":
        raise ValueError("Garment override report schema is not supported.")
    if override_report.get("status") != "completed-requires-acceptance-grading":
        raise ValueError("Garment override report does not describe a completed phase.")
    if (
        override_report.get("inputs", {}).get("sourceReportSha256")
        != sha256(source_report_path)
    ):
        raise ValueError("Garment override was not derived from this source report.")
    override_hash = sha256(override_path)
    if override_report.get("outputs", {}).get("finalObjSha256") != override_hash:
        raise ValueError("Garment override hash does not match its PPF report.")
    return override_path, {
        "canonicalGarment": str(canonical_garment),
        "canonicalGarmentSha256": canonical_hash,
        "simulationGarment": str(override_path),
        "simulationGarmentSha256": override_hash,
        "simulationGarmentOverride": True,
        "simulationGarmentReport": str(override_report_path),
        "simulationGarmentReportSha256": sha256(override_report_path),
        "previousCollisionBodySha256": override_report.get("inputs", {}).get(
            "collisionBodySha256"
        ),
        "previousBodyContactActive": bool(
            override_report.get("topology", {}).get("bodyContactActive")
        ),
    }


def main() -> None:
    import numpy as np

    args = parse_args()
    if args.frames < 2:
        raise ValueError("--frames must be at least 2.")
    if args.maximum_seam_phase < 0 or args.maximum_seam_phase >= len(
        SEAM_PHASE_ORDER
    ):
        raise ValueError(
            f"--maximum-seam-phase must be between 0 and {len(SEAM_PHASE_ORDER) - 1}."
        )
    if args.body_contact_start_phase < 0 or args.body_contact_start_phase >= len(
        SEAM_PHASE_ORDER
    ):
        raise ValueError(
            "--body-contact-start-phase must be between 0 and "
            f"{len(SEAM_PHASE_ORDER) - 1}."
        )
    if (
        args.dt <= 0.0
        or args.release_time_seconds < 0.0
        or args.stitch_stiffness <= 0.0
        or args.stitch_length_factor <= 0.0
        or args.direct_seam_capture_cm <= 0.0
    ):
        raise ValueError("PPF time and stiffness parameters must be positive.")
    runtime_root = args.runtime_root.resolve()
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    report_path = output_directory / "ppf-patterna-report.json"
    final_vertices_path = output_directory / "final-garment-vertices.npy"
    final_obj_path = output_directory / "patterna-ppf-final.obj"
    staged_obj_path = output_directory / "patterna-ppf-staged-initial.obj"
    input_gate_path = output_directory / "ppf-input-gate.json"
    for stale_output in (
        report_path,
        final_vertices_path,
        final_obj_path,
        staged_obj_path,
        input_gate_path,
    ):
        stale_output.unlink(missing_ok=True)

    manifest, manifest_path = prepare_runtime(runtime_root)
    source_report_path = args.source_report.resolve()
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    garment_path, garment_identity = resolve_garment_mesh(
        source_report,
        source_report_path,
        args.garment_override,
        args.garment_override_report,
    )
    body_path, body_identity = resolve_body_mesh(
        source_report,
        args.body_override,
        args.body_override_report,
    )
    segmentation_path = require_source_path(source_report, "panel_ownership_path")
    rest_lengths_path = require_source_path(source_report, "rest_lengths_path")
    material_coordinates_path = require_source_path(source_report, "material_coordinates_path")
    panel_index_map_path = require_source_path(source_report, "panel_index_map_path")

    garment_vertices_cm, garment_faces = read_obj(garment_path)
    body_vertices_m, body_faces = read_obj(body_path)
    body_contact_active = args.maximum_seam_phase >= args.body_contact_start_phase
    continuing_same_body_contact = bool(
        body_contact_active
        and garment_identity.get("simulationGarmentOverride")
        and garment_identity.get("previousBodyContactActive")
        and garment_identity.get("previousCollisionBodySha256") == sha256(body_path)
    )
    seam_links = load_seam_links(segmentation_path, len(garment_vertices_cm))
    panel_owners = load_panel_owners(panel_index_map_path, len(garment_vertices_cm))
    assembly_plan = seam_assembly_plan(
        garment_vertices_cm * 0.01,
        seam_links,
        panel_owners,
    )
    active_seam_links = active_seam_links_for_phase(
        seam_links,
        panel_owners,
        args.maximum_seam_phase,
    )
    stitch_indices, stitch_weights = stitch_arrays(active_seam_links)
    rest_lengths_cm = load_rest_lengths(rest_lengths_path, len(garment_vertices_cm))
    material = np.load(material_coordinates_path)
    panel_vertices_cm = np.asarray(material["panel_vertices_cm"], dtype=np.float64)
    panel_faces = np.asarray(material["panel_faces"], dtype=np.int64)
    if panel_vertices_cm.shape != (len(garment_vertices_cm), 2):
        raise ValueError("Material coordinates do not match garment vertices.")
    if not np.array_equal(panel_faces, garment_faces):
        raise ValueError("Material-coordinate faces do not match the garment OBJ.")

    from frontend import App
    from frontend._intersection_ import check_self_intersection
    from frontend._proximity_ import check_contact_offset_violation
    from frontend._scene_ import ValidationError

    staged_vertices_m, intersection_staging = stage_cross_panel_intersections(
        garment_vertices_cm * 0.01,
        garment_faces,
        panel_owners,
        check_self_intersection,
    )

    def find_body_clearance_violating_faces(candidate_vertices_m):
        candidate_combined_vertices = np.vstack((candidate_vertices_m, body_vertices_m))
        candidate_combined_faces = np.vstack(
            (garment_faces, body_faces + len(candidate_vertices_m))
        ).astype(np.int32)
        candidate_collider_faces = np.concatenate(
            (
                np.zeros(len(garment_faces), dtype=bool),
                np.ones(len(body_faces), dtype=bool),
            )
        )
        candidate_offsets_m = np.full(
            len(candidate_combined_faces), 0.00125, dtype=np.float64
        )
        pairs = cross_group_pairs(
            check_contact_offset_violation(
                candidate_combined_vertices,
                F=candidate_combined_faces,
                is_collider=candidate_collider_faces,
                contact_offset=candidate_offsets_m,
            ),
            len(garment_faces),
        )
        return [
            first if first < len(garment_faces) else second
            for first, second in pairs
        ]

    if continuing_same_body_contact:
        clearance_staging = {
            "method": "trusted-native-same-collider-continuation",
            "active": True,
            "initialViolationCount": None,
            "finalViolationCount": None,
            "panelTranslationsCm": {},
        }
    elif body_contact_active:
        staged_vertices_m, clearance_staging = stage_body_clearance(
            staged_vertices_m,
            garment_faces,
            panel_owners,
            body_vertices_m,
            find_body_clearance_violating_faces,
            check_self_intersection,
        )
    else:
        clearance_staging = {
            "method": "inactive-before-configured-seam-phase",
            "bodyContactStartPhaseIndex": args.body_contact_start_phase,
            "bodyContactStartPhaseName": SEAM_PHASE_ORDER[
                args.body_contact_start_phase
            ],
            "active": False,
            "initialViolationCount": 0,
            "finalViolationCount": 0,
            "panelTranslationsCm": {},
        }
    staging = {
        "panelIntersection": intersection_staging,
        "bodyClearance": clearance_staging,
    }
    write_obj(garment_path, staged_obj_path, staged_vertices_m * 100.0)
    geometry_areas = triangle_area_metrics_cm2(staged_vertices_m * 100.0, garment_faces)
    material_areas = triangle_area_metrics_cm2(panel_vertices_cm, panel_faces)
    initial_strain = strain_metrics(staged_vertices_m, rest_lengths_cm)
    body_intersections = []
    body_clearance_violations = []
    if body_contact_active:
        combined_vertices = np.vstack((staged_vertices_m, body_vertices_m))
        combined_faces = np.vstack(
            (garment_faces, body_faces + len(staged_vertices_m))
        ).astype(np.int32)
        collider_faces = np.concatenate(
            (
                np.zeros(len(garment_faces), dtype=bool),
                np.ones(len(body_faces), dtype=bool),
            )
        )
        body_intersections = cross_group_pairs(
            check_self_intersection(
                combined_vertices,
                combined_faces,
                is_collider=collider_faces,
            ),
            len(garment_faces),
        )
        clearance_offsets_m = np.full(len(combined_faces), 0.00125, dtype=np.float64)
        body_clearance_violations = cross_group_pairs(
            check_contact_offset_violation(
                combined_vertices,
                F=combined_faces,
                is_collider=collider_faces,
                contact_offset=clearance_offsets_m,
            ),
            len(garment_faces),
        )
    input_rejections: list[str] = []
    if source_report.get("schema_version") != "patterna.style3d-source/1.0":
        input_rejections.append("source report schema is not supported")
    if source_report.get("initial_arrangement_research_override") is True:
        input_rejections.append("source report uses a research-only arrangement override")
    if source_report.get("initial_arrangement_rejection_reasons"):
        input_rejections.append("source report contains initial-arrangement rejections")
    for label, metrics in (("geometry", geometry_areas), ("material", material_areas)):
        if float(metrics["minimumAreaCm2"]) < 0.001:
            input_rejections.append(
                f"{label} minimum triangle area is below 0.001 cm2"
            )
    if float(initial_strain["maximumRatio"]) > 2.0:
        input_rejections.append("initial maximum edge strain exceeds 2.0")
    if float(initial_strain["p95Ratio"]) > 0.25:
        input_rejections.append("initial 95th-percentile edge strain exceeds 0.25")
    if body_intersections:
        input_rejections.append("staged garment intersects the collision body")
    if body_clearance_violations and not continuing_same_body_contact:
        input_rejections.append("staged garment clearance is below 0.25 cm")
    maximum_direct_seam_cm = max(
        float(phase["maximumInitialSeparationCm"])
        for phase in assembly_plan["phases"]
        if int(phase["index"]) <= args.maximum_seam_phase
    )
    spread_panel_research = maximum_direct_seam_cm > args.direct_seam_capture_cm
    if spread_panel_research and not args.allow_spread_panel_research:
        input_rejections.append(
            "authored seams exceed the direct solver capture distance and require "
            "cumulative seam-aware dressing"
        )
    input_gate = {
        "schemaVersion": "patterna.ppf-input-gate/1.0",
        "accepted": not input_rejections,
        "rejectionReasons": input_rejections,
        "geometryTriangleAreas": geometry_areas,
        "materialTriangleAreas": material_areas,
        "initialStrain": initial_strain,
        "initialStaging": staging,
        "bodyContactActive": body_contact_active,
        "continuingSameBodyContact": continuing_same_body_contact,
        "bodyContactStartPhaseIndex": args.body_contact_start_phase,
        "bodyContactStartPhaseName": SEAM_PHASE_ORDER[
            args.body_contact_start_phase
        ],
        "seamAssemblyPlan": {
            **assembly_plan,
            "activeThroughPhaseIndex": args.maximum_seam_phase,
            "activeThroughPhaseName": SEAM_PHASE_ORDER[args.maximum_seam_phase],
            "activeLinkCount": len(active_seam_links),
            "directCaptureThresholdCm": args.direct_seam_capture_cm,
            "maximumDirectSeamSeparationCm": maximum_direct_seam_cm,
            "requiresCumulativeDressing": spread_panel_research,
            "researchOverride": bool(
                spread_panel_research and args.allow_spread_panel_research
            ),
        },
        "bodyIntersectionCount": len(body_intersections),
        "bodyIntersectionSamples": cross_pair_details(
            body_intersections[:32],
            len(garment_faces),
            garment_faces,
            panel_owners,
        ),
        "bodyClearanceThresholdCm": 0.25,
        "bodyClearanceViolationCount": len(body_clearance_violations),
        "bodyClearanceViolationSamples": cross_pair_details(
            body_clearance_violations[:32],
            len(garment_faces),
            garment_faces,
            panel_owners,
        ),
        "inputs": {
            "sourceReportSha256": sha256(source_report_path),
            "garmentSha256": sha256(garment_path),
            "bodySha256": sha256(body_path),
        },
    }
    input_gate_path.write_text(json.dumps(input_gate, indent=2) + "\n", encoding="utf-8")
    if input_rejections:
        raise ValueError("PPF input gate rejected the source: " + "; ".join(input_rejections))
    if args.preflight_only:
        print(json.dumps(input_gate, indent=2))
        return

    cache_directory = output_directory / "cache"
    data_directory = output_directory / "data"
    App.get_data_dirpath = staticmethod(lambda: str(data_directory))
    app = App.create("patterna-ppf-common-bundle", cache_dir=str(cache_directory))
    garment_asset = np.column_stack(
        [staged_vertices_m, panel_vertices_cm * 0.01]
    )
    app.asset.add.tri("patterna-garment", garment_asset, garment_faces)
    app.asset.add.stitch("patterna-authored-seams", (stitch_indices, stitch_weights))
    if body_contact_active:
        app.asset.add.tri("patterna-body", body_vertices_m, body_faces)

    scene = app.scene.create()
    garment = scene.add("patterna-garment")
    garment.stitch("patterna-authored-seams")
    garment.param.set("model", "baraff-witkin")
    garment.param.set("density", 0.12).set("young-mod", 400.0)
    garment.param.set("poiss-rat", 0.30).set("bend", 0.20)
    garment.param.set("strain-limit", 0.15).set("friction", 0.45)
    garment.param.set("contact-gap", 0.002).set("contact-offset", 0.0)
    garment.param.set("deformation-damping", 0.002)
    garment.param.set("bending-damping", 0.0005)
    garment.param.set("stitch-stiffness", args.stitch_stiffness)

    if body_contact_active:
        body = scene.add("patterna-body").as_pdrd()
        body.param.set("friction", 0.45)
        body.param.set("contact-gap", 0.004).set("contact-offset", 0.0)
        body.pin().move_by(
            [0.0, 0.0, 0.0],
            t_start=0.0,
            t_end=max(args.frames * args.dt, 0.01),
        )
    try:
        fixed_scene = scene.build()
    except ValidationError as error:
        failure_path = output_directory / "ppf-scene-validation-failure.json"
        failure_path.write_text(
            json.dumps(
                {
                    "schemaVersion": "patterna.ppf-scene-validation-failure/1.0",
                    "message": str(error),
                    "violations": error.violations,
                    "inputs": {
                        "garmentSha256": sha256(garment_path),
                        "bodySha256": sha256(body_path),
                        "authoredSeamLinkCount": len(seam_links),
                        "activeSeamLinkCount": len(active_seam_links),
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        raise

    session = app.session.create(fixed_scene)
    parameters = session.param.set("inactive-momentum", True)
    parameters.set("dt", 0.001)
    parameters.set("min-newton-steps", 8).set("max-newton-steps", 2048)
    parameters.set("stitch-length-factor", args.stitch_length_factor)
    parameters.set("gravity", [0.0, 0.0, 0.0])
    if args.release_time_seconds > 0.0:
        parameters.dyn("inactive-momentum").time(
            args.release_time_seconds
        ).hold().change(False)
        parameters.dyn("dt").time(args.release_time_seconds).hold().change(args.dt)
        parameters.dyn("gravity").time(
            args.release_time_seconds
        ).hold().change([0.0, -9.8, 0.0])
    else:
        parameters.set("inactive-momentum", False).set("dt", args.dt)
        parameters.set("gravity", [0.0, -9.8, 0.0])
    # Dynamic timeline builders derive their own default frame count. Apply the
    # caller's explicit request last so the native session cannot silently
    # shorten an acceptance run to the release keyframe.
    parameters.set("frames", args.frames)

    fixed_session = session.build()
    started = time.perf_counter()
    fixed_session.start(force=True, blocking=True)
    elapsed = time.perf_counter() - started
    if not fixed_session.finished():
        raise RuntimeError("PPF session ended without its finished marker.")
    latest_frame_index = fixed_session.get.latest_frame()
    try:
        previous_frame_index, final_frame_index = final_frame_indices(latest_frame_index)
    except ValueError as error:
        raise RuntimeError(
            f"PPF produced only {latest_frame_index + 1} vertex snapshots."
        ) from error
    final_frame = fixed_session.get.vertex(final_frame_index)
    previous_frame = fixed_session.get.vertex(previous_frame_index)
    if final_frame is None or previous_frame is None:
        raise RuntimeError("PPF final frames could not be read.")
    final_all = np.asarray(final_frame[0], dtype=np.float64)
    previous_all = np.asarray(previous_frame[0], dtype=np.float64)
    garment_vertex_map = fixed_scene._map_by_name["patterna-garment"]
    final_garment = mapped_object_vertices(final_all, garment_vertex_map)
    previous_garment = mapped_object_vertices(previous_all, garment_vertex_map)
    if final_garment.shape != garment_vertices_cm.shape or not np.isfinite(final_garment).all():
        raise RuntimeError(f"Unexpected PPF garment output: {final_garment.shape}")

    np.save(final_vertices_path, final_garment)
    write_obj(garment_path, final_obj_path, final_garment * 100.0)
    displacement_cm = 100.0 * np.linalg.norm(final_garment - previous_garment, axis=1)
    log_path = Path(fixed_session.info.path) / "stdout.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    contact_counts = [
        int(match.group(1))
        for match in re.finditer(r"^\* num_contact: ([0-9]+)$", log_text, re.MULTILINE)
    ]

    report = {
        "schemaVersion": "patterna.ppf-common-bundle/1.0",
        "status": "completed-requires-acceptance-grading",
        "runtime": {
            "path": str(runtime_root),
            "version": manifest["version"],
            "manifestSha256": sha256(manifest_path),
            "solverSha256": manifest["entrypoints"]["target\\release\\ppf-contact-solver.exe"],
        },
        "gpu": read_gpu_identity(),
        "inputs": {
            "sourceReport": str(source_report_path),
            "sourceReportSha256": sha256(source_report_path),
            "patternSpecificationSha256": source_report["pattern_specification_sha256"],
            "garment": str(garment_path),
            "garmentSha256": sha256(garment_path),
            **garment_identity,
            **body_identity,
            "segmentationSha256": sha256(segmentation_path),
            "restLengthsSha256": sha256(rest_lengths_path),
            "materialCoordinatesSha256": sha256(material_coordinates_path),
            "panelIndexMapSha256": sha256(panel_index_map_path),
        },
        "topology": {
            "garmentVertexCount": len(garment_vertices_cm),
            "garmentFaceCount": len(garment_faces),
            "bodyVertexCount": len(body_vertices_m),
            "bodyFaceCount": len(body_faces),
            "bodyContactActive": body_contact_active,
            "authoredSeamLinkCount": len(seam_links),
            "activeSeamLinkCount": len(active_seam_links),
            "activeThroughSeamPhaseIndex": args.maximum_seam_phase,
            "activeThroughSeamPhaseName": SEAM_PHASE_ORDER[
                args.maximum_seam_phase
            ],
            "weldedVertexReduction": 0,
        },
        "initialStaging": staging,
        "inputGate": {
            "path": str(input_gate_path),
            "sha256": sha256(input_gate_path),
        },
        "fabric": {
            "model": "baraff-witkin",
            "densityKgM2": 0.12,
            "youngModulusPreNormalized": 400.0,
            "poissonRatio": 0.30,
            "bend": 0.20,
            "strainLimit": 0.15,
            "friction": 0.45,
            "physicalThicknessCm": 0.034,
            "clothContactGapCm": 0.20,
            "bodyContactGapCm": 0.40,
            "combinedContactGapCm": 0.30,
            "stitchStiffness": args.stitch_stiffness,
            "stitchLengthFactor": args.stitch_length_factor,
        },
        "simulation": {
            "savedVertexSnapshotCount": latest_frame_index + 1,
            "elapsedSeconds": elapsed,
            "requestedFrames": args.frames,
            "releaseTimeSeconds": args.release_time_seconds,
            "dynamicDtSeconds": args.dt,
            "sessionPath": fixed_session.info.path,
            "contactSamples": len(contact_counts),
            "nonzeroContactSamples": sum(count > 0 for count in contact_counts),
            "maximumContacts": max(contact_counts, default=0),
            "stdoutLogSha256": sha256(log_path),
            "lastFrameMaximumDisplacementCm": float(displacement_cm.max()),
            "lastFrameMeanDisplacementCm": float(displacement_cm.mean()),
            "lastFrameP999DisplacementCm": float(np.percentile(displacement_cm, 99.9)),
        },
        "seams": seam_metrics(final_garment, seam_links),
        "activeSeams": seam_metrics(final_garment, active_seam_links),
        "strain": strain_metrics(final_garment, rest_lengths_cm),
        "acceptancePending": [
            "body edge intersections",
            "cloth self intersections",
            "multi-frame static equilibrium",
            "six-view visual review",
        ],
        "outputs": {
            "finalVertices": str(final_vertices_path),
            "finalVerticesSha256": sha256(final_vertices_path),
            "finalObj": str(final_obj_path),
            "finalObjSha256": sha256(final_obj_path),
            "stagedInitialObj": str(staged_obj_path),
            "stagedInitialObjSha256": sha256(staged_obj_path),
        },
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
