#!/usr/bin/env python3
"""Package an existing body and garment OBJ pair for the viewport's solved view.

Some accepted results predate the arrangement lane and exist only as a finished
body surface and a finished garment surface. They are already in the two formats
the viewport reads, so comparing them against a newer result needs packaging,
not re-solving.

This writes the same report the arrangement exporter writes, so the packaged
application, the renderer-contract verifier, and the product acceptance gate all
read one shape whatever produced the meshes. It copies geometry unchanged, and
its claims are false unless the caller supplies evidence for them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

SCHEMA_VERSION = "patterna.packaged-drape-assets/1.0"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--body", required=True, type=Path, help="Body OBJ in meters.")
    parser.add_argument(
        "--garment", required=True, type=Path, help="Garment OBJ in centimeters."
    )
    parser.add_argument("--identity", required=True, help="What this pair is.")
    parser.add_argument("--open-gate", action="append", default=[])
    parser.add_argument(
        "--body-fit-report",
        type=Path,
        help="An MPFB avatar fit report, used to decide whether this body is the "
        "one the pattern was drafted for.",
    )
    parser.add_argument(
        "--pattern-body",
        action="append",
        default=[],
        metavar="KEY=CM",
        help="A measurement the pattern was drafted to, named as the fit report "
        "names it, for example bust_circumference=112.",
    )
    parser.add_argument(
        "--six-view-manifest",
        type=Path,
        help="A six-view manifest whose images a visual review must judge.",
    )
    parser.add_argument(
        "--producer-report",
        type=Path,
        help="The solver report that produced this garment, used to decide "
        "whether its producer accepted it.",
    )
    parser.add_argument(
        "--fabric-coherence-report",
        type=Path,
        help="A fabric coherence audit for the fabric this garment was solved with.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def assess_producer_acceptance(
    producer_report: Path | None, body_sha: str, garment_sha: str
) -> tuple[bool, dict]:
    """Decide whether the solver accepted these exact two meshes.

    A report that accepts some result says nothing about the files in hand, so
    acceptance transfers only when the report names their hashes.
    """
    if producer_report is None:
        return False, {"evaluated": False, "reason": "No producer report was supplied."}

    report = json.loads(producer_report.read_text(encoding="utf-8"))
    accepted = report.get("accepted") is True
    declared_garment = str(report.get("bundled_render_mesh_sha256", "")).lower()
    declared_body = str(report.get("bundled_body_mesh_sha256", "")).lower()
    garment_matches = declared_garment == garment_sha.lower()
    body_matches = declared_body == body_sha.lower()
    gates = {
        "bodyCollisions": report.get("body_collisions"),
        "selfCollisions": report.get("self_collisions"),
        "staticEquilibriumReached": report.get("static_equilibrium_reached"),
        "maximumSeamSeparationCm": report.get("maximum_seam_separation_cm"),
        "maximumEdgeStrainRatio": report.get("maximum_edge_strain_ratio"),
        "p95EdgeStrainRatio": report.get("ninety_fifth_percentile_edge_strain_ratio"),
        "p999EdgeStrainRatio": report.get(
            "ninety_ninth_point_ninth_percentile_edge_strain_ratio"
        ),
        "p9999EdgeStrainRatio": report.get(
            "ninety_ninth_point_ninety_ninth_percentile_edge_strain_ratio"
        ),
        "highStrainEdgeFraction": report.get("high_strain_edge_fraction"),
    }
    return accepted and garment_matches and body_matches, {
        "evaluated": True,
        "reportSchema": report.get("schema_version"),
        "reportSha256": sha256_file(producer_report),
        "reportAccepted": accepted,
        "rejectionReasons": report.get("rejection_reasons", []),
        "garmentHashMatches": garment_matches,
        "bodyHashMatches": body_matches,
        "solver": report.get("solver"),
        "clothGates": gates,
    }


def assess_drafted_for_this_body(
    fit_report: Path | None, requested: list[str]
) -> tuple[bool, dict]:
    """Decide whether the body reaches the measurements the pattern was cut to.

    This is the difference between a garment that fits by design and one that
    fits by luck, so it is derived from the body's own fit report rather than
    asserted. Every measurement the pattern was drafted to must be one the body
    was fitted to, and must land inside that fit's declared tolerance.
    """
    if fit_report is None or not requested:
        return False, {"evaluated": False, "reason": "No body fit report was supplied."}

    report = json.loads(fit_report.read_text(encoding="utf-8"))
    results = report.get("fit_results", {})
    achieved = report.get("final_measurements_cm", {})
    tolerance = float(report.get("fit_tolerance_cm", 0.15))

    rows: list[dict] = []
    for item in requested:
        key, _, value = item.partition("=")
        key = key.strip()
        wanted = float(value)
        entry = results.get(key)
        got = achieved.get(key)
        if entry is None or got is None:
            rows.append({"measurement": key, "requestedCm": wanted, "state": "not fitted"})
            continue
        target = float(entry.get("target_cm"))
        rows.append(
            {
                "measurement": key,
                "requestedCm": wanted,
                "fitTargetCm": target,
                "achievedCm": got,
                "errorCm": got - wanted,
                "state": "met" if abs(got - wanted) <= tolerance else "missed",
            }
        )
    drafted = bool(rows) and all(row["state"] == "met" for row in rows)
    return drafted, {
        "evaluated": True,
        "toleranceCm": tolerance,
        "fitReportSha256": sha256_file(fit_report),
        "measurements": rows,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarise(path: Path) -> dict:
    vertices: list[list[float]] = []
    triangles = 0
    # A mesh may carry vertices that only seam and edge lines reference. The
    # renderer draws a surface from triangles, so the count that describes what
    # it shows is the number of vertices a triangle actually uses.
    surface: set[int] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("v "):
            parts = line.split()
            vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif line.startswith("f "):
            corners = [int(token.split("/")[0]) - 1 for token in line.split()[1:]]
            triangles += max(0, len(corners) - 2)
            surface.update(corners)
    points = np.asarray(vertices, dtype=np.float64)
    return {
        "vertexCount": len(surface),
        "totalVertexCount": int(len(points)),
        "triangleCount": int(triangles),
        "minimum": [float(value) for value in points.min(axis=0)],
        "maximum": [float(value) for value in points.max(axis=0)],
    }


def main() -> int:
    arguments = parse_arguments()
    body = arguments.body.resolve(strict=True)
    garment = arguments.garment.resolve(strict=True)
    output = arguments.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    (output / "body.obj").write_bytes(body.read_bytes())
    (output / "garment.obj").write_bytes(garment.read_bytes())
    body_summary = summarise(output / "body.obj")
    garment_summary = summarise(output / "garment.obj")

    drafted, fit_evidence = assess_drafted_for_this_body(
        arguments.body_fit_report.resolve(strict=True)
        if arguments.body_fit_report
        else None,
        arguments.pattern_body,
    )

    body_sha = sha256_file(output / "body.obj")
    garment_sha = sha256_file(output / "garment.obj")
    producer_accepted, producer_evidence = assess_producer_acceptance(
        arguments.producer_report.resolve(strict=True)
        if arguments.producer_report
        else None,
        body_sha,
        garment_sha,
    )

    open_gates = list(arguments.open_gate)
    if not producer_accepted:
        open_gates.append("The producing solver has not accepted these exact meshes.")

    # Coherence is what can be established without an instrument: that the
    # fabric numbers could describe a real cloth. Calibration needs a swatch and
    # stays separate, so a coherent fabric never becomes a calibrated one here.
    fabric_coherence = {"evaluated": False}
    if arguments.fabric_coherence_report is not None:
        coherence_path = arguments.fabric_coherence_report.resolve(strict=True)
        coherence = json.loads(coherence_path.read_text(encoding="utf-8"))
        fabric_coherence = {
            "evaluated": True,
            "reportSha256": sha256_file(coherence_path),
            "physicallyCoherent": coherence.get("claims", {}).get("physicallyCoherent"),
            "failedRelations": coherence.get("failedRelations", []),
            "fabricClass": coherence.get("fabricClass"),
            "checkedRelations": [
                item["relation"] for item in coherence.get("checks", [])
            ],
        }
        if not fabric_coherence["physicallyCoherent"]:
            open_gates.append(
                "The fabric parameters do not describe a physically coherent cloth."
            )
    visual_review = {
        # Only a person can accept how something looks. This records the exact
        # images they must judge and stays false until they have.
        "accepted": False,
        "reviewer": None,
    }
    if arguments.six_view_manifest is not None:
        manifest_path = arguments.six_view_manifest.resolve(strict=True)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        visual_review["sixViewManifestSha256"] = sha256_file(manifest_path)
        visual_review["sixViewManifestComplete"] = bool(manifest.get("complete"))
        visual_review["views"] = [view["view"] for view in manifest.get("views", [])]
        if not manifest.get("complete"):
            open_gates.append("The six-view manifest is missing required views.")
    else:
        open_gates.append("No six-view manifest was supplied for visual review.")
    open_gates.append("No person has reviewed and accepted these six views.")
    if not drafted:
        open_gates.append(
            "It is not established that this body reaches the measurements the "
            "pattern was drafted to."
        )

    report = {
        "schemaVersion": SCHEMA_VERSION,
        "claims": {
            "producerAccepted": producer_accepted,
            "packagedVisualQualityAccepted": False,
            "calibratedFabric": False,
            "patternDraftedForThisBody": drafted,
        },
        "producerAcceptanceEvidence": producer_evidence,
        "fabricCoherenceEvidence": fabric_coherence,
        "draftedForThisBodyEvidence": fit_evidence,
        "visualReview": visual_review,
        "openGates": open_gates or ["No gate evidence was supplied with this pair."],
        "arrangementId": sha256_file(output / "garment.obj"),
        "sourceBundleId": sha256_file(output / "body.obj"),
        "garmentArchetype": arguments.identity,
        "method": {"engine": "packaged from an existing accepted pair, not re-solved"},
        "inputs": {
            "bodySource": str(body),
            "garmentSource": str(garment),
        },
        "body": {
            "vertexCount": body_summary["vertexCount"],
            "triangleCount": body_summary["triangleCount"],
            "statureMeters": body_summary["maximum"][1] - body_summary["minimum"][1],
            "units": "meters",
            "upAxis": "y",
            "consumer": "parseProductionObj",
        },
        "garment": {
            "vertexCount": garment_summary["vertexCount"],
            "triangleCount": garment_summary["triangleCount"],
            "panelCount": None,
            "seamLineCount": None,
            "edgeSegmentCount": None,
            "fabricTileCentimeters": None,
            "units": "centimeters",
            "upAxis": "y",
            "consumer": "parseTexturedObj",
            "boundsCentimeters": {
                "minimum": garment_summary["minimum"],
                "maximum": garment_summary["maximum"],
            },
        },
        "outputs": {
            "body.obj": sha256_file(output / "body.obj"),
            "garment.obj": sha256_file(output / "garment.obj"),
        },
    }
    (output / "packaged-drape-assets.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "bodyVertices": body_summary["vertexCount"],
                "garmentVertices": garment_summary["vertexCount"],
                "statureMeters": round(report["body"]["statureMeters"], 4),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
