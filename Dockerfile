FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system vtd && adduser --system --ingroup vtd --home /home/vtd vtd \
    && mkdir -p /data/vtd && chown -R vtd:vtd /data/vtd /home/vtd
COPY rc6_runtime_min.zip /tmp/rc6_runtime_min.zip
RUN python -m zipfile -e /tmp/rc6_runtime_min.zip /app \
    && pip install --no-cache-dir -r /app/requirements.txt \
    && rm -f /tmp/rc6_runtime_min.zip \
    && chown -R vtd:vtd /app
ENV MCP_HOST=0.0.0.0 MCP_TRANSPORT=streamable-http VTD_ENV=production VTD_DATA_DIR=/data/vtd \
    VTD_RUN_LOCK_TIMEOUT=30 VTD_RUNSTORE_LEGACY_MIRROR=1 VTD_LOG_LEVEL=INFO
EXPOSE 10000
USER vtd
CMD ["sh", "-c", "uvicorn render_entrypoint:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers"]
