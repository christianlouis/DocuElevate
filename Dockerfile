# Use multi-stage build for a smaller final image
FROM python:3.14.1 AS builder

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Second stage for the actual runtime
FROM python:3.14.3-slim

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

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
COPY ./LICENSE /app/LICENSE

# Copy build metadata files (generated at build time)
COPY ./VERSION /app/VERSION
COPY ./BUILD_DATE /app/BUILD_DATE
COPY ./GIT_SHA /app/GIT_SHA
COPY ./RUNTIME_INFO /app/RUNTIME_INFO

# Create runtime_info directory
RUN mkdir -p /app/runtime_info

# Create necessary directories
RUN mkdir -p /workdir

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose the port the app runs on
EXPOSE 8000

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
