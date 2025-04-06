# Stage 1: Python dependencies
FROM python:3.13 AS builder

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Ghostscript Builder
FROM debian:bullseye-slim AS gs-builder

RUN apt-get update && apt-get install -y \
    build-essential \
    libjpeg-dev libpng-dev libtiff-dev zlib1g-dev \
    curl && \
    rm -rf /var/lib/apt/lists/*

# Build Ghostscript 9.56.1
WORKDIR /tmp
RUN curl -L -O https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs9561/ghostscript-9.56.1.tar.gz && \
    tar -xzf ghostscript-9.56.1.tar.gz && \
    cd ghostscript-9.56.1 && \
    ./configure --prefix=/ghostscript && \
    make -j$(nproc) && make install

# Stage 3: Final slim image
FROM python:3.13.2-slim AS final


# Copy Ghostscript binary from builder
COPY --from=gs-builder /ghostscript /usr/local

# Copy installed Python dependencies
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app
WORKDIR /app
COPY ./app /app/app
COPY ./frontend /app/frontend
COPY ./VERSION /app/VERSION
COPY ./LICENSE /app/LICENSE

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Expose API
EXPOSE 8000

# Start the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
