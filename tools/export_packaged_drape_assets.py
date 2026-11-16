#!/usr/bin/env python3
"""Export an accepted arrangement as the two OBJ files the packaged app renders.

The Windows application draws its three-dimensional view from exactly two
meshes: a body surface read by ``parseProductionObj`` in Y-up meters, and a
garment surface read by ``parseTexturedObj`` in Y-up centimeters carrying
texture coordinates plus ``patterna_seams`` and ``patterna_edges`` line groups.
The libuipc lane produces neither shape directly, so this tool converts one
settled arrangement into both, without moving a single vertex relative to any
other.

Everything the garment needs already lives inside the arrangement artifact: the
settled positions in centimeters, each panel's triangles, its outline edge
chains, its flat material coordinates, and the seam constraints that joined the
panels. The body comes from the same revision bundle the arrangement was solved
against. Both are bound by hash before they are read, so a stale or edited
input fails rather than rendering something that merely looks plausible.

Texture coordinates are the panels' own material coordinates divided by a
declared fabric tile size, so the weave repeats at a real physical distance
instead of being stretched to fit an arbitrary unit square.

This tool accepts nothing. It restates the acceptance recorded by the
independent arrangement verifier, lists the gates that remain open, and says so
in its report's own claims block.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from revision_bundle import verify_bundle  # noqa: E402

SCHEMA_VERSION = "patterna.packaged-drape-assets/1.0"
ARRANGEMENT_MANIFEST_SCHEMA = "patterna.exact-triangle-arrangement-manifest/1.0"
ARRANGEMENT_SCHEMA = "patterna.exact-triangle-arrangement/1.0"
# A fabric texture tile stands for a real distance across the cloth. Ten
# centimeters keeps the weave visible at garment scale without tiling so
# tightly that the repeat reads as noise.
FABRIC_TILE_CENTIMETERS = 10.0
# Revision bundles put the anatomical front along +z. The viewport expects it
# along -z: its "front" camera sits at yaw 180 and its "rear" camera at yaw 0,
# and the body it already ships has its face and toes at negative z. Turning
# both meshes half a turn about the vertical axis moves them into the display
# frame. This is a rotation, not a mirror, so winding, surface orientation, and
# the body's own left and right all survive it, and the garment stays exactly
# where it settled relative to the body.
DISPLAY_HALF_TURN = np.diag([-1.0, 1.0, -1.0])


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arrangement-artifact", required=True, type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("v "):
                parts = line.split()
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif line.startswith("f "):
                parts = line.split()
                faces.append([int(part.split("/")[0]) - 1 for part in parts[1:4]])
    return (
        np.asarray(vertices, dtype=np.float64),
        np.asarray(faces, dtype=np.int64).reshape(-1, 3),
    )


def verify_manifest_files(root: Path, manifest: dict) -> None:
    for entry in manifest["files"]:
        path = root / entry["path"]
        if path.stat().st_size != entry["byteLength"]:
            raise ValueError(f"{entry['path']} byte length changed.")
        if sha256_file(path) != entry["sha256"]:
            raise ValueError(f"{entry['path']} hash changed.")


def role_path(bundle: Path, manifest: dict, role: str) -> Path:
    """Locate one role inside a bundle whose hashes verify_bundle already checked."""
    matches = [entry for entry in manifest["inputs"] if entry.get("role") == role]
    if len(matches) != 1:
        raise ValueError(f"The bundle must carry exactly one {role} input.")
    return bundle / matches[0]["bundlePath"]


def write_body_obj(source: Path, destination: Path) -> dict:
    """Rewrite the bundle collider through a parse so the output is proven usable."""
    vertices, faces = read_obj(source)
    if len(vertices) < 1000 or len(faces) < 1000:
        raise ValueError("The body mesh is too small for the packaged renderer.")
    floor = float(vertices[:, 1].min())
    if abs(floor) > 1.0e-6:
        raise ValueError("The bundle collider does not stand on the floor plane.")
    vertices = vertices @ DISPLAY_HALF_TURN
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Patterna packaged body surface (Y-up meters, floor at y=0)\n")
        stream.write("# Turned half a turn about the vertical axis into the viewport frame.\n")
        for vertex in vertices:
            stream.write(f"v {vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f}\n")
        for face in faces:
            stream.write(f"f {face[0] + 1} {face[1] + 1} {face[2] + 1}\n")
    return {
        "vertexCount": int(len(vertices)),
        "triangleCount": int(len(faces)),
        "statureMeters": float(vertices[:, 1].max() - vertices[:, 1].min()),
    }


def build_garment(arrangement: dict, positions: np.ndarray) -> dict:
    """Assemble the render-ready garment from the artifact's own panel records."""
    if arrangement.get("units") != "cm":
        raise ValueError("The arrangement must carry centimeter positions.")

    texcoords = np.zeros((len(positions), 2), dtype=np.float64)
    groups: list[tuple[str, np.ndarray]] = []
    edge_chains: list[list[int]] = []
    offsets: dict[str, int] = {}
    covered = 0
    for panel in arrangement["panels"]:
        panel_id = str(panel["panelId"])
        base = int(panel["vertexOffset"])
        count = int(panel["vertexCount"])
        offsets[panel_id] = base
        covered += count

        material = np.asarray(panel["materialPositionsCm"], dtype=np.float64)
        if material.shape != (count, 2):
            raise ValueError(f"{panel_id} material coordinates do not match its vertices.")
        texcoords[base : base + count] = material / FABRIC_TILE_CENTIMETERS

        triangles = np.asarray(panel["triangles"], dtype=np.int64)
        if triangles.shape != (int(panel["triangleCount"]), 3):
            raise ValueError(f"{panel_id} triangle table is malformed.")
        if triangles.min() < 0 or triangles.max() >= count:
            raise ValueError(f"{panel_id} triangles reference vertices it does not own.")
        groups.append((panel_id, triangles + base))

        for chain in panel["edgeVertexIndices"].values():
            if len(chain) < 2:
                continue
            edge_chains.append([int(index) + base for index in chain])

    if covered != len(positions):
        raise ValueError("The panels do not account for every settled vertex.")

    seam_lines: list[tuple[int, int]] = []
    for constraint in arrangement["constraints"]:
        side_a, side_b = constraint["sideA"], constraint["sideB"]
        if side_a["kind"] != "vertex" or side_b["kind"] != "vertex":
            raise ValueError("Only vertex-to-vertex seam constraints are supported.")
        seam_lines.append(
            (
                offsets[str(side_a["panelId"])] + int(side_a["vertexIndex"]),
                offsets[str(side_b["panelId"])] + int(side_b["vertexIndex"]),
            )
        )
    return {
        "texcoords": texcoords,
        "groups": groups,
        "edgeChains": edge_chains,
        "seamLines": seam_lines,
    }


