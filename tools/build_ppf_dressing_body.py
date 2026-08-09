#!/usr/bin/env python3
"""Build a hash-bound reduced body used only for staged PPF dressing."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from tools.run_ppf_patterna_bundle import read_obj, write_obj


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scaled_body_vertices(
    vertices,
    scale_xz: float,
    *,
    upper_scale_xz: float | None = None,
    blend_start_y_m: float = 1.32,
    blend_end_y_m: float = 1.42,
):
    points = np.asarray(vertices, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or not len(points):
        raise ValueError("Dressing body requires an N by 3 vertex array.")
    if not np.isfinite(points).all():
        raise ValueError("Dressing body vertices must be finite.")
    if not np.isfinite(scale_xz) or scale_xz <= 0.0 or scale_xz >= 1.0:
        raise ValueError("Dressing body XZ scale must be between zero and one.")
    upper_scale = scale_xz if upper_scale_xz is None else upper_scale_xz
    if not np.isfinite(upper_scale) or upper_scale <= 0.0 or upper_scale >= 1.0:
        raise ValueError("Upper dressing body XZ scale must be between zero and one.")
    if not np.isfinite([blend_start_y_m, blend_end_y_m]).all():
        raise ValueError("Dressing body blend heights must be finite.")
    if blend_end_y_m <= blend_start_y_m:
        raise ValueError("Dressing body blend end must exceed its start.")
    center_xz = 0.5 * (
        points[:, (0, 2)].min(axis=0) + points[:, (0, 2)].max(axis=0)
    )
    blend = np.clip(
        (points[:, 1] - blend_start_y_m) / (blend_end_y_m - blend_start_y_m),
        0.0,
        1.0,
    )
    blend = blend * blend * (3.0 - 2.0 * blend)
    scales = scale_xz * (1.0 - blend) + upper_scale * blend
    result = points.copy()
    result[:, 0] = center_xz[0] + scales * (points[:, 0] - center_xz[0])
    result[:, 2] = center_xz[1] + scales * (points[:, 2] - center_xz[1])
    return result, center_xz, scales


def build(
    source_body: Path,
    source_report: Path,
    output_directory: Path,
    scale_xz: float,
    upper_scale_xz: float | None = None,
    blend_start_y_m: float = 1.32,
    blend_end_y_m: float = 1.42,
) -> dict[str, object]:
    source_body = source_body.resolve()
    source_report = source_report.resolve()
    output_directory = output_directory.resolve()
    if not source_body.is_file() or not source_report.is_file():
        raise FileNotFoundError("Accepted collision body or report is missing.")
    report = json.loads(source_report.read_text(encoding="utf-8"))
    if report.get("schemaVersion") != "patterna.body-collision-proxy/1.0":
        raise ValueError("Dressing body source must be an accepted collision proxy.")
    if report.get("accepted") is not True:
        raise ValueError("Dressing body source collision proxy is not accepted.")
    source_hash = sha256(source_body)
    if report.get("outputs", {}).get("proxyMeshSha256") != source_hash:
        raise ValueError("Collision proxy hash does not match its accepted report.")
    canonical_hash = report.get("inputs", {}).get("sourceMeshSha256")
    if not isinstance(canonical_hash, str) or not canonical_hash:
        raise ValueError("Collision proxy report has no canonical body identity.")

    vertices, faces = read_obj(source_body)
    staged, center_xz, vertex_scales = scaled_body_vertices(
        vertices,
        scale_xz,
        upper_scale_xz=upper_scale_xz,
        blend_start_y_m=blend_start_y_m,
        blend_end_y_m=blend_end_y_m,
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    upper_scale = scale_xz if upper_scale_xz is None else upper_scale_xz
    scale_label = (
        f"{scale_xz:.3f}xz"
        if upper_scale_xz is None
        else f"{scale_xz:.3f}to{upper_scale:.3f}xz"
    )
    output_body = output_directory / f"patterna-dressing-body-{scale_label}.obj"
    output_report = output_directory / f"patterna-dressing-body-{scale_label}.report.json"
    write_obj(source_body, output_body, staged)
    output_hash = sha256(output_body)

    issues = []
    if not np.array_equal(staged[:, 1], vertices[:, 1]):
        issues.append("vertical coordinates changed")
    if len(staged) != len(vertices):
        issues.append("vertex count changed")
    if not np.isfinite(staged).all():
        issues.append("output contains non-finite vertices")
    source_triangles = vertices[faces]
    output_triangles = staged[faces]
    source_normals = np.cross(
        source_triangles[:, 1] - source_triangles[:, 0],
        source_triangles[:, 2] - source_triangles[:, 0],
    )
    output_normals = np.cross(
        output_triangles[:, 1] - output_triangles[:, 0],
        output_triangles[:, 2] - output_triangles[:, 0],
    )
    flipped_face_count = int(
        np.count_nonzero(np.einsum("ij,ij->i", source_normals, output_normals) <= 0.0)
    )
    if flipped_face_count:
        issues.append(f"{flipped_face_count} face orientations changed")
    document = {
        "schemaVersion": "patterna.ppf-dressing-body/1.0",
        "accepted": not issues,
        "issues": issues,
        "role": "temporary-reduced-contact-body",
        "inputs": {
            "canonicalBodySha256": canonical_hash,
            "sourceCollisionBody": str(source_body),
            "sourceCollisionBodySha256": source_hash,
            "sourceCollisionBodyReport": str(source_report),
            "sourceCollisionBodyReportSha256": sha256(source_report),
        },
        "transform": {
            "method": (
                "uniform-xz-scale-about-bounds-center"
                if upper_scale_xz is None
                else "smooth-upper-taper-xz-scale-about-bounds-center"
            ),
            "scaleXZ": scale_xz,
            "upperScaleXZ": upper_scale,
            "blendStartYM": blend_start_y_m,
            "blendEndYM": blend_end_y_m,
            "minimumAppliedScaleXZ": float(vertex_scales.min()),
            "maximumAppliedScaleXZ": float(vertex_scales.max()),
            "centerXM": float(center_xz[0]),
            "centerZM": float(center_xz[1]),
            "verticalScale": 1.0,
        },
        "topology": {
            "vertexCount": len(vertices),
            "faceCount": len(faces),
            "sourceFaceCount": len(faces),
            "sourceVertexCount": len(vertices),
            "flippedFaceCount": flipped_face_count,
        },
        "bounds": {
            "sourceMinimumM": vertices.min(axis=0).tolist(),
            "sourceMaximumM": vertices.max(axis=0).tolist(),
            "outputMinimumM": staged.min(axis=0).tolist(),
            "outputMaximumM": staged.max(axis=0).tolist(),
        },
        "outputs": {
            "dressingBody": str(output_body),
            "dressingBodySha256": output_hash,
        },
    }
    output_report.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    if issues:
        raise ValueError("Dressing body gate failed: " + "; ".join(issues))
    return {
        "body": str(output_body),
        "bodySha256": output_hash,
        "report": str(output_report),
        "reportSha256": sha256(output_report),
        "scaleXZ": scale_xz,
        "upperScaleXZ": upper_scale,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-body", required=True, type=Path)
    parser.add_argument("--source-report", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--scale-xz", required=True, type=float)
    parser.add_argument("--upper-scale-xz", type=float)
    parser.add_argument("--blend-start-y-m", type=float, default=1.32)
    parser.add_argument("--blend-end-y-m", type=float, default=1.42)
    args = parser.parse_args()
    print(
        json.dumps(
            build(
                args.source_body,
                args.source_report,
                args.output_directory,
                args.scale_xz,
                args.upper_scale_xz,
                args.blend_start_y_m,
                args.blend_end_y_m,
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
