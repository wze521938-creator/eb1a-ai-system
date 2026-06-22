# EB1A AI System

Flask MVP that converts Chinese source documents into an attorney-review EB-1A drafting package.

## Features

- Upload up to 10 TXT, PDF, DOC, or DOCX files
- Translate for U.S. immigration-law meaning rather than literally
- Classify evidence into six A–F workflow groups covering the EB-1A regulatory criteria
- Generate a petition-letter draft and case-summary report
- Export Markdown and JSON outputs in a ZIP archive
- Docker and Render Blueprint deployment support

## Project structure

```text
EB1A-AI-System/
├── frontend/              # Static HTML, CSS, and JavaScript
├── backend/               # Flask routes, parsing, and AI generation
├── output/                # Generated job packages (runtime only)
├── app.py                 # Flask entry point
├── Dockerfile
├── render.yaml
└── requirements.txt
```

## Local setup

Python 3.11+ and `antiword` are required for legacy `.doc` files.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
python app.py
```

Set a valid `OPENAI_API_KEY` in `.env`, then open `http://localhost:5000`.

## Render deployment

1. Push this directory to a Git repository.
2. In Render, create a new Blueprint and select the repository.
3. Set the prompted `OPENAI_API_KEY` secret.
4. Deploy. `render.yaml` uses the Dockerfile so legacy DOC parsing is available.

Render's filesystem is ephemeral. Generated packages remain downloadable during the current instance lifetime; production deployments should move them to object storage and add scheduled cleanup.

## Security and legal limitations

- The system does not provide legal advice or determine eligibility.
- Every factual claim and legal argument must be verified by a qualified U.S. immigration attorney.
- Uploaded documents are sent to the configured AI provider for processing.
- The MVP has no authentication; do not expose it publicly with sensitive client files without adding access control, retention controls, and a privacy review.
- Scanned/image-only PDFs require OCR before upload.
