# Commodity AI news judge: a daily Cloud Run Job (standard library only, no pip install).
# Mount the shared bucket at DATA_MOUNT; OPENROUTER_API_KEY comes from Secret Manager.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src DATA_MOUNT=/mnt/tank MAX_ARTICLES=20
COPY src ./src
COPY data ./data
COPY scripts/cloud_job.sh ./scripts/cloud_job.sh
CMD ["/app/scripts/cloud_job.sh"]
