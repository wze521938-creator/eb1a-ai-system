import json
import os
import uuid
import zipfile
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file
from openai import OpenAIError

from .ai_service import CATEGORY_GUIDE, generate_case
from .document_parser import DocumentError, extract_text


api = Blueprint("api", __name__)


@api.post("/generate")
def generate():
    files = request.files.getlist("documents")
    if not files or all(not item.filename for item in files):
        return jsonify(error="Upload at least one document."), 400
    if len(files) > 10:
        return jsonify(error="Upload no more than 10 documents per case."), 400

    documents = []
    try:
        for index, item in enumerate(files, start=1):
            original_name = Path(item.filename or "document").name.replace("\n", " ").replace("\r", " ")[:200]
            suffix = Path(original_name).suffix.lower()
            parser_name = f"document_{index}{suffix}"
            documents.append({"filename": original_name, "text": extract_text(parser_name, item.read())})
        result = generate_case(documents)
        job_id = str(uuid.uuid4())
        zip_path = _write_package(job_id, result)
    except DocumentError as exc:
        return jsonify(error=str(exc)), 400
    except (OpenAIError, RuntimeError, json.JSONDecodeError) as exc:
        current_app.logger.exception("Case generation failed")
        return jsonify(error=f"Case generation failed: {exc}"), 502

    return jsonify(
        job_id=job_id,
        evidence_count=len(result["evidence"]),
        warnings=result["warnings"],
        download_url=f"/api/download/{job_id}",
    )


@api.get("/download/<job_id>")
def download(job_id: str):
    try:
        canonical_id = str(uuid.UUID(job_id))
    except ValueError:
        return jsonify(error="Invalid package identifier."), 400

    path = Path(current_app.config["OUTPUT_DIR"]) / canonical_id / "EB1A_case_package.zip"
    if not path.is_file():
        return jsonify(error="Package not found or no longer available."), 404
    return send_file(path, as_attachment=True, download_name="EB1A_case_package.zip")


def _write_package(job_id: str, result: dict) -> Path:
    job_dir = Path(current_app.config["OUTPUT_DIR"]) / job_id
    job_dir.mkdir(parents=True, exist_ok=False)

    evidence_json = json.dumps(result["evidence"], ensure_ascii=False, indent=2)
    evidence_md = _evidence_markdown(result["evidence"])
    files = {
        "01_legal_translation.md": result["legal_translation"],
        "02_evidence_classification.md": evidence_md,
        "02_evidence_classification.json": evidence_json,
        "03_petition_letter.md": result["petition_letter"],
        "04_case_summary.md": result["case_summary"],
        "05_review_warnings.md": "# Attorney Review Warnings\n\n" + "\n".join(f"- {w}" for w in result["warnings"]),
    }
    for filename, content in files.items():
        (job_dir / filename).write_text(content.strip() + "\n", encoding="utf-8")

    zip_path = job_dir / "EB1A_case_package.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename in files:
            archive.write(job_dir / filename, arcname=filename)
    return zip_path


def _evidence_markdown(items: list[dict]) -> str:
    sections = ["# EB-1A Evidence Classification", "", CATEGORY_GUIDE.strip(), ""]
    for item in items:
        sections.extend(
            [
                f"## {item['category']} — {item['title']}",
                f"**Source:** {item['source_file']}  ",
                f"**Strength:** {item['strength']}",
                "",
                item["facts"],
                "",
                f"**Relevance:** {item['relevance']}",
                "",
                "**Verification needed:**",
                *[f"- {point}" for point in item["verification_needed"]],
                "",
            ]
        )
    return "\n".join(sections)
