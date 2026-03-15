FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY janitor/ janitor/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/janitor /usr/local/bin/janitor
COPY config.example.yaml ./config.example.yaml

CMD ["janitor", "/app/config.yaml"]
