"""Substance 3D Painter plugin: debounced automatic texture handoff."""
import hashlib
import json
import os
from pathlib import Path
import uuid
import time

import substance_painter as sp
import substance_painter.export
import substance_painter.project
import substance_painter.textureset
import substance_painter.ui
import substance_painter.event
import substance_painter.js
try:
    from PySide2 import QtWidgets, QtGui, QtCore
    QT_BINDING = "PySide2"
except ImportError:
    from PySide6 import QtWidgets, QtGui, QtCore
    QT_BINDING = "PySide6"

DEFAULT_SYNC = "D:/UnrealPlugins/PainterUEBridge/Sync"
_actions = []
_connections = []
_timer = None
_live_action = None
_live = False
_dirty = False
_exporting = False
_due = 0.0
_last_signature = None
_status = "Live Sync off"
_mesh_exports = {}


def _export_model(folder, project_path):
    key = (str(folder.resolve()), project_path)
    cached = _mesh_exports.get(key)
    if cached and (folder / cached["file"]).is_file():
        return cached
    # Painter 2022 exports the processed mesh, including the mesh embedded in sample SPPs.
    target = folder.resolve() / "meshes" / uuid.uuid4().hex / "model.obj"
    target.parent.mkdir(parents=True, exist_ok=False)
    sp.js.evaluate("alg.project.exportMesh(" + json.dumps(target.as_uri()) + ");")
    if not target.is_file() or not target.stat().st_size:
        raise RuntimeError("Painter did not export the OBJ model")
    mesh = {"file": target.relative_to(folder.resolve()).as_posix()}
    _mesh_exports[key] = mesh
    return mesh


def _set_status(message):
    global _status
    if message != _status:
        _status = message
        print("[Painter UE Bridge] " + message)
    if _live_action is not None:
        _live_action.setToolTip(message)


def _on_texture_changed(event=None):
    global _dirty, _due
    # Export can itself emit texture events. Never export inside a Painter event callback.
    if _live and not _exporting:
        _dirty = True
        _due = time.monotonic() + 0.6


def _on_project_closed(event=None):
    global _dirty, _last_signature
    _dirty = False
    _last_signature = None
    _mesh_exports.clear()


def set_live(enabled):
    global _live, _dirty, _last_signature
    _live = bool(enabled)
    _dirty = False
    _last_signature = None
    if _live:
        if not hasattr(sp.event, "TextureStateEvent") or not callable(getattr(sp.project, "is_busy", None)):
            _live = False
            _set_status("Live Sync unavailable: this Painter version needs TextureStateEvent and project.is_busy().")
        else:
            _set_status("Live Sync on; waiting for a saved project")
            _on_texture_changed()
    else:
        _set_status("Live Sync off")
    if _live_action is not None:
        _live_action.blockSignals(True)
        _live_action.setChecked(_live)
        _live_action.blockSignals(False)


def _poll_live():
    global _dirty, _exporting, _due
    if not _live or not _dirty or _exporting or time.monotonic() < _due:
        return
    try:
        if not sp.project.is_open() or sp.project.is_busy():
            return
        if not sp.project.file_path():
            _set_status("Save the Painter project once to start Live Sync")
            return
        # Allow only one unacknowledged export. Keep edits dirty while UE is busy/offline.
        if next(sync_folder().glob("*.ready.json"), None) is not None:
            _set_status("Waiting for UE5; latest edits will sync after the pending job")
            _due = time.monotonic() + 0.5
            return
        _dirty = False
        _exporting = True
        _export_textures(live=True)
    except Exception as exc:
        set_live(False)
        _set_status("Live Sync paused after error: " + str(exc) + "; fix and re-enable Live Sync")
    finally:
        _exporting = False


def show_status():
    import sys
    details = "\nPython " + sys.version.split()[0] + " / " + QT_BINDING
    event_type = getattr(sp.event, "TextureStateEvent", None)
    get_period = getattr(event_type, "cache_key_invalidation_throttling_period", None)
    if callable(get_period):
        details += "\nPainter event interval: " + str(get_period().total_seconds()) + " s"
    QtWidgets.QMessageBox.information(None, "Painter → UE5", _status + "\n" + str(sync_folder()) + details)


