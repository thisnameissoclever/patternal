#!/usr/bin/env python3
"""Offline install smoke test for the evaluation-only pyuipc challenger runtime.

Runs inside the dedicated pyuipc virtual environment. It blocks outbound
network access for the whole process, imports ``uipc``, records the complete
installed-package license inventory including the pyuipc Apache-license-text
versus GPLv3-classifier conflict, probes CUDA engine creation inside a
caller-owned workspace, and writes a JSON report. It proves clean installation
and native solver startup only; it authorizes no arrangement or product claim.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
import traceback


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
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


def license_inventory() -> list[dict]:
    rows = []
    for distribution in importlib.metadata.distributions():
        metadata = distribution.metadata
        license_text = metadata.get("License") or ""
        rows.append(
            {
                "name": distribution.name,
                "version": distribution.version,
                "licenseExpression": metadata.get("License-Expression"),
                "licenseFieldPrefix": " ".join(license_text.split())[:120],
                "licenseClassifiers": [
                    value
                    for value in metadata.get_all("Classifier", [])
                    if value.startswith("License ::")
                ],
                "fileCount": len(distribution.files or []),
            }
        )
    return sorted(rows, key=lambda row: row["name"].lower())


def main() -> int:
    arguments = parse_arguments()
    workspace = arguments.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "schemaVersion": "patterna.libuipc-install-smoke/1.0",
        "scope": "evaluation-runtime-install-smoke-only",
        "executionAuthorizedForProduct": False,
        "arrangementAccepted": False,
        "networkAttempts": 0,
        "workspace": str(workspace),
    }
    install_network_guard(report)

    import uipc  # noqa: E402  (deliberately after the network guard)

    pyuipc_version = importlib.metadata.version("pyuipc")
    report["pyuipcVersion"] = pyuipc_version
    report["uipcModuleFile"] = getattr(uipc, "__file__", None)
    report["topLevelNames"] = sorted(name for name in dir(uipc) if not name.startswith("_"))

    pyuipc_rows = [row for row in license_inventory() if row["name"].lower() == "pyuipc"]
    report["licenses"] = license_inventory()
    report["pyuipcLicenseConflict"] = {
        "apacheLicenseFieldText": bool(
            pyuipc_rows and pyuipc_rows[0]["licenseFieldPrefix"].startswith("Apache License")
        ),
        "gplV3Classifier": bool(
            pyuipc_rows
            and any("GNU General Public License v3" in c for c in pyuipc_rows[0]["licenseClassifiers"])
        ),
        "note": (
            "The pyuipc 0.0.25 package embeds the Apache-2.0 license text while its"
            " classifier declares GPLv3. Recorded per the libuipc arrangement"
            " challenger contract; this runtime is local evaluation only."
        ),
    }

    engine_probe: dict = {"created": False, "signatureUsed": None, "error": None}
    try:
        try:
            engine = uipc.Engine("cuda", str(workspace))
            engine_probe["signatureUsed"] = "Engine(backend, workspace)"
        except TypeError:
            engine = uipc.Engine("cuda")
            engine_probe["signatureUsed"] = "Engine(backend)"
        engine_probe["created"] = True
        engine_probe["backendName"] = getattr(engine, "backend_name", lambda: None)()
        del engine
    except Exception:
        engine_probe["error"] = traceback.format_exc(limit=8)
    report["cudaEngineProbe"] = engine_probe

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if report["networkAttempts"] != 0:
        print("The smoke test attempted outbound network access.", file=sys.stderr)
        return 3
    if not engine_probe["created"]:
        print("CUDA engine creation failed; see the JSON report.", file=sys.stderr)
        return 2
    print(json.dumps({"pyuipcVersion": pyuipc_version, "cudaEngine": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
