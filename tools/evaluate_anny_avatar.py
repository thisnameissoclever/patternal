#!/usr/bin/env python3
"""Generate bounded Anny body candidates for Patterna backend evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import anny
import numpy as np
import torch
import trimesh


TARGET_HEIGHT_M = 1.67


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def candidate_parameters() -> dict[str, tuple[dict[str, float], dict[str, float]]]:
    base = {
        "gender": 1.0,
        "age": 0.67,
        "muscle": 0.18,
        "weight": 0.62,
        "height": 0.5,
        "proportions": 0.52,
        "cupsize": 1.0,
        "firmness": 0.85,
        "african": 0.72,
        "asian": 0.08,
        "caucasian": 0.20,
    }
    return {
        "macro-large": (base, {}),
        "supported-low": (
            {**base, "firmness": 0.70},
            {"breast-trans-up": 0.20, "breast-volume-vert-up": 0.15},
        ),
        "supported-medium": (
            {**base, "firmness": 0.85},
            {"breast-trans-up": 0.30, "breast-volume-vert-up": 0.25},
        ),
        "supported-firm": (
            {**base, "firmness": 1.0},
            {"breast-trans-up": 0.30, "breast-volume-vert-up": 0.25},
        ),
        "supported-separated": (
            {**base, "firmness": 0.88},
            {
                "breast-trans-up": 0.30,
                "breast-volume-vert-up": 0.25,
                "breast-dist-incr": 0.25,
            },
        ),
        "supported-projected": (
            {**base, "firmness": 0.88},
            {
                "breast-trans-up": 0.30,
                "breast-volume-vert-up": 0.25,
                "breast-dist-incr": 0.15,
                "breast-point-incr": 0.20,
            },
        ),
    }


def main() -> None:
    args = parse_args()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    model = anny.create_fullbody_model(
        rig="default-notoes",
        topology="default",
        local_changes="default",
        triangulate_faces=True,
        all_phenotypes=True,
        extrapolate_phenotypes=True,
    ).to(dtype=torch.float64)
    faces = model.faces.detach().cpu().numpy()
    report: dict[str, object] = {
        "schemaVersion": "patterna.anny-evaluation/1.0",
        "backend": "Anny 0.5",
        "targetHeightCm": TARGET_HEIGHT_M * 100.0,
        "candidates": {},
    }
    for name, (phenotype, local_changes) in candidate_parameters().items():
        with torch.no_grad():
            result = model(
                phenotype_kwargs=phenotype,
                local_changes_kwargs=local_changes,
            )
        vertices = result["vertices"].squeeze(0).detach().cpu().numpy()
        height = float(np.ptp(vertices[:, 2]))
        scale = TARGET_HEIGHT_M / height
        vertices *= scale
        vertices[:, 2] -= float(vertices[:, 2].min())
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        obj_path = output_dir / f"{name}.obj"
        mesh.export(obj_path)
        report["candidates"][name] = {
            "phenotype": phenotype,
            "localChanges": local_changes,
            "sourceHeightCm": height * 100.0,
            "scale": scale,
            "output": str(obj_path),
            "vertexCount": int(len(vertices)),
            "faceCount": int(len(faces)),
            "boundsMeters": {
                "minimum": vertices.min(axis=0).tolist(),
                "maximum": vertices.max(axis=0).tolist(),
            },
        }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
