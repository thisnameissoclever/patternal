#!/usr/bin/env python3
"""Record a human-reviewed decision for an exact product turntable."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


REQUIRED_VIEWS = (
    "front",
    "front-oblique",
    "left",
    "back",
    "back-oblique",
    "right",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proof-manifest", type=Path, required=True)
    decision = parser.add_mutually_exclusive_group(required=True)
    decision.add_argument("--accept", action="store_true")
    decision.add_argument("--reject", action="store_true")
    parser.add_argument("--issue", action="append", default=[])
    return parser.parse_args()


def record_review(manifest_path: Path, *, accepted: bool, issues: list[str]) -> None:
    manifest_path = manifest_path.resolve()
    proof = json.loads(manifest_path.read_text(encoding="utf-8"))
    if proof.get("schema_version") != "patterna.product-turntable/1.0":
        raise ValueError("Unsupported product-turntable manifest schema.")
    if accepted and issues:
        raise ValueError("An accepted visual review cannot retain rejection issues.")
    if not accepted and not issues:
        raise ValueError("A rejected visual review must record at least one concrete issue.")

    reviewed_hashes: dict[str, str] = {}
    renders = proof.get("renders", {})
    for view in REQUIRED_VIEWS:
        render = renders.get(view, {})
        relative_path = render.get("path")
        expected_hash = render.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
            raise ValueError(f"Product proof is missing {view} render identity.")
        render_path = (manifest_path.parent / relative_path).resolve()
        if manifest_path.parent not in render_path.parents or not render_path.is_file():
            raise ValueError(f"Product proof {view} render escapes or is missing from its proof directory.")
        actual_hash = sha256(render_path)
        if actual_hash != expected_hash:
            raise ValueError(f"Product proof {view} render does not match its manifest hash.")
        reviewed_hashes[view] = actual_hash

    proof["visual_quality"] = {
        "accepted": accepted,
        "review_required": False,
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewed_render_sha256": reviewed_hashes,
        "issues": list(issues),
    }
    manifest_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    decision = "accepted" if accepted else "rejected"
    print(f"Recorded {decision} visual review for {manifest_path}")


def main() -> None:
    args = parse_args()
    record_review(
        args.proof_manifest,
        accepted=bool(args.accept),
        issues=list(args.issue),
    )


if __name__ == "__main__":
    main()
