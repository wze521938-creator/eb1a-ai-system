# EB1A-AI-SYSTEM-RELEASE

A single, consolidated internal EB-1A case-preparation workflow. There is one Flask entry point, one JSON case store, one processing pipeline, and one React dashboard. It contains no SaaS accounts, billing, database, V3/V4 branches, or duplicate processors.

> Internal attorney-review preparation only. The system does not file petitions with USCIS and does not replace qualified legal review.

## Repository

```text
EB1A-AI-SYSTEM-RELEASE/
├── backend/
│   ├── main.py       # only application entry: backend.main:app
│   ├── api.py        # HTTP endpoints
│   ├── pipeline.py   # one upload-to-ZIP workflow
│   ├── ocr.py        # direct extraction + safe OCR fallback
│   └── utils.py      # JSON store, upload safety, PDF helpers
├── frontend/         # React + Vite + Tailwind dashboard
├── data/
│   └── cases.json    # created automatically; no database
├── tests/
├── Dockerfile
├── render.yaml
└── requirements.txt
```

## Pipeline

```text
upload → OCR/extraction → A–F classification → petition → exhibits → FINAL_CASE.zip
```

- TXT, text/scanned PDF, DOCX, JPG, PNG, TIFF, WebP, multi-file upload, and ZIP batch input.
- PDF pages with selectable text bypass OCR. Scanned pages render at 300 DPI.
- Tesseract attempts Chinese + English, then English, across enhanced image variants.
- A failed page becomes a manual-review `mock_ocr` result; later pages and files continue.
- Each completed extraction has a SHA-256 checkpoint and is reused on rerun.
- Every stage records status in `data/cases.json`; an error is logged and processing continues.
- All six exhibit PDFs are created even when a category is empty.
- ZIP export fills missing PDF components with review placeholders and CRC-checks the archive.

Classification and petition text are deliberately conservative preliminary drafts. Keyword placement and generated legal prose require attorney verification; the system never treats its own output as a legal conclusion.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/upload_case` | Multipart upload using `files`; optional `case_name` |
| `POST` | `/run_pipeline/{case_id}` | Start or resume the single pipeline |
| `GET` | `/case/{case_id}` | View stage, progress, logs, warnings, and export readiness |
| `GET` | `/case/{case_id}/export` | Download `FINAL_CASE.zip` |
| `GET` | `/api/health` | Deployment health check |

## Local development

Backend (Python 3.12+, Tesseract with `chi_sim` and `eng` recommended):

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m backend.main
```

Frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

The Vite server proxies the API to `http://localhost:5000`.

Run tests:

```bash
pytest -q
```

## Docker

```bash
docker build -t eb1a-ai-system-release .
docker run --rm -p 10000:10000 -v eb1a-data:/data eb1a-ai-system-release
```

Open `http://localhost:10000`. The Docker image builds the React app and serves it through Flask. Gunicorn intentionally uses one worker because `cases.json` is an atomic, process-local locked store; four threads allow uploads, polling, and background case processing to coexist.

## Render

Create a Blueprint from `render.yaml`. The configuration uses:

- Docker runtime
- `backend.main:app` through the image command
- persistent disk mounted at `/data`
- health check at `/api/health`
- a single Gunicorn worker to preserve JSON write serialization

For production continuity, do not remove the persistent disk or run multiple container instances against the same JSON file.
