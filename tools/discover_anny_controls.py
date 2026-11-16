#!/usr/bin/env python3
"""Discover the exact control labels of the pinned Anny 0.6.0 runtime.

Runs inside the installed Anny challenger virtual environment. It blocks
outbound network access, instantiates the native ``anny`` topology and rig
with every phenotype, all local changes, and all facial actions enabled, and
writes the complete label inventory to JSON. The control map for the avatar
bakeoff must reference only labels recorded by this discovery run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def install_network_guard() -> None:
    import socket

    def denied(*_args, **_kwargs):
        raise RuntimeError("Outbound network access is disabled for Anny control discovery.")

    class DeniedSocket(socket.socket):
        def connect(self, *args, **kwargs):
            return denied()

        def connect_ex(self, *args, **kwargs):
            return denied()

    socket.socket = DeniedSocket
    socket.create_connection = denied
    socket.getaddrinfo = denied


def main() -> int:
    arguments = parse_arguments()
    cache_dir = arguments.cache_dir.resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["ANNY_CACHE_DIR"] = str(cache_dir)
    install_network_guard()

    import torch
    import anny

    torch.manual_seed(0)
    model = anny.Anny(phenotypes="all", local_changes="all", facial_actions="all")

    def labels(value) -> list[str]:
        return [str(item) for item in value]

    inventory = {
        "schemaVersion": "patterna.anny-control-discovery/1.0",
        "scope": "pinned-runtime-label-inventory-only",
        "annyVersion": anny.__version__,
        "torchVersion": torch.__version__,
        "configuration": {
            "topology": "anny",
            "rig": "anny",
            "phenotypes": "all",
            "localChanges": "all",
            "facialActions": "all",
        },
        "boneCount": int(model.bone_count),
        "phenotypeLabels": labels(model.phenotype_labels),
        "localChangeLabels": labels(model.local_change_labels),
        "facialActionLabels": labels(model.facial_action_labels),
        "boneLabels": labels(model.bone_labels),
    }

    default_model = anny.Anny()
    inventory["defaultConfiguration"] = {
        "boneCount": int(default_model.bone_count),
        "phenotypeLabelCount": len(list(default_model.phenotype_labels)),
        "localChangeLabelCount": len(list(default_model.local_change_labels)),
        "facialActionLabelCount": len(list(default_model.facial_action_labels)),
        "vertexCount": int(default_model.faces.max()) + 1,
        "faceCount": int(len(default_model.faces)),
    }

    identity = {
        key: inventory[key]
        for key in (
            "annyVersion",
            "boneCount",
            "phenotypeLabels",
            "localChangeLabels",
            "facialActionLabels",
            "boneLabels",
        )
    }
    inventory["inventoryId"] = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "inventoryId": inventory["inventoryId"],
                "phenotypes": len(inventory["phenotypeLabels"]),
                "localChanges": len(inventory["localChangeLabels"]),
                "facialActions": len(inventory["facialActionLabels"]),
                "bones": len(inventory["boneLabels"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
