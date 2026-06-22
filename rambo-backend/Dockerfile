# ---------- BASE PYTHON IMAGE ----------
FROM python:3.11-slim AS base

# Prevent Python from buffering logs
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies (very lightweight)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ---------- INSTALL DEPENDENCIES ----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- COPY APPLICATION CODE ----------
COPY . .

# ---------- PRODUCTION STARTUP ----------
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------- HEALTHCHECK ----------
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/ || exit 1
