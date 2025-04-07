FROM ghcr.io/astral-sh/uv:latest as uv
FROM python:3.13-slim-bookworm as builder

ENV UV_COMPILE_BYTECODE=1
ENV UV_NO_INSTALLER_METADATA=1
ENV UV_LINK_MODE=copy

WORKDIR /build
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=/build/pyproject.toml \
    --mount=type=bind,source=uv.lock,target=/build/uv.lock \
    uv export --frozen --no-emit-workspace --no-dev -o requirements.txt && \
    uv pip install -r requirements.txt --target /packages

FROM python:3.13-slim-bookworm

WORKDIR /app

COPY --from=builder /packages /packages

COPY app /app

ENV PYTHONPATH=/packages
ENV PATH="/packages/bin:$PATH"
ENV API_HOST=0.0.0.0
ENV API_PORT=8000

EXPOSE 8000

# Command to run the application
CMD ["python", "-m", "uvicorn", "app.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
