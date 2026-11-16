#!/usr/bin/env python3
"""Offline neutral-body smoke test for an installed Anny challenger runtime.

Runs inside the dedicated Anny virtual environment. It blocks outbound network
access for the whole process, points ``ANNY_CACHE_DIR`` at a caller-owned fresh
directory, instantiates the native ``anny`` topology and rig on CPU, and writes
a JSON report with content hashes of the neutral mesh, the discovered control
labels, every source data file the run opened, and every cache file the run
wrote. Two clean runs must produce identical deterministic sections before the
installer may promote the runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def install_network_guard(report: dict) -> None:
    """Fail closed on any in-process outbound connection attempt."""
    import socket

    def denied(*_args, **_kwargs):
        report["networkAttempts"] += 1
        raise RuntimeError("Outbound network access is disabled for this offline smoke test.")

    class DeniedSocket(socket.socket):
        def connect(self, *args, **kwargs):
            return denied()

        def connect_ex(self, *args, **kwargs):
            return denied()

    socket.socket = DeniedSocket
    socket.create_connection = denied
    socket.getaddrinfo = denied


class OpenRecorder:
    """Record every file path opened for reading under the given roots."""

    def __init__(self, roots: list[Path]) -> None:
        self.roots = [root.resolve() for root in roots]
        self.paths: set[str] = set()

    def install(self) -> None:
        def hook(event: str, args: tuple) -> None:
            if event != "open":
                return
            raw = args[0]
            if not isinstance(raw, (str, bytes, os.PathLike)):
                return
            try:
                path = Path(os.fsdecode(raw))
                if not path.is_absolute():
                    return
                resolved = path.resolve()
            except (OSError, ValueError):
                return
            for root in self.roots:
                if resolved.is_relative_to(root):
                    self.paths.add(resolved.relative_to(root).as_posix())
                    return

        sys.addaudithook(hook)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_inventory(root: Path) -> list[dict]:
    if not root.exists():
        return []
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return rows


def user_cache_snapshot() -> dict:
    home = Path.home()
    watched = {
        "userAnnyCache": home / ".cache" / "anny",
        "userTorchCache": home / ".cache" / "torch",
        "userHuggingFaceCache": home / ".cache" / "huggingface",
    }
    snapshot = {}
    for name, root in watched.items():
        if root.exists():
            files = [path for path in root.rglob("*") if path.is_file()]
            snapshot[name] = {
                "exists": True,
                "fileCount": len(files),
                "totalBytes": sum(path.stat().st_size for path in files),
            }
        else:
            snapshot[name] = {"exists": False, "fileCount": 0, "totalBytes": 0}
    return snapshot


def main() -> int:
    arguments = parse_arguments()
    cache_dir = arguments.cache_dir.resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["ANNY_CACHE_DIR"] = str(cache_dir)

    report: dict = {
        "schemaVersion": "patterna.anny-install-smoke/1.0",
        "scope": "offline-neutral-body-install-smoke-only",
        "executionAuthorizedForProduct": False,
        "networkAttempts": 0,
        "cacheDir": str(cache_dir),
        "userCachesBefore": user_cache_snapshot(),
    }
    install_network_guard(report)

    import numpy  # noqa: E402  (deliberately after the network guard)
    import torch  # noqa: E402

    package_root = None
    recorder = OpenRecorder([cache_dir])
    import importlib.util

    spec = importlib.util.find_spec("anny")
    if spec is None or not spec.origin:
        raise RuntimeError("The anny package is not importable in this environment.")
    package_root = Path(spec.origin).parent
    recorder.roots.append(package_root.resolve())
    recorder.install()

    import anny  # noqa: E402

    torch.manual_seed(0)
    model = anny.Anny()
    model = model.to(device="cpu")

    call_path = "default"
    try:
        output = model()
    except TypeError:
        call_path = "identity-pose"
        pose = torch.eye(4)[None, None].repeat(1, model.bone_count, 1, 1)
        output = model(pose_parameters=pose)

    vertices = numpy.asarray(output["vertices"].detach().cpu().numpy(), dtype="<f8")
    faces = numpy.asarray(model.faces, dtype="<i8")

    def labels_digest(labels) -> dict:
        values = [str(label) for label in labels]
        return {
            "count": len(values),
            "sha256": sha256_bytes("\n".join(values).encode("utf-8")),
        }

    report["deterministic"] = {
        "annyVersion": anny.__version__,
        "torchVersion": torch.__version__,
        "callPath": call_path,
        "outputKeys": sorted(str(key) for key in output.keys()),
        "vertexCount": int(vertices.shape[1]),
        "vertexShape": list(vertices.shape),
        "verticesSha256": sha256_bytes(vertices.tobytes()),
        "faceCount": int(faces.shape[0]),
        "facesSha256": sha256_bytes(faces.tobytes()),
        "boneCount": int(model.bone_count),
        "phenotypeLabels": labels_digest(model.phenotype_labels),
        "localChangeLabels": labels_digest(model.local_change_labels),
        "facialActionLabels": labels_digest(model.facial_action_labels),
        "boneLabels": labels_digest(model.bone_labels),
        "openedSourceFiles": sorted(recorder.paths),
    }
    report["cacheInventory"] = directory_inventory(cache_dir)
    report["cacheFileNames"] = sorted(row["path"] for row in report["cacheInventory"])
    report["userCachesAfter"] = user_cache_snapshot()
    report["userCachesUnchanged"] = report["userCachesBefore"] == report["userCachesAfter"]

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not report["userCachesUnchanged"]:
        print("User-level caches changed during the offline smoke test.", file=sys.stderr)
        return 2
    if report["networkAttempts"] != 0:
        print("The smoke test attempted outbound network access.", file=sys.stderr)
        return 3
    print(json.dumps({"verticesSha256": report["deterministic"]["verticesSha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
