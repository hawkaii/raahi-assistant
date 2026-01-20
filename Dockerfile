# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

# Copy dependency files first
COPY pyproject.toml ./

# Install dependencies only (not editable install)
RUN uv pip install --system --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    google-cloud-aiplatform>=1.38.0 \
    google-cloud-texttospeech>=2.14.0 \
    typesense>=0.21.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    redis>=5.0.0 \
    python-multipart>=0.0.6 \
    httpx>=0.26.0

# Copy application code
COPY . .

# Expose the application port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
