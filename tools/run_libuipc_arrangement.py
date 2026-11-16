#!/usr/bin/env python3
"""Execute the declared libuipc contact-aware arrangement plan.

Runs inside the dedicated LibUIPC challenger virtual environment. It verifies
the immutable arrangement plan and the pinned runtime identity, loads the
declared fixed progressive stitch schedule, and runs one zero-gravity IPC
assembly per phase: every panel keeps its exact material-space rest mesh, the
collider stays fixed, positions carry across phase boundaries, velocities
reset, and only the schedule's cumulative stitch groups are active. It writes
raw final positions plus a hash-bound execution report and claims nothing:
wrapping and independent verification happen in separate tools.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np


SCHEDULE_SCHEMA = "patterna.libuipc-arrangement-schedule/1.0"
PLAN_SCHEMA = "patterna.libuipc-arrangement-plan/1.0"
REPORT_SCHEMA = "patterna.libuipc-arrangement-execution/1.0"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--schedule", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
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


def verify_plan_directory(plan_dir: Path) -> dict:
    manifest = json.loads((plan_dir / "scene-plan-manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        path = plan_dir / entry["path"]
        if path.stat().st_size != entry["byteLength"]:
            raise ValueError(f"Plan file byte length changed: {entry['path']}")
        if sha256_file(path) != entry["sha256"]:
            raise ValueError(f"Plan file hash changed: {entry['path']}")
    plan = json.loads((plan_dir / "scene-plan.json").read_text(encoding="utf-8"))
    if plan.get("schemaVersion") != PLAN_SCHEMA:
        raise ValueError("Unexpected arrangement plan schema.")
    if plan["claims"] != {
        "acceptedArrangement": False,
        "acceptedCloth": False,
        "executionAuthorized": False,
    }:
        raise ValueError("Arrangement plan claims changed.")
    return {"manifest": manifest, "plan": plan}


def verify_runtime(runtime_root: Path, plan: dict) -> dict:
    manifest = json.loads((runtime_root / "runtime-manifest.json").read_text(encoding="utf-8"))
    target = plan["runtimeTarget"]
    if manifest["archive"]["sha256"] != target["wheelSha256"]:
        raise ValueError("The installed pyuipc wheel does not match the plan's pinned runtime.")
    import importlib.metadata

    installed = importlib.metadata.version("pyuipc")
    if installed != target["version"]:
        raise ValueError(f"Installed pyuipc {installed} differs from pinned {target['version']}.")
    return {
        "runtimeManifestSha256": sha256_file(runtime_root / "runtime-manifest.json"),
        "name": manifest["name"],
        "version": manifest["version"],
        "wheelSha256": manifest["archive"]["sha256"],
        "pyuipcVersion": installed,
    }


def load_schedule(schedule_path: Path, plan: dict) -> dict:
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    if schedule.get("schemaVersion") != SCHEDULE_SCHEMA:
        raise ValueError("Unexpected arrangement schedule schema.")
    manifest_plan_id = plan["_manifestPlanId"]
    if schedule["planId"] != manifest_plan_id:
        raise ValueError(
            f"Schedule targets plan {schedule['planId']}, not the loaded plan {manifest_plan_id}."
        )
    declared = [group for phase in schedule["phases"] for group in phase["stitchGroups"]]
    plan_groups = [group["groupId"] for group in plan["scene"]["stitchGroups"]]
    if sorted(declared) != sorted(plan_groups) or len(declared) != len(set(declared)):
        raise ValueError("The schedule must cover every stitch group exactly once.")
    return schedule


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


def main() -> int:
    arguments = parse_arguments()
    plan_dir = arguments.plan.resolve(strict=True)
    verified = verify_plan_directory(plan_dir)
    plan = verified["plan"]
    plan["_manifestPlanId"] = verified["manifest"]["planId"]
    runtime = verify_runtime(arguments.runtime_root.resolve(strict=True), plan)
    schedule = load_schedule(arguments.schedule.resolve(strict=True), plan)

    output = arguments.output.resolve()
    if output.exists():
        raise ValueError(f"Refusing to overwrite an existing execution output: {output}")
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
    calibration = scene_plan["cloth"]["assemblyOnlyCalibration"]

    panel_current: dict[str, np.ndarray] = {}
    panel_rest: dict[str, np.ndarray] = {}
    panel_faces: dict[str, np.ndarray] = {}
    for panel in panels:
        initial_vertices, initial_faces = read_obj(plan_dir / panel["initialMesh"])
        rest_vertices, rest_faces = read_obj(plan_dir / panel["restMesh"])
        if initial_vertices.shape[0] != panel["vertexCount"]:
            raise ValueError(f"Panel {panel['panelId']} vertex count changed.")
        if not np.array_equal(initial_faces, rest_faces):
            raise ValueError(f"Panel {panel['panelId']} rest topology differs from initial.")
        panel_current[panel["panelId"]] = initial_vertices
        panel_rest[panel["panelId"]] = rest_vertices
        panel_faces[panel["panelId"]] = initial_faces

    collider_vertices, collider_faces = read_obj(plan_dir / scene_plan["collider"]["mesh"])

    def group_separation(group: dict) -> float:
        slot_a, slot_b = group["geometrySlots"]
        pairs = np.asarray(group["vertexPairs"], dtype=np.int64)
        a = panel_current[slot_a][pairs[:, 0]]
        b = panel_current[slot_b][pairs[:, 1]]
        return float(np.linalg.norm(a - b, axis=1).max())

    phase_records = []
    convergence = schedule["convergence"]
    active_groups: list[str] = []
    total_frames = 0
    started = time.perf_counter()

    for phase_index, phase in enumerate(schedule["phases"]):
        active_groups.extend(phase["stitchGroups"])
        phase_started = time.perf_counter()
        workspace = output / f"engine-phase-{phase_index + 1}"
        workspace.mkdir()

        engine = Engine("cuda", str(workspace))
        world = World(engine)
        config = Scene.default_config()
        config["gravity"] = [[value] for value in scene_plan["gravityMetersPerSecondSquared"]]
        config["dt"] = scene_plan["dtSeconds"]
        # The schedule owns the execution-time contact envelope; the plan's
        # value is the declared default. This keeps envelope corrections in
        # the schedule lane instead of forcing a plan regeneration.
        config["contact"]["d_hat"] = schedule["contact"].get(
            "dHatMeters", scene_plan["contact"]["dHatMeters"]
        )
        config["newton"]["max_iter"] = scene_plan["newton"]["maximumIterations"]
        config["newton"]["velocity_tol"] = scene_plan["newton"]["velocityTolerance"]
        scene = Scene(config)

        shell = StrainLimitingBaraffWitkinShell()
        bending = DiscreteShellBending()
        stitch = SoftVertexStitch()
        contact_tabular = scene.contact_tabular()
        contact_tabular.default_model(
            schedule["contact"]["frictionCoefficient"],
            schedule["contact"]["resistance"],
        )
        panel_elements = {
            panel["panelId"]: contact_tabular.create(panel["panelId"]) for panel in panels
        }
        collider_element = contact_tabular.create("collider")
        # A sewn seam with contact enabled rests at the mutual thickness sum,
        # which still satisfies every seam gate, and contact prevents the two
        # bordering panels from crossing at the seam. Contact is disabled only
        # for sewn pairs whose staged separation already sits inside the
        # contact envelope, where the initial state would otherwise be
        # invalid; with the body-frame staging that is the two coincident
        # collar assembly pairs.
        cloth_thickness = schedule["contact"]["clothContactThicknessMeters"]
        contact_floor = 2.0 * cloth_thickness + 0.0002
        disabled_pairs = []
        sewn_pairs = set()
        for group in stitch_groups.values():
            slot_a, slot_b = group["geometrySlots"]
            if slot_a != slot_b:
                sewn_pairs.add(tuple(sorted((slot_a, slot_b))))
        staged_minimum = {}
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
        for pair_a, pair_b in sorted(sewn_pairs):
            if staged_minimum[(pair_a, pair_b)] < contact_floor:
                contact_tabular.insert(
                    panel_elements[pair_a],
                    panel_elements[pair_b],
                    schedule["contact"]["frictionCoefficient"],
                    schedule["contact"]["resistance"],
                    False,
                )
                disabled_pairs.append([pair_a, pair_b])
        # The shell API takes one isotropic pair. Feeding the calibration's
        # separate 600 Pa shear value into youngs_shear() implies a Poisson
        # ratio of 49 and a negative Lame lambda, which detonates the material.
        # The declared adaptation keeps the calibration stretch modulus and
        # Poisson ratio; the isotropic shear follows from them.
        moduli = ElasticModuli2D.youngs_poisson(
            calibration["stretchYoungsPa"], calibration["poissonRatio"]
        )

        def override_contact_thickness(sc, thickness: float) -> None:
            attribute = sc.vertices().find(builtin.thickness)
            view(attribute)[:] = thickness

        panel_object = scene.objects().create("panels")
        panel_slots: dict[str, object] = {}
        for panel in panels:
            panel_id = panel["panelId"]
            # Build at the exact material-space rest shape so the constitution
            # derives mass and rest metrics there, copy that as the rest slot,
            # then write the staged or carried positions into the live mesh.
            simulated = uipc.geometry.trimesh(
                panel_rest[panel_id], panel_faces[panel_id]
            )
            uipc.geometry.label_surface(simulated)
            shell.apply_to(
                simulated,
                moduli,
                calibration["massDensityKgPerM3"],
                calibration["thicknessMeters"],
            )
            bending.apply_to(simulated, calibration["bendingStiffness"])
            panel_elements[panel_id].apply_to(simulated)
            override_contact_thickness(
                simulated, schedule["contact"]["clothContactThicknessMeters"]
            )
            rest = simulated.copy()
            view(simulated.positions())[:] = panel_current[panel_id][:, :, None]
            slot, _ = panel_object.geometries().create(simulated, rest)
            panel_slots[panel_id] = slot

        collider_mesh = uipc.geometry.trimesh(collider_vertices, collider_faces)
        uipc.geometry.label_surface(collider_mesh)
        shell.apply_to(
            collider_mesh,
            moduli,
            calibration["massDensityKgPerM3"],
            calibration["thicknessMeters"],
        )
        collider_element.apply_to(collider_mesh)
        override_contact_thickness(
            collider_mesh, schedule["contact"]["colliderContactThicknessMeters"]
        )
        fixed = collider_mesh.vertices().find(builtin.is_fixed)
        if fixed is None:
            fixed = collider_mesh.vertices().create(builtin.is_fixed, 0)
        view(fixed)[:] = 1
        # The exact revision collider carries pre-existing internal
        # self-intersections (closed body contact regions). It is a fixed
        # obstacle, so it participates in cloth contact only; collider
        # self-contact stays disabled and the cloth keeps full self-collision.
        collider_self_collision = collider_mesh.meta().find(builtin.self_collision)
        view(collider_self_collision)[:] = 0
        collider_object = scene.objects().create("collider")
        collider_object.geometries().create(collider_mesh)

        stitch_object = scene.objects().create("stitches")
        # The pinned pyuipc 0.0.25 CUDA backend faults on a SoftVertexStitch
        # geometry with more than roughly one hundred pairs (the 246-pair
        # torso seam group crashes; 32 pairs run). Splitting a group across
        # several stitch geometries keeps the summed energy identical, so the
        # declared constitution and constraints are unchanged.
        stitch_chunk = 64
        for group_id in active_groups:
            group = stitch_groups[group_id]
            slot_a = panel_slots[group["geometrySlots"][0]]
            slot_b = panel_slots[group["geometrySlots"][1]]
            pairs = np.asarray(group["vertexPairs"], dtype=np.float64)
            for start in range(0, len(pairs), stitch_chunk):
                stitch_geometry = stitch.create_geometry(
                    (slot_a, slot_b),
                    pairs[start : start + stitch_chunk],
                    schedule["stitch"]["kappa"],
                    schedule["stitch"]["restLengthMeters"],
                )
                stitch_object.geometries().create(stitch_geometry)

        world.init(scene)
        if not world.is_valid():
            raise RuntimeError(
                f"World initialization failed for phase {phase['phaseId']};"
                " see the engine log lines above for the backend error."
            )

        frame_separations: list[dict] = []
        satisfied_streak = 0
        frames_run = 0
        for frame in range(phase["frameBudget"]):
            world.advance()
            world.retrieve()
            frames_run = frame + 1
            total_frames += 1
            for panel in panels:
                panel_id = panel["panelId"]
                positions = np.asarray(view(panel_slots[panel_id].geometry().positions()))
                panel_current[panel_id] = positions.reshape(-1, 3).astype(np.float64)
            worst = max(group_separation(stitch_groups[g]) for g in active_groups)
            frame_separations.append(
                {"frame": frames_run, "activeMaxSeparationMeters": worst}
            )
            if not np.isfinite(worst):
                raise ValueError(
                    f"Phase {phase['phaseId']} produced a non-finite seam separation."
                )
            if worst <= convergence["activeSeamMaxSeparationMeters"]:
                satisfied_streak += 1
                if satisfied_streak >= convergence["consecutiveFrames"]:
                    break
            else:
                satisfied_streak = 0
            if arguments.snapshot_every > 0 and frames_run % arguments.snapshot_every == 0:
                snapshot = output / "snapshots" / (
                    f"phase-{phase_index + 1}-frame-{frames_run:04d}.npz"
                )
                np.savez_compressed(
                    snapshot,
                    **{panel_id: panel_current[panel_id] for panel_id in panel_current},
                )

        for panel_id, positions in panel_current.items():
            if not np.isfinite(positions).all():
                raise ValueError(f"Panel {panel_id} has non-finite positions.")

        phase_records.append(
            {
                "phaseId": phase["phaseId"],
                "activeStitchGroups": list(active_groups),
                "framesRun": frames_run,
                "frameBudget": phase["frameBudget"],
                "earlyStop": frames_run < phase["frameBudget"],
                "finalGroupSeparationsMeters": {
                    group_id: group_separation(stitch_groups[group_id])
                    for group_id in active_groups
                },
                "frameSeparations": frame_separations,
                "wallSeconds": time.perf_counter() - phase_started,
            }
        )

        del world
        del engine

    ordered_ids = [panel["panelId"] for panel in panels]
    final_positions = np.concatenate([panel_current[panel_id] for panel_id in ordered_ids])
    positions_path = output / "final-positions.npy"
    np.save(positions_path, final_positions, allow_pickle=False)

    report = {
        "schemaVersion": REPORT_SCHEMA,
        "claims": {"acceptedArrangement": False, "acceptedCloth": False},
        "planId": verified["manifest"]["planId"],
        "sourceBundleId": plan["sourceBundleId"],
        "executorSha256": sha256_file(Path(__file__).resolve()),
        "scheduleSha256": sha256_file(arguments.schedule.resolve()),
        "schedule": schedule,
        "runtime": runtime,
        "panelOrder": [
            {
                "panelId": panel["panelId"],
                "vertexCount": panel["vertexCount"],
            }
            for panel in panels
        ],
        "coordinateSystem": plan["coordinateSystem"],
        "scenePolicies": {
            "sewnPairContactDisabledOnlyFor": disabled_pairs,
            "colliderSelfCollisionDisabled": (
                "The exact revision collider contains pre-existing internal"
                " self-intersections, so it participates in cloth contact only;"
                " every cloth panel keeps full self-collision."
            )
        },
        "totalFrames": total_frames,
        "phases": phase_records,
        "wallSeconds": time.perf_counter() - started,
        "finalPositions": {
            "path": "final-positions.npy",
            "byteLength": positions_path.stat().st_size,
            "sha256": sha256_file(positions_path),
        },
    }
    (output / "execution-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "totalFrames": total_frames,
                "wallSeconds": report["wallSeconds"],
                "finalPositionsSha256": report["finalPositions"]["sha256"],
                "phaseFrames": [record["framesRun"] for record in phase_records],
                "phaseFinalWorst": [
                    max(record["finalGroupSeparationsMeters"].values())
                    for record in phase_records
                ],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
