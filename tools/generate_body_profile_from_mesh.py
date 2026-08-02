#!/usr/bin/env python3
"""Generate Patterna's compiler body profile from the exact simulation mesh."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import trimesh


SAMPLING_METHOD = "segmented-triangle-plane-intersection"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--body",
        type=Path,
        default=Path("third_party/GarmentCode/assets/bodies/patterna_mpfb_female.obj"),
    )
    parser.add_argument(
        "--segmentation",
        type=Path,
        default=Path(
            "third_party/GarmentCode/assets/bodies/"
            "patterna_mpfb_female.segmentation.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("PatternaUnreal/Saved/Patterna/MPFB/LiveBodyProfile.json"),
    )
    parser.add_argument("--lowest-height-cm", type=float, default=95.0)
    parser.add_argument("--highest-height-cm", type=float, default=139.0)
    parser.add_argument("--step-cm", type=float, default=2.0)
    parser.add_argument("--angular-sectors", type=int, default=72)
    parser.add_argument(
        "--mesh-units",
        choices=("meters", "centimeters"),
        default="meters",
    )
    return parser.parse_args()


def resolve(repo_root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def triangle_plane_points(triangle: np.ndarray, height: float) -> list[np.ndarray]:
    points: list[np.ndarray] = []
    for start_index, end_index in ((0, 1), (1, 2), (2, 0)):
        start = triangle[start_index]
        end = triangle[end_index]
        start_delta = start[1] - height
        end_delta = end[1] - height
        if abs(start_delta) < 1.0e-8:
            points.append(start[[0, 2]])
        if start_delta * end_delta < 0.0:
            blend = -start_delta / (end_delta - start_delta)
            point = start + blend * (end - start)
            points.append(point[[0, 2]])
    unique: list[np.ndarray] = []
    for point in points:
        if not any(np.linalg.norm(point - existing) < 1.0e-6 for existing in unique):
            unique.append(point)
    return unique


def outer_surface(points: np.ndarray, center: np.ndarray, sectors: int) -> list[dict[str, float]]:
    offsets = points - center
    angles = np.arctan2(offsets[:, 1], offsets[:, 0])
    radii = np.linalg.norm(offsets, axis=1)
    sector_width = 2.0 * math.pi / sectors
    results: list[dict[str, float]] = []
    for sector in range(sectors):
        center_angle = -math.pi + (sector + 0.5) * sector_width
        wrapped = (angles - center_angle + math.pi) % (2.0 * math.pi) - math.pi
        candidates = np.flatnonzero(np.abs(wrapped) <= sector_width)
        if candidates.size == 0:
            continue
        index = int(candidates[np.argmax(radii[candidates])])
        point = points[index]
        angle = float(math.atan2(point[1] - center[1], point[0] - center[0]))
        results.append(
            {
                "angleRadians": angle,
                "radiusCm": float(np.linalg.norm(point - center)),
                "xCm": float(point[0]),
                "yCm": float(point[1]),
            }
        )
    return sorted(results, key=lambda point: point["angleRadians"])


def ellipse_circumference(width: float, depth: float) -> float:
    a = width * 0.5
    b = depth * 0.5
    h = ((a - b) ** 2) / ((a + b) ** 2)
    return math.pi * (a + b) * (1.0 + 3.0 * h / (10.0 + math.sqrt(4.0 - 3.0 * h)))


def main() -> None:
    args = parse_args()
    if args.step_cm <= 0 or args.angular_sectors < 24:
        raise ValueError("The profile requires a positive step and at least 24 sectors.")
    repo_root = Path(__file__).resolve().parents[1]
    body_path = resolve(repo_root, args.body)
    segmentation_path = resolve(repo_root, args.segmentation)
    output_path = resolve(repo_root, args.output)

    loaded = trimesh.load(body_path, process=False, maintain_order=True)
    if not isinstance(loaded, trimesh.Trimesh):
        raise TypeError(f"Expected one body mesh, received {type(loaded).__name__}.")
    vertices = np.asarray(loaded.vertices, dtype=float)
    if args.mesh_units == "meters":
        vertices *= 100.0
    faces = np.asarray(loaded.faces, dtype=int)
    segmentation = json.loads(segmentation_path.read_text(encoding="utf-8"))
    torso_vertices = set(int(index) for index in segmentation["body"])
    torso_faces = faces[
        np.asarray(
            [all(int(index) in torso_vertices for index in face) for face in faces],
            dtype=bool,
        )
    ]

    sections: list[dict[str, object]] = []
    heights = np.arange(
        args.lowest_height_cm,
        args.highest_height_cm + args.step_cm * 0.5,
        args.step_cm,
    )
    for height in heights:
        candidate_faces = torso_faces[
            (vertices[torso_faces, 1].min(axis=1) <= height)
            & (vertices[torso_faces, 1].max(axis=1) >= height)
        ]
        intersections: list[np.ndarray] = []
        for face in candidate_faces:
            intersections.extend(triangle_plane_points(vertices[face], float(height)))
        points = np.asarray(intersections, dtype=float)
        if len(points) < 64:
            raise RuntimeError(
                f"Body section {height:.1f} cm has only {len(points)} intersections."
            )
        lower = np.percentile(points, 5.0, axis=0)
        upper = np.percentile(points, 95.0, axis=0)
        center = (lower + upper) * 0.5
        width, depth = upper - lower
        surface = outer_surface(points, center, args.angular_sectors)
        if len(surface) < 24:
            raise RuntimeError(
                f"Body section {height:.1f} cm covers only {len(surface)} sectors."
            )
        sections.append(
            {
                "heightCm": float(height),
                "widthCm": float(width),
                "depthCm": float(depth),
                "centerXCm": float(center[0]),
                "centerYCm": float(center[1]),
                "ellipseCircumferenceCm": ellipse_circumference(float(width), float(depth)),
                "sampleCount": int(len(points)),
                "surfacePointCount": len(surface),
                "surfacePoints": surface,
            }
        )

    payload = {
        "schemaVersion": "patterna.live-body-profile/1.1",
        "bodyAssetPath": str(body_path),
        "bodySha256": hashlib.sha256(body_path.read_bytes()).hexdigest(),
        "segmentationPath": str(segmentation_path),
        "segmentationSha256": hashlib.sha256(segmentation_path.read_bytes()).hexdigest(),
        "sourceMeshUnits": args.mesh_units,
        "sampleHalfBandCm": 0.0,
        "lowestSampleHeightCm": args.lowest_height_cm,
        "highestSampleHeightCm": args.highest_height_cm,
        "sampleHeightStepCm": args.step_cm,
        "lowerPercentile": 0.05,
        "upperPercentile": 0.95,
        "surfaceSampling": SAMPLING_METHOD,
        "sections": sections,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path),
                "bodySha256": payload["bodySha256"],
                "sectionCount": len(sections),
                "minimumIntersections": min(section["sampleCount"] for section in sections),
                "minimumSectors": min(section["surfacePointCount"] for section in sections),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
