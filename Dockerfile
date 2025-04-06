# Use multi-stage build for a smaller final image
FROM python:3.13 AS builder

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Second stage for the actual runtime
FROM python:3.13.2-slim

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY ./app /app/app
COPY ./VERSION /app/VERSION
COPY ./frontend /app/frontend

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
