from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from .api import api
from .utils import CaseStore


ROOT = Path(__file__).resolve().parents[1]


def create_app(data_dir: str | Path | None = None) -> Flask:
    frontend = ROOT / "frontend" / "dist"
    app = Flask(__name__, static_folder=str(frontend), static_url_path="")
    app.config.update(
        DATA_DIR=str(Path(data_dir or os.getenv("DATA_DIR", ROOT / "data")).resolve()),
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_UPLOAD_MB", "500")) * 1024 * 1024,
        JSON_SORT_KEYS=False,
    )
    CaseStore(app.config["DATA_DIR"])
    app.register_blueprint(api)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "EB1A-AI-SYSTEM-RELEASE"})

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify({"error": "Upload exceeds MAX_UPLOAD_MB."}), 413

    @app.errorhandler(Exception)
    def unexpected(error):
        app.logger.exception("Unhandled request error")
        return jsonify({"error": "The request could not be completed.", "detail": str(error)}), 500

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def frontend_app(path: str):
        candidate = frontend / path
        if path and candidate.is_file():
            return send_from_directory(frontend, path)
        if (frontend / "index.html").is_file():
            return send_from_directory(frontend, "index.html")
        return jsonify({"service": "EB1A-AI-SYSTEM-RELEASE", "frontend": "Run the Vite dev server or build frontend/"})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
