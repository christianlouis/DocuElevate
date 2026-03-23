# syntax=docker/dockerfile:1

# ── Stage 1: Python dependency builder ──────────────────────────────────────
# Use the same slim variant as the runtime to keep Python versions in sync.
# build-essential + libffi-dev cover the few packages (e.g. cryptography) that
# need a C compiler; they are discarded after this stage.
FROM python:3.14.3-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create an isolated virtual environment so only installed packages are copied
# to the runtime image (no pip, setuptools, or other builder artefacts).
RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt /build/
RUN pip install --no-cache-dir -r requirements.txt \
    # Remove bytecode and cache to keep the venv lean
    && find /opt/venv -type f -name "*.pyc" -delete \
    && find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# ── Stage 2: Frontend asset builder (Tailwind CSS) ──────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# Install dependencies first (layer-cached unless package.json/lockfile changes)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy source files and compile Tailwind CSS
COPY frontend/ ./
RUN npm run build

# ── Stage 3: Documentation builder ──────────────────────────────────────────
FROM python:3.14.3-slim AS docs-builder

WORKDIR /docs

# Install MkDocs Material and its dependencies
COPY docs/requirements.txt /docs/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy documentation sources
COPY docs /docs/docs
COPY mkdocs.yml /docs/mkdocs.yml

# Build the static documentation site
RUN mkdocs build --config-file /docs/mkdocs.yml --site-dir /docs/docs_build

# ── Stage 4: Runtime image ───────────────────────────────────────────────────
FROM python:3.14.3-slim

WORKDIR /app

# Copy only the pre-built virtual environment from the builder
COPY --from=builder /opt/venv /opt/venv

# Install system-level OCR tools required for local OCR workflows:
#   tesseract-ocr   – OCR engine used by pytesseract and ocrmypdf
#   ghostscript     – required by ocrmypdf for PDF/PS operations
#   poppler-utils   – provides pdfinfo/pdftoppm used by pdf2image
#   unpaper         – optional deskewing pre-processor used by ocrmypdf
#   wget            – used by ocr_language_manager to download tessdata files
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        ghostscript \
        poppler-utils \
        unpaper \
        wget \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY ./app /app/app
COPY ./frontend /app/frontend
# Overlay compiled Tailwind CSS from the frontend build stage
COPY --from=frontend-builder /frontend/static/styles.css /app/frontend/static/styles.css
COPY ./migrations /app/migrations
COPY ./alembic.ini /app/alembic.ini
COPY ./LICENSE /app/LICENSE

# Copy build metadata files (generated at build time)
COPY ./VERSION /app/VERSION
COPY ./BUILD_DATE /app/BUILD_DATE
COPY ./GIT_SHA /app/GIT_SHA
COPY ./RUNTIME_INFO /app/RUNTIME_INFO

# Copy the pre-built MkDocs documentation site (served at /help)
COPY --from=docs-builder /docs/docs_build /app/docs_build

# Create necessary runtime directories in a single layer
RUN mkdir -p /app/runtime_info /workdir

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose the port the app runs on
EXPOSE 8000

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
