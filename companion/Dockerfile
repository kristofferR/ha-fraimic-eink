FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY fraimic_backend ./fraimic_backend
RUN uv sync --frozen --no-dev && mkdir /data && chown 10001:10001 /data
USER 10001:10001
EXPOSE 8443 8080
ENTRYPOINT ["/app/.venv/bin/fraimic-backend", "--config", "/data/config.json"]