def write_garment_obj(garment: dict, positions: np.ndarray, destination: Path) -> dict:
    positions = positions @ DISPLAY_HALF_TURN
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Patterna packaged garment surface (Y-up centimeters)\n")
        stream.write("# Turned half a turn about the vertical axis into the viewport frame.\n")
        stream.write(
            "# Texture coordinates are material centimeters divided by a "
            f"{FABRIC_TILE_CENTIMETERS:g} cm fabric tile.\n"
        )
        for vertex in positions:
            stream.write(f"v {vertex[0]:.4f} {vertex[1]:.4f} {vertex[2]:.4f}\n")
        for coordinate in garment["texcoords"]:
            stream.write(f"vt {coordinate[0]:.6f} {coordinate[1]:.6f}\n")
        for panel_id, triangles in garment["groups"]:
            stream.write(f"g {panel_id}\n")
            for triangle in triangles:
                a, b, c = (int(index) + 1 for index in triangle)
                stream.write(f"f {a}/{a} {b}/{b} {c}/{c}\n")
        stream.write("g patterna_seams\n")
        for first, second in garment["seamLines"]:
            stream.write(f"l {first + 1} {second + 1}\n")
        stream.write("g patterna_edges\n")
        for chain in garment["edgeChains"]:
            stream.write("l " + " ".join(str(index + 1) for index in chain) + "\n")

    edge_segments = sum(len(chain) - 1 for chain in garment["edgeChains"])
    return {
        "vertexCount": int(len(positions)),
        "triangleCount": int(sum(len(t) for _, t in garment["groups"])),
        "panelCount": len(garment["groups"]),
        "seamLineCount": len(garment["seamLines"]),
        "edgeSegmentCount": edge_segments,
        "fabricTileCentimeters": FABRIC_TILE_CENTIMETERS,
        "boundsCentimeters": {
            "minimum": [float(value) for value in positions.min(axis=0)],
            "maximum": [float(value) for value in positions.max(axis=0)],
        },
    }


