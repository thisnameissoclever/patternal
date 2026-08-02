#!/usr/bin/env python3
"""Export GarmentCode panel coordinates for a Patterna physical surface."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import pickle
import sys

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GARMENTCODE_ROOT = PROJECT_ROOT / "third_party" / "GarmentCode"
if str(GARMENTCODE_ROOT) not in sys.path:
    sys.path.insert(0, str(GARMENTCODE_ROOT))

from pygarment.meshgen.boxmeshgen import BoxMesh  # noqa: E402


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_obj_faces(path: Path) -> tuple[int, np.ndarray]:
    vertex_count = 0
    faces: list[list[int]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("v "):
            vertex_count += 1
        elif line.startswith("f "):
            corners = line.split()[1:]
            if len(corners) != 3:
                raise ValueError(f"Physical surface must be triangulated: {line}")
            faces.append([int(corner.split("/")[0]) - 1 for corner in corners])
    return vertex_count, np.asarray(faces, dtype=np.int32)


def export(source_report_path: Path, output_path: Path) -> dict[str, object]:
    source_report_path = source_report_path.resolve()
    output_path = output_path.resolve()
    report = json.loads(source_report_path.read_text(encoding="utf-8"))
    pattern_path = Path(report["pattern_specification_path"]).resolve()
    physical_mesh_path = Path(report["physical_mesh_path"]).resolve()
    rest_lengths_path = Path(report["rest_lengths_path"]).resolve()
    resolution_cm = float(report["mesh_resolution_cm"])
    topology_mode = str(report["garment_topology_mode"])

    mesh = BoxMesh(str(pattern_path), resolution_cm)
    mesh.load(topology_mode=topology_mode)
    expected_vertex_count, expected_faces = load_obj_faces(physical_mesh_path)
    actual_faces = np.asarray(mesh.faces, dtype=np.int32)
    if len(mesh.vertices) != expected_vertex_count:
        raise ValueError(
            f"Reconstructed mesh has {len(mesh.vertices)} vertices, expected {expected_vertex_count}."
        )
    if not np.array_equal(actual_faces, expected_faces):
        raise ValueError("Reconstructed panel faces do not match the physical surface.")

    panel_vertices_cm = np.empty((expected_vertex_count, 2), dtype=np.float64)
    for global_index, locations in enumerate(mesh.verts_glob_loc):
        if len(locations) != 1:
            raise ValueError(
                "Material-coordinate export requires one panel-local owner per render vertex."
            )
        panel_name, local_index = locations[0]
        panel_vertices_cm[global_index] = np.asarray(
            mesh.panels[panel_name].panel_vertices[local_index],
            dtype=np.float64,
        )
    if not np.isfinite(panel_vertices_cm).all():
        raise ValueError("Reconstructed panel coordinates contain non-finite values.")

    with rest_lengths_path.open("rb") as stream:
        rest_lengths = pickle.load(stream)
    maximum_rest_length_error_cm = 0.0
    for raw_pair, raw_length in rest_lengths.items():
        first, second = int(raw_pair[0]), int(raw_pair[1])
        reconstructed = float(
            np.linalg.norm(panel_vertices_cm[first] - panel_vertices_cm[second])
        )
        maximum_rest_length_error_cm = max(
            maximum_rest_length_error_cm,
            abs(reconstructed - float(raw_length)),
        )
    if maximum_rest_length_error_cm > 1.0e-8:
        raise ValueError(
            "Reconstructed panel coordinates do not match stored material rest lengths: "
            f"maximum error {maximum_rest_length_error_cm:.12g} cm."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        panel_vertices_cm=panel_vertices_cm,
        panel_faces=actual_faces,
    )
    return {
        "schema_version": "patterna.material-coordinates/1.0",
        "source_report_path": str(source_report_path),
        "source_report_sha256": sha256_file(source_report_path),
        "pattern_specification_path": str(pattern_path),
        "pattern_specification_sha256": sha256_file(pattern_path),
        "physical_mesh_path": str(physical_mesh_path),
        "physical_mesh_sha256": sha256_file(physical_mesh_path),
        "rest_lengths_path": str(rest_lengths_path),
        "rest_lengths_sha256": sha256_file(rest_lengths_path),
        "vertex_count": len(panel_vertices_cm),
        "face_count": len(actual_faces),
        "maximum_rest_length_error_cm": maximum_rest_length_error_cm,
        "output_path": str(output_path),
        "output_sha256": sha256_file(output_path),
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    report = export(args.source_report, args.output)
    metadata_path = args.output.resolve().with_suffix(".json")
    metadata_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
