#!/usr/bin/env python3
"""Load and verify a source-bound named shirt arrangement template."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "patterna.named-garment-arrangement-template/1.0"


def map_torso_half(
    lateral_fraction: float,
    lateral_radius: float,
    front_depth: float,
    back_depth: float,
    *,
    front: bool,
) -> tuple[float, float]:
    if not -1.0 <= lateral_fraction <= 1.0:
        raise ValueError("Torso lateral fraction must be between -1 and 1.")
    if min(lateral_radius, front_depth, back_depth) <= 0:
        raise ValueError("Torso envelope radii must be positive.")
    if lateral_fraction == 0:
        return (0.0, front_depth if front else -back_depth)
    if abs(lateral_fraction) == 1:
        return (math.copysign(lateral_radius, lateral_fraction), 0.0)
    theta = (
        lateral_fraction * math.pi / 2
        if front
        else math.pi - lateral_fraction * math.pi / 2
    )
    depth = front_depth if front else back_depth
    return lateral_radius * math.sin(theta), depth * math.cos(theta)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_template(template_path: Path, source_document_path: Path) -> dict[str, Any]:
    template = json.loads(template_path.read_text(encoding="utf-8"))
    if template.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("Unsupported named garment arrangement template schema.")
    if sha256_file(source_document_path) != template.get("sourceDocumentSha256"):
        raise ValueError("The named garment template does not match the source document.")

    source = json.loads(source_document_path.read_text(encoding="utf-8"))
    stitches = source.get("pattern", {}).get("stitches")
    if not isinstance(stitches, list):
        raise ValueError("The source document has no stitch table.")
    if template.get("stitchCount") != len(stitches):
        raise ValueError("The named garment template stitch count changed.")

    roles = template.get("stitchRoles")
    if not isinstance(roles, dict) or not roles:
        raise ValueError("The named garment template has no stitch roles.")
    classified: list[int] = []
    for role, indices in roles.items():
        if not isinstance(role, str) or not role or not isinstance(indices, list):
            raise ValueError("Every named garment stitch role must be a non-empty array.")
        if any(isinstance(index, bool) or not isinstance(index, int) for index in indices):
            raise ValueError(f"Stitch role {role} contains a non-integer index.")
        classified.extend(indices)
    if sorted(classified) != list(range(len(stitches))) or len(classified) != len(
        set(classified)
    ):
        raise ValueError("Every source stitch must be classified exactly once.")
    return template