def sync_folder():
    return Path(QtCore.QSettings("PainterUEBridge", "PainterUEBridge").value("sync_folder", DEFAULT_SYNC))


def choose_folder():
    folder = QtWidgets.QFileDialog.getExistingDirectory(None, "Choose shared UE5 sync folder", str(sync_folder()))
    if folder:
        QtCore.QSettings("PainterUEBridge", "PainterUEBridge").setValue("sync_folder", folder)
        _on_project_closed()
        _on_texture_changed()


def channel(source, destination, source_channel="L"):
    return {"destChannel": destination, "srcChannel": source_channel,
            "srcMapType": "documentMap", "srcMapName": source}


def export_preset():
    return {"name": "PainterUEBridge", "maps": [
        {"fileName": "$textureSet_BaseColor", "channels": [channel("baseColor", c, c) for c in "RGB"]},
        {"fileName": "$textureSet_Normal", "channels": [
            {"destChannel": c, "srcChannel": c, "srcMapType": "virtualMap", "srcMapName": "Normal_DirectX"} for c in "RGB"]},
        {"fileName": "$textureSet_ORM", "channels": [
            {"destChannel": "R", "srcChannel": "L", "srcMapType": "virtualMap", "srcMapName": "AO_Mixed"},
            channel("roughness", "G"), channel("metallic", "B")]}
    ]}


def _export_textures(live=False):
    global _last_signature
    if not sp.project.is_open():
        raise RuntimeError("Open and save a Painter project first.")
    project_path = sp.project.file_path()
    if not project_path:
        raise RuntimeError("Save the Painter project before sending.")
    # UDIM imports require a separate virtual-texture material workflow.
    sets = sp.textureset.all_texture_sets()
    for texture_set in sets:
        layered = getattr(texture_set, "is_layered_material", None)
        if callable(layered) and layered():
            raise RuntimeError("Layered materials are not supported")
        has_tiles = getattr(texture_set, "has_uv_tiles", None)
        if callable(has_tiles) and has_tiles():
            raise RuntimeError("UDIM texture sets are not supported")
    folder = sync_folder()
    job_id = uuid.uuid4().hex
    job_folder = folder / "jobs" / job_id
    job_folder.mkdir(parents=True, exist_ok=False)
    config = {
        "exportPath": str(job_folder), "exportShaderParams": False,
        "defaultExportPreset": "PainterUEBridge",
        "exportPresets": [export_preset()],
        "exportList": [{"rootPath": str(s.name())} for s in sets],
        "exportParameters": [{"parameters": {"fileFormat": "png", "bitDepth": "8",
            "dithering": False, "paddingAlgorithm": "infinite"}}]
    }
    result = sp.export.export_project_textures(config)
    if result.status != sp.export.ExportStatus.Success:
        raise RuntimeError(str(result.message))
    materials = {}
    for paths in result.textures.values():
        for exported in paths:
            path = Path(exported).resolve()
            path.relative_to(job_folder.resolve())
            for kind in ("BaseColor", "Normal", "ORM"):
                suffix = "_" + kind
                if path.stem.endswith(suffix):
                    name = path.stem[:-len(suffix)]
                    maps = materials.setdefault(name, {})
                    if kind in maps:
                        raise RuntimeError("Duplicate export output; UDIM/layered texture sets are not supported.")
                    maps[kind] = path.relative_to(folder.resolve()).as_posix()
    if not materials or any(set(m) != {"BaseColor", "Normal", "ORM"} for m in materials.values()):
        raise RuntimeError("Export did not produce one BaseColor, Normal and ORM map per texture set.")
    manifest = {"version": 1, "id": job_id, "project": Path(project_path).stem,
                "project_path": str(Path(project_path).resolve()), "materials": materials,
                "producer": "PainterUEBridge", "live": live}
    manifest["mesh"] = _export_model(folder, manifest["project_path"])
    digest = hashlib.sha256()
    digest.update((str(folder.resolve()) + manifest["project_path"]).encode("utf-8"))
    for name, maps in sorted(materials.items()):
        for kind, relative in sorted(maps.items()):
            digest.update((name + "|" + kind).encode("utf-8"))
            with (folder / relative).open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
    signature = digest.hexdigest()
    if live and signature == _last_signature:
        _remove_snapshot(folder, manifest)
        _set_status("Live Sync on; exported pixels unchanged")
        return
    pending = folder / (job_id + ".tmp")
    pending.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(pending), str(folder / (job_id + ".ready.json")))
    _last_signature = signature
    _set_status("Textures queued for UE5" + (" (Live Sync)" if live else ""))
    _prune_completed(folder, manifest["project_path"])


