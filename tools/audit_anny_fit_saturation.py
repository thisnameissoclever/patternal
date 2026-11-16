#!/usr/bin/env python3
"""Report which fit failures are range limits rather than search failures.

A fit report records a loss, and a loss that stops improving looks the same
whether the optimiser has converged or whether its parameters have run out of
room. Those two call for opposite responses: one is answered by a better
search, the other only by changing the model or the target.

This separates them. For every objective outside tolerance it looks at the
controls that objective declares and reports whether they are sitting on a
bound. An objective whose controls are saturated and which still misses cannot
be closed by any amount of further optimisation, and an objective whose several
controls are shared with an objective that needs them to move the other way
cannot be closed at all.

It reads artifacts and accepts nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

SCHEMA_VERSION = "patterna.anny-fit-saturation-audit/1.0"
FIT_SCHEMA = "patterna.anny-worker-fit/1.0"
MEASUREMENT_SCHEMA = "patterna.anny-worker-measurements/1.0"
# Anny's fitted controls are normalised to this closed interval.
CONTROL_BOUND = 1.0
BOUND_EPSILON = 1.0e-9


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit-report", required=True, type=Path)
    parser.add_argument("--measurement-report", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--garment-critical",
        nargs="*",
        default=[
            "circumference|bust",
            "circumference|underbust",
            "circumference|waist",
            "circumference|hip",
            "circumference|neck-base",
            "distance|shoulder-breadth",
            "distance|bust-apex-separation",
            "height|nape-to-waist",
            "height|bust-apex",
            "projection|bust-apex",
            "depth|chest",
            "arc-length|front-hip",
            "arc-length|back-hip",
            "length|shoulder-to-wrist",
            "length|neck-to-shoulder-tip",
            "circumference|upper-arm::L",
            "circumference|upper-arm::R",
        ],
        help="Objectives a garment drafted on this body depends on.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    arguments = parse_arguments()
    fit_path = arguments.fit_report.resolve(strict=True)
    fit = json.loads(fit_path.read_text(encoding="utf-8"))
    if fit.get("schemaVersion") != FIT_SCHEMA:
        raise ValueError("Unsupported fit report schema.")
    measurement_path = arguments.measurement_report.resolve(strict=True)
    measured = json.loads(measurement_path.read_text(encoding="utf-8"))
    if measured.get("schemaVersion") != MEASUREMENT_SCHEMA:
        raise ValueError("Unsupported measurement report schema.")

    fitted = {str(key): float(value) for key, value in fit["fittedParameters"].items()}
    objectives = fit["objectives"]
    rows = {str(row["objective"]): row for row in measured["rows"]}

    saturated = {
        key: value
        for key, value in fitted.items()
        if abs(abs(value) - CONTROL_BOUND) < BOUND_EPSILON
    }

    # An objective can only be satisfied if it owns enough freedom. Controls
    # shared with another objective are freedom it does not own alone.
    owners: dict[str, list[str]] = defaultdict(list)
    for name, entry in objectives.items():
        for control in entry.get("targets", []):
            owners[str(control)].append(name)

    findings: list[dict] = []
    for name, row in sorted(rows.items()):
        if row.get("withinTolerance"):
            continue
        entry = objectives.get(name, {})
        controls = [str(control) for control in entry.get("targets", [])]
        control_states = [
            {
                "control": control,
                "value": fitted.get(control),
                "atBound": control in saturated,
                "sharedWith": [other for other in owners.get(control, []) if other != name],
            }
            for control in controls
        ]
        if not controls:
            verdict = "unreachable: the objective declares no control"
        elif all(state["atBound"] for state in control_states):
            verdict = "range limit: every control is on a bound and the target is still missed"
        elif any(state["sharedWith"] for state in control_states) and len(controls) == 1:
            verdict = "contended: its only control is shared with another objective"
        else:
            verdict = "search: controls have room left"
        findings.append(
            {
                "objective": name,
                "predictedCm": row["predictedCm"],
                "targetCm": row["targetCm"],
                "errorCm": row["errorCm"],
                "garmentCritical": name in arguments.garment_critical,
                "controls": control_states,
                "verdict": verdict,
            }
        )

    def count(prefix: str, critical_only: bool = False) -> int:
        return sum(
            1
            for finding in findings
            if finding["verdict"].startswith(prefix)
            and (finding["garmentCritical"] or not critical_only)
        )

    report = {
        "schemaVersion": SCHEMA_VERSION,
        "claims": {"accepted": False, "fitAccepted": False},
        "sources": {
            "fitReport": {"path": str(fit_path), "sha256": sha256_file(fit_path)},
            "measurementReport": {
                "path": str(measurement_path),
                "sha256": sha256_file(measurement_path),
            },
        },
        "controlBound": CONTROL_BOUND,
        "fittedControlCount": len(fitted),
        "controlsOnBound": sorted(saturated),
        "finalLoss": fit["history"][-1]["loss"] if fit.get("history") else None,
        "objectivesOutsideTolerance": len(findings),
        "summary": {
            "rangeLimited": count("range limit"),
            "rangeLimitedGarmentCritical": count("range limit", critical_only=True),
            "contended": count("contended"),
            "unreachable": count("unreachable"),
            "searchImprovable": count("search"),
        },
        "findings": findings,
    }
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report["summary"], indent=2))
    print("\nGarment-critical objectives no further optimisation can close:")
    for finding in findings:
        if finding["garmentCritical"] and not finding["verdict"].startswith("search"):
            controls = ", ".join(
                f"{state['control'].split(':')[-1]}={state['value']}"
                for state in finding["controls"]
            ) or "none"
            print(
                f"  {finding['objective']:<32} off by {finding['errorCm']:+7.2f} cm  "
                f"[{finding['verdict'].split(':')[0]}]  {controls}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
