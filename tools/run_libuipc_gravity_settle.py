#!/usr/bin/env python3
"""Settle an accepted libuipc arrangement under gravity into static drape.

Runs inside the dedicated LibUIPC challenger virtual environment. It consumes
one independently accepted arrangement artifact plus the plan that produced it,
restarts the exact garment at those accepted positions with every seam already
sewn, switches gravity on, and integrates until the cloth stops moving. The
result is a drape state, not accepted cloth: the fabric constants are a
declared physical estimate rather than swatch-calibrated data, and acceptance
still belongs to the independent verifier and to visual review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np


SETTLE_SCHEMA = "patterna.libuipc-gravity-settle/1.0"
ARRANGEMENT_SCHEMA = "patterna.exact-triangle-arrangement/1.0"
VERIFICATION_SCHEMA = "patterna.arrangement-verification/1.0"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--arrangement", required=True, type=Path)
    parser.add_argument("--verification", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--snapshot-every", type=int, default=60)
    parser.add_argument("--log-level", choices=("Info", "Warn", "Error"), default="Warn")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("v "):
                parts = line.split()
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif line.startswith("f "):
                parts = line.split()
                faces.append([int(part.split("/")[0]) - 1 for part in parts[1:4]])
    return np.asarray(vertices, dtype=np.float64), np.asarray(faces, dtype=np.int32)


def load_accepted_arrangement(
    arrangement_directory: Path, verification_path: Path
) -> tuple[dict, np.ndarray]:
    manifest = json.loads(
        (arrangement_directory / "arrangement-manifest.json").read_text(encoding="utf-8")
    )
    for entry in manifest["files"]:
        path = arrangement_directory / entry["path"]
        if path.stat().st_size != entry["byteLength"]:
            raise ValueError(f"Arrangement file byte length changed: {entry['path']}")
        if sha256_file(path) != entry["sha256"]:
            raise ValueError(f"Arrangement file hash changed: {entry['path']}")
    document = json.loads(
        (arrangement_directory / "arrangement.json").read_text(encoding="utf-8")
    )
    if document.get("schemaVersion") != ARRANGEMENT_SCHEMA:
        raise ValueError("Unexpected arrangement schema.")
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    if verification.get("schemaVersion") != VERIFICATION_SCHEMA:
        raise ValueError("Unexpected arrangement verification schema.")
    if verification.get("arrangementId") != manifest["arrangementId"]:
        raise ValueError("The verification report targets a different arrangement.")
    if verification.get("accepted") is not True:
        raise ValueError(
            "Gravity settle requires an independently accepted arrangement;"
            f" {manifest['arrangementId']} is not accepted."
        )
    positions_cm = np.load(arrangement_directory / "positions.npy", allow_pickle=False)
    return {
        "manifest": manifest,
        "document": document,
        "verification": verification,
    }, positions_cm


def main() -> int:
    arguments = parse_arguments()
    plan_dir = arguments.plan.resolve(strict=True)
    plan = json.loads((plan_dir / "scene-plan.json").read_text(encoding="utf-8"))
    plan_manifest = json.loads(
        (plan_dir / "scene-plan-manifest.json").read_text(encoding="utf-8")
    )
    accepted, positions_cm = load_accepted_arrangement(
        arguments.arrangement.resolve(strict=True),
        arguments.verification.resolve(strict=True),
    )
    recipe = json.loads(arguments.recipe.read_text(encoding="utf-8"))
    if recipe.get("schemaVersion") != SETTLE_SCHEMA:
        raise ValueError(f"The settle recipe schema must be {SETTLE_SCHEMA}.")
    if recipe.get("planId") != plan_manifest["planId"]:
        raise ValueError("The settle recipe targets a different plan.")
    if recipe["claims"] != {"acceptedCloth": False, "calibratedFabric": False}:
        raise ValueError("A settle recipe must not claim accepted or calibrated cloth.")

    output = arguments.output.resolve()
    if output.exists():
        raise ValueError(f"Refusing to overwrite an existing settle output: {output}")
    output.mkdir(parents=True)
    (output / "snapshots").mkdir()

    import uipc
    from uipc import Engine, World, Scene, Logger, view, builtin
    from uipc.constitution import (
        DiscreteShellBending,
        ElasticModuli2D,
        SoftVertexStitch,
        StrainLimitingBaraffWitkinShell,
    )

    Logger.set_level(getattr(Logger.Level, arguments.log_level))

    scene_plan = plan["scene"]
    panels = scene_plan["panels"]
    stitch_groups = {group["groupId"]: group for group in scene_plan["stitchGroups"]}
    fabric = recipe["fabric"]
    contact = recipe["contact"]
    integration = recipe["integration"]

    # The arrangement artifact stores centimeters in exact source panel order.
    panel_current: dict[str, np.ndarray] = {}
    panel_rest: dict[str, np.ndarray] = {}
    panel_faces: dict[str, np.ndarray] = {}
    offset = 0
    for panel, artifact_panel in zip(panels, accepted["document"]["panels"]):
        panel_id = panel["panelId"]
        if artifact_panel["panelId"] != panel_id:
            raise ValueError("Arrangement panel order differs from the plan.")
        count = panel["vertexCount"]
        panel_current[panel_id] = positions_cm[offset : offset + count] * 0.01
        offset += count
        rest_vertices, rest_faces = read_obj(plan_dir / panel["restMesh"])
        panel_rest[panel_id] = rest_vertices
        panel_faces[panel_id] = rest_faces
    if offset != positions_cm.shape[0]:
        raise ValueError("Arrangement vertex count differs from the plan.")

    collider_vertices, collider_faces = read_obj(plan_dir / scene_plan["collider"]["mesh"])

    workspace = output / "engine"
    workspace.mkdir()
    engine = Engine("cuda", str(workspace))
    world = World(engine)
    config = Scene.default_config()
    config["gravity"] = [[value] for value in integration["gravityMetersPerSecondSquared"]]
    config["dt"] = integration["dtSeconds"]
    config["contact"]["d_hat"] = contact["dHatMeters"]
    config["newton"]["max_iter"] = integration["newtonMaximumIterations"]
    config["newton"]["velocity_tol"] = integration["newtonVelocityTolerance"]
    scene = Scene(config)

    shell = StrainLimitingBaraffWitkinShell()
    bending = DiscreteShellBending()
    stitch = SoftVertexStitch()
    contact_tabular = scene.contact_tabular()
    contact_tabular.default_model(
        contact["frictionCoefficient"], contact["resistance"]
    )
    panel_elements = {
        panel["panelId"]: contact_tabular.create(panel["panelId"]) for panel in panels
    }
    collider_element = contact_tabular.create("collider")
    # The garment arrives assembled, so every sewn border already sits a full
    # seam apart. Contact stays enabled everywhere except pairs that start
    # inside the contact envelope, which would make the initial state invalid.
    contact_floor = 2.0 * contact["clothContactThicknessMeters"] + 0.0002
    disabled_pairs: list[list[str]] = []
    staged_minimum: dict[tuple[str, str], float] = {}
    for group in stitch_groups.values():
        slot_a, slot_b = group["geometrySlots"]
        if slot_a == slot_b:
            continue
        pairs = np.asarray(group["vertexPairs"], dtype=np.int64)
        distances = np.linalg.norm(
            panel_current[slot_a][pairs[:, 0]] - panel_current[slot_b][pairs[:, 1]],
            axis=1,
        )
        key = tuple(sorted((slot_a, slot_b)))
        staged_minimum[key] = min(
            staged_minimum.get(key, float("inf")), float(distances.min())
        )
    for pair_a, pair_b in sorted(staged_minimum):
        if staged_minimum[(pair_a, pair_b)] < contact_floor:
            contact_tabular.insert(
                panel_elements[pair_a],
                panel_elements[pair_b],
                contact["frictionCoefficient"],
                contact["resistance"],
                False,
            )
            disabled_pairs.append([pair_a, pair_b])

    moduli = ElasticModuli2D.youngs_poisson(
        fabric["stretchYoungsPa"], fabric["poissonRatio"]
    )

    def override_contact_thickness(sc, thickness: float) -> None:
        view(sc.vertices().find(builtin.thickness))[:] = thickness

    panel_object = scene.objects().create("panels")
    panel_slots: dict[str, object] = {}
    for panel in panels:
        panel_id = panel["panelId"]
        simulated = uipc.geometry.trimesh(panel_rest[panel_id], panel_faces[panel_id])
        uipc.geometry.label_surface(simulated)
        shell.apply_to(
            simulated,
            moduli,
            fabric["massDensityKgPerM3"],
            fabric["thicknessMeters"],
        )
        bending.apply_to(simulated, fabric["bendingStiffnessKiloPascals"])
        panel_elements[panel_id].apply_to(simulated)
        override_contact_thickness(simulated, contact["clothContactThicknessMeters"])
        rest = simulated.copy()
        view(simulated.positions())[:] = panel_current[panel_id][:, :, None]
        slot, _ = panel_object.geometries().create(simulated, rest)
        panel_slots[panel_id] = slot

    collider_mesh = uipc.geometry.trimesh(collider_vertices, collider_faces)
    uipc.geometry.label_surface(collider_mesh)
    shell.apply_to(
        collider_mesh, moduli, fabric["massDensityKgPerM3"], fabric["thicknessMeters"]
    )
    collider_element.apply_to(collider_mesh)
    override_contact_thickness(collider_mesh, contact["colliderContactThicknessMeters"])
    view(collider_mesh.vertices().find(builtin.is_fixed))[:] = 1
    view(collider_mesh.meta().find(builtin.self_collision))[:] = 0
    scene.objects().create("collider").geometries().create(collider_mesh)

    stitch_object = scene.objects().create("stitches")
    stitch_chunk = 64
    for group_id in sorted(stitch_groups):
        group = stitch_groups[group_id]
        slot_a = panel_slots[group["geometrySlots"][0]]
        slot_b = panel_slots[group["geometrySlots"][1]]
        pairs = np.asarray(group["vertexPairs"], dtype=np.float64)
        for start in range(0, len(pairs), stitch_chunk):
            stitch_object.geometries().create(
                stitch.create_geometry(
                    (slot_a, slot_b),
                    pairs[start : start + stitch_chunk],
                    recipe["stitch"]["kappa"],
                    recipe["stitch"]["restLengthMeters"],
                )
            )

    world.init(scene)
    if not world.is_valid():
        raise RuntimeError("Gravity settle world initialization failed.")

    equilibrium = recipe["equilibrium"]
    frame_records: list[dict] = []
    previous = {panel_id: value.copy() for panel_id, value in panel_current.items()}
    settled_streak = 0
    frames_run = 0
    started = time.perf_counter()
    for frame in range(integration["frameBudget"]):
        world.advance()
        world.retrieve()
        frames_run = frame + 1
        motion = 0.0
        for panel in panels:
            panel_id = panel["panelId"]
            current = np.asarray(
                view(panel_slots[panel_id].geometry().positions())
            ).reshape(-1, 3).astype(np.float64)
            motion = max(
                motion,
                float(np.linalg.norm(current - previous[panel_id], axis=1).max()),
            )
            previous[panel_id] = current
            panel_current[panel_id] = current
        if not np.isfinite(motion):
            raise ValueError("The settle produced non-finite motion.")
        frame_records.append({"frame": frames_run, "maximumVertexMotionMeters": motion})
        if motion <= equilibrium["maximumVertexMotionMeters"]:
            settled_streak += 1
            if settled_streak >= equilibrium["consecutiveFrames"]:
                break
        else:
            settled_streak = 0
        if arguments.snapshot_every > 0 and frames_run % arguments.snapshot_every == 0:
            np.savez_compressed(
                output / "snapshots" / f"frame-{frames_run:04d}.npz",
                **{key: value for key, value in panel_current.items()},
            )

    ordered = [panel["panelId"] for panel in panels]
    final_positions = np.concatenate([panel_current[panel_id] for panel_id in ordered])
    positions_path = output / "final-positions.npy"
    np.save(positions_path, final_positions, allow_pickle=False)

    report = {
        "schemaVersion": SETTLE_SCHEMA,
        "claims": {"acceptedCloth": False, "calibratedFabric": False},
        "planId": plan_manifest["planId"],
        "sourceArrangementId": accepted["manifest"]["arrangementId"],
        "sourceVerificationId": accepted["verification"]["verificationId"],
        "recipeSha256": sha256_file(arguments.recipe.resolve()),
        "settlerSha256": sha256_file(Path(__file__).resolve()),
        "recipe": recipe,
        "coordinateSystem": plan["coordinateSystem"],
        "scenePolicies": {
            "sewnPairContactDisabledOnlyFor": disabled_pairs,
            "colliderSelfCollisionDisabled": (
                "The exact revision collider contains pre-existing internal"
                " self-intersections, so it participates in cloth contact only."
            ),
        },
        "panelOrder": [
            {"panelId": panel["panelId"], "vertexCount": panel["vertexCount"]}
            for panel in panels
        ],
        "framesRun": frames_run,
        "frameBudget": integration["frameBudget"],
        "reachedEquilibrium": settled_streak >= equilibrium["consecutiveFrames"],
        "finalMaximumVertexMotionMeters": frame_records[-1][
            "maximumVertexMotionMeters"
        ],
        "frames": frame_records,
        "wallSeconds": time.perf_counter() - started,
        "finalPositions": {
            "path": "final-positions.npy",
            "byteLength": positions_path.stat().st_size,
            "sha256": sha256_file(positions_path),
        },
    }
    (output / "settle-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "framesRun": frames_run,
                "reachedEquilibrium": report["reachedEquilibrium"],
                "finalMotionMeters": report["finalMaximumVertexMotionMeters"],
                "wallSeconds": round(report["wallSeconds"], 1),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