def _remove_snapshot(folder, manifest):
    """Remove only this producer's listed derived files; never recursively delete directories."""
    if manifest.get("producer") != "PainterUEBridge":
        return
    job_id = manifest["id"]
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise ValueError("Invalid snapshot ID")
    root = (folder / "jobs").resolve()
    job = (root / job_id).resolve()
    if job.parent != root:
        raise ValueError("Snapshot outside jobs folder")
    paths = [(folder / relative).resolve() for maps in manifest["materials"].values() for relative in maps.values()]
    if any(path.parent != job or path.suffix.lower() != ".png" for path in paths):
        raise ValueError("Invalid snapshot file path")
    for path in set(paths):
        path.unlink(missing_ok=True)
    if job.exists():
        job.rmdir()  # Fails safely if unexpected files are present.


def _prune_completed(folder, project_path):
    # Retain two acknowledged full snapshots for this project, including UE reimport sources.
    try:
        completed = []
        for path in folder.glob("*.done.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if (data.get("producer") == "PainterUEBridge" and data.get("live") is True
                    and data.get("project_path") == project_path and path.name == data["id"] + ".done.json"):
                completed.append((path.stat().st_mtime_ns, path, data))
        for _, path, data in sorted(completed, key=lambda item: item[0])[:-2]:
            _remove_snapshot(folder, data)
            path.unlink()
    except Exception as exc:
        print("[Painter UE Bridge] Snapshot cleanup skipped: " + str(exc))


def send_to_unreal():
    global _exporting
    if _exporting:
        return
    try:
        _exporting = True
        _export_textures()
        QtWidgets.QMessageBox.information(None, "Painter → UE5", "Textures exported and queued for UE5.\n" + str(sync_folder()))
    except Exception as exc:
        QtWidgets.QMessageBox.warning(None, "Painter → UE5 failed", str(exc))
    finally:
        _exporting = False


def start_plugin():
    global _timer, _live_action
    close_plugin()
    action_class = getattr(QtGui, "QAction", None) or QtWidgets.QAction
    for label, callback in (("Send textures to UE5", send_to_unreal), ("UE5 sync folder…", choose_folder),
                            ("UE5 sync status…", show_status)):
        action = action_class(label, sp.ui.get_main_window())
        action.triggered.connect(callback)
        sp.ui.add_action(sp.ui.ApplicationMenu.File, action)
        _actions.append(action)
    _live_action = action_class("UE5 Live Sync", sp.ui.get_main_window())
    _live_action.setCheckable(True)
    _live_action.toggled.connect(set_live)
    sp.ui.add_action(sp.ui.ApplicationMenu.File, _live_action)
    _actions.append(_live_action)
    for event_name, callback in (("TextureStateEvent", _on_texture_changed),
                                 ("ProjectOpened", _on_texture_changed),
                                 ("ProjectSaved", _on_texture_changed),
                                 ("ProjectAboutToClose", _on_project_closed)):
        event_type = getattr(sp.event, event_name, None)
        if event_type is not None:
            sp.event.DISPATCHER.connect(event_type, callback)
            _connections.append((event_type, callback))
    _timer = QtCore.QTimer(sp.ui.get_main_window())
    _timer.setInterval(150)
    _timer.timeout.connect(_poll_live)
    _timer.start()


def close_plugin():
    global _timer, _live_action
    set_live(False)
    if _timer is not None:
        _timer.stop()
        _timer.deleteLater()
        _timer = None
    for event_type, callback in _connections:
        sp.event.DISPATCHER.disconnect(event_type, callback)
    _connections.clear()
    for action in _actions:
        sp.ui.delete_ui_element(action)
    _actions.clear()
    _live_action = None
