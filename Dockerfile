# Single container image used for both the Cloud Run web service,
# the private Cloud Run background worker, and Cloud Run migration jobs.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Install runtime dependencies for Pillow and PostgreSQL client
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY . /app

# Create non-root user for Cloud Run runtime
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/staticfiles /app/local_media /app/local_evidence \
    && chown -R appuser:appuser /app

USER appuser

# Collect static assets at image build time (safe dummy secret for build step)
RUN DJANGO_SECRET_KEY=build-only-placeholder \
    DJANGO_DEBUG=False \
    python manage.py collectstatic --noinput

EXPOSE 8080

# Default command runs the web server; worker Cloud Run service can pass
# the same image with WORKER_MODE=True and restricted IAM invoker access.
CMD ["sh", "-c", "gunicorn siteapp.wsgi:application --bind 0.0.0.0:${PORT:-8080} --workers ${GUNICORN_WORKERS:-2} --threads ${GUNICORN_THREADS:-4} --timeout 60 --access-logfile -"]
