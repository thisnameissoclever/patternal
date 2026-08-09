#!/usr/bin/env python3
"""Patterna control contract for the CharMorph female avatar backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from charmorph_morphs import combine_morphs


PATTERNA_FULL_BUST_CONTROLS: dict[str, float] = {
    "Arms_UpperarmGirth": -0.66,
    "Arms_UpperarmMass": -0.58,
    "Arms_UpperarmSize": -0.44,
    "Arms_UpperarmTone": -0.72,
    "Chest_Girth": 0.00,
    "Chest_SizeX": 0.10,
    "Chest_SizeY": 0.05,
    "Abdomen_Mass": 0.00,
    "Pelvis_Girth": -0.05,
    "Pelvis_GluteusSize": 0.08,
    "Pelvis_SizeX": 0.00,
    "Pelvis_SizeY": 0.00,
    "Shoulders_Length": -0.20,
    "Shoulders_Mass": -0.48,
    "Shoulders_PosZ": -0.10,
    "Shoulders_Size": -0.30,
    "Shoulders_Tone": -0.55,
    "Stomach_LocalFat": 0.10,
    "Stomach_Volume": 0.00,
    "Torso_BreastMass": 0.58,
    "Torso_BreastPosX": -0.50,
    "Torso_BreastPosZ": 0.18,
    "Torso_BreastScaleY": -0.15,
    "Torso_BreastTone": 0.35,
    "Torso_BreastNipple": -0.80,
    "Torso_Mass": 0.05,
    "Torso_SizeX": 0.00,
    "Torso_SizeY": 0.00,
    "Torso_Tone": -0.20,
    "Waist_Size": 0.25,
}


FIT_CONTROL_NAMES = (
    "Abdomen_Mass",
    "Chest_Girth",
    "Chest_SizeX",
    "Chest_SizeY",
    "Pelvis_Girth",
    "Pelvis_SizeX",
    "Pelvis_SizeY",
    "Stomach_LocalFat",
    "Stomach_Volume",
    "Torso_BreastMass",
    "Torso_BreastPosX",
    "Torso_BreastScaleY",
    "Torso_Mass",
    "Torso_SizeX",
    "Torso_SizeY",
    "Waist_Size",
)

FIT_TARGET_NAMES = (
    "hip",
    "abdomen",
    "waist",
    "underbust",
    "bust",
    "bust_separation",
)

FIT_CONTROL_BOUNDS: dict[str, tuple[float, float]] = {
    "Abdomen_Mass": (-0.30, 0.35),
    "Chest_Girth": (-0.35, 0.40),
    "Chest_SizeX": (-0.20, 0.40),
    "Chest_SizeY": (-0.20, 0.40),
    "Pelvis_Girth": (-0.60, 0.35),
    "Pelvis_SizeX": (-0.30, 0.30),
    "Pelvis_SizeY": (-0.30, 0.30),
    "Stomach_LocalFat": (-0.30, 0.35),
    "Stomach_Volume": (-0.30, 0.35),
    "Torso_BreastMass": (0.35, 0.72),
    "Torso_BreastPosX": (-0.65, 0.10),
    "Torso_BreastScaleY": (-0.30, 0.15),
    "Torso_Mass": (-0.20, 0.35),
    "Torso_SizeX": (-0.30, 0.30),
    "Torso_SizeY": (-0.30, 0.30),
    "Waist_Size": (-0.20, 0.85),
}


ANTONIA_FULL_BUST_CONTROLS: dict[str, float] = {
    "Breast big": 0.5095,
    "Breast diameter": 0.016,
    "Breast implant": 0.1836,
    "PBM-breasts-classic": 0.7396,
    "Breast move to outside": 0.0,
    "Breast move to inside": 0.1196,
    "Breast hang forward": 0.80,
    "Pear": 0.7077,
    "Hip narrow": 1.0,
    "Belly flat": 0.0,
    "Belly thick": 0.0,
    "Waist narrow": 0.0,
    "Arms petite": 0.35,
    "Shoulder small": 0.20,
}

ANTONIA_FIT_CONTROL_NAMES = (
    "Breast big",
    "Breast diameter",
    "Breast implant",
    "PBM-breasts-classic",
    "Breast move to outside",
    "Breast move to inside",
    "Breast hang forward",
    "Pear",
    "Hip narrow",
    "Belly flat",
    "Belly thick",
    "Waist narrow",
)

ANTONIA_FIT_CONTROL_BOUNDS: dict[str, tuple[float, float]] = {
    "Breast big": (0.35, 0.60),
    "Breast diameter": (0.0, 0.70),
    "Breast implant": (0.10, 0.35),
    "PBM-breasts-classic": (0.45, 1.0),
    "Breast move to outside": (0.0, 0.40),
    "Breast move to inside": (0.0, 0.60),
    "Breast hang forward": (0.35, 0.80),
    "Pear": (0.0, 1.0),
    "Hip narrow": (0.0, 1.0),
    "Belly flat": (0.0, 1.0),
    "Belly thick": (0.0, 1.0),
    "Waist narrow": (0.0, 1.0),
}


@dataclass(frozen=True)
class FitControlContract:
    backend: str
    initial_controls: Mapping[str, float]
    fit_control_names: tuple[str, ...]
    fit_control_bounds: Mapping[str, tuple[float, float]]
    bust_refinement_names: tuple[str, ...]
    bust_separation_weight: float


MB_FEMALE_FIT_CONTRACT = FitControlContract(
    backend="CharMorph MB female",
    initial_controls=PATTERNA_FULL_BUST_CONTROLS,
    fit_control_names=FIT_CONTROL_NAMES,
    fit_control_bounds=FIT_CONTROL_BOUNDS,
    bust_refinement_names=("Torso_BreastMass", "Torso_BreastPosX", "Torso_BreastScaleY"),
    bust_separation_weight=1.0,
)

ANTONIA_FIT_CONTRACT = FitControlContract(
    backend="Antonia Polygon",
    initial_controls=ANTONIA_FULL_BUST_CONTROLS,
    fit_control_names=ANTONIA_FIT_CONTROL_NAMES,
    fit_control_bounds=ANTONIA_FIT_CONTROL_BOUNDS,
    bust_refinement_names=(
        "Breast big",
        "Breast diameter",
        "Breast hang forward",
        "Breast move to inside",
    ),
    bust_separation_weight=2.0,
)


def resolve_fit_control_contract(raw_morphs: Mapping[str, object]) -> FitControlContract:
    grouped_controls = {
        control_name
        for group in combine_morphs(raw_morphs).values()
        for control_name in group.control_names
    }
    available = set(raw_morphs) | grouped_controls
    for contract in (MB_FEMALE_FIT_CONTRACT, ANTONIA_FIT_CONTRACT):
        required = set(contract.fit_control_names) | set(contract.bust_refinement_names)
        if required <= available:
            return contract
    raise ValueError(
        "CharMorph backend has no supported Patterna measurement-fit control contract"
    )


def clamp_controls(controls: dict[str, float]) -> dict[str, float]:
    return {name: max(-1.0, min(1.0, float(value))) for name, value in controls.items()}


def measurement_targets(profile: dict[str, object]) -> dict[str, float]:
    body = profile.get("body")
    measurements = profile.get("measurements")
    if not isinstance(body, dict) or not isinstance(measurements, dict):
        raise ValueError("CharMorph fitting requires body and measurements objects")
    targets = {
        "hip": float(measurements.get("hip", body["hips"])),
        "abdomen": float(measurements["abdomenCirc"]),
        "waist": float(measurements.get("waist", body["waist"])),
        "underbust": float(measurements["underBust"]),
        "bust": float(measurements.get("chest", body["bust"])),
        "bust_separation": float(
            measurements.get("bustSeparation", body["bust_points"])
        ),
        "high_chest": float(measurements["highChestCirc"]),
    }
    if any(value <= 0.0 for value in targets.values()):
        raise ValueError("CharMorph measurement targets must be positive")
    return targets
