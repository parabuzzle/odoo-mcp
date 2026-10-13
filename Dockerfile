# Pin the tested base; update this digest deliberately for Python/OS updates.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY odoo_mcp ./odoo_mcp
RUN --mount=type=cache,target=/root/.cache/pip python -m pip wheel --wheel-dir /wheels '.[http]'

FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    MCP_STATE_DIR=/data/oauth FASTMCP_HOME=/data/fastmcp HOME=/data
RUN groupadd --gid 10001 mcp && useradd --uid 10001 --gid mcp --no-create-home mcp \
    && mkdir -p /data/oauth /data/fastmcp && chown -R 10001:10001 /data
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels 'odoo-mcp[http]' \
    && rm -rf /wheels
USER 10001:10001
WORKDIR /app
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).close()"]
CMD ["odoo-mcp-http"]
