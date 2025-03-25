
# Stage 1: Build dependencies
FROM python:3.11 AS builder

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final image
FROM python:3.11-slim

WORKDIR /app

# Copy installed dependencies
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application files correctly
COPY ./app /app/app
COPY ./frontend /app/frontend

# Set Python path explicitly
ENV PYTHONPATH=/app

# Expose API port
EXPOSE 8000
WORKDIR /app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
