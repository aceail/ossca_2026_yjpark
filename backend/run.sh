#!/bin/bash
export TOMORROW_YOU_TRACING_ENABLED="${TOMORROW_YOU_TRACING_ENABLED:-true}"
export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://localhost:6006/v1/traces}"
export OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-tomorrow-you-backend}"
export TOMORROW_YOU_ENV="${TOMORROW_YOU_ENV:-dev}"
cd "$(dirname "$0")/.."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload
