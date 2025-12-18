# path: Dockerfile
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3 \
    PYTHONPATH=/app/src \
    HF_HOME=/app/weights/hf-cache \
    TRANSFORMERS_CACHE=/app/weights/hf-cache \
    SENTENCE_TRANSFORMERS_HOME=/app/weights/hf-cache \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# Системные зависимости для сборки некоторых Python-пакетов (если нужно)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git ca-certificates locales \
 && rm -rf /var/lib/apt/lists/*

# Poetry
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}" && poetry --version

WORKDIR /app

# Сначала зависимости (чтобы лучше работал Docker cache)
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
 && poetry install --only main --no-interaction --no-ansi

# PyTorch (как у тебя было, CUDA 12.1)
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu121 \
    torch torchvision torchaudio

# Копируем только исходники проекта.
# Шаблоны у тебя в src/templates/, поэтому отдельный COPY templates НЕ нужен.
COPY src ./src

EXPOSE 8000

# ВАЖНО: точка входа у тебя src.main:main_app, а не src.core.main:app
CMD ["poetry", "run", "uvicorn", "src.main:main_app", "--host", "0.0.0.0", "--port", "8000"]
