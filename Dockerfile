FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8001
CMD ["uvicorn", "securepay_apis.restricted_list.main:app", "--host", "0.0.0.0", "--port", "8001"]
