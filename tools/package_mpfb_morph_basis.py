#!/usr/bin/env python3
"""Package a generated MPFB morph basis into the shipped display avatar.

The basis is only meaningful against the exact body it was measured on. Matching
vertex counts do not establish that, so when the generator has written its
baseline body beside the basis this compares the two vertex by vertex and
refuses a basis measured on a body that has drifted from the packaged one. The
packaged body's hash is recorded alongside the basis as well, so a later body
change cannot silently keep an old basis.

This copies a candidate artifact into the application's assets and edits the
display avatar manifest. It accepts nothing: the basis stays marked as preview
only, and the interactive preview still reports which measurements it cannot
represent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def obj_vertices(path: Path) -> list[tuple[float, float, float]]:
    vertices: list[tuple[float, float, float]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("v "):
                parts = line.split()
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
    return vertices


def largest_separation(left: Path, right: Path) -> float:
    """The furthest any vertex of one body sits from its counterpart."""
    a, b = obj_vertices(left), obj_vertices(right)
    if len(a) != len(b):
        raise SystemExit(
            f"{left.name} has {len(a)} vertices and {right.name} has {len(b)}."
        )
    return max(
        sum((x - y) ** 2 for x, y in zip(first, second)) ** 0.5
        for first, second in zip(a, b)
    )


def read_application_defaults(path: Path) -> dict[str, float]:
    """The measurement values the application ships as its defaults.

    These come from the coverage audit, which reads them out of the
    application's own declarations rather than restating them here.
    """
    if not path.is_file():
        raise SystemExit(
            f"Run tools/audit_preview_dimension_coverage.py first: {path} is missing."
        )
    report = json.loads(path.read_text(encoding="utf-8"))
    defaults = {item["key"]: float(item["default"]) for item in report["dimensions"]}
    # The six primary measurements are sliders rather than inspector rows, so
    # the audit lists them as keys without a declared default of their own.
    defaults.setdefault("height", 167.0)
    defaults.setdefault("chest", 112.0)
    defaults.setdefault("waist", 82.0)
    defaults.setdefault("hip", 108.0)
    defaults.setdefault("shoulder", 37.0)
    defaults.setdefault("torso", 44.0)
    return defaults


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--basis-report",
        type=Path,
        default=REPO_ROOT / "artifacts/mpfb-morph-basis-v3/mpfb-morph-basis.json",
    )
    parser.add_argument(
        "--avatar-directory",
        type=Path,
        default=REPO_ROOT / "Patternal/Assets/Production/Avatar",
    )
    parser.add_argument(
        "--coverage-report",
        type=Path,
        default=REPO_ROOT / "artifacts/preview-coverage/preview-dimension-coverage.json",
    )
    parser.add_argument(
        "--maximum-baseline-separation-m",
        type=float,
        default=0.002,
        help="How far the basis body may sit from the packaged body, in metres.",
    )
    arguments = parser.parse_args()

    report = json.loads(arguments.basis_report.read_text(encoding="utf-8"))
    basis_source = arguments.basis_report.parent / report["file"]
    if not basis_source.is_file():
        raise SystemExit(f"The basis file named by the report is missing: {basis_source}")

    actual_bytes = basis_source.stat().st_size
    if actual_bytes != report["bytes"]:
        raise SystemExit(
            f"The basis is {actual_bytes} bytes and its report says {report['bytes']}."
        )
    actual_hash = sha256_of(basis_source)
    if actual_hash != report["sha256"]:
        raise SystemExit("The basis hash does not match its report.")

    manifest_path = arguments.avatar_directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    body_path = arguments.avatar_directory / "body.obj"
    body_vertices = len(obj_vertices(body_path))
    if body_vertices != report["sourceVertexCount"]:
        raise SystemExit(
            f"The display body has {body_vertices} vertices and the basis was "
            f"measured on {report['sourceVertexCount']}. Regenerate the basis "
            "against this body before packaging it."
        )

    # A delta measured as the application's whole response is a difference from
    # one particular body, and adding it to a different body is wrong however
    # similar they look. A delta measured as the MPFB target contribution alone
    # is a property of the target: MPFB targets are additive vertex offsets, so
    # the same control displaces any body with this topology identically, and
    # the generator proves that on every run by measuring one control before
    # and after the ruler fit and requiring the two to agree.
    body_independent = bool(report.get("bodyIndependent"))
    separation = None
    baseline_path = arguments.basis_report.parent / "baseline-body.obj"
    if baseline_path.is_file():
        separation = largest_separation(baseline_path, body_path)
        print(f"baseline separation from the packaged body: {separation * 100:.4f} cm")
    if body_independent:
        print(
            f"delta kind: {report.get('deltaKind')}, so that separation does not "
            "constrain packaging"
        )
    elif separation is None:
        raise SystemExit(
            "These deltas carry the application's full response, so they are only "
            "valid against the body they were measured on, and no baseline body "
            "was written beside them to check that."
        )
    elif separation > arguments.maximum_baseline_separation_m:
        raise SystemExit(
            f"The basis was measured on a body that differs from the packaged "
            f"one by up to {separation * 100:.3f} cm, over the "
            f"{arguments.maximum_baseline_separation_m * 100:.3f} cm limit. "
            "Package the body the basis was measured on, or measure the basis "
            "on the packaged body."
        )

    # Re-anchor every parameter to the measurement the application ships as its
    # default.
    #
    # The generator records, as `baseline`, the value at which a control adds
    # nothing to the body it measured. For 29 of these controls that value is
    # not what the application calls the default: the specs were authored
    # around the MakeHuman baseline body, so `upperBustFullness` rests at 50
    # while the application ships 85, and `deltoidProminence` rests at 50 while
    # the application ships 0. Leaving it that way tells the preview it is
    # already far from rest before anything is edited, and it deforms the body
    # on load; the visible result was the bust pushed through the packaged
    # shirt.
    #
    # Anchoring to the application default makes the two agree: at the default
    # measurements every weight is zero and the body drawn is the body that
    # ships, and each endpoint still lands exactly on the body measured there.
    defaults = read_application_defaults(arguments.coverage_report)
    reanchored = 0
    for parameter in report["parameters"]:
        keys = parameter["avatarSourceKeys"]
        values = [defaults[key] for key in keys if key in defaults]
        if len(values) != len(keys):
            continue
        anchor = sum(values) / len(values) if parameter.get("aggregation") == "mean" else values[0]
        if not parameter["minimum"] <= anchor <= parameter["maximum"]:
            raise SystemExit(
                f"{parameter['avatarKey']} would rest at {anchor}, outside its "
                f"range [{parameter['minimum']}, {parameter['maximum']}]."
            )
        if abs(anchor - parameter["baseline"]) >= 0.001:
            reanchored += 1
        parameter["restValueOnMeasuredBody"] = parameter["baseline"]
        parameter["baseline"] = anchor
    print(f"parameters re-anchored to the application's defaults: {reanchored}")

    shutil.copyfile(basis_source, arguments.avatar_directory / report["file"])
    manifest["morph_basis"] = {
        "schemaVersion": report["schemaVersion"],
        "accepted": False,
        "previewOnly": True,
        "validationScope": report["validationScope"],
        "source": report["source"],
        "license": report["license"],
        "file": report["file"],
        "bytes": report["bytes"],
        "sha256": report["sha256"],
        "encoding": report["encoding"],
        "sourceVertexCount": report["sourceVertexCount"],
        "sourceBodySha256": sha256_of(body_path),
        "deltaKind": report.get("deltaKind"),
        "bodyIndependent": body_independent,
        "baselineHeightCm": report["baselineHeightCm"],
        "baselineSeparationFromPackagedBodyM": separation,
        "minimumDisplacementM": report["minimumDisplacementM"],
        "parameters": report["parameters"],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    represented = sorted({key for item in report["parameters"] for key in item["avatarSourceKeys"]})
    print(f"packaged {report['file']} ({actual_bytes / (1024 * 1024):.2f} MB)")
    print(f"parameters: {len(report['parameters'])}")
    print(f"measurement keys represented: {len(represented)}")
    print(f"manifest updated: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
