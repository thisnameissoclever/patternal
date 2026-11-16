#!/usr/bin/env python3
"""Build the output recipe for a completed Anny worker run and create the
immutable, producer-rejected avatar-worker output.

Host-side orchestration: it maps the worker's raw artifacts onto the required
output roles, writes the ``patterna.avatar-worker-output-recipe/1.0`` document,
then calls the immutable producer (`avatar_worker_output.create_output`) and
its verifier. All acceptance claims stay false.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.avatar_worker_output import RECIPE_SCHEMA, create_output, verify_output


RENDER_ROLES = {
    "renderFront": "render-front.png",
    "renderBack": "render-back.png",
    "renderLeft": "render-left.png",
    "renderRight": "render-right.png",
    "renderFrontOblique": "render-front-oblique.png",
    "renderRearOblique": "render-rear-oblique.png",
    "renderFace": "render-face.png",
    "renderHands": "render-hands.png",
    "renderFeet": "render-feet.png",
    "renderShoulder": "render-shoulder.png",
    "renderBust": "render-bust.png",
    "renderWaist": "render-waist.png",
    "renderHip": "render-hip.png",
}
DATA_ROLES = {
    "displayMesh": "display-mesh.obj",
    "collisionMesh": "collision-mesh.obj",
    "displayToColliderMap": "display-to-collider-map.json",
    "controlApplicationReport": "control-application-report.json",
    "landmarks": "landmarks.json",
    "measurements": "measurements.json",
    "colliderRegistration": "collider-registration.json",
    "rejectionList": "rejection-list.json",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-run", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--control-map", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--worker-version", default="anny-worker/1.0")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    worker_run = arguments.worker_run.resolve(strict=True)
    fit_report = json.loads(
        (worker_run / "anny-fit-report.json").read_text(encoding="utf-8")
    )

    files: dict[str, dict[str, str]] = {}
    for role, name in DATA_ROLES.items():
        files[role] = {"path": str(worker_run / name)}
    for role, name in RENDER_ROLES.items():
        files[role] = {"path": str(worker_run / "renders" / name)}

    recipe = {
        "schemaVersion": RECIPE_SCHEMA,
        "worker": {
            "path": str(Path(__file__).resolve().parent / "run_anny_avatar_worker.py"),
            "version": arguments.worker_version,
        },
        "controlMap": {"path": str(arguments.control_map.resolve(strict=True))},
        "configuration": {
            "topology": "anny",
            "rig": "anny-104-bone",
            "offline": True,
            "implicitDownloadsAllowed": False,
            "dtype": "float64",
            "device": "cpu",
            "seed": int(fit_report["seed"]),
        },
        "claims": {
            "producerAccepted": False,
            "avatarAccepted": False,
            "displayAccepted": False,
            "colliderAccepted": False,
            "productAccepted": False,
        },
        "files": files,
    }
    recipe_path = worker_run / "output-recipe.json"
    recipe_path.write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")

    manifest = create_output(recipe_path, arguments.input, arguments.output)
    verify_output(arguments.output, arguments.input)
    print(
        json.dumps(
            {
                "outputId": manifest["outputId"],
                "files": len(manifest["files"]),
                "claims": manifest["claims"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