def main() -> int:
    arguments = parse_arguments()
    artifact = arguments.arrangement_artifact.resolve(strict=True)
    bundle = arguments.bundle.resolve(strict=True)

    manifest = read_json(artifact / "arrangement-manifest.json")
    if manifest.get("schemaVersion") != ARRANGEMENT_MANIFEST_SCHEMA:
        raise ValueError("Unsupported arrangement manifest schema.")
    verify_manifest_files(artifact, manifest)

    arrangement = read_json(artifact / "arrangement.json")
    if arrangement.get("schemaVersion") != ARRANGEMENT_SCHEMA:
        raise ValueError("Unsupported arrangement schema.")
    if arrangement["sourceBundleId"] != manifest["sourceBundleId"]:
        raise ValueError("The arrangement and its manifest name different bundles.")

    # verify_bundle recomputes every object hash, so a bundle that passes here
    # is byte-identical to the one the arrangement was solved against.
    bundle_manifest = verify_bundle(bundle)
    bundle_id = bundle_manifest.get("bundleId") or bundle_manifest.get("revisionId")
    if bundle_id != manifest["sourceBundleId"]:
        raise ValueError("This bundle is not the one the arrangement was solved on.")

    positions = np.load(artifact / "positions.npy", allow_pickle=False)
    garment = build_garment(arrangement, positions)

    output = arguments.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    collider = role_path(bundle, bundle_manifest, "collider")
    body_summary = write_body_obj(collider, output / "body.obj")
    garment_summary = write_garment_obj(garment, positions, output / "garment.obj")

    verification = read_json(arguments.verification) if arguments.verification else None
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "claims": {
            "producerAccepted": False,
            "packagedVisualQualityAccepted": False,
            "calibratedFabric": False,
            "patternDraftedForThisBody": False,
        },
        "openGates": [
            "The packaged multi-angle visual review of these assets has not been recorded.",
            "The fabric constants are declared estimates, not swatch measurements.",
            "The pattern was graded to the Antonia measurement set, not to this body.",
        ],
        "arrangementId": manifest["arrangementId"],
        "sourceBundleId": manifest["sourceBundleId"],
        "garmentArchetype": arrangement["garmentArchetype"],
        "method": arrangement["method"],
        "inputs": {
            "arrangementManifestSha256": sha256_file(artifact / "arrangement-manifest.json"),
            "arrangementSha256": sha256_file(artifact / "arrangement.json"),
            "positionsSha256": sha256_file(artifact / "positions.npy"),
            "colliderSha256": sha256_file(collider),
        },
        "body": {
            **body_summary,
            "units": "meters",
            "upAxis": "y",
            "consumer": "parseProductionObj",
        },
        "garment": {
            **garment_summary,
            "units": "centimeters",
            "upAxis": "y",
            "consumer": "parseTexturedObj",
        },
        "outputs": {
            "body.obj": sha256_file(output / "body.obj"),
            "garment.obj": sha256_file(output / "garment.obj"),
        },
    }
    if verification is not None:
        report["independentVerification"] = {
            "schemaVersion": verification.get("schemaVersion"),
            "accepted": verification.get("accepted"),
            "verificationId": verification.get("verificationId"),
        }
    (output / "packaged-drape-assets.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "garmentVertices": garment_summary["vertexCount"],
                "garmentTriangles": garment_summary["triangleCount"],
                "seamLines": garment_summary["seamLineCount"],
                "edgeSegments": garment_summary["edgeSegmentCount"],
                "bodyVertices": body_summary["vertexCount"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
