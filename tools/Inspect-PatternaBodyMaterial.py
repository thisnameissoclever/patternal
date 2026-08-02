import unreal


MATERIAL_PATH = (
    "/Game/PatternaMeasuredV2/MH_Patterna_Female_Default/Body/"
    "Materials/MI_Body_Baked"
)

material = unreal.load_asset(MATERIAL_PATH)
if material is None:
    raise RuntimeError(f"Patterna body material could not be loaded: {MATERIAL_PATH}")

unreal.log(f"Patterna body material: {material.get_path_name()}")
for method_name in dir(unreal.MaterialEditingLibrary):
    if "parameter" in method_name.lower() and "texture" in method_name.lower():
        unreal.log(f"Patterna material API: {method_name}")

parameter_names = unreal.MaterialEditingLibrary.get_texture_parameter_names(material)
for parameter_name in parameter_names:
    texture = unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_value(
        material,
        parameter_name,
    )
    texture_path = texture.get_path_name() if texture is not None else "<none>"
    unreal.log(f"Patterna texture parameter {parameter_name}: {texture_path}")
