#!/usr/bin/env python3
"""Fail closed unless packaged drape evidence satisfies every product gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


PACKAGED_SCHEMA = "patterna.packaged-drape-assets/1.0"
RENDERER_SCHEMA = "patterna.packaged-drape-asset-verification/1.0"
ACCEPTANCE_SCHEMA = "patterna.product-drape-acceptance/1.0"
REQUIRED_PACKAGED_CLAIMS = (
    "producerAccepted",
    "packagedVisualQualityAccepted",
    "calibratedFabric",
    "patternDraftedForThisBody",
)
REQUIRED_RENDERER_CLAIMS = (
    "accepted",
    "packagedVisualQualityAccepted",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def evaluate_product_drape_acceptance(
    packaged: dict[str, Any], renderer: dict[str, Any]
) -> dict[str, Any]:
    """Return a complete rejection list rather than trusting one acceptance flag."""
    reasons: list[str] = []

    if packaged.get("schemaVersion") != PACKAGED_SCHEMA:
        reasons.append(f"packaged schemaVersion must be {PACKAGED_SCHEMA}.")
    if renderer.get("schemaVersion") != RENDERER_SCHEMA:
        reasons.append(f"renderer schemaVersion must be {RENDERER_SCHEMA}.")

    packaged_arrangement = packaged.get("arrangementId")
    renderer_arrangement = renderer.get("arrangementId")
    if packaged_arrangement != renderer_arrangement:
        reasons.append("packaged and renderer arrangementId values must match.")
    if not isinstance(packaged_arrangement, str) or not SHA256_PATTERN.fullmatch(
        packaged_arrangement
    ):
        reasons.append("packaged arrangementId must be a SHA-256 value.")

    packaged_claims = _mapping(packaged.get("claims"))
    for claim in REQUIRED_PACKAGED_CLAIMS:
        if packaged_claims.get(claim) is not True:
            reasons.append(f"packaged claims.{claim} must be true.")

    renderer_claims = _mapping(renderer.get("claims"))
    for claim in REQUIRED_RENDERER_CLAIMS:
        if renderer_claims.get(claim) is not True:
            reasons.append(f"renderer claims.{claim} must be true.")

    open_gates = packaged.get("openGates")
    if open_gates != []:
        reasons.append("packaged openGates must be an empty list.")

    visual_review = _mapping(packaged.get("visualReview"))
    if visual_review.get("accepted") is not True:
        reasons.append("packaged visualReview.accepted must be true.")
    review_hash = visual_review.get("sixViewManifestSha256")
    if not isinstance(review_hash, str) or not SHA256_PATTERN.fullmatch(review_hash):
        reasons.append(
            "packaged visualReview.sixViewManifestSha256 must be a SHA-256 value."
        )

    if renderer.get("rendererWouldLoad") is not True:
        reasons.append("renderer rendererWouldLoad must be true.")
    renderer_issues = renderer.get("issues")
    if renderer_issues != []:
        reasons.append("renderer issues must be an empty list.")

    return {
        "schemaVersion": ACCEPTANCE_SCHEMA,
        "accepted": not reasons,
        "arrangementId": packaged_arrangement,
        "reasons": reasons,
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-report", required=True, type=Path)
    parser.add_argument("--renderer-report", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return value


def main() -> int:
    arguments = parse_arguments()
    result = evaluate_product_drape_acceptance(
        load_json(arguments.assets_report),
        load_json(arguments.renderer_report),
    )
    rendered = json.dumps(result, indent=2) + "\n"
    if arguments.report is not None:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
