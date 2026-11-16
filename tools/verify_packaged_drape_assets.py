#!/usr/bin/env python3
"""Check exported drape assets against the packaged renderer's own parsers.

``Patternal/Assets/avatar3d.html`` reads the body with ``parseProductionObj``
and the garment with ``parseTexturedObj``. Both throw on input they cannot use,
and a throw inside the viewport surfaces only as a one-line error banner, so a
malformed export would look like a rendering failure rather than a bad file.

This verifier reimplements the two parsers' acceptance rules and their scene
transform, then reports what the renderer would actually see: how many surface
vertices and texture corners survive, where the meshes land in scene space, and
whether the garment sits on the body rather than through it. It is an
independent check on the exporter and makes no acceptance claim of its own.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

SCHEMA_VERSION = "patterna.packaged-drape-asset-verification/1.0"
# avatar3d.html transforms both meshes into scene space the same way: scale to
# meters, double, then drop the floor to y = -1.67.
SCENE_SCALE = 2.0
SCENE_FLOOR = -1.67
CENTIMETERS_TO_METERS = 0.01


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser.parse_args()


def parse_production_obj(source: str) -> dict:
    """Mirror of parseProductionObj for a body mesh in meters."""
    vertices: list[list[float]] = []
    indices: list[int] = []
    for line in source.splitlines():
        if line.startswith("v "):
            parts = line.split()
            vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif line.startswith("f "):
            face = [int(token.split("/")[0]) - 1 for token in line.split()[1:]]
            if len(face) < 3 or any(v < 0 or v >= len(vertices) for v in face):
                continue
            for corner in range(1, len(face) - 1):
                indices.extend((face[0], face[corner], face[corner + 1]))
    if len(vertices) < 1000 or len(indices) < 3000:
        raise ValueError("The renderer would reject this body as incomplete.")
    scene = np.asarray(vertices, dtype=np.float64) * SCENE_SCALE
    scene[:, 1] += SCENE_FLOOR
    return {
        "scenePositions": scene,
        "faces": np.asarray(indices, dtype=np.int64).reshape(-1, 3),
        "triangleCount": len(indices) // 3,
    }


def parse_textured_obj(source: str) -> dict:
    """Mirror of parseTexturedObj for a garment mesh in centimeters."""
    vertices: list[list[float]] = []
    uvs: list[list[float]] = []
    faces: list[list[tuple[int, int]]] = []
    line_groups: dict[str, list[tuple[int, int]]] = {}
    active = "default"
    for line in source.splitlines():
        if line.startswith("v "):
            parts = line.split()
            vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif line.startswith("vt "):
            parts = line.split()
            uvs.append([float(parts[1]), float(parts[2])])
        elif line.startswith("g "):
            parts = line.split()
            active = parts[1] if len(parts) > 1 else "default"
        elif line.startswith("l "):
            members = [int(token.split("/")[0]) - 1 for token in line.split()[1:]]
            if len(members) >= 2 and all(0 <= v < len(vertices) for v in members):
                segments = line_groups.setdefault(active, [])
                for index in range(1, len(members)):
                    segments.append((members[index - 1], members[index]))
        elif line.startswith("f "):
            corners = []
            for token in line.split()[1:]:
                parts = token.split("/")
                uv = int(parts[1]) - 1 if len(parts) > 1 and parts[1] else -1
                corners.append((int(parts[0]) - 1, uv))
            if len(corners) >= 3 and all(
                0 <= vertex < len(vertices) for vertex, _ in corners
            ):
                faces.append(corners)
    if len(vertices) < 10 or len(faces) < 8:
        raise ValueError("The renderer would reject this garment as incomplete.")

    unique_corners = {corner for face in faces for corner in face}
    missing_uv = [corner for corner in unique_corners if not 0 <= corner[1] < len(uvs)]
    surface_vertices = {vertex for face in faces for vertex, _ in face}
    scene = np.asarray(vertices, dtype=np.float64) * CENTIMETERS_TO_METERS * SCENE_SCALE
    scene[:, 1] += SCENE_FLOOR
    triangles = [
        [face[0][0], face[corner][0], face[corner + 1][0]]
        for face in faces
        for corner in range(1, len(face) - 1)
    ]
    return {
        "scenePositions": scene,
        "faces": np.asarray(triangles, dtype=np.int64).reshape(-1, 3),
        "triangleCount": sum(len(face) - 2 for face in faces),
        "uvCornerCount": len(unique_corners),
        "surfaceVertexCount": len(surface_vertices),
        "cornersMissingTexture": len(missing_uv),
        "textureCoordinates": np.asarray(uvs, dtype=np.float64),
        "seamSegments": line_groups.get("patterna_seams", []),
        "edgeSegments": line_groups.get("patterna_edges", []),
    }


def convex_hull_perimeter(points: np.ndarray) -> float:
    """Perimeter of the convex hull of a planar point set, by monotone chain.

    A hull is used rather than an angular sweep about the centroid because at
    chest and waist height a horizontal plane cuts the arms as well as the
    torso. Sweeping by angle across those disjoint rings threads a path between
    them and returns a number many times the true girth; a hull cannot.
    """
    if len(points) < 3:
        return 0.0
    order = np.lexsort((points[:, 1], points[:, 0]))
    ordered = points[order]

    def half(sequence: np.ndarray) -> list[np.ndarray]:
        chain: list[np.ndarray] = []
        for point in sequence:
            while len(chain) >= 2:
                first = chain[-1] - chain[-2]
                second = point - chain[-2]
                if first[0] * second[1] - first[1] * second[0] > 0:
                    break
                chain.pop()
            chain.append(point)
        return chain

    hull = half(ordered)[:-1] + half(ordered[::-1])[:-1]
    if len(hull) < 3:
        return 0.0
    loop = np.vstack([np.asarray(hull), np.asarray(hull)[:1]])
    return float(np.sum(np.linalg.norm(np.diff(loop, axis=0), axis=1)))


def section_outline(
    points: np.ndarray, faces: np.ndarray, height: float, torso_half_width: float
) -> float:
    """Girth of the torso where the mesh crosses one horizontal plane."""
    signed = points[:, 1] - height
    crossings: list[np.ndarray] = []
    for triangle in faces:
        values = signed[triangle]
        if np.all(values > 0) or np.all(values < 0):
            continue
        corners = points[triangle]
        for first, second in ((0, 1), (1, 2), (2, 0)):
            a, b = values[first], values[second]
            if a == b or (a > 0) == (b > 0):
                continue
            ratio = a / (a - b)
            crossings.append(corners[first] + ratio * (corners[second] - corners[first]))
    if len(crossings) < 3:
        return 0.0
    flat = np.asarray(crossings)
    # Drop the arms, which the same plane also cuts at these heights.
    flat = flat[np.abs(flat[:, 0]) <= torso_half_width]
    if len(flat) < 3:
        return 0.0
    return convex_hull_perimeter(flat[:, [0, 2]])


def fit_profile(
    garment: np.ndarray,
    garment_faces: np.ndarray,
    body: np.ndarray,
    body_faces: np.ndarray,
    stations: int = 9,
) -> list[dict]:
    """Girth of garment and body at matched heights, and the ease between them.

    A garment that is the right size for a body shows a positive, roughly even
    gap between the two girths. A negative gap means the cloth is smaller than
    what it covers, and a gap that swings widely along the body is a garment cut
    for different proportions, which is what a drag line or a flaring hem is
    before it becomes visible.
    """
    low = float(garment[:, 1].min())
    high = float(garment[:, 1].max())
    span = high - low
    # The torso is the part of the body near the centre line; the arms reach
    # far outside it in this stance. Half of the garment's own half-width is a
    # generous torso bound that no arm falls inside.
    torso_half_width = 0.55 * float(np.abs(garment[:, 0]).max())
    rows: list[dict] = []
    # Stay clear of the hem and the neck opening, where a section cuts an edge
    # rather than a closed ring.
    for index in range(stations):
        fraction = 0.10 + 0.70 * index / (stations - 1)
        height = low + fraction * span
        cloth = section_outline(garment, garment_faces, height, torso_half_width)
        skin = section_outline(body, body_faces, height, torso_half_width)
        if cloth <= 0.0 or skin <= 0.0:
            continue
        rows.append(
            {
                "heightFraction": round(fraction, 3),
                "sceneHeight": height,
                "garmentGirthCm": cloth * 50.0,
                "bodyGirthCm": skin * 50.0,
                "easeCm": (cloth - skin) * 50.0,
            }
        )
    return rows


def nearest_body_distances(garment: np.ndarray, body: np.ndarray) -> np.ndarray:
    """Distance from every garment vertex to the nearest body vertex."""
    distances = np.empty(len(garment), dtype=np.float64)
    for start in range(0, len(garment), 512):
        block = garment[start : start + 512]
        gaps = np.linalg.norm(block[:, None, :] - body[None, :, :], axis=2)
        distances[start : start + len(block)] = gaps.min(axis=1)
    return distances


def main() -> int:
    arguments = parse_arguments()
    assets = arguments.assets.resolve(strict=True)
    declared = json.loads(
        (assets / "packaged-drape-assets.json").read_text(encoding="utf-8")
    )

    body = parse_production_obj((assets / "body.obj").read_text(encoding="utf-8"))
    garment = parse_textured_obj((assets / "garment.obj").read_text(encoding="utf-8"))

    issues: list[str] = []
    if garment["cornersMissingTexture"]:
        issues.append(
            f"{garment['cornersMissingTexture']} face corners carry no texture "
            "coordinate, so the fabric would sample the tile origin."
        )
    if not garment["seamSegments"]:
        issues.append("The garment carries no patterna_seams line group.")
    if not garment["edgeSegments"]:
        issues.append("The garment carries no patterna_edges line group.")
    if garment["surfaceVertexCount"] != declared["garment"]["vertexCount"]:
        issues.append(
            "Some settled vertices are absent from the rendered surface: the "
            f"report declares {declared['garment']['vertexCount']} but "
            f"{garment['surfaceVertexCount']} appear in triangles."
        )
    if garment["triangleCount"] != declared["garment"]["triangleCount"]:
        issues.append("The rendered triangle count disagrees with the report.")

    body_scene = body["scenePositions"]
    garment_scene = garment["scenePositions"]
    body_floor = float(body_scene[:, 1].min())
    if abs(body_floor - SCENE_FLOOR) > 1.0e-4:
        issues.append("The body does not stand on the scene floor.")

    garment_low = float(garment_scene[:, 1].min())
    garment_high = float(garment_scene[:, 1].max())
    body_high = float(body_scene[:, 1].max())
    if not body_floor < garment_low < garment_high < body_high:
        issues.append(
            "The garment does not sit within the body's vertical extent, so the "
            "two meshes are not in a shared frame."
        )

    # The viewport's "front" camera sits at yaw 180, so a body it shows
    # face-on has its face, chest, and toes at negative z. A body facing the
    # other way renders back-to-front under every camera label, which reads as
    # a modelling fault rather than a frame error, so check it here.
    stature = body_high - body_floor
    face_band = body_scene[
        (body_scene[:, 1] > body_floor + 0.88 * stature)
        & (body_scene[:, 1] < body_floor + 0.95 * stature)
    ]
    facing_z = float(face_band[:, 2].mean()) if len(face_band) else 0.0
    if facing_z >= 0.0:
        issues.append(
            "The body faces away from the viewport's front camera: the head "
            f"centroid sits at z {facing_z:+.3f}, and the renderer expects a "
            "negative value."
        )

    fit = fit_profile(
        garment_scene, garment["faces"], body_scene, body["faces"]
    )
    eases = [row["easeCm"] for row in fit]
    if not eases:
        issues.append("No horizontal section cut both the garment and the body.")
    elif min(eases) < 0.0:
        issues.append(
            f"The garment is smaller than the body it covers at some heights: "
            f"the tightest section has {min(eases):.1f} cm of ease."
        )

    distances = nearest_body_distances(garment_scene, body_scene)
    tile = declared["garment"]["fabricTileCentimeters"]
    coordinates = garment["textureCoordinates"]
    span = coordinates.max(axis=0) - coordinates.min(axis=0)

    report = {
        "schemaVersion": SCHEMA_VERSION,
        "claims": {
            # This tool checks one thing: that the packaged renderer can load
            # and draw these two meshes. Accepting that is exactly what it is
            # for, so the claim is its own result rather than a constant. It is
            # not a statement about how the result looks, which no tool can
            # make, and which stays false here.
            "accepted": not issues,
            "packagedVisualQualityAccepted": False,
        },
        "claimScope": (
            "accepted means the renderer contract is satisfied: both meshes "
            "parse, carry their texture and line groups, share a frame, and the "
            "garment sits on the body. It says nothing about appearance."
        ),
        "arrangementId": declared["arrangementId"],
        "rendererWouldLoad": not issues,
        "issues": issues,
        "body": {
            "vertexCount": int(len(body_scene)),
            "triangleCount": body["triangleCount"],
            "sceneFloor": body_floor,
            "sceneTop": body_high,
            "headCentroidZ": facing_z,
            "facesFrontCamera": facing_z < 0.0,
        },
        "garment": {
            "surfaceVertexCount": garment["surfaceVertexCount"],
            "uvCornerCount": garment["uvCornerCount"],
            "triangleCount": garment["triangleCount"],
            "seamSegmentCount": len(garment["seamSegments"]),
            "edgeSegmentCount": len(garment["edgeSegments"]),
            "sceneLow": garment_low,
            "sceneHigh": garment_high,
            "fabricTileCentimeters": tile,
            "textureRepeatsAcross": [float(value) for value in span],
        },
        "fitProfile": fit,
        "easeCm": {
            "minimum": min(eases) if eases else None,
            "maximum": max(eases) if eases else None,
            "mean": float(np.mean(eases)) if eases else None,
            "spread": (max(eases) - min(eases)) if eases else None,
        },
        "garmentToBodySceneDistanceMeters": {
            "minimum": float(distances.min()),
            "median": float(np.median(distances)),
            "maximum": float(distances.max()),
        },
    }
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "rendererWouldLoad": report["rendererWouldLoad"],
                "issues": issues,
                "surfaceVertices": garment["surfaceVertexCount"],
                "uvCorners": garment["uvCornerCount"],
                "seams": len(garment["seamSegments"]),
                "edges": len(garment["edgeSegments"]),
            },
            indent=2,
        )
    )
    return 0 if report["rendererWouldLoad"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
