# Pin the tested base; update this digest deliberately for Python/OS updates.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS base
# Security update not yet incorporated into the pinned upstream image.
RUN apt-get update && apt-get install --only-upgrade --no-install-recommends -y liblzma5=5.8.1-1+deb13u2 ca-certificates=20250419+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements-build.lock requirements-http.lock ./
RUN --mount=type=cache,target=/root/.cache/pip python -m pip install --require-hashes -r requirements-build.lock
RUN --mount=type=cache,target=/root/.cache/pip python -m pip wheel --no-build-isolation --no-deps \
    --require-hashes -r requirements-http.lock --wheel-dir /wheels
COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.txt ./
COPY odoo_mcp ./odoo_mcp
RUN python -m pip wheel --no-build-isolation --no-deps --wheel-dir /wheels .
RUN python -m pip install --prefix=/install --ignore-installed --no-index --no-deps /wheels/*.whl

FROM base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    MCP_STATE_DIR=/data/oauth FASTMCP_HOME=/data/fastmcp HOME=/data
RUN groupadd --gid 10001 mcp && useradd --uid 10001 --gid mcp --no-create-home mcp \
    && mkdir -p /data/oauth /data/fastmcp && chown -R 10001:10001 /data
# No build tools or package installer are retained in the runtime image.
RUN python -m pip uninstall -y pip
COPY --from=builder /install /usr/local
COPY scripts/image_inventory.py /tmp/image_inventory.py
COPY LICENSE THIRD_PARTY_NOTICES.txt requirements-http.lock /usr/share/odoo-mcp/
RUN python /tmp/image_inventory.py > /usr/share/odoo-mcp/python-packages.json \
    && dpkg-query -W > /usr/share/odoo-mcp/os-packages.txt \
    && rm /tmp/image_inventory.py
USER 10001:10001
WORKDIR /app
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).close()"]
CMD ["odoo-mcp-http"]
