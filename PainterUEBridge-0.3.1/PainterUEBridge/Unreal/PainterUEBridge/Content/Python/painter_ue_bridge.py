"""UE editor-thread consumer. Only publishes imports from completed export jobs."""
import json
from pathlib import Path
import time

import unreal
from bridge_protocol import asset_name, validate, validate_mesh, match_slots

_handle = None
_next_poll = 0.0
_processing = False
_blocked = set()
_config_path = Path(unreal.Paths.project_saved_dir()) / "PainterUEBridge.json"
_config = {"sync_folder": "D:/UnrealPlugins/PainterUEBridge/Sync", "destination": "/Game/PainterSync"}


def configure(sync_folder, destination="/Game/PainterSync"):
    import re
    if not re.fullmatch(r"/Game/[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*", destination):
        raise ValueError("Destination must be a content folder such as /Game/PainterSync")
    folder = Path(sync_folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    _config.update(sync_folder=str(folder), destination=destination)
    _config_path.parent.mkdir(parents=True, exist_ok=True)
    _config_path.write_text(json.dumps(_config, indent=2), encoding="utf-8")
    unreal.log("Painter UE Bridge configured: " + str(folder))


def _save(asset):
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False):
        raise RuntimeError("Could not save " + asset.get_path_name())


def _load_typed(path, cls):
    asset = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
    if asset is not None and not isinstance(asset, cls):
        raise RuntimeError("Existing asset has incompatible type: " + path)
    return asset


def _texture(source, folder, name, kind):
    path = folder + "/" + name
    _load_typed(path, unreal.Texture2D)
    task = unreal.AssetImportTask()
    for prop, value in {"filename": source, "destination_path": folder, "destination_name": name,
                        "automated": True, "replace_existing": True, "save": False}.items():
        task.set_editor_property(prop, value)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    if not task.get_editor_property("imported_object_paths"):
        raise RuntimeError("Texture import failed: " + source)
    texture = _load_typed(path, unreal.Texture2D)
    if texture is None:
        raise RuntimeError("Imported texture missing: " + path)
    texture.set_editor_property("srgb", kind == "BaseColor")
    compression = {"BaseColor": unreal.TextureCompressionSettings.TC_DEFAULT,
                   "Normal": unreal.TextureCompressionSettings.TC_NORMALMAP,
                   "ORM": unreal.TextureCompressionSettings.TC_MASKS}[kind]
    texture.set_editor_property("compression_settings", compression)
    if kind == "Normal":
        texture.set_editor_property("flip_green_channel", False)
    _save(texture)
    return texture


def _master(folder, textures):
    path = folder + "/M_PainterBridge"
    material = _load_typed(path, unreal.Material)
    if material:
        return material
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        "M_PainterBridge", folder, unreal.Material, unreal.MaterialFactoryNew())
    if not material:
        raise RuntimeError("Could not create master material")
    library = unreal.MaterialEditingLibrary
    for index, kind in enumerate(("BaseColor", "Normal", "ORM")):
        node = library.create_material_expression(material, unreal.MaterialExpressionTextureSampleParameter2D, -500, index * 260)
        node.set_editor_property("parameter_name", kind)
        node.set_editor_property("texture", textures[kind])
        node.set_editor_property("sampler_type", {"BaseColor": unreal.MaterialSamplerType.SAMPLERTYPE_COLOR,
            "Normal": unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL,
            "ORM": unreal.MaterialSamplerType.SAMPLERTYPE_MASKS}[kind])
        outputs = {"BaseColor": [("RGB", unreal.MaterialProperty.MP_BASE_COLOR)],
                   "Normal": [("RGB", unreal.MaterialProperty.MP_NORMAL)],
                   "ORM": [("R", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION),
                           ("G", unreal.MaterialProperty.MP_ROUGHNESS),
                           ("B", unreal.MaterialProperty.MP_METALLIC)]}[kind]
        for output, prop in outputs:
            if not library.connect_material_property(node, output, prop):
                raise RuntimeError("Could not connect material property: " + kind)
    library.recompile_material(material)
    _save(material)
    return material


