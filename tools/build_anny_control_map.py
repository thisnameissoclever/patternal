#!/usr/bin/env python3
"""Build the immutable ``patterna.anny-control-map/1.0`` document.

Combines the declared mapping table with the exact avatar-worker input and the
pinned runtime's control-label discovery inventory. Every mapped target label
must exist in the discovery inventory, every input control must receive exactly
one row, and the emitted document must satisfy the avatar-worker output
producer's own control-map validator before it is written. The map declares
completeness and keeps acceptance false; only independent verification and
review may accept anything downstream.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.anny_control_map_table import CONTROL_TABLE, CUSTOM_CONTROL_REASON
from tools.avatar_worker_input import ANNY_RELEASE_VERSION, ANNY_WHEEL_SHA256
from tools.avatar_worker_output import (
    CONTROL_MAP_SCHEMA,
    expected_controls,
    load_input,
    validate_control_map,
)
from tools.revision_bundle import canonical_json, sha256_bytes


DISCOVERY_SCHEMA = "patterna.anny-control-discovery/1.0"
FAMILY_TO_INVENTORY = {
    "phenotype": "phenotypeLabels",
    "localChange": "localChangeLabels",
    "facialAction": "facialActionLabels",
    "bone": "boneLabels",
    "pose": "boneLabels",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--discovery", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def validate_target_labels(discovery: dict[str, Any]) -> None:
    for key, entry in CONTROL_TABLE.items():
        if entry["status"] != "mapped":
            continue
        target = entry["target"]
        inventory = discovery[FAMILY_TO_INVENTORY[target["family"]]]
        labels = [target["key"]]
        transform = target["transform"]
        if transform.get("kind") == "bounded-differentiable-fit":
            labels.extend(transform["objective"].get("additionalTargetKeys", []))
        for label in labels:
            if label not in inventory:
                raise ValueError(
                    f"Control {key} references {target['family']} label {label!r}"
                    " that the pinned runtime discovery does not contain."
                )


def build_rows(input_document: dict[str, Any]) -> list[dict[str, Any]]:
    expected = expected_controls(input_document)
    rows: list[dict[str, Any]] = []
    for key, source in expected.items():
        if source["sourceKind"] == "custom":
            entry: dict[str, Any] = {
                "status": "unsupported",
                "unsupportedReason": CUSTOM_CONTROL_REASON,
            }
        elif key in CONTROL_TABLE:
            entry = CONTROL_TABLE[key]
        else:
            raise ValueError(f"The declared mapping table is missing control {key}.")
        row: dict[str, Any] = {
            "key": key,
            "sourceKind": source["sourceKind"],
            "sourceUnit": source["sourceUnit"],
            "status": entry["status"],
        }
        if entry["status"] == "mapped":
            row["target"] = entry["target"]
        else:
            row["unsupportedReason"] = entry["unsupportedReason"]
        rows.append(row)
    table_only = set(CONTROL_TABLE) - {row["key"] for row in rows}
    if table_only:
        raise ValueError(
            "The mapping table declares controls absent from the input: "
            + ", ".join(sorted(table_only))
        )
    return rows


def main() -> int:
    arguments = parse_arguments()
    discovery = json.loads(arguments.discovery.read_text(encoding="utf-8"))
    if discovery.get("schemaVersion") != DISCOVERY_SCHEMA:
        raise ValueError("Unsupported Anny control discovery schema.")
    if discovery.get("annyVersion") != ANNY_RELEASE_VERSION:
        raise ValueError(
            f"Discovery ran against Anny {discovery.get('annyVersion')};"
            f" the map requires {ANNY_RELEASE_VERSION}."
        )
    validate_target_labels(discovery)

    _, input_document = load_input(arguments.input)
    rows = build_rows(input_document)

    candidate = {
        "backend": "Anny",
        "releaseVersion": ANNY_RELEASE_VERSION,
        "wheelSha256": ANNY_WHEEL_SHA256,
        "topology": "anny",
        "rig": "anny-104-bone",
    }
    claims = {"declaredComplete": True, "accepted": False}
    identity = {
        "schemaVersion": CONTROL_MAP_SCHEMA,
        "candidate": candidate,
        "claims": claims,
        "controls": rows,
    }
    document = {
        **identity,
        "controlMapId": sha256_bytes(canonical_json(identity)),
        "discoveryInventoryId": discovery["inventoryId"],
    }

    computed_id = validate_control_map(document, input_document)
    if computed_id != document["controlMapId"]:
        raise ValueError("Control map identity self-check failed.")

    mapped = sum(1 for row in rows if row["status"] == "mapped")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "controlMapId": document["controlMapId"],
                "controls": len(rows),
                "mapped": mapped,
                "unsupported": len(rows) - mapped,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
