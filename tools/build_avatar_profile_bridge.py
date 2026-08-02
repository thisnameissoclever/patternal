#!/usr/bin/env python3
"""Apply an editable avatar profile to a Patterna simulation bridge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PERCENT_MEASUREMENTS = {
    "bustSupport": "Supported bust shaping",
    "upperBustFullness": "Upper bust fullness",
    "deltoidProminenceL": "Left deltoid cap prominence",
    "deltoidProminenceR": "Right deltoid cap prominence",
    "upperArmSoftTissueL": "Left upper arm soft-tissue fullness",
    "upperArmSoftTissueR": "Right upper arm soft-tissue fullness",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-bridge", type=Path, required=True)
    parser.add_argument("--avatar-profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def build_bridge(
    base_bridge: dict[str, Any],
    avatar_profile: dict[str, Any],
) -> dict[str, Any]:
    body = base_bridge.get("body")
    values = avatar_profile.get("measurements")
    if not isinstance(body, dict) or not isinstance(body.get("measurements"), list):
        raise ValueError("The base bridge has no detailed body measurements.")
    if not isinstance(values, dict) or not values:
        raise ValueError("The avatar profile does not contain any measurements.")

    existing = {
        item.get("key"): item
        for item in body["measurements"]
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    origins = avatar_profile.get("measurementOrigins")
    if not isinstance(origins, dict):
        origins = {}

    measurements: list[dict[str, Any]] = []
    ordered_keys = [
        item["key"]
        for item in body["measurements"]
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    ]
    ordered_keys.extend(key for key in values if key not in existing)
    for key in ordered_keys:
        raw_value = values[key] if key in values else existing[key].get("value")
        if not isinstance(key, str) or not isinstance(raw_value, (int, float)):
            raise ValueError(f"Invalid avatar measurement {key!r}.")
        prior = existing.get(key, {})
        measurement = dict(prior)
        measurement.update({
            "key": key,
            "label": prior.get("label", PERCENT_MEASUREMENTS.get(key, key)),
            "value": float(raw_value),
            "unit": prior.get("unit", "%" if key in PERCENT_MEASUREMENTS else "cm"),
            "origin": origins.get(key, prior.get("origin", "manual-or-baseline")),
        })
        measurements.append(measurement)

    body["measurements"] = measurements
    base_bridge["body"] = body
    return base_bridge


def main() -> int:
    args = parse_args()
    bridge = build_bridge(
        load_object(args.base_bridge),
        load_object(args.avatar_profile),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bridge, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output.resolve()),
        "measurement_count": len(bridge["body"]["measurements"]),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
