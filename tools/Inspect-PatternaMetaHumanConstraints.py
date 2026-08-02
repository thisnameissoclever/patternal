import json
from pathlib import Path

import unreal


CHARACTER_PATH = "/Game/MH_Patterna_Female_Default.MH_Patterna_Female_Default"
REPORT_PATH = Path(unreal.Paths.project_saved_dir()) / "Patterna" / "MetaHumanBodyConstraints.json"


def constraint_record(constraint):
    return {
        "name": str(constraint.name),
        "isActive": bool(constraint.is_active),
        "targetMeasurementCm": float(constraint.target_measurement),
        "minimumMeasurementCm": float(constraint.min_measurement),
        "maximumMeasurementCm": float(constraint.max_measurement),
    }


character = unreal.load_asset(CHARACTER_PATH)
if character is None:
    raise RuntimeError(f"Patterna MetaHuman Character asset was not found: {CHARACTER_PATH}")

subsystem = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
if not subsystem.try_add_object_to_edit(character):
    raise RuntimeError("Patterna MetaHuman Character could not be opened for constraint inspection.")

try:
    records = [constraint_record(item) for item in subsystem.get_body_constraints(character)]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")
    unreal.log(f"Patterna exported {len(records)} MetaHuman body constraints to {REPORT_PATH}")
finally:
    if subsystem.is_object_added_for_editing(character):
        subsystem.remove_object_to_edit(character)
