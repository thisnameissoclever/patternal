#!/usr/bin/env python3
"""Run a small headless GPU smoke test against an installed PPF runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_hash(path: Path, expected: str, description: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {description}: {path}")
    actual = sha256(path)
    if actual != expected:
        raise ValueError(
            f"{description} SHA-256 is {actual}; runtime manifest requires {expected}."
        )


def read_gpu_identity() -> dict[str, str | None]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total,compute_cap",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return {"query": "failed", "error": result.stderr.strip()}
    values = [value.strip() for value in result.stdout.strip().split(",")]
    return {
        "name": values[0] if len(values) > 0 else None,
        "driverVersion": values[1] if len(values) > 1 else None,
        "memoryMiB": values[2] if len(values) > 2 else None,
        "computeCapability": values[3] if len(values) > 3 else None,
    }


def prepare_runtime(runtime_root: Path) -> tuple[dict[str, object], Path]:
    manifest_path = runtime_root / "runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != "patterna.challenger-runtime/1.0":
        raise ValueError("PPF runtime manifest schema is not supported.")
    if manifest.get("name") != "PPF":
        raise ValueError("The selected challenger runtime is not PPF.")
    entrypoints = manifest.get("entrypoints")
    if not isinstance(entrypoints, dict):
        raise ValueError("PPF runtime manifest has no entrypoint hash map.")
    for relative_path, expected_hash in entrypoints.items():
        require_hash(runtime_root / relative_path, str(expected_hash), relative_path)

    path_entries = [
        runtime_root / "python",
        runtime_root / "python" / "Scripts",
        runtime_root / "bin",
        runtime_root / "target" / "release",
        runtime_root / "mingit" / "cmd",
    ]
    os.environ["PATH"] = os.pathsep.join(str(path) for path in path_entries) + os.pathsep + os.environ.get("PATH", "")
    for path in path_entries:
        if path.is_dir() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(path))
    sys.path.insert(0, str(runtime_root))
    return manifest, manifest_path


def main() -> None:
    args = parse_args()
    runtime_root = args.runtime_root.resolve()
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    report_path = output_directory / "ppf-runtime-smoke-report.json"
    final_path = output_directory / "final-vertices.npy"
    for stale_output in (report_path, final_path):
        stale_output.unlink(missing_ok=True)
    manifest, manifest_path = prepare_runtime(runtime_root)

    import numpy as np
    from frontend import App

    cache_directory = output_directory / "cache"
    data_directory = output_directory / "data"
    App.get_data_dirpath = staticmethod(lambda: str(data_directory))
    app = App.create("patterna-ppf-runtime-smoke", cache_dir=str(cache_directory))

    vertices, faces = app.mesh.square(res=20, ex=[0, 0, 1], ey=[0, 1, 0])
    app.asset.add.tri("sheet", vertices, faces)
    collider_vertices, collider_faces = app.mesh.icosphere(r=0.45, subdiv_count=2)
    app.asset.add.tri("sphere", collider_vertices, collider_faces)

    scene = app.scene.create()
    sheet = scene.add("sheet")
    sheet.at(0, 0, 0)
    sheet.pin(sheet.grab([0, 1, 0]))
    sheet.param.set("strain-limit", 0.05).set("young-mod", 100).set("bend", 1.0)
    scene.add("sphere").at(-0.9, 0, 0).pin().move_by(
        [1.8, 0, 0], t_start=0.0, t_end=0.2
    )
    fixed_scene = scene.build()

    session = app.session.create(fixed_scene)
    session.param.set("dt", 0.01).set("min-newton-steps", 6).set("frames", 20)
    fixed_session = session.build()
    started = time.perf_counter()
    fixed_session.start(force=True, blocking=True)
    elapsed = time.perf_counter() - started
    if not fixed_session.finished():
        raise RuntimeError("PPF session ended without its finished marker.")
    frame_count = fixed_session.get.latest_frame()
    if frame_count < 1:
        raise RuntimeError("PPF session produced no frames.")
    frame = fixed_session.get.vertex(frame_count - 1)
    if frame is None:
        raise RuntimeError("PPF final frame could not be read.")
    final_vertices, _ = frame
    final_vertices = np.asarray(final_vertices)
    if final_vertices.ndim != 2 or final_vertices.shape[1] != 3:
        raise RuntimeError(f"Unexpected PPF vertex shape: {final_vertices.shape}")
    if not np.isfinite(final_vertices).all():
        raise RuntimeError("PPF final frame contains non-finite vertices.")
    np.save(final_path, final_vertices)
    log_path = Path(fixed_session.info.path) / "stdout.log"
    if not log_path.is_file():
        raise RuntimeError(f"PPF solver stdout log is missing: {log_path}")
    contact_counts = [
        int(match.group(1))
        for match in re.finditer(
            r"^\* num_contact: ([0-9]+)$",
            log_path.read_text(encoding="utf-8", errors="replace"),
            re.MULTILINE,
        )
    ]
    maximum_contacts = max(contact_counts, default=0)
    if maximum_contacts < 1:
        raise RuntimeError("PPF smoke completed without exercising contact constraints.")

    report = {
        "schemaVersion": "patterna.ppf-runtime-smoke/1.0",
        "status": "accepted",
        "runtime": {
            "path": str(runtime_root),
            "version": manifest["version"],
            "manifestSha256": sha256(manifest_path),
            "solverSha256": manifest["entrypoints"][
                "target\\release\\ppf-contact-solver.exe"
            ],
            "embeddedPythonVersion": manifest["embeddedPythonVersion"],
        },
        "gpu": read_gpu_identity(),
        "simulation": {
            "frames": frame_count,
            "elapsedSeconds": elapsed,
            "vertexCount": int(final_vertices.shape[0]),
            "boundsMinimum": final_vertices.min(axis=0).tolist(),
            "boundsMaximum": final_vertices.max(axis=0).tolist(),
            "sessionPath": fixed_session.info.path,
            "contactSamples": len(contact_counts),
            "nonzeroContactSamples": sum(count > 0 for count in contact_counts),
            "maximumContacts": maximum_contacts,
            "stdoutLogSha256": sha256(log_path),
        },
        "outputs": {
            "finalVertices": str(final_path),
            "finalVerticesSha256": sha256(final_path),
        },
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
