#!/usr/bin/env python3
"""Collect and grade an existing headless PPF Patterna session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tomllib

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.run_ppf_patterna_bundle import (
    load_rest_lengths,
    load_seam_links,
    mapped_object_vertices,
    prepare_runtime,
    read_obj,
    require_source_path,
    resolve_body_mesh,
    seam_metrics,
    sha256,
    strain_metrics,
    write_obj,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--source-report", required=True, type=Path)
    parser.add_argument("--body-override", type=Path)
    parser.add_argument("--body-override-report", type=Path)
    parser.add_argument("--session-directory", required=True, type=Path)
    parser.add_argument("--staged-initial", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--minimum-simulated-frames", type=int, default=20)
    return parser.parse_args()


def sorted_frame_paths(output_directory: Path) -> list[Path]:
    paths = list(output_directory.glob("vert_*.bin"))
    invalid = [path for path in paths if not re.fullmatch(r"vert_[0-9]+", path.stem)]
    if invalid:
        raise ValueError(f"PPF output has invalid frame names: {invalid[:8]}")
    return sorted(paths, key=lambda path: int(path.stem.split("_")[1]))


def native_session_parameters(session_directory: Path) -> dict[str, object]:
    parameter_path = session_directory / "param.toml"
    if not parameter_path.is_file():
        raise FileNotFoundError(f"PPF session parameters are missing: {parameter_path}")
    document = tomllib.loads(parameter_path.read_text(encoding="utf-8"))
    parameters = document.get("param", {})
    if not isinstance(parameters, dict):
        raise ValueError("PPF session parameter file has no parameter table.")
    return parameters


def configured_frame_count(session_directory: Path) -> int:
    frames = native_session_parameters(session_directory).get("frames")
    if not isinstance(frames, int) or frames < 1:
        raise ValueError("PPF session parameter file has no valid frame count.")
    return frames


def main() -> None:
    import numpy as np

    args = parse_args()
    runtime_root = args.runtime_root.resolve()
    source_report_path = args.source_report.resolve()
    session_directory = args.session_directory.resolve()
    staged_initial_path = args.staged_initial.resolve()
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    manifest, manifest_path = prepare_runtime(runtime_root)
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    garment_path = require_source_path(source_report, "physical_mesh_path")
    body_path, body_identity = resolve_body_mesh(
        source_report,
        args.body_override,
        args.body_override_report,
    )
    segmentation_path = require_source_path(source_report, "panel_ownership_path")
    rest_lengths_path = require_source_path(source_report, "rest_lengths_path")
    if not staged_initial_path.is_file():
        raise FileNotFoundError(f"Staged initial mesh is missing: {staged_initial_path}")

    finished_path = session_directory / "output" / "finished.txt"
    error_path = session_directory / "error.log"
    stdout_path = session_directory / "stdout.log"
    map_path = session_directory / "map.pickle"
    for path in (finished_path, error_path, stdout_path, map_path):
        if not path.is_file():
            raise FileNotFoundError(f"PPF session evidence is missing: {path}")
    error_text = error_path.read_text(encoding="utf-8", errors="replace").strip()
    if error_text:
        raise RuntimeError(f"PPF solver error log is not empty: {error_path}")

    sys.path.insert(0, str(runtime_root))
    from frontend import _cbor_bridge_ as cbor_bridge

    vertex_map = cbor_bridge.loads_vertex_map(map_path.read_bytes())
    garment_vertex_map = vertex_map.get("patterna-garment")
    if garment_vertex_map is None:
        raise ValueError("PPF session map has no patterna-garment object.")
    frame_paths = sorted_frame_paths(session_directory / "output")
    if len(frame_paths) < 2:
        raise RuntimeError("PPF session has fewer than two vertex frames.")

    expected_global_vertices = (session_directory / "bin" / "vert_dmap.bin").stat().st_size // 4
    garment_snapshots = []
    for path in frame_paths:
        global_vertices = np.fromfile(path, dtype=np.float32)
        if global_vertices.size != expected_global_vertices * 3:
            raise ValueError(f"PPF frame size does not match the scene: {path}")
        garment_snapshots.append(
            mapped_object_vertices(
                global_vertices.reshape(expected_global_vertices, 3),
                garment_vertex_map,
            ).astype(np.float64)
        )
    previous_garment, final_garment = garment_snapshots[-2:]

    source_vertices_cm, source_faces = read_obj(garment_path)
    body_vertices_m, body_faces = read_obj(body_path)
    if final_garment.shape != source_vertices_cm.shape:
        raise ValueError("Collected PPF garment topology does not match the source.")
    seam_links = load_seam_links(segmentation_path, len(source_vertices_cm))
    rest_lengths = load_rest_lengths(rest_lengths_path, len(source_vertices_cm))
    seams = seam_metrics(final_garment, seam_links)
    strain = strain_metrics(final_garment, rest_lengths)
    displacement_cm = 100.0 * np.linalg.norm(final_garment - previous_garment, axis=1)
    progression = []
    for snapshot_index, (path, snapshot) in enumerate(
        zip(frame_paths, garment_snapshots)
    ):
        snapshot_seams = seam_metrics(snapshot, seam_links)
        snapshot_strain = strain_metrics(snapshot, rest_lengths)
        entry = {
            "nativeFrameIndex": int(path.stem.split("_")[1]),
            "maximumSeamSeparationCm": snapshot_seams["maximumSeparationCm"],
            "meanSeamSeparationCm": snapshot_seams["meanSeparationCm"],
            "p95SeamSeparationCm": snapshot_seams["p95SeparationCm"],
            "p95StrainRatio": snapshot_strain["p95Ratio"],
            "p999StrainRatio": snapshot_strain["p999Ratio"],
        }
        if snapshot_index > 0:
            motion = 100.0 * np.linalg.norm(
                snapshot - garment_snapshots[snapshot_index - 1], axis=1
            )
            entry.update(
                {
                    "maximumDisplacementCm": float(motion.max()),
                    "meanDisplacementCm": float(motion.mean()),
                    "p999DisplacementCm": float(np.percentile(motion, 99.9)),
                }
            )
        progression.append(entry)

    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    contacts = [
        int(match.group(1))
        for match in re.finditer(r"^\* num_contact: ([0-9]+)$", stdout_text, re.MULTILINE)
    ]
    session_parameters = native_session_parameters(session_directory)
    simulated_frames = configured_frame_count(session_directory)
    stiffness_path = session_directory / "bin" / "stitch_stiffness.bin"
    stitch_stiffness = np.fromfile(stiffness_path, dtype=np.float32)
    if stitch_stiffness.size != len(seam_links):
        raise ValueError("PPF stitch-stiffness evidence does not match authored seams.")
    elapsed_seconds = max(
        0.0,
        finished_path.stat().st_mtime - frame_paths[0].stat().st_mtime,
    )
    rejection_reasons: list[str] = []
    if simulated_frames < args.minimum_simulated_frames:
        rejection_reasons.append(
            f"simulated frames {simulated_frames} are below required "
            f"{args.minimum_simulated_frames}"
        )
    if float(displacement_cm.max()) > 0.01 or float(np.mean(displacement_cm)) > 0.001:
        rejection_reasons.append("solver did not reach static equilibrium")
    if float(seams["maximumSeparationCm"]) > 0.25:
        rejection_reasons.append(
            f"maximum seam separation {seams['maximumSeparationCm']:.3f} cm exceeds 0.250 cm"
        )
    for key, label, limit in (
        ("p95Ratio", "95th-percentile", 0.15),
        ("p999Ratio", "99.9th-percentile", 0.29),
        ("p9999Ratio", "99.99th-percentile", 0.55),
    ):
        if float(strain[key]) > limit:
            rejection_reasons.append(
                f"{label} edge strain {strain[key]:.3f} exceeds {limit:.3f}"
            )
    if float(strain["highStrainEdgeFraction"]) > 0.0005:
        rejection_reasons.append(
            "high-strain edge fraction "
            f"{strain['highStrainEdgeFraction']:.6f} exceeds 0.000500"
        )

    final_vertices_path = output_directory / "final-garment-vertices.npy"
    final_obj_path = output_directory / "patterna-ppf-final.obj"
    np.save(final_vertices_path, final_garment)
    write_obj(garment_path, final_obj_path, final_garment * 100.0)
    report = {
        "schemaVersion": "patterna.ppf-common-bundle-collection/1.0",
        "status": "rejected" if rejection_reasons else "requires-remaining-acceptance",
        "rejectionReasons": rejection_reasons,
        "acceptancePending": [
            "body edge intersections",
            "cloth self intersections",
            "six-view visual review",
        ],
        "runtime": {
            "path": str(runtime_root),
            "version": manifest["version"],
            "manifestSha256": sha256(manifest_path),
            "solverSha256": manifest["entrypoints"]["target\\release\\ppf-contact-solver.exe"],
        },
        "inputs": {
            "sourceReport": str(source_report_path),
            "sourceReportSha256": sha256(source_report_path),
            "patternSpecificationSha256": source_report["pattern_specification_sha256"],
            "garmentSha256": sha256(garment_path),
            **body_identity,
            "stagedInitialSha256": sha256(staged_initial_path),
        },
        "topology": {
            "garmentVertexCount": len(source_vertices_cm),
            "garmentFaceCount": len(source_faces),
            "bodyVertexCount": len(body_vertices_m),
            "bodyFaceCount": len(body_faces),
            "authoredSeamLinkCount": len(seam_links),
            "weldedVertexReduction": 0,
        },
        "simulation": {
            "simulatedFrameCount": simulated_frames,
            "savedVertexSnapshotCount": len(frame_paths),
            "stitchLengthFactor": session_parameters.get("stitch_length_factor"),
            "stitchStiffnessMinimum": float(stitch_stiffness.min()),
            "stitchStiffnessMaximum": float(stitch_stiffness.max()),
            "elapsedSeconds": elapsed_seconds,
            "secondsPerFrame": elapsed_seconds / max(simulated_frames, 1),
            "contactSamples": len(contacts),
            "nonzeroContactSamples": sum(value > 0 for value in contacts),
            "maximumContacts": max(contacts, default=0),
            "lastFrameMaximumDisplacementCm": float(displacement_cm.max()),
            "lastFrameMeanDisplacementCm": float(displacement_cm.mean()),
            "lastFrameP999DisplacementCm": float(np.percentile(displacement_cm, 99.9)),
            "finishedMarkerSha256": sha256(finished_path),
            "stdoutLogSha256": sha256(stdout_path),
            "vertexMapSha256": sha256(map_path),
            "progression": progression,
        },
        "seams": seams,
        "strain": strain,
        "outputs": {
            "finalVertices": str(final_vertices_path),
            "finalVerticesSha256": sha256(final_vertices_path),
            "finalObj": str(final_obj_path),
            "finalObjSha256": sha256(final_obj_path),
        },
    }
    report_path = output_directory / "ppf-patterna-collection-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
