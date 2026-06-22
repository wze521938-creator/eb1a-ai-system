import os

from flask import Flask, jsonify, send_from_directory
from dotenv import load_dotenv

from backend.routes import api


load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__, static_folder="frontend", static_url_path="")
    max_mb = int(os.getenv("MAX_CONTENT_LENGTH_MB", "20"))
    app.config["MAX_CONTENT_LENGTH"] = max_mb * 1024 * 1024
    app.config["OUTPUT_DIR"] = os.path.join(app.root_path, "output")
    os.makedirs(app.config["OUTPUT_DIR"], exist_ok=True)
    app.register_blueprint(api, url_prefix="/api")

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", service="EB1A-AI-System")

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(error=f"Upload exceeds the {max_mb} MB limit."), 413

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
