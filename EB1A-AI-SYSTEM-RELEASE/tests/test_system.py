import io
import json
import time
import zipfile
from pathlib import Path

from backend.main import create_app
from backend.ocr import MOCK_TEXT, extract_file
from backend.utils import CaseStore


def test_health_and_complete_pipeline(tmp_path):
    app = create_app(tmp_path / "data")
    app.config["TESTING"] = True
    client = app.test_client()
    assert client.get("/api/health").get_json()["status"] == "ok"

    response = client.post("/upload_case", data={
        "case_name": "Internal Test",
        "files": (io.BytesIO("国家行业奖项证书".encode()), "award.txt"),
    }, content_type="multipart/form-data")
    assert response.status_code == 201
    case_id = response.get_json()["case"]["id"]
    assert client.post(f"/run_pipeline/{case_id}").status_code == 202

    deadline = time.time() + 15
    while time.time() < deadline:
        case = client.get(f"/case/{case_id}").get_json()["case"]
        if case["status"].startswith("completed"):
            break
        time.sleep(0.05)
    assert case["progress"] == 100
    exported = client.get(f"/case/{case_id}/export")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.data)) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert "FINAL_CASE/Petition_Letter.pdf" in names
        assert all(f"FINAL_CASE/Exhibits/Exhibit_{key}.pdf" in names for key in "ABCDEF")


def test_broken_image_uses_nonfatal_mock_ocr(tmp_path):
    image = tmp_path / "broken.png"
    image.write_bytes(b"not an image")
    result = extract_file(image)
    assert result["status"] == "manual_review"
    assert result["ocr_method"] == "mock_ocr"
    assert result["extracted_text"] == MOCK_TEXT


def test_json_store_recovers_corrupt_index(tmp_path):
    store = CaseStore(tmp_path)
    store.path.write_text("{broken", encoding="utf-8")
    case = {"id": "a" * 32, "name": "Recovered", "logs": [], "errors": []}
    store.create(case)
    assert store.get(case["id"])["name"] == "Recovered"
