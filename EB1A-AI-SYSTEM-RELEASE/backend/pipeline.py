from __future__ import annotations

import json
import shutil
import traceback
import zipfile
from pathlib import Path
from typing import Any, Callable

from .ocr import extract_file
from .utils import CaseStore, atomic_json_write, build_pdf, case_root, utc_now


CATEGORIES = {
    "A": ("Awards and Honors", ("award", "prize", "honor", "获奖", "奖项", "证书")),
    "B": ("Memberships", ("member", "membership", "association", "会员", "协会", "学会")),
    "C": ("Published Material", ("media", "news", "interview", "报道", "媒体", "专访")),
    "D": ("Judging Others", ("judge", "reviewer", "panel", "评委", "评审", "裁判")),
    "E": ("Original Contributions", ("patent", "innovation", "contribution", "专利", "创新", "贡献")),
    "F": ("High Salary / Commercial Success", ("salary", "revenue", "investment", "薪酬", "营收", "投资")),
}


def run_pipeline(case_id: str, data_dir: str | Path) -> None:
    store = CaseStore(data_dir)
    root = case_root(data_dir, case_id)
    case = store.get(case_id)
    if not case:
        return
    store.update(case_id, status="processing", stage="ocr", progress=5)
    store.add_log(case_id, "pipeline", "started", "Processing started or resumed.")

    extracted = _safe_stage(store, case_id, "ocr", 30, lambda: _run_ocr(case, root, store)) or []
    evidence = _safe_stage(store, case_id, "classify", 50, lambda: _classify(extracted, root)) or []
    petition = _safe_stage(store, case_id, "petition", 70, lambda: _petition(case, evidence, root)) or {}
    _safe_stage(store, case_id, "exhibits", 85, lambda: _exhibits(evidence, root))

    zip_path = None
    try:
        zip_path = _always_zip(case, root, petition, evidence)
        store.add_log(case_id, "zip", "complete", "FINAL_CASE.zip generated and CRC checked.")
    except Exception as exc:  # Last-resort ZIP recovery.
        store.add_log(case_id, "zip", "error", f"Primary ZIP export failed: {exc}")
        try:
            zip_path = _minimal_zip(root, str(exc))
        except Exception as final_exc:
            store.add_log(case_id, "zip", "error", f"Filesystem prevented ZIP creation: {final_exc}")

    errors = (store.get(case_id) or {}).get("errors", [])
    final_status = "completed_with_warnings" if errors else "completed"
    store.update(case_id, status=final_status, stage="complete", progress=100,
                 output_zip=str(zip_path.relative_to(Path(data_dir).resolve())) if zip_path else None,
                 completed_at=utc_now())


def _safe_stage(store: CaseStore, case_id: str, stage: str, progress: int, function: Callable[[], Any]) -> Any:
    try:
        value = function()
        store.update(case_id, stage=stage, progress=progress)
        store.add_log(case_id, stage, "complete", f"{stage.title()} stage completed.")
        return value
    except Exception as exc:
        store.add_log(case_id, stage, "error", f"{exc}\n{traceback.format_exc(limit=2)}")
        store.update(case_id, stage=stage, progress=progress)
        return None


def _run_ocr(case: dict[str, Any], root: Path, store: CaseStore) -> list[dict[str, Any]]:
    output_dir = root / "work" / "ocr"
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, record in enumerate(case.get("files", []), 1):
        checkpoint = output_dir / f"{index:04d}.json"
        if checkpoint.exists():
            try:
                cached = json.loads(checkpoint.read_text(encoding="utf-8"))
                if cached.get("source_sha256") == record.get("sha256"):
                    results.append(cached)
                    continue
            except (OSError, json.JSONDecodeError):
                pass
        source = root / record["path"]
        result = extract_file(source)
        result["document_id"] = f"DOC-{index:03d}"
        result["source_sha256"] = record.get("sha256")
        atomic_json_write(checkpoint, result)
        results.append(result)
        if result["status"] != "complete":
            store.add_log(case["id"], "ocr", "error", f"{record['name']}: OCR requires manual review.")
    atomic_json_write(root / "work" / "ocr_results.json", results)
    return results


