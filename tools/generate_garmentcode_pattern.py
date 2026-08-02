import argparse
import copy
import json
import sys
from pathlib import Path

import yaml


def apply_fitted_bodice_ease(body, chest_ease: float, waist_ease: float) -> dict[str, float]:
    """Distribute wearing ease before a fitted bodice computes its darts."""

    if chest_ease < -6.0 or chest_ease > 50.0:
        raise ValueError("Chest ease must be from -6 through 50 centimeters.")
    if waist_ease < -6.0 or waist_ease > 50.0:
        raise ValueError("Waist ease must be from -6 through 50 centimeters.")

    base_bust = float(body["bust"])
    base_back_width = float(body["back_width"])
    base_waist = float(body["waist"])
    base_waist_back_width = float(body["waist_back_width"])
    if min(base_bust, base_back_width, base_waist, base_waist_back_width) <= 0.0:
        raise ValueError("Fitted bodice measurements must be positive.")
    if base_back_width >= base_bust or base_waist_back_width >= base_waist:
        raise ValueError("Back widths must be smaller than their circumferences.")

    back_bust_share = base_back_width / base_bust
    back_waist_share = base_waist_back_width / base_waist
    drafting_bust = base_bust + chest_ease
    drafting_waist = base_waist + waist_ease
    if drafting_bust <= 0.0 or drafting_waist <= 0.0:
        raise ValueError("Wearing ease produced a non-positive drafting measurement.")

    body["bust"] = drafting_bust
    body["back_width"] = base_back_width + chest_ease * back_bust_share
    body["waist"] = drafting_waist
    body["waist_back_width"] = (
        base_waist_back_width + waist_ease * back_waist_share
    )
    return {
        "base_bust_cm": base_bust,
        "drafting_bust_cm": drafting_bust,
        "base_back_width_cm": base_back_width,
        "drafting_back_width_cm": float(body["back_width"]),
        "base_waist_cm": base_waist,
        "drafting_waist_cm": drafting_waist,
        "base_waist_back_width_cm": base_waist_back_width,
        "drafting_waist_back_width_cm": float(body["waist_back_width"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a body-specific GarmentCode sewing pattern for Patterna."
    )
    parser.add_argument("--garmentcode-root", required=True, type=Path)
    parser.add_argument("--body", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--style",
        choices=[
            "fitted-pencil-dress",
            "fitted-sleeveless-top",
            "crew-neck-shirt",
            "fitted-crew-neck-shirt",
            "patterna-shaped-crew-neck-shirt",
            "cup-aware-princess-top",
        ],
        default="fitted-pencil-dress",
    )
    parser.add_argument("--shirt-width", type=float, default=1.04)
    parser.add_argument("--shirt-length", type=float, default=1.08)
    parser.add_argument("--shirt-flare", type=float, default=1.02)
    parser.add_argument("--chest-ease", type=float, default=6.0)
    parser.add_argument(
        "--underbust-ease",
        type=float,
        help=(
            "Finished underbust ease in centimeters for the cup-aware block. "
            "When omitted, fitted defaults are capped independently of bust ease."
        ),
    )
    parser.add_argument(
        "--upper-torso-ease",
        type=float,
        help=(
            "Finished upper-torso ease in centimeters for the cup-aware block. "
            "When omitted, fitted defaults are capped independently of bust ease."
        ),
    )
    parser.add_argument(
        "--underarm-ease",
        type=float,
        help=(
            "Finished closed underarm-circuit ease in centimeters for the "
            "cup-aware block."
        ),
    )
    parser.add_argument("--waist-ease", type=float, default=6.0)
    parser.add_argument("--hip-ease", type=float, default=6.0)
    parser.add_argument("--hem-extension-depth", type=float, default=0.0)
    parser.add_argument("--hem-extension-ease", type=float, default=4.0)
    parser.add_argument("--neck-width", type=float, default=-0.20)
    parser.add_argument("--front-neck-depth", type=float, default=0.16)
    parser.add_argument("--back-neck-depth", type=float, default=0.025)
    parser.add_argument(
        "--neck-band-depth",
        type=float,
        default=0.0,
        help=(
            "Add a sewn neckline band with this finished depth in centimeters. "
            "Zero preserves the raw neckline edge."
        ),
    )
    parser.add_argument("--sleeve-length", type=float, default=0.24)
    parser.add_argument("--sleeve-angle", type=int, default=46)
    parser.add_argument("--sleeve-end-width", type=float, default=0.92)
    parser.add_argument("--high-bust", type=float)
    parser.add_argument("--underbust", type=float)
    parser.add_argument("--bust-span", type=float)
    parser.add_argument("--front-waist-length", type=float)
    parser.add_argument("--back-waist-length", type=float)
    parser.add_argument(
        "--shoulder-to-bust",
        type=float,
        help=(
            "Shoulder or front-neck landmark to bust point ruler in centimeters. "
            "The block converts this to a waist-relative bust station."
        ),
    )
    parser.add_argument("--bust-height-from-waist", type=float)
    parser.add_argument(
        "--front-princess-contour-length",
        type=float,
        help=(
            "Body-surface ruler from the front waist to the bust point along "
            "the princess line, in centimeters."
        ),
    )
    parser.add_argument(
        "--front-princess-upper-contour-length",
        type=float,
        help=(
            "Avatar-surface ruler from the bust point to the shoulder along "
            "the princess line, in centimeters."
        ),
    )
    parser.add_argument("--armscye-depth", type=float)
    parser.add_argument("--armscye-circumference", type=float)
    parser.add_argument("--upper-arm-circumference", type=float)
    parser.add_argument("--neck-half-width", type=float)
    parser.add_argument(
        "--sleeve-cuff-depth",
        type=float,
        default=0.0,
        help=(
            "Add a sewn sleeve band with this finished depth in centimeters. "
            "Zero preserves the plain sleeve opening."
        ),
    )
    args = parser.parse_args()

    root = args.garmentcode_root.resolve()
    sys.path.insert(0, str(root / "pygarment"))
    sys.path.insert(0, str(root))

    from assets.bodies.body_params import BodyParameters
    from assets.garment_programs.meta_garment import MetaGarment
    from assets.garment_programs import tee
    from patterna_garment_blocks import (
        PatternaPrincessBodice,
        PatternaTorsoBackHalfPanel,
        PatternaTorsoFrontHalfPanel,
    )
    from patterna_pattern_postprocess import merge_mirrored_torso_halves

    with args.body.open("r", encoding="utf-8") as body_file:
        body_payload = (
            yaml.safe_load(body_file)
            if args.body.suffix.lower() in {".yaml", ".yml"}
            else json.load(body_file)
        )
    if "body" not in body_payload or not isinstance(body_payload["body"], dict):
        raise ValueError("Patterna body input must contain a body object.")

    body = BodyParameters(root / "assets" / "bodies" / "mean_female.yaml")
    body.load_from_dict(body_payload["body"])

    with (root / "assets" / "design_params" / "t-shirt.yaml").open(
        "r", encoding="utf-8"
    ) as design_file:
        design = copy.deepcopy(yaml.safe_load(design_file)["design"])

    is_crew_neck_shirt = args.style in {
        "crew-neck-shirt",
        "fitted-crew-neck-shirt",
        "patterna-shaped-crew-neck-shirt",
    }
    is_fitted_crew_neck = args.style == "fitted-crew-neck-shirt"
    is_patterna_shaped = args.style == "patterna-shaped-crew-neck-shirt"
    is_cup_aware_princess = args.style == "cup-aware-princess-top"
    uses_fitted_bodice = is_fitted_crew_neck or not is_crew_neck_shirt
    fitted_drafting_measurements = None
    if uses_fitted_bodice:
        fitted_drafting_measurements = apply_fitted_bodice_ease(
            body,
            args.chest_ease,
            args.waist_ease,
        )
    if is_patterna_shaped:
        tee.TorsoFrontHalfPanel = PatternaTorsoFrontHalfPanel
        tee.TorsoBackHalfPanel = PatternaTorsoBackHalfPanel
    design["meta"]["upper"]["v"] = (
        "FittedShirt" if is_fitted_crew_neck or not is_crew_neck_shirt else "Shirt"
    )
    design["meta"]["wb"]["v"] = None
    design["meta"]["bottom"]["v"] = (
        "PencilSkirt" if args.style == "fitted-pencil-dress" else None
    )
    design["shirt"]["width"]["v"] = args.shirt_width if is_crew_neck_shirt else 1.03
    design["shirt"]["length"]["v"] = args.shirt_length
    design["shirt"]["flare"]["v"] = (
        args.shirt_flare if args.style == "crew-neck-shirt" else 1.0
    )
    for name, value in (
        ("patterna_chest_ease", args.chest_ease),
        ("patterna_waist_ease", args.waist_ease),
        ("patterna_hip_ease", args.hip_ease),
    ):
        if value < -6 or value > 50:
            raise ValueError(f"{name} must be from -6 through 50 centimeters.")
        design["shirt"][name] = {"v": value}
    for name, value in (
        ("patterna_high_bust", args.high_bust),
        ("patterna_underbust", args.underbust),
        ("patterna_underbust_ease", args.underbust_ease),
        ("patterna_upper_torso_ease", args.upper_torso_ease),
        ("patterna_underarm_ease", args.underarm_ease),
        ("patterna_bust_span", args.bust_span),
        ("patterna_front_waist_length", args.front_waist_length),
        ("patterna_back_waist_length", args.back_waist_length),
        ("patterna_shoulder_to_bust", args.shoulder_to_bust),
        ("patterna_bust_height_from_waist", args.bust_height_from_waist),
        (
            "patterna_front_princess_contour_length",
            args.front_princess_contour_length,
        ),
        (
            "patterna_front_princess_upper_contour_length",
            args.front_princess_upper_contour_length,
        ),
        ("patterna_armscye_depth", args.armscye_depth),
        ("patterna_armscye_circumference", args.armscye_circumference),
        ("patterna_neck_half_width", args.neck_half_width),
    ):
        if value is not None:
            design["shirt"][name] = {"v": value}
    if args.hem_extension_depth < 0 or args.hem_extension_depth > body["hips_line"]:
        raise ValueError("Hem extension depth must be from zero through the body's hip depth.")
    if args.hem_extension_ease < -4 or args.hem_extension_ease > 30:
        raise ValueError("Hem extension ease must be from -4 through 30 centimeters.")
    if args.hem_extension_depth > 0:
        if not is_fitted_crew_neck:
            raise ValueError("The fitted hem extension currently requires the fitted crew-neck block.")
        design["meta"]["wb"]["v"] = "FittedWB"
        design["waistband"]["width"]["v"] = args.hem_extension_depth / body["hips_line"]
        design["waistband"]["waist"]["v"] = (
            body["waist"] + args.hem_extension_ease
        ) / body["waist"]
    design["sleeve"]["sleeveless"]["v"] = not (
        is_crew_neck_shirt or is_cup_aware_princess
    )
    design["sleeve"]["length"]["v"] = args.sleeve_length
    design["sleeve"]["sleeve_angle"]["v"] = args.sleeve_angle
    design["sleeve"]["end_width"]["v"] = args.sleeve_end_width
    design["sleeve"]["connect_ruffle"]["v"] = 1.0
    design["sleeve"]["cuff"]["type"]["v"] = None
    if args.sleeve_cuff_depth < 0 or args.sleeve_cuff_depth > 8:
        raise ValueError("Sleeve cuff depth must be from zero through eight centimeters.")
    if args.sleeve_end_width <= 0:
        raise ValueError("Sleeve end width must be positive.")
    if args.sleeve_cuff_depth > 0:
        design["sleeve"]["cuff"]["type"]["v"] = "CuffBand"
        design["sleeve"]["cuff"]["cuff_len"]["v"] = (
            args.sleeve_cuff_depth / body["arm_length"]
        )
    design["collar"]["f_collar"]["v"] = "CircleNeckHalf"
    design["collar"]["b_collar"]["v"] = "CircleNeckHalf"
    design["collar"]["width"]["v"] = args.neck_width
    design["collar"]["fc_depth"]["v"] = args.front_neck_depth
    design["collar"]["bc_depth"]["v"] = args.back_neck_depth
    if args.neck_band_depth < 0:
        raise ValueError("Neck band depth cannot be negative.")
    if args.neck_band_depth > 0:
        design["collar"]["component"]["style"]["v"] = "Turtle"
        design["collar"]["component"]["depth"]["v"] = args.neck_band_depth

    garment = (
        PatternaPrincessBodice(body, design)
        if is_cup_aware_princess
        else MetaGarment(args.style, body, design)
    )
    pattern = garment.assembly()
    if garment.is_self_intersecting():
        intersecting_panels = [
            name
            for name in pattern.pattern["panels"]
            if pattern._is_panel_self_intersecting(name)
        ]
        rejected_path = args.output.with_suffix(args.output.suffix + ".rejected.json")
        rejected_path.parent.mkdir(parents=True, exist_ok=True)
        with rejected_path.open("w", encoding="utf-8") as output_file:
            json.dump(
                {
                    "schemaVersion": "patterna.rejected-pattern-diagnostic/1.0",
                    "intersectingPanels": intersecting_panels,
                    "draftingMetadata": (
                        garment.drafting_metadata()
                        if is_cup_aware_princess
                        else None
                    ),
                    "pattern": pattern.spec,
                },
                output_file,
                indent=2,
            )
            output_file.write("\n")
        raise RuntimeError(
            "GarmentCode generated self-intersecting panels: "
            + ", ".join(intersecting_panels)
            + f". Diagnostic: {rejected_path}"
        )

    pattern.spec["patterna"] = {
        "generator": "tools/generate_garmentcode_pattern.py",
        "style": args.style,
        "body_parameter_count": len(body_payload["body"]),
        "body_reference": {
            "chest_cm": float(body_payload["body"]["bust"]),
            "waist_cm": float(body_payload["body"]["waist"]),
            "hip_cm": float(body_payload["body"]["hips"]),
            "shoulder_cm": float(body_payload["body"]["shoulder_w"]),
            "torso_cm": float(
                body_payload["body"].get(
                    "patterna_torso", body_payload["body"]["waist_line"]
                )
            ),
            "arm_length_cm": float(body_payload["body"]["arm_length"]),
            "upper_arm_circumference_cm": float(
                body_payload["body"].get(
                    "patterna_upper_arm_circumference",
                    args.upper_arm_circumference
                    if args.upper_arm_circumference is not None
                    else body_payload["body"].get("upper_arm_circumference", 31.0),
                )
            ),
            "armhole_depth_cm": float(
                body_payload["body"].get(
                    "patterna_requested_armhole_depth",
                    body_payload["body"].get(
                        "patterna_armhole_depth",
                        args.armscye_depth
                        if args.armscye_depth is not None
                        else body_payload["body"].get("armscye_depth", 20.0),
                    ),
                )
            ),
            "armscye_circumference_cm": float(
                body_payload["body"].get(
                    "patterna_armscye_circumference",
                    args.armscye_circumference
                    if args.armscye_circumference is not None
                    else body_payload["body"].get("armscye_circumference", 45.5),
                )
            ),
        },
        "design": {
            "shirt_width": design["shirt"]["width"]["v"],
            "shirt_length": design["shirt"]["length"]["v"],
            "shirt_flare": design["shirt"]["flare"]["v"],
            "chest_ease_cm": args.chest_ease,
            "underbust_ease_cm": args.underbust_ease,
            "upper_torso_ease_cm": args.upper_torso_ease,
            "underarm_ease_cm": args.underarm_ease,
            "waist_ease_cm": args.waist_ease,
            "hip_ease_cm": args.hip_ease,
            "hem_extension_depth_cm": args.hem_extension_depth,
            "hem_extension_ease_cm": args.hem_extension_ease,
            "neck_width": args.neck_width,
            "front_neck_depth": args.front_neck_depth,
            "back_neck_depth": args.back_neck_depth,
            "neck_band_depth": args.neck_band_depth,
            "sleeve_length": args.sleeve_length,
            "sleeve_angle": args.sleeve_angle,
            "sleeve_end_width": args.sleeve_end_width,
            "sleeve_cuff_depth": args.sleeve_cuff_depth,
            "fitted_ease_applied_to_block": uses_fitted_bodice,
            "fitted_drafting_measurements": fitted_drafting_measurements,
            "cup_aware_block": (
                garment.drafting_metadata() if is_cup_aware_princess else None
            ),
        },
    }
    if is_patterna_shaped:
        pattern.spec = merge_mirrored_torso_halves(pattern.spec)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output_file:
        json.dump(pattern.spec, output_file, indent=2)
        output_file.write("\n")

    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "panels": len(pattern.spec["pattern"]["panels"]),
                "stitches": len(pattern.spec["pattern"]["stitches"]),
                "style": args.style,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
