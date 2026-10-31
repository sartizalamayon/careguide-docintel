# One image for both the API and the Celery worker.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng libgl1 libglib2.0-0 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# requirements*.txt are exported from uv.lock (`make lock`); hashes pin every package.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --require-hashes -r requirements.txt && pip install --require-hashes -r requirements-dev.txt

# Bake the embedding model into the image (no download at runtime).
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/models')"

COPY . .

RUN useradd --create-home --uid 1000 app && mkdir -p /data/uploads && chown -R app:app /data /models /app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