def _classify(documents: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    evidence = []
    for document in documents:
        haystack = f"{document.get('file_name', '')} {document.get('extracted_text', '')}".lower()
        scored = {key: sum(1 for keyword in keywords if keyword in haystack)
                  for key, (_, keywords) in CATEGORIES.items()}
        exhibit = max(scored, key=scored.get) if max(scored.values(), default=0) else "E"
        category = CATEGORIES[exhibit][0]
        confidence = "Medium" if scored.get(exhibit, 0) else "Weak"
        evidence.append({
            "document_id": document.get("document_id"), "file_name": document.get("file_name"),
            "exhibit": exhibit, "category": category, "strength": confidence,
            "classification_reason": f"Keyword-based preliminary placement under {category}; attorney verification required.",
            "extracted_text": document.get("extracted_text", ""), "ocr_status": document.get("status"),
        })
    atomic_json_write(root / "work" / "evidence.json", evidence)
    return evidence


def _petition(case: dict[str, Any], evidence: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    counts = {key: sum(item["exhibit"] == key for item in evidence) for key in CATEGORIES}
    evidence_lines = [f"Exhibit {key} ({CATEGORIES[key][0]}): {count} document(s)." for key, count in counts.items()]
    petition_text = "\n".join([
        "DRAFT FOR ATTORNEY REVIEW — NOT FOR FILING",
        f"Re: Form I-140 EB-1A Petition — {case.get('name', case['id'])}",
        "This draft petition is submitted under INA section 203(b)(1)(A) and 8 C.F.R. section 204.5(h). It is generated from the supplied record and must be reviewed by qualified immigration counsel before use.",
        "The evidence inventory is organized as follows:", *evidence_lines,
        "The record should be evaluated first against the regulatory criteria and then in a final-merits determination. No unsupported fact, acclaim, or impact is asserted by this automated draft.",
        "For the foregoing reasons, and subject to attorney verification and supplementation of the record, the Petitioner respectfully requests favorable adjudication.",
    ])
    result = {"text": petition_text, "counts": counts, "generated_at": utc_now()}
    atomic_json_write(root / "work" / "petition.json", result)
    build_pdf(root / "outputs" / "Petition_Letter.pdf", "EB-1A Petition Letter — Attorney Review Draft", [
        ("Legal Draft", petition_text),
        ("Review Notice", "This internal preparation tool does not file with USCIS and does not provide legal advice."),
    ])
    build_pdf(root / "outputs" / "Case_Summary.pdf", "Case Evidence Summary", [
        ("Case", case.get("name", case["id"])),
        ("Evidence Inventory", "\n".join(evidence_lines)),
        ("Manual Review", "OCR and classification warnings must be resolved before attorney approval."),
    ])
    return result


def _exhibits(evidence: list[dict[str, Any]], root: Path) -> None:
    exhibit_dir = root / "outputs" / "Exhibits"
    for key, (label, _) in CATEGORIES.items():
        items = [item for item in evidence if item["exhibit"] == key]
        sections = []
        for item in items:
            text = (f"Document ID: {item['document_id']}\nFile: {item['file_name']}\n"
                    f"Strength: {item['strength']}\nReason: {item['classification_reason']}\n\n"
                    f"Extracted source text:\n{item['extracted_text'][:12000]}")
            sections.append((item["file_name"], text))
        if not sections:
            sections = [("No evidence assigned", "This exhibit is intentionally present but currently contains no assigned evidence.")]
        build_pdf(exhibit_dir / f"Exhibit_{key}.pdf", f"Exhibit {key} — {label}", sections)


def _always_zip(case: dict[str, Any], root: Path, petition: dict[str, Any], evidence: list[dict[str, Any]]) -> Path:
    output = root / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    expected = [output / "Petition_Letter.pdf", output / "Case_Summary.pdf"]
    expected.extend(output / "Exhibits" / f"Exhibit_{key}.pdf" for key in CATEGORIES)
    missing = []
    for path in expected:
        if not path.exists() or path.stat().st_size == 0:
            missing.append(path.relative_to(output).as_posix())
            build_pdf(path, path.stem.replace("_", " "), [("Unavailable", "This component could not be generated and requires manual review.")])
    manifest = {
        "case_id": case["id"], "case_name": case.get("name"), "generated_at": utc_now(),
        "missing_components_recovered": missing, "evidence_count": len(evidence),
        "notice": "Attorney-review draft only. This system does not submit filings to USCIS.",
    }
    atomic_json_write(output / "manifest.json", manifest)
    atomic_json_write(output / "OCR_Extracted_Text.json", json.loads((root / "work" / "ocr_results.json").read_text(encoding="utf-8"))
                      if (root / "work" / "ocr_results.json").exists() else [])

    zip_path = output / "FINAL_CASE.zip"
    temporary = output / "FINAL_CASE.tmp.zip"
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path not in {zip_path, temporary}:
                archive.write(path, f"FINAL_CASE/{path.relative_to(output).as_posix()}")
    with zipfile.ZipFile(temporary) as archive:
        broken = archive.testzip()
        if broken:
            raise RuntimeError(f"ZIP CRC validation failed for {broken}")
    temporary.replace(zip_path)
    return zip_path


def _minimal_zip(root: Path, error: str) -> Path:
    output = root / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    notice = output / "MANUAL_REVIEW_REQUIRED.txt"
    notice.write_text(f"The standard export encountered an error.\n{error}\n", encoding="utf-8")
    zip_path = output / "FINAL_CASE.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as archive:
        archive.write(notice, "FINAL_CASE/MANUAL_REVIEW_REQUIRED.txt")
    return zip_path
