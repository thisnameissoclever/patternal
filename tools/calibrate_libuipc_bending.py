#!/usr/bin/env python3
"""Calibrate the libuipc shell bending coefficient against beam theory.

The discrete shell bending energy is ``kappa * (theta - theta_rest)^2 * L0 /
h_bar``, which is linear in ``kappa``, so the element's effective flexural
rigidity is proportional to it. This tool hangs a clamped strip of the declared
fabric under gravity for several ``kappa`` values, extracts the effective
rigidity from the small-deflection cantilever solution, and solves for the
``kappa`` that reproduces the fabric's own physical rigidity.

That target rigidity comes from the declared Young's modulus, thickness, and
Poisson ratio, and is cross-checked against the textile bending length
``c = (B / (areal_density * g))^(1/3)``, the quantity a Peirce cantilever test
measures. This is a derivation against a standard test definition, not a visual
tuning pass, and it produces no cloth acceptance claim.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np


GRAVITY = 9.81


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--overhang-cm", type=float, default=1.2)
    parser.add_argument("--clamp-cm", type=float, default=0.8)
    parser.add_argument("--width-cm", type=float, default=2.5)
    parser.add_argument("--cell-mm", type=float, default=1.0)
    parser.add_argument("--frames", type=int, default=400)
    return parser.parse_args()


def build_strip(
    total_length_m: float, width_m: float, cell_m: float
) -> tuple[np.ndarray, np.ndarray]:
    """A flat strip in the x-z plane at y=0, length along +x."""
    columns = max(int(round(total_length_m / cell_m)) + 1, 3)
    rows = max(int(round(width_m / cell_m)) + 1, 3)
    xs = np.linspace(0.0, total_length_m, columns)
    zs = np.linspace(-0.5 * width_m, 0.5 * width_m, rows)
    vertices = np.array(
        [[x, 0.0, z] for x in xs for z in zs], dtype=np.float64
    )
    faces = []
    for column in range(columns - 1):
        for row in range(rows - 1):
            a = column * rows + row
            b = a + 1
            c = a + rows
            d = c + 1
            faces.append([a, c, b])
            faces.append([b, c, d])
    return vertices, np.asarray(faces, dtype=np.int32)


def main() -> int:
    arguments = parse_arguments()
    recipe = json.loads(arguments.recipe.read_text(encoding="utf-8"))
    fabric = recipe["fabric"]
    youngs = fabric["stretchYoungsPa"]
    poisson = fabric["poissonRatio"]
    thickness = fabric["thicknessMeters"]
    density = fabric["massDensityKgPerM3"]

    width = arguments.width_cm * 0.01
    overhang = arguments.overhang_cm * 0.01
    clamp = arguments.clamp_cm * 0.01
    cell = arguments.cell_mm * 0.001

    # Continuum targets for the declared fabric.
    second_moment = width * thickness**3 / 12.0
    target_rigidity = youngs * second_moment / (1.0 - poisson**2)
    areal_density = density * thickness
    bending_modulus = youngs * thickness**3 / (12.0 * (1.0 - poisson**2))
    bending_length = (bending_modulus / (areal_density * GRAVITY)) ** (1.0 / 3.0)
    load_per_length = areal_density * GRAVITY * width
    theoretical_deflection = (
        load_per_length * overhang**4 / (8.0 * target_rigidity)
    )

    import uipc
    from uipc import Engine, World, Scene, Logger, view, builtin
    from uipc.constitution import (
        DiscreteShellBending,
        ElasticModuli2D,
        StrainLimitingBaraffWitkinShell,
    )

    Logger.set_level(Logger.Level.Error)
    vertices, faces = build_strip(clamp + overhang, width, cell)
    clamped = vertices[:, 0] <= clamp + 1.0e-9
    workspace_root = arguments.output.parent / "engine"
    workspace_root.mkdir(parents=True, exist_ok=True)

    def measure(kappa: float) -> dict:
        workspace = workspace_root / f"kappa-{kappa:g}"
        workspace.mkdir(exist_ok=True)
        engine = Engine("cuda", str(workspace))
        world = World(engine)
        config = Scene.default_config()
        config["gravity"] = [[0.0], [-GRAVITY], [0.0]]
        config["dt"] = 1.0 / 120.0
        config["contact"]["enable"] = 0
        scene = Scene(config)
        shell = StrainLimitingBaraffWitkinShell()
        bending = DiscreteShellBending()
        mesh = uipc.geometry.trimesh(vertices, faces)
        uipc.geometry.label_surface(mesh)
        shell.apply_to(
            mesh,
            ElasticModuli2D.youngs_poisson(youngs, poisson),
            density,
            thickness,
        )
        bending.apply_to(mesh, kappa)
        fixed = mesh.vertices().find(builtin.is_fixed)
        view(fixed)[clamped] = 1
        slot, _ = scene.objects().create("strip").geometries().create(mesh)
        world.init(scene)
        if not world.is_valid():
            raise RuntimeError(f"Cantilever world invalid for kappa {kappa}.")
        previous = vertices.copy()
        for _ in range(arguments.frames):
            world.advance()
            world.retrieve()
            current = np.asarray(view(slot.geometry().positions())).reshape(-1, 3)
            motion = float(np.linalg.norm(current - previous, axis=1).max())
            previous = current.copy()
            if motion < 1.0e-7:
                break
        tip = current[current[:, 0] >= clamp + overhang - 1.0e-9]
        deflection = float(-tip[:, 1].mean())
        del world
        del engine
        return {
            "kappa": kappa,
            "tipDeflectionMeters": deflection,
            "deflectionOverOverhang": deflection / overhang,
        }

    sweep = (0.01, 1.0, 100.0, 1.0e4, 1.0e6, 1.0e8)
    probes = []
    for kappa in sweep:
        probe = measure(kappa)
        probes.append(probe)
        print(json.dumps(probe), flush=True)
    # In the small-deflection regime the deflection is inversely proportional
    # to the rigidity, and the rigidity is linear in kappa, so kappa times
    # deflection is the constant that maps one to the other.
    usable = [p for p in probes if p["deflectionOverOverhang"] < 0.2]
    if not usable:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(
                {
                    "schemaVersion": "patterna.libuipc-bending-calibration/1.0",
                    "claims": {"acceptedCloth": False, "swatchCalibratedFabric": False},
                    "result": "no-small-deflection-probe",
                    "probes": probes,
                    "theoreticalTipDeflectionMillimeters": theoretical_deflection * 1000.0,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        raise ValueError(
            "Every probe left the small-deflection regime; see the written report."
        )
    constants = [
        p["kappa"] * p["tipDeflectionMeters"] for p in usable
    ]
    constant = float(np.median(constants))
    calibrated_kappa = constant / theoretical_deflection
    verification = measure(calibrated_kappa)

    report = {
        "schemaVersion": "patterna.libuipc-bending-calibration/1.0",
        "claims": {"acceptedCloth": False, "swatchCalibratedFabric": False},
        "method": (
            "Clamped-strip cantilever under gravity, compared with the"
            " small-deflection cantilever solution for the declared fabric."
            " The discrete shell bending energy is linear in its coefficient,"
            " so one constant maps the coefficient to flexural rigidity."
        ),
        "declaredFabric": fabric,
        "geometry": {
            "clampCm": arguments.clamp_cm,
            "overhangCm": arguments.overhang_cm,
            "widthCm": arguments.width_cm,
            "cellMillimeters": arguments.cell_mm,
            "vertexCount": int(vertices.shape[0]),
            "triangleCount": int(faces.shape[0]),
        },
        "continuumTargets": {
            "flexuralRigidityNewtonMeterSquared": target_rigidity,
            "bendingModulusNewtonMeter": bending_modulus,
            "arealDensityKilogramsPerSquareMeter": areal_density,
            "bendingLengthCm": bending_length * 100.0,
            "theoreticalTipDeflectionMillimeters": theoretical_deflection * 1000.0,
        },
        "probes": probes,
        "usableProbeCount": len(usable),
        "kappaTimesDeflectionConstant": constant,
        "calibratedBendingStiffness": calibrated_kappa,
        "verification": verification,
        "verificationErrorPercent": 100.0
        * abs(verification["tipDeflectionMeters"] - theoretical_deflection)
        / theoretical_deflection,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "bendingLengthCm": round(bending_length * 100.0, 3),
                "theoreticalTipDeflectionMm": round(theoretical_deflection * 1000.0, 4),
                "calibratedBendingStiffness": calibrated_kappa,
                "verificationErrorPercent": round(report["verificationErrorPercent"], 2),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
