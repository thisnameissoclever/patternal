#!/usr/bin/env python3
"""Compare each candidate body model against the controls a garment needs.

Choosing a body model has been argued from renders and from fit losses. Neither
answers the question that decides it, which is whether a model owns an
independent control for each thing a pattern is drafted from. A model missing a
control cannot be made to hit that measurement by any amount of fitting, and a
model whose control is shared between two measurements cannot hit both.

This reads each candidate's own declaration of what it can move and reports
coverage against the control groups named in
`docs/measurement-native-avatar-cage-contract.md`. It reads artifacts, decides
nothing, and accepts nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

SCHEMA_VERSION = "patterna.avatar-control-coverage/1.0"

# The measurements a 14-panel crew-neck is drafted from, grouped as the cage
# contract groups them. Each entry names the objective a fitter would have to
# satisfy to claim the group.
REQUIRED_CONTROLS: dict[str, list[str]] = {
    "vertical landmarks": [
        "stature|floor-to-crown",
        "height|nape-to-waist",
        "height|waist-to-hip",
        "height|bust-apex",
    ],
    "station girths": [
        "circumference|bust",
        "circumference|underbust",
        "circumference|waist",
        "circumference|hip",
    ],
    "station depths": [
        "depth|chest",
        "depth|underbust",
        "depth|waist",
        "depth|hip",
    ],
    "independent front and back arcs": [
        "arc-length|front-hip",
        "arc-length|back-hip",
    ],
    "bust position and projection": [
        "distance|bust-apex-separation",
        "projection|bust-apex",
    ],
    "shoulder and armscye": [
        "distance|shoulder-breadth",
        "length|neck-to-shoulder-tip",
        "circumference|upper-arm::L",
        "length|shoulder-to-wrist",
    ],
    "neck": [
        "circumference|neck-base",
        "circumference|mid-neck",
    ],
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anny-fit-report", required=True, type=Path)
    parser.add_argument("--anny-measurement-report", required=True, type=Path)
    parser.add_argument("--mhr-manifest", required=True, type=Path)
    parser.add_argument("--mpfb-fit-report", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assess_anny(fit_path: Path, measurement_path: Path) -> dict:
    fit = json.loads(fit_path.read_text(encoding="utf-8"))
    measured = json.loads(measurement_path.read_text(encoding="utf-8"))
    objectives = fit["objectives"]
    fitted = {str(key): float(value) for key, value in fit["fittedParameters"].items()}
    rows = {str(row["objective"]): row for row in measured["rows"]}

    owners: dict[str, list[str]] = defaultdict(list)
    for name, entry in objectives.items():
        for control in entry.get("targets", []):
            owners[str(control)].append(name)

    groups: dict[str, dict] = {}
    for group, wanted in REQUIRED_CONTROLS.items():
        details = []
        for objective in wanted:
            entry = objectives.get(objective)
            row = rows.get(objective)
            controls = [str(c) for c in entry.get("targets", [])] if entry else []
            saturated = [
                c for c in controls if abs(abs(fitted.get(c, 0.0)) - 1.0) < 1.0e-9
            ]
            shared = sorted(
                {other for c in controls for other in owners.get(c, []) if other != objective}
            )
            if not controls:
                state = "absent"
            elif row is not None and not row.get("withinTolerance") and len(saturated) == len(controls):
                state = "saturated"
            elif len(controls) == 1 and shared:
                state = "shared"
            elif row is not None and not row.get("withinTolerance"):
                state = "missed"
            else:
                state = "met"
            details.append(
                {
                    "objective": objective,
                    "state": state,
                    "errorCm": row["errorCm"] if row else None,
                    "controls": controls,
                    "saturatedControls": saturated,
                    "sharedWith": shared,
                }
            )
        usable = all(item["state"] == "met" for item in details)
        groups[group] = {"usable": usable, "objectives": details}
    return {
        "model": "Anny 0.6.0",
        "kind": "parametric, differentiable",
        "fittedParameterCount": len(fitted),
        "controlsOnBound": sum(
            1 for value in fitted.values() if abs(abs(value) - 1.0) < 1.0e-9
        ),
        "groups": groups,
    }


def assess_mhr(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    basis = manifest.get("morphBasis", {})
    names = [
        str(entry.get("name") or entry.get("key") or entry.get("parameter") or "")
        for entry in basis.get("parameters", [])
    ]
    names = [name for name in names if name]
    if not names:
        # Older baskets key the parameters by dictionary rather than by list.
        names = sorted(
            key
            for key in basis.get("parameters", {})
            if isinstance(basis.get("parameters"), dict)
        )
    covered = {
        "station girths": {"chest", "underBust", "waist", "hip", "abdomenCirc"},
        "station depths": {"chestDepth", "underBustDepth", "waistDepth", "hipDepth", "abdomenDepth"},
        "shoulder and armscye": {"upperArmCirc"},
    }
    groups: dict[str, dict] = {}
    available = set(names)
    for group, wanted in REQUIRED_CONTROLS.items():
        known = covered.get(group, set())
        present = sorted(known & available) if available else sorted(known)
        groups[group] = {
            "usable": False,
            "note": (
                f"{len(present)} of this group's quantities have a morph parameter"
                if present
                else "no morph parameter in this group"
            ),
            "parameters": present,
        }
    return {
        "model": "Meta Momentum Human Rig candidate",
        "kind": "morph preview over a fixed baseline",
        "parameterCount": len(names) or basis.get("parameterCount"),
        "declaredAccepted": basis.get("accepted"),
        "previewOnly": basis.get("previewOnly"),
        "limitations": basis.get("limitations", []),
        "groups": groups,
    }


# The MPFB fitter names its measurements in its own vocabulary. This maps each
# required objective onto the fit result that answers it, so coverage is read
# from the same evidence for every candidate.
MPFB_OBJECTIVE_KEYS: dict[str, str] = {
    "stature|floor-to-crown": "height",
    "height|nape-to-waist": "nape_to_waist",
    "height|waist-to-hip": "waist_to_hip",
    "circumference|bust": "bust_circumference",
    "circumference|underbust": "underbust_circumference",
    "circumference|waist": "waist_circumference",
    "circumference|hip": "hip_circumference",
    "circumference|mid-neck": "neck_circumference",
    "circumference|upper-arm::L": "upper_arm_circumference",
    "length|neck-to-shoulder-tip": "shoulder_distance",
    "length|shoulder-to-wrist": "upper_arm_length",
}


def assess_mpfb(report_path: Path) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    results = report.get("fit_results", {})
    achieved = report.get("final_measurements_cm", {})
    tolerance = float(report.get("fit_tolerance_cm", 0.15))

    groups: dict[str, dict] = {}
    for group, wanted in REQUIRED_CONTROLS.items():
        details = []
        for objective in wanted:
            key = MPFB_OBJECTIVE_KEYS.get(objective)
            if key is None or key not in results:
                details.append({"objective": objective, "state": "not measured here"})
                continue
            entry = results[key]
            target = entry.get("target_cm") if isinstance(entry, dict) else None
            value = achieved.get(key)
            error = (value - target) if (target is not None and value is not None) else None
            details.append(
                {
                    "objective": objective,
                    "mpfbKey": key,
                    "state": "met" if error is not None and abs(error) <= tolerance else "missed",
                    "targetCm": target,
                    "achievedCm": value,
                    "errorCm": error,
                }
            )
        measured = [item for item in details if item["state"] in {"met", "missed"}]
        groups[group] = {
            "usable": bool(measured) and all(item["state"] == "met" for item in measured),
            "measuredHere": len(measured),
            "objectives": details,
        }
    errors = [
        abs(item["errorCm"])
        for group in groups.values()
        for item in group["objectives"]
        if item.get("errorCm") is not None
    ]
    return {
        "model": "MPFB2 hm08 (CC0 MakeHuman assets)",
        "kind": "parametric over 1,258 morph targets",
        "declaredAccepted": report.get("accepted"),
        "toleranceCm": tolerance,
        "blockingFailures": report.get("fit_acceptance", {}).get("blocking_failures"),
        "estimatedUnreachable": report.get("fit_acceptance", {}).get(
            "accepted_estimated_unreachable"
        ),
        "largestErrorCm": max(errors) if errors else None,
        "groups": groups,
    }


def main() -> int:
    arguments = parse_arguments()
    anny = assess_anny(
        arguments.anny_fit_report.resolve(strict=True),
        arguments.anny_measurement_report.resolve(strict=True),
    )
    mhr = assess_mhr(arguments.mhr_manifest.resolve(strict=True))
    antonia = {
        "model": "Antonia (CharMorph character)",
        "kind": "one authored body, not parametric",
        "groups": {
            group: {
                "usable": True,
                "note": "reaches every value because the target set was measured from this body",
            }
            for group in REQUIRED_CONTROLS
        },
        "limitations": [
            "It is a single body. There are no controls to move, so it cannot represent any other person.",
            "Its bundle recipe records the display candidate as visually rejected.",
        ],
    }

    candidates = [anny, mhr, antonia]
    sources = {
        "annyFitReport": sha256_file(arguments.anny_fit_report),
        "annyMeasurementReport": sha256_file(arguments.anny_measurement_report),
        "mhrManifest": sha256_file(arguments.mhr_manifest),
    }
    mpfb = None
    if arguments.mpfb_fit_report is not None:
        mpfb = assess_mpfb(arguments.mpfb_fit_report.resolve(strict=True))
        candidates.append(mpfb)
        sources["mpfbFitReport"] = sha256_file(arguments.mpfb_fit_report)

    report = {
        "schemaVersion": SCHEMA_VERSION,
        "claims": {"accepted": False, "recommendsAModel": False},
        "requiredControlGroups": REQUIRED_CONTROLS,
        "sources": sources,
        "candidates": candidates,
    }
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"{'control group':<34} {'Anny':<12} {'MHR':<16} {'Antonia':<12} MPFB2")
    for group in REQUIRED_CONTROLS:
        states = [item["state"] for item in anny["groups"][group]["objectives"]]
        worst = (
            "saturated" if "saturated" in states
            else "shared" if "shared" in states
            else "absent" if "absent" in states
            else "missed" if "missed" in states
            else "met"
        )
        parameters = mhr["groups"][group]["parameters"]
        mhr_state = f"{len(parameters)} parameters" if parameters else "none"
        if mpfb is None:
            mpfb_state = "not audited"
        else:
            entry = mpfb["groups"][group]
            mpfb_state = (
                f"all {entry['measuredHere']} within tolerance"
                if entry["usable"]
                else "not measured here"
                if entry["measuredHere"] == 0
                else "missed"
            )
        print(
            f"{group:<34} {worst:<12} {mhr_state:<16} "
            f"{'reaches it' if antonia['groups'][group]['usable'] else 'no':<12} {mpfb_state}"
        )
    if mpfb is not None:
        print(
            f"\nMPFB2 accepted={mpfb['declaredAccepted']} "
            f"tolerance={mpfb['toleranceCm']} cm "
            f"largest error={mpfb['largestErrorCm']:.3f} cm "
            f"blocking failures={mpfb['blockingFailures']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
