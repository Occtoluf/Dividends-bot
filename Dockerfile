FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY pyproject.toml ./
RUN pip install --prefix=/install \
      "aiogram>=3.4,<4" \
      "tinkoff-investments>=0.2.0b114" \
      "pydantic>=2.6" \
      "pydantic-settings>=2.2" \
      "rapidfuzz>=3.6" \
      "aiosqlite>=0.20"


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --from=builder /install /usr/local
COPY src ./src
COPY run.py ./

RUN useradd --system --uid 1000 app \
    && mkdir -p /app/data \
    && chown -R app:app /app
USER app

VOLUME ["/app/data"]
CMD ["python", "run.py"]
