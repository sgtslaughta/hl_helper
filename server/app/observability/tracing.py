"""OpenTelemetry tracing configuration for the fleet server.

Configures TracerProvider with parent-based sampling, optional OTLP export,
and auto-instrumentation for FastAPI, SQLAlchemy, httpx, and gRPC.
"""

from __future__ import annotations

import logging
from typing import Any

import opentelemetry.trace as trace_api
from opentelemetry.trace import Tracer
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.grpc import (
    GrpcInstrumentorClient,
    GrpcInstrumentorServer,
)
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
from opentelemetry.semconv.resource import ResourceAttributes

_LOGGER = logging.getLogger(__name__)

_configured_provider: TracerProvider | None = None


def configure_tracing(
    *,
    service_name: str = "hl_helper",
    sample_rate: float = 0.01,
    otel_endpoint: str | None = None,
    otel_headers: dict[str, str] | None = None,
) -> None:
    """@brief Configure OpenTelemetry TracerProvider with sampling and optional OTLP export.

    @param service_name Service name emitted as ``service.name``.
    @param sample_rate Sampling rate (0.0 to 1.0). Matches ``FleetSettings.trace_sample_rate``.
    @param otel_endpoint OTLP gRPC collector endpoint. Matches ``FleetSettings.otel_endpoint``.
    @param otel_headers Optional headers for OTLP (for example bearer auth).
    """
    global _configured_provider

    if _configured_provider is not None:
        _configured_provider.shutdown()
        _configured_provider = None

    resource = Resource.create({ResourceAttributes.SERVICE_NAME: service_name})
    sampler = ParentBasedTraceIdRatio(rate=sample_rate)
    provider = TracerProvider(resource=resource, sampler=sampler)

    if otel_endpoint:
        exporter = OTLPSpanExporter(endpoint=otel_endpoint, headers=otel_headers)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace_api.set_tracer_provider(provider)
    _configured_provider = provider
    _LOGGER.debug(
        "Tracing configured (service=%s sample_rate=%s otlp=%s)",
        service_name,
        sample_rate,
        bool(otel_endpoint),
    )


def instrument_fastapi(app: Any) -> None:
    """@brief Instrument a FastAPI application with OpenTelemetry.

    @param app ASGI FastAPI application instance.
    """
    FastAPIInstrumentor.instrument_app(app)


def instrument_sqlalchemy(engine: Any) -> None:
    """@brief Instrument a SQLAlchemy engine with OpenTelemetry.

    @param engine Bound SQLAlchemy engine.
    """
    SQLAlchemyInstrumentor().instrument(engine=engine)


def instrument_httpx() -> None:
    """@brief Instrument httpx clients with OpenTelemetry."""
    HTTPXClientInstrumentor().instrument()


def instrument_grpc() -> None:
    """@brief Instrument gRPC client and server stubs with OpenTelemetry."""
    GrpcInstrumentorClient().instrument()  # type: ignore[no-untyped-call]
    GrpcInstrumentorServer().instrument()  # type: ignore[no-untyped-call]


def get_tracer(name: str) -> Tracer:
    """@brief Get a named tracer from the global TracerProvider.

    @param name Instrumentation scope name for the tracer.
    @return An :class:`~opentelemetry.trace.Tracer` from the active provider.
    """
    return trace_api.get_tracer(name)


def shutdown_tracing() -> None:
    """@brief Shut down the TracerProvider and flush spans.

    Safe to call multiple times; only the last configured provider is tracked.
    """
    global _configured_provider

    if _configured_provider is not None:
        _configured_provider.shutdown()
        _configured_provider = None
