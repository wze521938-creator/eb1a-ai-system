from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from werkzeug.datastructures import FileStorage


ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
MAX_ARCHIVE_FILES = 500
MAX_ARCHIVE_BYTES = 500 * 1024 * 1024
_store_lock = threading.RLock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str) -> str:
    name = Path(value or "document").name
    name = re.sub(r"[^\w.()\-\u4e00-\u9fff ]+", "_", name, flags=re.UNICODE).strip(" .")
    return name[:180] or "document"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


class CaseStore:
    """Single-process, atomic JSON case store. Docker runs one worker by design."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).resolve()
        self.path = self.data_dir / "cases.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            atomic_json_write(self.path, {"cases": {}})

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data.get("cases"), dict) else {"cases": {}}
        except (OSError, json.JSONDecodeError):
            backup = self.path.with_name(f"cases.corrupt-{int(datetime.now().timestamp())}.json")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            atomic_json_write(self.path, {"cases": {}})
            return {"cases": {}}

    def create(self, case: dict[str, Any]) -> dict[str, Any]:
        with _store_lock:
            data = self._read()
            data["cases"][case["id"]] = case
            atomic_json_write(self.path, data)
            return case

    def get(self, case_id: str) -> dict[str, Any] | None:
        with _store_lock:
            case = self._read()["cases"].get(case_id)
            return json.loads(json.dumps(case)) if case else None

    def update(self, case_id: str, **changes: Any) -> dict[str, Any]:
        with _store_lock:
            data = self._read()
            if case_id not in data["cases"]:
                raise KeyError(case_id)
            data["cases"][case_id].update(changes)
            data["cases"][case_id]["updated_at"] = utc_now()
            atomic_json_write(self.path, data)
            return json.loads(json.dumps(data["cases"][case_id]))

    def add_log(self, case_id: str, stage: str, status: str, message: str) -> None:
        with _store_lock:
            data = self._read()
            case = data["cases"].get(case_id)
            if not case:
                return
            entry = {"timestamp": utc_now(), "stage": stage, "status": status, "message": str(message)[:2000]}
            case.setdefault("logs", []).append(entry)
            case["logs"] = case["logs"][-500:]
            if status == "error":
                case.setdefault("errors", []).append(entry)
            case["updated_at"] = utc_now()
            atomic_json_write(self.path, data)


def case_root(data_dir: str | Path, case_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", case_id):
        raise ValueError("Invalid case identifier")
    root = (Path(data_dir).resolve() / "cases" / case_id).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_uploads(files: Iterable[FileStorage], destination: Path) -> tuple[list[dict[str, Any]], list[str]]:
    destination.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, uploaded in enumerate(files, 1):
        if not uploaded or not uploaded.filename:
            continue
        name = safe_name(uploaded.filename)
        target = destination / f"{index:03d}_{name}"
        uploaded.save(target)
        if target.suffix.lower() == ".zip":
            extracted, archive_warnings = extract_safe_zip(target, destination / f"archive_{index:03d}")
            warnings.extend(archive_warnings)
            records.extend(_file_record(path, destination) for path in extracted)
            continue
        if target.suffix.lower() not in ALLOWED_EXTENSIONS:
            warnings.append(f"Unsupported file skipped: {name}")
            target.unlink(missing_ok=True)
            continue
        records.append(_file_record(target, destination))
    return records, warnings


def _file_record(path: Path, base: Path) -> dict[str, Any]:
    return {
        "name": path.name,
        "path": path.relative_to(base.parent).as_posix(),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def extract_safe_zip(source: Path, destination: Path) -> tuple[list[Path], list[str]]:
    extracted: list[Path] = []
    warnings: list[str] = []
    total = 0
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(source) as archive:
            for index, member in enumerate(archive.infolist()):
                if index >= MAX_ARCHIVE_FILES:
                    warnings.append("Archive file-count limit reached; remaining entries skipped.")
                    break
                if member.is_dir() or member.flag_bits & 0x1:
                    continue
                total += member.file_size
                suffix = Path(member.filename).suffix.lower()
                if total > MAX_ARCHIVE_BYTES:
                    warnings.append("Archive uncompressed-size limit reached; remaining entries skipped.")
                    break
                if suffix not in ALLOWED_EXTENSIONS:
                    warnings.append(f"Unsupported archive member skipped: {safe_name(member.filename)}")
                    continue
                target = destination / f"{index + 1:04d}_{safe_name(member.filename)}"
                try:
                    with archive.open(member) as reader, target.open("wb") as writer:
                        while chunk := reader.read(1024 * 1024):
                            writer.write(chunk)
                    extracted.append(target)
                except Exception as exc:
                    target.unlink(missing_ok=True)
                    warnings.append(f"Broken archive member skipped: {safe_name(member.filename)} ({exc})")
    except (OSError, zipfile.BadZipFile) as exc:
        warnings.append(f"Archive could not be read: {exc}")
    return extracted, warnings


def build_pdf(path: Path, title: str, sections: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        body_font = "STSong-Light"
    except Exception:
        body_font = "Helvetica"
    styles = getSampleStyleSheet()
    body = ParagraphStyle("LegalBody", parent=styles["BodyText"], fontName=body_font, fontSize=9.5, leading=14)
    heading = ParagraphStyle("LegalHeading", parent=styles["Heading2"], fontName=body_font, fontSize=12, leading=16)
    story = [Paragraph(_escape(title), styles["Title"]), Spacer(1, 8 * mm)]
    for index, (label, text) in enumerate(sections):
        if index:
            story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(_escape(label), heading))
        for paragraph in str(text or "[Not available]").splitlines():
            if paragraph.strip():
                story.append(Paragraph(_escape(paragraph), body))
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm, title=title)
    doc.build(story)


def _escape(value: str) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br/>"))
