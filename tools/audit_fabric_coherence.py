#!/usr/bin/env python3
"""Check whether a solver's fabric parameters describe a physically real cloth.

Measuring a swatch on an instrument is the only thing that makes a fabric
calibrated, and this is not that. It is the check that comes before it: whether
the numbers a solver was given could describe any real fabric at all. That is
answerable from the numbers themselves, because they are not independent.
Areal density and thickness imply a packing fraction against the fibre's own
density. Flexural rigidity and areal density imply a bending length, the
quantity a Peirce cantilever test measures, which has a well known range per
fabric class. Shear is always a fraction of tensile in a woven or knitted
fabric, never a multiple.

This check has already earned its place here once. A shear modulus supplied
alongside a Young's modulus implied a Poisson ratio of 49 and a negative Lame
first parameter, and the material tore itself apart at the first solver step;
the numbers were self-inconsistent before any cloth was simulated.

The report says whether each relation holds and shows the working. It does not
claim the fabric is calibrated, because no reading from an instrument went into
it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = "patterna.fabric-coherence-audit/1.0"
GRAVITY = 9.80665
# Cotton fibre, dry. A fabric is fibre plus air, so its bulk density must be a
# fraction of this and the fraction is the packing.
COTTON_FIBRE_DENSITY_KG_PER_M3 = 1540.0
# Bending length in centimetres, from Peirce's cantilever test, by fabric class.
BENDING_LENGTH_RANGES_CM = {
    "jersey": (0.8, 1.8),
    "shirting": (1.4, 2.5),
    "denim": (2.2, 3.6),
}
# Membrane stiffness, the product of Young's modulus and thickness, in newtons
# per metre. Woven and knitted apparel fabrics sit inside this band.
MEMBRANE_STIFFNESS_RANGE_N_PER_M = (40.0, 1200.0)
PACKING_FRACTION_RANGE = (0.10, 0.75)
SHEAR_TO_TENSILE_RANGE = (0.002, 0.5)
# Bending rigidity measured on a KES-FB2 for cotton knit fabrics, reported in
# the textile literature as 0.002 to 0.050 gram-force centimetre squared per
# centimetre of width, with 0.003 to 0.045 the usual band. Those units are a
# force times a length once the width divides out, so one gram-force centimetre
# is 9.80665e-3 newtons times 1e-2 metres.
GRAM_FORCE_CENTIMETRE_IN_NEWTON_METRES = 9.80665e-5
PUBLISHED_KNIT_BENDING_RIGIDITY_NM = (
    0.002 * GRAM_FORCE_CENTIMETRE_IN_NEWTON_METRES,
    0.050 * GRAM_FORCE_CENTIMETRE_IN_NEWTON_METRES,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path, help="Solver report to read.")
    parser.add_argument("--fabric-class", default="jersey", choices=sorted(BENDING_LENGTH_RANGES_CM))
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(name: str, value: float | None, low: float, high: float, working: str) -> dict:
    holds = value is not None and low <= value <= high
    return {
        "relation": name,
        "value": value,
        "expectedRange": [low, high],
        "holds": bool(holds),
        "working": working,
    }


def main() -> int:
    arguments = parse_arguments()
    path = arguments.report.resolve(strict=True)
    document = json.loads(path.read_text(encoding="utf-8"))
    fabric = document.get("fabric")
    if not isinstance(fabric, dict):
        raise ValueError("The report carries no fabric block.")

    areal = fabric.get("density_kg_m2")
    thickness_cm = fabric.get("physical_thickness_cm")
    thickness_m = thickness_cm / 100.0 if thickness_cm else None
    tensile = fabric.get("weft_stiffness")
    warp = fabric.get("warp_stiffness")
    shear = fabric.get("shear_stiffness")
    bend = fabric.get("bend_weft")
    friction = fabric.get("body_friction")

    checks: list[dict] = []

    packing = (
        areal / (thickness_m * COTTON_FIBRE_DENSITY_KG_PER_M3)
        if areal and thickness_m
        else None
    )
    checks.append(
        check(
            "fibre packing fraction",
            packing,
            *PACKING_FRACTION_RANGE,
            working=(
                f"areal density {areal} kg/m2 over thickness {thickness_m} m gives a bulk "
                f"density of {areal / thickness_m:.1f} kg/m3 if both hold, which is that "
                f"fraction of cotton fibre at {COTTON_FIBRE_DENSITY_KG_PER_M3} kg/m3. Below "
                "the range the cloth is mostly air and could not hold its own weave; above "
                "it there is no room for air between the fibres."
            )
            if areal and thickness_m
            else "areal density or thickness is missing",
        )
    )

    bending_length_cm = (
        100.0 * (bend / (areal * GRAVITY)) ** (1.0 / 3.0) if bend and areal else None
    )
    low, high = BENDING_LENGTH_RANGES_CM[arguments.fabric_class]
    checks.append(
        check(
            f"bending length against {arguments.fabric_class}",
            bending_length_cm,
            low,
            high,
            working=(
                f"the cube root of flexural rigidity {bend} N m over areal weight "
                f"{areal * GRAVITY:.4f} N/m2 is the bending length Peirce's cantilever test "
                "measures. It is the one fabric quantity that can be checked against "
                "published values without an instrument."
            )
            if bend and areal
            else "flexural rigidity or areal density is missing",
        )
    )

    # The only relation here that compares against somebody else's instrument
    # rather than against physics. It does not make the fabric calibrated,
    # because these readings are of other fabrics of the same class, but a
    # value outside the range no instrument has reported for this class is a
    # value no swatch would produce either.
    checks.append(
        check(
            "bending rigidity against published KES-FB2 readings for cotton knits",
            bend,
            *PUBLISHED_KNIT_BENDING_RIGIDITY_NM,
            working=(
                f"{bend} N m against a published {PUBLISHED_KNIT_BENDING_RIGIDITY_NM[0]:.3g} "
                f"to {PUBLISHED_KNIT_BENDING_RIGIDITY_NM[1]:.3g} N m, converted from 0.002 "
                "to 0.050 gram-force centimetre squared per centimetre measured on a "
                "KES-FB2 bending tester."
            )
            if bend
            else "flexural rigidity is missing",
        )
    )

    checks.append(
        check(
            "membrane stiffness",
            tensile,
            *MEMBRANE_STIFFNESS_RANGE_N_PER_M,
            working=(
                "tensile stiffness is Young's modulus times thickness, so it is directly "
                "comparable with published apparel fabric values."
            ),
        )
    )

    ratio = shear / tensile if shear and tensile else None
    checks.append(
        check(
            "shear as a fraction of tensile",
            ratio,
            *SHEAR_TO_TENSILE_RANGE,
            working=(
                "a fabric shears far more easily than it stretches, because shear rotates "
                "the yarn crossings while tension has to extend the yarns themselves. A "
                "ratio at or above one describes a solid, not a cloth, and is the shape of "
                "the error that once implied a Poisson ratio of 49 here."
            ),
        )
    )

    checks.append(
        check(
            "friction against skin",
            friction,
            0.1,
            0.8,
            working="dry cotton against skin sits well inside this band.",
        )
    )

    anisotropy = None
    if warp and tensile:
        anisotropy = max(warp, tensile) / min(warp, tensile)
    checks.append(
        check(
            "warp to weft anisotropy",
            anisotropy,
            1.0,
            4.0,
            working=(
                "warp and weft differ in a real fabric but not by orders of magnitude; a "
                "ratio of exactly one means the model is isotropic by declaration."
            ),
        )
    )

    failures = [item["relation"] for item in checks if not item["holds"]]
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "claims": {
            # Coherence is not calibration. Nothing here came from an instrument.
            "calibratedFabric": False,
            "physicallyCoherent": not failures,
        },
        "note": (
            "Every relation holding means the numbers could describe a real fabric. It "
            "does not mean they describe the fabric anyone intends to sew, which needs a "
            "swatch measured on an instrument."
        ),
        "source": {"path": str(path), "sha256": sha256_file(path)},
        "fabricClass": arguments.fabric_class,
        "fabric": fabric,
        "checks": checks,
        "failedRelations": failures,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"physically coherent: {not failures}")
    for item in checks:
        value = item["value"]
        shown = f"{value:.4g}" if isinstance(value, (int, float)) else "missing"
        low, high = item["expectedRange"]
        print(
            f"  {'ok ' if item['holds'] else 'FAIL'} {item['relation']:<38} "
            f"{shown:>10}   expected {low:g} to {high:g}"
        )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
