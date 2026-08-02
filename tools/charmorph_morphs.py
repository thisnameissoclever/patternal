#!/usr/bin/env python3
"""Load and evaluate CharMorph packed morphs without the Blender UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np


@dataclass(frozen=True)
class MorphDelta:
    indices: np.ndarray | None
    delta: np.ndarray

    def apply(self, vertices: np.ndarray, weight: float) -> None:
        if abs(weight) < 1.0e-6:
            return
        if self.indices is None:
            vertices += self.delta * weight
        else:
            vertices[self.indices] += self.delta * weight


@dataclass(frozen=True)
class MorphGroup:
    name: str
    control_names: tuple[str, ...]
    corners: Mapping[tuple[int, ...], MorphDelta]


def _decode_names(raw: np.ndarray) -> list[str]:
    return [item.decode("utf-8") for item in bytes(raw).split(b"\0") if item]


def load_packed_morphs(path: Path) -> dict[str, MorphDelta]:
    """Decode CharMorph's sequential sparse/full NPZ representation."""
    with np.load(path) as pack:
        names = _decode_names(pack["names"])
        counts = pack["cnt"]
        if len(names) != len(counts):
            raise ValueError(f"Packed morph name/count mismatch: {len(names)} != {len(counts)}")

        indices = pack["idx"]
        deltas = pack["delta"]
        full = pack.get("full")
        result: dict[str, MorphDelta] = {}
        sparse_offset = 0
        full_offset = 0
        for name, count_value in zip(names, counts):
            count = int(count_value)
            if count >= 0:
                end = sparse_offset + count
                result[name] = MorphDelta(
                    indices=indices[sparse_offset:end].astype(np.int64, copy=True),
                    delta=deltas[sparse_offset:end].astype(np.float64, copy=True),
                )
                sparse_offset = end
            elif count == -1:
                if full is None:
                    raise ValueError(f"Full morph {name!r} has no full array")
                result[name] = MorphDelta(
                    indices=None,
                    delta=full[full_offset].astype(np.float64, copy=True),
                )
                full_offset += 1
            elif count == -2:
                continue
            else:
                raise ValueError(f"Unsupported packed morph count {count} for {name!r}")

        if sparse_offset != len(indices) or sparse_offset != len(deltas):
            raise ValueError("Packed morph sparse data was not consumed exactly")
        if full is not None and full_offset != len(full):
            raise ValueError("Packed morph full data was not consumed exactly")
        return result


def combine_morphs(raw_morphs: Mapping[str, MorphDelta]) -> dict[str, MorphGroup]:
    """Rebuild CharMorph's min/max and multidimensional morph groups."""
    grouped: dict[str, tuple[tuple[str, ...], dict[tuple[int, ...], MorphDelta]]] = {}
    for raw_name, morph in raw_morphs.items():
        try:
            base_name, sign_text = raw_name.rsplit("_", 1)
            category, dimension_text = base_name.split("_", 1)
        except ValueError:
            continue
        signs = tuple(sign_text.split("-"))
        dimensions = tuple(dimension_text.split("-"))
        if len(signs) != len(dimensions) or any(sign not in {"min", "max"} for sign in signs):
            continue
        control_names = tuple(f"{category}_{dimension}" for dimension in dimensions)
        corner = tuple(1 if sign == "max" else -1 for sign in signs)
        if base_name not in grouped:
            grouped[base_name] = (control_names, {})
        existing_names, corners = grouped[base_name]
        if existing_names != control_names:
            raise ValueError(f"Morph group {base_name!r} has inconsistent dimensions")
        corners[corner] = morph

    return {
        name: MorphGroup(name=name, control_names=control_names, corners=corners)
        for name, (control_names, corners) in grouped.items()
    }


def morph_weights(
    groups: Mapping[str, MorphGroup],
    controls: Mapping[str, float],
) -> dict[str, float]:
    """Return raw-corner weights using CharMorph's interpolation rule."""
    result: dict[str, float] = {}
    for group in groups.values():
        values = tuple(float(np.clip(controls.get(name, 0.0), -1.0, 1.0)) for name in group.control_names)
        coefficient = 2.0 / (2 ** len(values))
        for corner in group.corners:
            raw_name = f"{group.name}_{'-'.join('max' if sign > 0 else 'min' for sign in corner)}"
            if len(values) == 1:
                weight = max(values[0] * corner[0], 0.0)
            else:
                weight = max(sum(value * sign for value, sign in zip(values, corner)), 0.0) * coefficient
            if weight > 1.0e-6:
                result[raw_name] = weight
    return result


def apply_controls(
    basis: np.ndarray,
    raw_morphs: Mapping[str, MorphDelta],
    controls: Mapping[str, float],
) -> tuple[np.ndarray, dict[str, float]]:
    groups = combine_morphs(raw_morphs)
    weights = morph_weights(groups, controls)
    vertices = basis.astype(np.float64, copy=True)
    for raw_name, weight in weights.items():
        raw_morphs[raw_name].apply(vertices, weight)
    return vertices, weights
