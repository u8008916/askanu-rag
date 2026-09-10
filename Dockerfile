FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/runtime \
    PORT=8081

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir --disable-pip-version-check \
        --target /app/runtime . \
    && python -m pip check \
    && find /app/runtime -type d -name __pycache__ -prune -exec rm -rf '{}' +

# Preserve the existing deterministic fallback used when no external handoff
# path is configured. Day 7 will replace this runtime path with Cloud SQL.
COPY fixtures/day2_course_program_records.json ./fixtures/day2_course_program_records.json

# Cloud Run invokes the container as a non-root user and supplies PORT.
USER 65532:65532

EXPOSE 8081

CMD ["python", "-m", "askanu_rag.server"]
