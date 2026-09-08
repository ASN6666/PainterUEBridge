"""Validation shared by the importer and offline tests (no Unreal dependency)."""
import hashlib
import re
from pathlib import Path


def asset_name(value):
    safe = re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_")[:48] or "Asset"
    return safe + "_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def validate(data, folder):
    if data.get("version") != 1:
        raise ValueError("Unsupported manifest version")
    if not re.fullmatch(r"[0-9a-f]{32}", data.get("id", "")):
        raise ValueError("Invalid job ID")
    for field in ("project", "project_path"):
        if not isinstance(data.get(field), str) or not data[field]:
            raise ValueError("Missing " + field)
    materials = data.get("materials")
    if not isinstance(materials, dict) or not materials:
        raise ValueError("Empty materials")
    root = (Path(folder) / "jobs" / data["id"]).resolve()
    checked = {}
    for name, maps in materials.items():
        if not isinstance(name, str) or not name or not isinstance(maps, dict) or set(maps) != {"BaseColor", "Normal", "ORM"}:
            raise ValueError("Invalid texture set")
        checked[name] = {}
        for kind, relative in maps.items():
            path = (Path(folder) / relative).resolve()
            path.relative_to(root)
            if path.suffix.lower() != ".png" or not path.is_file() or path.stat().st_size == 0:
                raise ValueError("Missing or invalid PNG: " + str(path))
            checked[name][kind] = str(path)
    return checked


def validate_mesh(data, folder):
    mesh = data.get("mesh")
    if mesh is None:
        return None  # Existing texture-only jobs remain compatible.
    if not isinstance(mesh, dict) or not isinstance(mesh.get("file"), str):
        raise ValueError("Invalid mesh manifest")
    root = (Path(folder) / "meshes").resolve()
    path = (Path(folder) / mesh["file"]).resolve()
    relative = path.relative_to(root)
    if (len(relative.parts) != 2 or not re.fullmatch(r"[0-9a-f]{32}", relative.parts[0])
            or path.name != "model.obj" or not path.is_file() or not path.stat().st_size):
        raise ValueError("Invalid OBJ source")
    return str(path)


def match_slots(slot_names, material_names):
    """Exact source names first; only normalize when there is one unambiguous match."""
    result = []
    for slot in slot_names:
        if slot in material_names:
            result.append(slot)
            continue
        normalize = lambda value: re.sub(r"[^a-z0-9]", "", value.lower())
        matches = [name for name in material_names if normalize(name) == normalize(slot)]
        if len(matches) == 1:
            result.append(matches[0])
        elif len(slot_names) == 1 and len(material_names) == 1:
            result.append(next(iter(material_names)))
        else:
            raise ValueError("Cannot uniquely match model material slot: " + slot)
    return result
