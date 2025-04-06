# Stage 1: Build dependencies
FROM python:3.13 AS builder

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final image
FROM python:3.13.2-slim

WORKDIR /app

# Copy installed dependencies
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application files correctly
COPY ./app /app/app
COPY ./frontend /app/frontend
COPY ./VERSION /app/VERSION
COPY ./LICENSE /app/LICENSE

# Copy build script and generate build date
COPY ./docker/build-scripts/save-build-date.sh /tmp/
RUN mkdir -p /app/docker/build-scripts/ && \
    cp /tmp/save-build-date.sh /app/docker/build-scripts/ && \
    chmod +x /tmp/save-build-date.sh && \
    /tmp/save-build-date.sh

# Set build date as environment variable
#ENV BUILD_DATE=$(cat /app/BUILD_DATE)

# Set Python path explicitly
ENV PYTHONPATH=/app

# Expose API port
EXPOSE 8000
WORKDIR /app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
