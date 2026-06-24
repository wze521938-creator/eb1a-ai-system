from __future__ import annotations

import threading
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

from .pipeline import run_pipeline
from .utils import CaseStore, case_root, save_uploads, utc_now


api = Blueprint("api", __name__)
_running: set[str] = set()
_running_lock = threading.Lock()


def _store() -> CaseStore:
    return CaseStore(current_app.config["DATA_DIR"])


@api.post("/upload_case")
def upload_case():
    uploads = request.files.getlist("files") or request.files.getlist("file")
    if not uploads:
        return jsonify({"error": "Upload at least one ZIP, PDF, DOCX, image, or TXT file."}), 400
    case_id = uuid.uuid4().hex
    root = case_root(current_app.config["DATA_DIR"], case_id)
    records, warnings = save_uploads(uploads, root / "uploads")
    case = {
        "id": case_id, "name": (request.form.get("case_name") or f"Case {case_id[:8]}")[:120],
        "status": "uploaded", "stage": "upload", "progress": 0, "files": records,
        "output_zip": None, "created_at": utc_now(), "updated_at": utc_now(),
        "logs": [], "errors": [], "warnings": warnings,
    }
    _store().create(case)
    return jsonify({"case": _public_case(case)}), 201


@api.post("/run_pipeline/<case_id>")
def start_pipeline(case_id: str):
    store = _store()
    case = store.get(case_id)
    if not case:
        return jsonify({"error": "Case not found."}), 404
    with _running_lock:
        if case_id in _running:
            return jsonify({"case": _public_case(case), "message": "Pipeline is already running."}), 202
        _running.add(case_id)
    data_dir = current_app.config["DATA_DIR"]

    def worker() -> None:
        try:
            run_pipeline(case_id, data_dir)
        finally:
            with _running_lock:
                _running.discard(case_id)

    threading.Thread(target=worker, name=f"case-{case_id[:8]}", daemon=True).start()
    store.update(case_id, status="processing", stage="queued", progress=max(1, case.get("progress", 0)))
    return jsonify({"case": _public_case(store.get(case_id)), "message": "Pipeline started."}), 202


@api.get("/case/<case_id>")
def get_case(case_id: str):
    case = _store().get(case_id)
    if not case:
        return jsonify({"error": "Case not found."}), 404
    return jsonify({"case": _public_case(case)})


@api.get("/case/<case_id>/export")
def export_case(case_id: str):
    case = _store().get(case_id)
    if not case:
        return jsonify({"error": "Case not found."}), 404
    if not case.get("output_zip"):
        return jsonify({"error": "Export is not ready."}), 409
    path = (Path(current_app.config["DATA_DIR"]) / case["output_zip"]).resolve()
    allowed = Path(current_app.config["DATA_DIR"]).resolve()
    if allowed not in path.parents or not path.is_file():
        return jsonify({"error": "Export file is unavailable."}), 404
    return send_file(path, as_attachment=True, download_name="FINAL_CASE.zip", mimetype="application/zip")


def _public_case(case: dict | None) -> dict:
    if not case:
        return {}
    value = dict(case)
    value["download_url"] = f"/case/{case['id']}/export" if case.get("output_zip") else None
    return value
