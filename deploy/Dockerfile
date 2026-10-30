FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY switchback ./switchback
COPY docs ./docs
COPY tests/fixtures ./tests/fixtures

RUN pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1
ENV SWITCHBACK_TRACE=/app/switchback-run/trace.jsonl
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318

EXPOSE 8780

CMD ["python", "-m", "switchback.cli", "serve", "--host", "0.0.0.0", "--port", "8780"]
