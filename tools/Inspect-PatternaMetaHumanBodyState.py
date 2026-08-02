import json
from pathlib import Path

import unreal


CHARACTER_PATH = "/Game/MH_Patterna_Female_Default.MH_Patterna_Female_Default"
REPORT_PATH = (
    Path(unreal.Paths.project_saved_dir())
    / "Patterna"
    / "MetaHumanBodyStateDiagnostics.json"
)


character = unreal.load_asset(CHARACTER_PATH)
if character is None:
    raise RuntimeError(f"MetaHuman Character was not found: {CHARACTER_PATH}")

subsystem = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
if not subsystem.try_add_object_to_edit(character):
    raise RuntimeError("MetaHuman Character could not be opened for diagnostics.")

try:
    result = unreal.PatternaMetaHumanEditorLibrary.get_body_state_diagnostics(
        character
    )
    global_delta_scale, lod_zero_vertex_count, minimum, maximum = result
    report = {
        "schemaVersion": "patterna.metahuman-body-state-diagnostics/1.0",
        "character": CHARACTER_PATH,
        "globalDeltaScale": float(global_delta_scale),
        "lodZeroVertexCount": int(lod_zero_vertex_count),
        "boundsCm": {
            "minimum": [float(minimum.x), float(minimum.y), float(minimum.z)],
            "maximum": [float(maximum.x), float(maximum.y), float(maximum.z)],
        },
    }
    section_values = (
        unreal.PatternaMetaHumanEditorLibrary.get_evaluated_body_cross_sections(
            character,
            [97.0, 99.0, 101.0, 103.0, 105.0, 107.0, 109.0],
        )
    )
    report["crossSections"] = [
        {
            "heightCm": float(section.x),
            "widthCm": float(section.y),
            "depthCm": float(section.z),
            "ellipseCircumferenceCm": float(section.w),
        }
        for section in section_values
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    unreal.log(f"Patterna wrote MetaHuman body diagnostics to {REPORT_PATH}")
finally:
    if subsystem.is_object_added_for_editing(character):
        subsystem.remove_object_to_edit(character)