def _model(source, folder, instances):
    mesh = _load_typed(folder + "/SM_PainterModel", unreal.StaticMesh)
    created = mesh is None
    axis_version = "PainterOBJ_YUp_v1"
    needs_import = created or unreal.EditorAssetLibrary.get_metadata_tag(mesh, "PainterBridgeAxis") != axis_version
    if needs_import:
        options = unreal.FbxImportUI()
        options.set_editor_property("import_mesh", True)
        options.set_editor_property("import_as_skeletal", False)
        options.set_editor_property("import_materials", False)
        options.set_editor_property("import_textures", False)
        options.set_editor_property("automated_import_should_detect_type", False)
        options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
        options.static_mesh_import_data.set_editor_property("combine_meshes", True)
        # OBJ does not carry an up-axis declaration. Painter exports Y-up.
        options.static_mesh_import_data.set_editor_property("convert_scene", False)
        options.static_mesh_import_data.set_editor_property("import_rotation", unreal.Rotator(pitch=0, yaw=0, roll=90))
        task = unreal.AssetImportTask()
        for prop, value in {"filename": source, "destination_path": folder,
                            "destination_name": "SM_PainterModel", "automated": True,
                            "replace_existing": True, "replace_existing_settings": True,
                            "save": False, "options": options, "factory": unreal.FbxFactory()}.items():
            task.set_editor_property(prop, value)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        mesh = _load_typed(folder + "/SM_PainterModel", unreal.StaticMesh)
        if mesh is None:
            raise RuntimeError("Model import failed: " + source)
    slots = mesh.get_editor_property("static_materials")
    if not slots:
        raise RuntimeError("Imported model has no material slots")
    names = []
    for slot in slots:
        original = str(slot.get_editor_property("imported_material_slot_name"))
        names.append(original if original not in ("", "None") else str(slot.get_editor_property("material_slot_name")))
    matched = match_slots(names, instances)
    changed = False
    for index, name in enumerate(matched):
        if mesh.get_material(index) != instances[name]:
            mesh.set_material(index, instances[name])
            changed = True
    if needs_import:
        unreal.EditorAssetLibrary.set_metadata_tag(mesh, "PainterBridgeAxis", axis_version)
    if changed or needs_import:
        _save(mesh)
    unreal.log("Painter UE Bridge model ready: " + mesh.get_path_name())


def _consume(manifest):
    data = json.loads(manifest.read_text(encoding="utf-8"))
    maps = validate(data, _config["sync_folder"])
    model_source = validate_mesh(data, _config["sync_folder"])
    if manifest.name != data["id"] + ".ready.json":
        raise ValueError("Manifest filename does not match job ID")
    project = asset_name(data["project"] + "|" + data["project_path"])
    folder = _config["destination"] + "/" + project
    instances = {}
    for set_name, files in maps.items():
        name = asset_name(set_name)
        textures = {kind: _texture(source, folder, "T_" + name + "_" + kind, kind)
                    for kind, source in files.items()}
        master = _master(folder, textures)
        instance_name = "MI_" + name
        instance = _load_typed(folder + "/" + instance_name, unreal.MaterialInstanceConstant)
        if not instance:
            instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                instance_name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        if not instance:
            raise RuntimeError("Could not create material instance")
        changed = False
        if instance.get_editor_property("parent") != master:
            unreal.MaterialEditingLibrary.set_material_instance_parent(instance, master)
            changed = True
        for kind, texture in textures.items():
            # UE 5.8 returns false even after setting successfully; verify by reading back.
            actual = unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_value(instance, kind)
            if actual != texture:
                unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(instance, kind, texture)
                if unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_value(instance, kind) != texture:
                    raise RuntimeError("Could not update material parameter: " + kind)
                changed = True
        if changed:
            unreal.MaterialEditingLibrary.update_material_instance(instance)
            _save(instance)
        instances[set_name] = instance
    if model_source:
        _model(model_source, folder, instances)
    manifest.rename(manifest.with_name(data["id"] + ".done.json"))
    unreal.log("Painter UE Bridge synced: " + data["project"])


def _tick(delta):
    global _next_poll, _processing
    # Import/save can pump Slate events and re-enter this callback on the same thread.
    if _processing or time.monotonic() < _next_poll:
        return
    _processing = True
    _next_poll = time.monotonic() + 0.25
    try:
        manifests = sorted(Path(_config["sync_folder"]).glob("*.ready.json"), key=lambda p: p.stat().st_mtime_ns)
        # Process in order. A failed job blocks newer jobs until explicitly retried.
        if not manifests or str(manifests[0]) in _blocked:
            return
        manifest = manifests[0]
        try:
            _consume(manifest)
        except Exception as exc:
            _blocked.add(str(manifest))
            unreal.log_error("Painter UE Bridge: " + str(exc) + "; fix the issue, then run painter_ue_bridge.retry()")
    except Exception as exc:
        unreal.log_error("Painter UE Bridge polling failed: " + str(exc))
        _next_poll = time.monotonic() + 30.0
    finally:
        _processing = False


def retry():
    _blocked.clear()


def start():
    global _handle
    stop()
    if _config_path.exists():
        saved = json.loads(_config_path.read_text(encoding="utf-8"))
        configure(saved["sync_folder"], saved["destination"])
    _handle = unreal.register_slate_post_tick_callback(_tick)
    unreal.log("Painter UE Bridge listening: " + _config["sync_folder"])


def stop():
    global _handle
    if _handle is not None:
        unreal.unregister_slate_post_tick_callback(_handle)
        _handle = None
