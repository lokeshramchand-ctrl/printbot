# syntax=docker/dockerfile:1

# ---- runtime image (default target) ----
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

# LibreOffice (DOC/DOCX -> PDF), CUPS client, build tools for native wheels, curl for the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    libreoffice-writer \
    cups-client \
    libcups2-dev \
    gcc \
    g++ \
    make \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
    CMD curl -fsS http://localhost:8000/health | grep -q '"status":"ok"' || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- test image: same code + dev dependencies (tests are mounted by compose) ----
FROM runtime AS test
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
CMD ["python", "-m", "pytest", "tests", "-v", "-p", "no:cacheprovider"]
