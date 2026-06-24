FROM node:20-alpine AS frontend-build
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=10000
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY --from=frontend-build /ui/dist ./frontend/dist
RUN mkdir -p /data && chown -R 10001:10001 /app /data
USER 10001
EXPOSE 10000
CMD ["sh", "-c", "gunicorn --workers 1 --threads 4 --timeout 0 --bind 0.0.0.0:${PORT} backend.main:app"]
