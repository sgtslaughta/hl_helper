"""Unit tests for OpenTelemetry tracing configuration (:mod:`server.app.observability.tracing`)."""

from __future__ import annotations

from typing import Any, Iterator

import opentelemetry.trace as trace_api
import pytest
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import Tracer as SDKTracer
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.util._once import Once
from sqlalchemy import create_engine

from server.app.observability import tracing


def _reset_global_tracer_provider_lock() -> None:
    """Clear the API global so :func:`trace_api.set_tracer_provider` works again.

    OpenTelemetry allows only one successful ``set_tracer_provider`` per process.
    Tests call this to reconfigure the provider between cases (private API).
    """
    trace_api._TRACER_PROVIDER = None  # noqa: SLF001
    trace_api._TRACER_PROVIDER_SET_ONCE = Once()  # noqa: SLF001


def _span_exporter_iter(provider: SDKTracerProvider) -> Iterator[Any]:
    """Yield span exporters wired into *provider*, if any.

    @param provider: SDK :class:`~opentelemetry.sdk.trace.TracerProvider` instance.
    @yields Exporter objects attached via batch/simple processors (internal introspection).
    """
    smp = getattr(provider, "_active_span_processor", None)
    if smp is None or not hasattr(smp, "_span_processors"):
        return
    for processor in smp._span_processors:
        ex = getattr(processor, "span_exporter", None) or getattr(
            processor, "_span_exporter", None
        )
        if ex is not None:
            yield ex


@pytest.fixture(autouse=True)
def _isolate_tracing() -> Iterator[None]:
    """Reset tracer provider around each test."""
    tracing.shutdown_tracing()
    _reset_global_tracer_provider_lock()
    yield
    tracing.shutdown_tracing()
    _reset_global_tracer_provider_lock()


def test_tracer_provider_has_service_name_hl_helper() -> None:
    """TracerProvider exposes ``service.name`` ``hl_helper`` after configuration."""
    tracing.configure_tracing()
    tp = trace_api.get_tracer_provider()
    assert isinstance(tp, SDKTracerProvider)
    name = tp.resource.attributes.get(ResourceAttributes.SERVICE_NAME)
    assert name == "hl_helper"


def test_tracer_provider_custom_service_name() -> None:
    """@p service_name is reflected on resources."""
    tracing.configure_tracing(service_name="custom_fleet")
    tp = trace_api.get_tracer_provider()
    assert isinstance(tp, SDKTracerProvider)
    assert tp.resource.attributes.get(ResourceAttributes.SERVICE_NAME) == "custom_fleet"


def test_parent_based_trace_id_ratio_sample_rate_defaults() -> None:
    """Default sample rate applies ``ParentBasedTraceIdRatio`` with rate ``0.01``."""
    tracing.configure_tracing()
    tp = trace_api.get_tracer_provider()
    assert isinstance(tp, SDKTracerProvider)
    assert isinstance(tp.sampler, ParentBasedTraceIdRatio)
    assert getattr(tp.sampler._root, "rate", None) == pytest.approx(0.01)


def test_parent_based_trace_id_ratio_custom_rate() -> None:
    """Administrative trace sample rates map to sampler root ratio."""
    tracing.configure_tracing(sample_rate=0.42)
    tp = trace_api.get_tracer_provider()
    assert isinstance(tp, SDKTracerProvider)
    assert isinstance(tp.sampler, ParentBasedTraceIdRatio)
    assert getattr(tp.sampler._root, "rate", None) == pytest.approx(0.42)


def test_no_otel_endpoint_skips_exporter() -> None:
    """When OTLP endpoint is unset, SDK provider has no span processors / exporters."""
    tracing.configure_tracing(otel_endpoint=None)
    tp = trace_api.get_tracer_provider()
    assert isinstance(tp, SDKTracerProvider)
    processors = getattr(tp._active_span_processor, "_span_processors", ())
    assert len(processors) == 0
    assert list(_span_exporter_iter(tp)) == []


def test_otel_endpoint_adds_otlp_exporter() -> None:
    """When OTLP endpoint is provided, batch processor uses ``OTLPSpanExporter``."""
    tracing.configure_tracing(otel_endpoint="127.0.0.1:9", otel_headers={"Authorization": "Bearer x"})
    tp = trace_api.get_tracer_provider()
    assert isinstance(tp, SDKTracerProvider)
    exporters = list(_span_exporter_iter(tp))
    assert len(exporters) == 1
    assert isinstance(exporters[0], OTLPSpanExporter)


def test_instrumentation_helpers_run_cleanly() -> None:
    """FastAPI / SQLAlchemy / httpx / gRPC instrumentation entry points succeed."""
    from fastapi import FastAPI

    tracing.configure_tracing()
    tracing.instrument_fastapi(FastAPI())
    engine = create_engine("sqlite+pysqlite:///:memory:")
    tracing.instrument_sqlalchemy(engine)
    tracing.instrument_httpx()
    tracing.instrument_grpc()


def test_get_tracer_returns_sdk_tracer() -> None:
    """@returns A concrete SDK tracer usable for spans."""
    tracing.configure_tracing()
    tr = tracing.get_tracer("server.tests.observability")
    assert isinstance(tr, SDKTracer)


def test_shutdown_tracing_cleans_up_and_is_idempotent() -> None:
    """``shutdown_tracing`` flushes and tracks provider; repeats are safe."""
    tracing.configure_tracing(otel_endpoint="127.0.0.1:9")
    tracing.shutdown_tracing()
    tracing.shutdown_tracing()

