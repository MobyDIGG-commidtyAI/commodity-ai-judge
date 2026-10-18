# Daily Cloud Run Job. Runtime code uses only the Python standard library.
FROM python:3.12.15-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    DATA_MOUNT=/mnt/tank \
    MAX_ARTICLES=20
COPY src ./src
COPY data ./data
COPY scripts/cloud_job.sh ./scripts/cloud_job.sh
USER 65532:65532
CMD ["/app/scripts/cloud_job.sh"]
