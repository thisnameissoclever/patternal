#!/usr/bin/env python3
"""Report which editable body dimensions the shipped 3D preview can represent.

A screenshot comparison cannot answer this. The viewport draws its own status
text inside the captured region, so changing a dimension the preview does not
support still changes the image, and a pixel diff records that as the body
having moved. Every measurement therefore looks answered.

This reads the declarations instead. The application's editable dimensions come
from `BuildMeasurementGroups` in `MainPage.xaml.cs`, the six primary sliders are
named separately, and the set the preview can move comes from the morph basis
the avatar manifest ships plus the height scale the viewport applies on top of
it. The overlap is what a user can change and see; the remainder is what the
application accepts and cannot draw.

This reads source and artifacts, decides nothing, and accepts nothing.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SCHEMA_VERSION = "patterna.preview-dimension-coverage/1.0"

# Named in MainPage.xaml.cs rather than declared through P(...), and read
# directly by UpdateDrapeViewportAsync.
PRIMARY_SLIDER_KEYS = ("height", "chest", "waist", "hip", "shoulder", "torso")

# applyMhrMorphPreview seeds its supported set with the height scale before
# adding every morph parameter, because height is applied as a scale rather
# than as a morph.
VIEWPORT_IMPLICIT_KEYS = ("height",)

GROUP_PATTERN = re.compile(r'new\(\s*\n\s*"([^"]+)",')
PARAMETER_PATTERN = re.compile(
    r'\bP\(\s*\$?"([^"]+)"\s*,\s*\$?"([^"]*)"\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)'
    r'\s*,\s*(-?[\d.]+)(?:\s*,\s*-?[\d.]+\s*,\s*"([^"]*)")?'
)

# The two mirrored groups are built once and called once per side, so their
# keys exist only as interpolated templates in the source.
SIDED_BUILDERS = ("LimbGroup", "LegGroup")

# P(...) declares centimetres unless a measurement names its own unit, and the
# accessible name a control exposes is its label followed by that unit.
DEFAULT_UNIT = "cm"


def method_body(text: str, name: str) -> str:
    """The source of one method, from its signature to the next declaration."""
    match = re.search(rf"private static [\w<>\[\]]+ {name}\(", text)
    if match is None:
        raise SystemExit(f"{name} was not found in the source.")
    end = text.find("\n    private ", match.start() + 1)
    return text[match.start() : end if end != -1 else len(text)]


def read_editable_dimensions(source: Path) -> list[dict[str, str]]:
    """Every dimension the measurement inspector lets a user edit."""
    text = source.read_text(encoding="utf-8")

    builder = method_body(text, "BuildMeasurementGroups")
    groups = [
        (match.start(), match.group(1)) for match in GROUP_PATTERN.finditer(builder)
    ]

    dimensions: list[dict[str, str]] = []
    for match in PARAMETER_PATTERN.finditer(builder):
        enclosing = ""
        for offset, name in groups:
            if offset < match.start():
                enclosing = name
            else:
                break
        dimensions.append(
            {
                "key": match.group(1),
                "label": match.group(2),
                "group": enclosing,
                "default": float(match.group(3)),
                "minimum": float(match.group(4)),
                "maximum": float(match.group(5)),
                "unit": match.group(6) or DEFAULT_UNIT,
                "automationName": f"{match.group(2)} in {match.group(6) or DEFAULT_UNIT}",
            }
        )

    for name in SIDED_BUILDERS:
        body = method_body(text, name)
        templates = [
            (
                match.group(1),
                match.group(2),
                float(match.group(3)),
                float(match.group(4)),
                float(match.group(5)),
                match.group(6) or DEFAULT_UNIT,
            )
            for match in PARAMETER_PATTERN.finditer(body)
        ]
        call_sites = re.finditer(
            rf'{name}\(\s*"([^"]+)"\s*,\s*"([LR])"', builder
        )
        for call in call_sites:
            title, side = call.group(1), call.group(2)
            side_name = "Left" if side == "L" else "Right"
            for key, label, default, minimum, maximum, unit in templates:
                dimensions.append(
                    {
                        "key": key.replace("{side}", side),
                        "label": label.replace("{sideName}", side_name),
                        "group": title,
                        "default": default,
                        "minimum": minimum,
                        "maximum": maximum,
                        "unit": unit,
                        "automationName":
                            f"{label.replace('{sideName}', side_name)} in {unit}",
                    }
                )

    return dimensions


def read_preview_keys(manifests: list[Path]) -> tuple[set[str], list[dict[str, object]]]:
    """The avatar keys the shipped morph bases can move.

    The preview loads whichever display avatar is available, so a dimension is
    reachable if any packaged basis carries it. The GLB avatar spells the
    declaration `morphBasis` and the OBJ avatar spells it `morph_basis`.
    """
    parameters: list[dict[str, object]] = []
    for manifest in manifests:
        if not manifest.is_file():
            continue
        document = json.loads(manifest.read_text(encoding="utf-8"))
        declaration = document.get("morphBasis") or document.get("morph_basis") or {}
        for parameter in declaration.get("parameters", []):
            parameters.append(dict(parameter, manifest=manifest.name))
    keys: set[str] = set(VIEWPORT_IMPLICIT_KEYS)
    described: list[dict[str, object]] = []
    for parameter in parameters:
        sources = parameter.get("avatarSourceKeys") or [parameter.get("avatarKey")]
        sources = [key for key in sources if key]
        keys.update(sources)
        described.append(
            {
                "avatarKey": parameter.get("avatarKey"),
                "avatarSourceKeys": sources,
                "minimum": parameter.get("minimum"),
                "baseline": parameter.get("baseline"),
                "maximum": parameter.get("maximum"),
            }
        )
    return keys, described


def build_report(source: Path, manifests: list[Path]) -> dict[str, object]:
    dimensions = read_editable_dimensions(source)
    preview_keys, parameters = read_preview_keys(manifests)

    editable_keys = [dimension["key"] for dimension in dimensions]
    editable_keys.extend(PRIMARY_SLIDER_KEYS)

    represented = sorted(key for key in set(editable_keys) if key in preview_keys)
    unrepresented = sorted(key for key in set(editable_keys) if key not in preview_keys)

    by_group: dict[str, dict[str, object]] = {}
    for dimension in dimensions:
        group = by_group.setdefault(
            dimension["group"], {"represented": [], "unrepresented": []}
        )
        side = "represented" if dimension["key"] in preview_keys else "unrepresented"
        group[side].append(dimension["key"])
    by_group["Primary sliders"] = {
        "represented": [key for key in PRIMARY_SLIDER_KEYS if key in preview_keys],
        "unrepresented": [
            key for key in PRIMARY_SLIDER_KEYS if key not in preview_keys
        ],
    }

    # A morph key the application has no control for is a capability the user
    # cannot reach, which is the mirror of the gap this tool is looking for.
    unreachable = sorted(preview_keys - set(editable_keys))

    return {
        "schemaVersion": SCHEMA_VERSION,
        "claims": {"accepted": False, "realismAccepted": False},
        "note": (
            "A represented dimension is one the preview can move. It says "
            "nothing about whether the resulting shape is correct."
        ),
        "source": str(source).replace("\\", "/"),
        "manifests": [str(item).replace("\\", "/") for item in manifests],
        "summary": {
            "editableDimensions": len(set(editable_keys)),
            "representedInPreview": len(represented),
            "notRepresentedInPreview": len(unrepresented),
            "morphParameters": len(parameters),
        },
        "morphParameters": parameters,
        "dimensions": sorted(dimensions, key=lambda item: item["key"]),
        "representedInPreview": represented,
        "notRepresentedInPreview": unrepresented,
        "morphKeysWithNoControl": unreachable,
        "byGroup": {
            name: {
                "represented": sorted(entry["represented"]),
                "unrepresented": sorted(entry["unrepresented"]),
            }
            for name, entry in by_group.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("Patternal/MainPage.xaml.cs"))
    parser.add_argument(
        "--manifest",
        type=Path,
        action="append",
        dest="manifests",
        help="A display avatar manifest to read a morph basis from. Repeatable.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/preview-coverage/preview-dimension-coverage.json"),
    )
    arguments = parser.parse_args()

    manifests = arguments.manifests or [
        Path("Patternal/Assets/Candidate/MHR/manifest.json"),
        Path("Patternal/Assets/Production/Avatar/manifest.json"),
    ]
    report = build_report(arguments.source, manifests)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    summary = report["summary"]
    print(
        f"editable body dimensions: {summary['editableDimensions']}\n"
        f"the preview can move:     {summary['representedInPreview']}\n"
        f"the preview cannot move:  {summary['notRepresentedInPreview']}"
    )
    print()
    for name, entry in report["byGroup"].items():
        total = len(entry["represented"]) + len(entry["unrepresented"])
        print(f"  {len(entry['represented']):>3}/{total:<3} {name}")
    if report["morphKeysWithNoControl"]:
        print()
        print(
            "morph keys with no control: "
            + ", ".join(report["morphKeysWithNoControl"])
        )
    print()
    print(f"written to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
