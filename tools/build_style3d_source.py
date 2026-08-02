#!/usr/bin/env python3
"""Build an exact GarmentCode material surface for Patterna's Style3D solver."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import pickle
import re
import sys

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GARMENTCODE_ROOT = REPOSITORY_ROOT / "third_party" / "GarmentCode"
if str(GARMENTCODE_ROOT) not in sys.path:
    sys.path.insert(0, str(GARMENTCODE_ROOT))

from pygarment.meshgen.boxmeshgen import BoxMesh
from patterna_shell_assembly import arrange_independent_body_aware_panels


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def segmentation_row(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    raise ValueError(f"Unsupported segmentation value: {value!r}")


def normalized_panel_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", value.lower())
    return key[:-5] if key.endswith("panel") else key


def body_aware_vertices(
    arrangement: dict[str, object],
    panel_vertex_indices: dict[str, list[int]],
    vertex_count: int,
) -> np.ndarray:
    raw_panels = arrangement.get("panels")
    if not isinstance(raw_panels, list):
        raise ValueError("Initial arrangement contains no panel list.")
    arranged_by_key: dict[str, dict[str, object]] = {}
    for raw_panel in raw_panels:
        if not isinstance(raw_panel, dict):
            raise ValueError("Initial arrangement contains a non-object panel.")
        identifiers = [raw_panel.get("panelId"), raw_panel.get("pieceId")]
        for identifier in identifiers:
            if not isinstance(identifier, str):
                continue
            key = normalized_panel_key(identifier)
            if key in arranged_by_key and arranged_by_key[key] is not raw_panel:
                raise ValueError(f"Initial arrangement panel key is ambiguous: {identifier}")
            arranged_by_key[key] = raw_panel

    result = np.full((vertex_count, 3), np.nan, dtype=np.float64)
    for source_panel_name, global_indices in panel_vertex_indices.items():
        key = normalized_panel_key(source_panel_name)
        raw_panel = arranged_by_key.get(key)
        if raw_panel is None:
            raise ValueError(
                f"Initial arrangement has no panel matching {source_panel_name}."
            )
        raw_vertices = raw_panel.get("vertices")
        if not isinstance(raw_vertices, list) or len(raw_vertices) != len(global_indices):
            count = len(raw_vertices) if isinstance(raw_vertices, list) else 0
            raise ValueError(
                f"Initial arrangement panel {source_panel_name} has {count} vertices; "
                f"the Style3D material panel has {len(global_indices)}."
            )
        ordered: list[dict[str, object] | None] = [None] * len(global_indices)
        for raw_vertex in raw_vertices:
            if not isinstance(raw_vertex, dict) or not isinstance(raw_vertex.get("index"), int):
                raise ValueError(
                    f"Initial arrangement panel {source_panel_name} has an invalid vertex."
                )
            local_index = int(raw_vertex["index"])
            if local_index < 0 or local_index >= len(ordered) or ordered[local_index] is not None:
                raise ValueError(
                    f"Initial arrangement panel {source_panel_name} has an invalid local index."
                )
            ordered[local_index] = raw_vertex
        if any(value is None for value in ordered):
            raise ValueError(
                f"Initial arrangement panel {source_panel_name} has incomplete local indices."
            )
        for local_index, global_index in enumerate(global_indices):
            raw_vertex = ordered[local_index]
            assert raw_vertex is not None
            coordinates = [raw_vertex.get(axis) for axis in ("x", "y", "z")]
            if not all(isinstance(value, (int, float)) for value in coordinates):
                raise ValueError(
                    f"Initial arrangement panel {source_panel_name} has invalid coordinates."
                )
            # The Unreal compiler emits Z-up coordinates. Style3D and the
            # GarmentCode body boundary use Y-up coordinates.
            result[global_index] = np.asarray(
                [coordinates[0], coordinates[2], coordinates[1]],
                dtype=np.float64,
            )
    if not np.isfinite(result).all():
        raise ValueError("Initial arrangement did not map every Style3D vertex.")
    return result


def write_obj(
    path: Path,
    vertices_cm: np.ndarray,
    faces: np.ndarray,
    texture_coordinates_cm: np.ndarray | None = None,
) -> None:
    lines = [f"v {vertex[0]:.12g} {vertex[1]:.12g} {vertex[2]:.12g}" for vertex in vertices_cm]
    if texture_coordinates_cm is not None:
        lines.extend(
            f"vt {point[0]:.12g} {point[1]:.12g}"
            for point in texture_coordinates_cm
        )
        lines.extend(
            "f " + " ".join(f"{int(index) + 1}/{int(index) + 1}" for index in face)
            for face in faces
        )
    else:
        lines.extend(
            "f " + " ".join(str(int(index) + 1) for index in face)
            for face in faces
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_obj_vertices_centimeters(path: Path) -> np.ndarray:
    vertices = [
        [float(value) * 100.0 for value in line.split()[1:4]]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("v ")
    ]
    result = np.asarray(vertices, dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != 3 or not len(result):
        raise ValueError(f"Body OBJ contains no vertices: {path}")
    if not np.isfinite(result).all():
        raise ValueError(f"Body OBJ contains non-finite vertices: {path}")
    return result


def resolve_inputs(
    source_report_path: Path | None,
    pattern_path: Path | None,
    body_mesh_path: Path | None,
) -> tuple[Path | None, dict[str, object], Path, Path]:
    resolved_source_report = (
        source_report_path.resolve() if source_report_path is not None else None
    )
    source_report = (
        json.loads(resolved_source_report.read_text(encoding="utf-8"))
        if resolved_source_report is not None
        else {}
    )
    if pattern_path is None and "pattern_specification_path" not in source_report:
        raise ValueError("A direct Style3D source requires a pattern specification.")
    if body_mesh_path is None and "body_mesh_path" not in source_report:
        raise ValueError("A direct Style3D source requires a body mesh.")
    resolved_pattern = (
        pattern_path.resolve()
        if pattern_path is not None
        else Path(str(source_report["pattern_specification_path"])).resolve()
    )
    resolved_body = (
        body_mesh_path.resolve()
        if body_mesh_path is not None
        else Path(str(source_report["body_mesh_path"])).resolve()
    )
    if not resolved_pattern.is_file():
        raise FileNotFoundError(f"Pattern specification does not exist: {resolved_pattern}")
    if not resolved_body.is_file():
        raise FileNotFoundError(f"Body mesh does not exist: {resolved_body}")
    return resolved_source_report, source_report, resolved_pattern, resolved_body


def build(
    source_report_path: Path | None,
    output_dir: Path,
    resolution_cm: float,
    *,
    pattern_path: Path | None = None,
    body_mesh_path: Path | None = None,
    initial_arrangement_path: Path | None = None,
    body_segmentation_path: Path | None = None,
    rigid_body_staging: bool = False,
    rigid_body_staging_clearance_cm: float = 2.0,
) -> dict[str, object]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_source_report, source_report, resolved_pattern, resolved_body = resolve_inputs(
        source_report_path,
        pattern_path,
        body_mesh_path,
    )

    mesh = BoxMesh(str(resolved_pattern), resolution_cm)
    mesh.load(topology_mode="explicit")
    vertices_cm = np.asarray(mesh.vertices, dtype=np.float64).copy()
    faces = np.asarray(mesh.faces, dtype=np.int32)
    if len(mesh.verts_glob_loc) != len(vertices_cm):
        raise ValueError("GarmentCode material ownership does not match the rebuilt vertex count.")

    panel_vertices_cm = np.empty((len(vertices_cm), 2), dtype=np.float64)
    for global_index, locations in enumerate(mesh.verts_glob_loc):
        if len(locations) != 1:
            raise ValueError("Explicit Style3D source requires one panel owner per vertex.")
        panel_name, local_index = locations[0]
        panel_vertices_cm[global_index] = np.asarray(
            mesh.panels[panel_name].panel_vertices[local_index],
            dtype=np.float64,
        )

    resolved_body_segmentation = (
        body_segmentation_path.resolve()
        if body_segmentation_path is not None
        else None
    )
    rigid_staging_diagnostics = None
    rigid_staged_vertices_cm = None
    if rigid_body_staging:
        if initial_arrangement_path is not None:
            raise ValueError(
                "Rigid body staging and an initial arrangement are mutually exclusive."
            )
        if (
            not np.isfinite(rigid_body_staging_clearance_cm)
            or rigid_body_staging_clearance_cm <= 0.0
        ):
            raise ValueError("Rigid body staging clearance must be positive and finite.")
        if resolved_body_segmentation is None or not resolved_body_segmentation.is_file():
            raise FileNotFoundError(
                "Rigid body staging requires an existing body segmentation."
            )
        segmentation = json.loads(
            resolved_body_segmentation.read_text(encoding="utf-8")
        )
        torso_indices = np.asarray(segmentation.get("body", []), dtype=np.int32)
        body_vertices_cm = load_obj_vertices_centimeters(resolved_body)
        if torso_indices.ndim != 1 or not len(torso_indices):
            raise ValueError("Body segmentation contains no torso vertices.")
        if torso_indices.min() < 0 or torso_indices.max() >= len(body_vertices_cm):
            raise ValueError("Body segmentation contains an out-of-range vertex.")
        rigid_staging_diagnostics = arrange_independent_body_aware_panels(
            mesh,
            body_vertices_cm[torso_indices],
            clearance_cm=rigid_body_staging_clearance_cm,
            upper_blend_start_cm=1000.0,
            upper_blend_end_cm=1001.0,
            preserve_material_shape=True,
        ).as_dict()
        rigid_staged_vertices_cm = np.asarray(mesh.vertices, dtype=np.float64)

    stem = f"patterna-style3d-source-{resolution_cm:.3f}cm"
    physical_path = output_dir / f"{stem}.obj"
    segmentation_path = output_dir / f"{stem}.segmentation.txt"
    rest_lengths_path = output_dir / f"{stem}.rest-lengths.pickle"
    material_coordinates_path = output_dir / f"{stem}.material-coordinates.npz"
    panel_index_map_path = output_dir / f"{stem}.panel-index-map.json"
    initial_mesh_path = output_dir / f"{stem}.body-aware-initial.obj"
    report_path = output_dir / f"{stem}.report.json"

    write_obj(physical_path, vertices_cm, faces, panel_vertices_cm)
    segmentation_path.write_text(
        "\n".join(segmentation_row(value) for value in mesh.stitch_segmentation) + "\n",
        encoding="utf-8",
    )
    with rest_lengths_path.open("wb") as stream:
        pickle.dump(mesh.orig_lens, stream)
    np.savez_compressed(
        material_coordinates_path,
        panel_vertices_cm=panel_vertices_cm,
        panel_faces=faces,
    )
    panel_vertex_indices: dict[str, list[int]] = {
        panel_name: [-1] * len(panel.panel_vertices)
        for panel_name, panel in mesh.panels.items()
    }
    for global_index, locations in enumerate(mesh.verts_glob_loc):
        panel_name, local_index = locations[0]
        panel_vertex_indices[panel_name][local_index] = global_index
    if any(
        index < 0
        for indices in panel_vertex_indices.values()
        for index in indices
    ):
        raise ValueError("GarmentCode panel index map is incomplete.")
    resolved_initial_arrangement = (
        initial_arrangement_path.resolve()
        if initial_arrangement_path is not None
        else None
    )
    if rigid_staged_vertices_cm is not None:
        write_obj(
            initial_mesh_path,
            rigid_staged_vertices_cm,
            faces,
            panel_vertices_cm,
        )
    elif resolved_initial_arrangement is not None:
        if not resolved_initial_arrangement.is_file():
            raise FileNotFoundError(
                f"Initial arrangement does not exist: {resolved_initial_arrangement}"
            )
        arrangement = json.loads(
            resolved_initial_arrangement.read_text(encoding="utf-8")
        )
        arranged_vertices = body_aware_vertices(
            arrangement,
            panel_vertex_indices,
            len(vertices_cm),
        )
        write_obj(initial_mesh_path, arranged_vertices, faces, panel_vertices_cm)
    panel_index_map_path.write_text(
        json.dumps(
            {
                "schema_version": "patterna.style3d-panel-index-map/1.0",
                "vertex_count": len(vertices_cm),
                "panels": [
                    {
                        "source_panel_name": panel_name,
                        "vertex_indices": indices,
                    }
                    for panel_name, indices in panel_vertex_indices.items()
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    report = dict(source_report)
    report.update(
        {
            "schema_version": "patterna.style3d-source/1.0",
            "accepted": False,
            "rejection_reasons": ["rebuilt source requires a new exact solver evaluation"],
            "source_report_path": (
                str(resolved_source_report)
                if resolved_source_report is not None
                else None
            ),
            "source_report_sha256": (
                sha256_file(resolved_source_report)
                if resolved_source_report is not None
                else None
            ),
            "pattern_specification_path": str(resolved_pattern),
            "pattern_specification_sha256": sha256_file(resolved_pattern),
            "body_mesh_path": str(resolved_body),
            "body_mesh_sha256": sha256_file(resolved_body),
            "physical_mesh_path": str(physical_path),
            "physical_mesh_sha256": sha256_file(physical_path),
            "output_mesh_path": str(
                initial_mesh_path
                if resolved_initial_arrangement is not None
                or rigid_staged_vertices_cm is not None
                else physical_path
            ),
            "output_mesh_sha256": sha256_file(
                initial_mesh_path
                if resolved_initial_arrangement is not None
                or rigid_staged_vertices_cm is not None
                else physical_path
            ),
            "initial_arrangement_path": (
                str(resolved_initial_arrangement)
                if resolved_initial_arrangement is not None
                else None
            ),
            "initial_arrangement_sha256": (
                sha256_file(resolved_initial_arrangement)
                if resolved_initial_arrangement is not None
                else None
            ),
            "body_aware_initial_mesh_path": (
                str(initial_mesh_path)
                if resolved_initial_arrangement is not None
                or rigid_staged_vertices_cm is not None
                else None
            ),
            "body_aware_initial_mesh_sha256": (
                sha256_file(initial_mesh_path)
                if resolved_initial_arrangement is not None
                or rigid_staged_vertices_cm is not None
                else None
            ),
            "rigid_body_staging": rigid_staging_diagnostics,
            "body_segmentation_path": (
                str(resolved_body_segmentation)
                if resolved_body_segmentation is not None
                else None
            ),
            "body_segmentation_sha256": (
                sha256_file(resolved_body_segmentation)
                if resolved_body_segmentation is not None
                else None
            ),
            "panel_ownership_path": str(segmentation_path),
            "panel_ownership_sha256": sha256_file(segmentation_path),
            "rest_lengths_path": str(rest_lengths_path),
            "rest_lengths_sha256": sha256_file(rest_lengths_path),
            "material_coordinates_path": str(material_coordinates_path),
            "material_coordinates_sha256": sha256_file(material_coordinates_path),
            "panel_index_map_path": str(panel_index_map_path),
            "panel_index_map_sha256": sha256_file(panel_index_map_path),
            "mesh_resolution_cm": resolution_cm,
            "garment_topology_mode": "explicit",
            "physical_vertex_count": len(vertices_cm),
            "physical_face_count": len(faces),
            "seam_link_count": sum(
                1
                for value in mesh.stitch_segmentation
                for label in ([value] if isinstance(value, str) else value)
                if str(label).startswith("seam_link_")
            )
            // 2,
        }
    )
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {
        "report_path": str(report_path),
        "physical_mesh_path": str(physical_path),
        "material_coordinates_path": str(material_coordinates_path),
        "panel_index_map_path": str(panel_index_map_path),
        "vertex_count": len(vertices_cm),
        "face_count": len(faces),
        "seam_link_count": report["seam_link_count"],
        "mesh_resolution_cm": resolution_cm,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", type=Path)
    parser.add_argument("--pattern", type=Path)
    parser.add_argument("--body", type=Path)
    parser.add_argument("--initial-arrangement", type=Path)
    parser.add_argument("--body-segmentation", type=Path)
    parser.add_argument("--rigid-body-staging", action="store_true")
    parser.add_argument(
        "--rigid-body-staging-clearance-cm",
        type=float,
        default=2.0,
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--resolution-cm", required=True, type=float)
    args = parser.parse_args()
    if not np.isfinite(args.resolution_cm) or args.resolution_cm <= 0.0:
        raise ValueError("--resolution-cm must be finite and positive.")
    if args.source_report is None and (args.pattern is None or args.body is None):
        parser.error("provide --source-report, or provide both --pattern and --body")
    print(
        json.dumps(
            build(
                args.source_report,
                args.output_dir,
                args.resolution_cm,
                pattern_path=args.pattern,
                body_mesh_path=args.body,
                initial_arrangement_path=args.initial_arrangement,
                body_segmentation_path=args.body_segmentation,
                rigid_body_staging=args.rigid_body_staging,
                rigid_body_staging_clearance_cm=(
                    args.rigid_body_staging_clearance_cm
                ),
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
