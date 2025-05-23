"""OpenTelemetry instrumentation for the URL Shortener application."""

import logging
from contextlib import suppress
from functools import lru_cache
from typing import Optional, Tuple, Union, Dict, Any, List

from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPGrpcSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHttpSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter as OTLPGrpcMetricExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter as OTLPHttpMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import (
    ParentBasedTraceIdRatio,
    TraceIdRatioBased,
)

# Optional log exporter if enabled
try:
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter as OTLPGrpcLogExporter
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter as OTLPHttpLogExporter
    LOGS_AVAILABLE = True
except ImportError:
    LOGS_AVAILABLE = False

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache
def setup_telemetry() -> Tuple[Optional[TracerProvider], Optional[MeterProvider], Optional[object]]:
    """Initialize OpenTelemetry instrumentation."""
    if not settings.OTEL_ENABLED:
        logger.info("OpenTelemetry instrumentation is disabled")
        return None, None, None

    try:
        resource = Resource.create({
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.version": settings.APP_VERSION,
            "deployment.environment": settings.ENVIRONMENT,
            **_parse_resource_attributes(settings.OTEL_RESOURCE_ATTRIBUTES)
        })

        tracer_provider = _setup_tracing(resource)
        meter_provider = _setup_metrics(resource)
        logger_provider = _setup_logging(resource) if LOGS_AVAILABLE else None
        
        return tracer_provider, meter_provider, logger_provider
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry: {e}")
        return None, None, None


def instrument_app(db_engine=None, redis_client=None) -> None:
    """Instrument application dependencies."""
    if not settings.OTEL_ENABLED:
        return

    try:
        # Instrument logging
        LoggingInstrumentor().instrument(tracer_provider=trace.get_tracer_provider())
        logger.info("Logging instrumentation enabled")

        # Instrument SQLAlchemy if engine is provided
        if db_engine:
            with suppress(Exception):
                SQLAlchemyInstrumentor().instrument(
                    engine=db_engine,
                    tracer_provider=trace.get_tracer_provider(),
                    meter_provider=metrics.get_meter_provider()
                )
                logger.info("SQLAlchemy instrumentation enabled")

        # Instrument Redis if client is provided
        if redis_client:
            with suppress(Exception):
                RedisInstrumentor().instrument(
                    tracer_provider=trace.get_tracer_provider(),
                    meter_provider=metrics.get_meter_provider()
                )
                logger.info("Redis instrumentation enabled")
                
        # Create custom meters for application metrics
        _setup_custom_metrics()
    except Exception as e:
        logger.error(f"Failed to instrument application: {e}")


def _setup_tracing(resource: Resource) -> TracerProvider:
    """Set up tracing with the provided resource."""
    tracer_provider = TracerProvider(
        resource=resource,
        sampler=_create_sampler(
            settings.OTEL_TRACES_SAMPLER,
            float(settings.OTEL_TRACES_SAMPLER_ARG)
        )
    )
    trace.set_tracer_provider(tracer_provider)

    if settings.OTEL_EXPORTER_OTLP_PROTOCOL.lower() == "grpc":
        otlp_exporter = OTLPGrpcSpanExporter(
            endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            insecure=True
        )
    else:
        otlp_exporter = OTLPHttpSpanExporter(
            endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT
        )

    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    logger.info(f"OpenTelemetry tracer configured with {settings.OTEL_EXPORTER_OTLP_PROTOCOL} exporter")
    
    return tracer_provider


def _setup_metrics(resource: Resource) -> MeterProvider:
    """Set up metrics with the provided resource."""
    if settings.OTEL_EXPORTER_OTLP_PROTOCOL.lower() == "grpc":
        metric_exporter = OTLPGrpcMetricExporter(
            endpoint=settings.OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
            insecure=True
        )
    else:
        metric_exporter = OTLPHttpMetricExporter(
            endpoint=settings.OTEL_EXPORTER_OTLP_METRICS_ENDPOINT
        )
    
    reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=settings.OTEL_METRICS_EXPORT_INTERVAL_MILLIS
    )
    
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)
    logger.info(f"OpenTelemetry metrics configured with {settings.OTEL_EXPORTER_OTLP_PROTOCOL} exporter")
    
    return meter_provider


def _setup_logging(resource: Resource) -> Optional[object]:
    """Set up logging with the provided resource if available."""
    if not LOGS_AVAILABLE:
        logger.info("OpenTelemetry logs exporter not available")
        return None
    
    try:
        if settings.OTEL_EXPORTER_OTLP_PROTOCOL.lower() == "grpc":
            log_exporter = OTLPGrpcLogExporter(
                endpoint=settings.OTEL_EXPORTER_OTLP_LOGS_ENDPOINT,
                insecure=True
            )
        else:
            log_exporter = OTLPHttpLogExporter(
                endpoint=settings.OTEL_EXPORTER_OTLP_LOGS_ENDPOINT
            )
        
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        
        handler = LoggingHandler(level=getattr(logging, settings.OTEL_PYTHON_LOG_LEVEL), logger_provider=logger_provider)
        logging.getLogger().addHandler(handler)
        
        logger.info(f"OpenTelemetry logs configured with {settings.OTEL_EXPORTER_OTLP_PROTOCOL} exporter")
        return logger_provider
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry logging: {e}")
        return None


def _setup_custom_metrics() -> None:
    """Set up custom metrics for the application."""
    try:
        meter = metrics.get_meter(f"{settings.OTEL_SERVICE_NAME}_meter")
        
        # URL shortening metrics
        url_counter = meter.create_counter(
            name="url_shortener.urls.created",
            description="Number of URLs shortened",
            unit="1"
        )
        
        redirect_counter = meter.create_counter(
            name="url_shortener.redirects",
            description="Number of URL redirects",
            unit="1"
        )
        
        # Timing histograms
        url_create_histogram = meter.create_histogram(
            name="url_shortener.url_creation.duration",
            description="URL creation duration",
            unit="ms"
        )
        
        url_lookup_histogram = meter.create_histogram(
            name="url_shortener.url_lookup.duration",
            description="URL lookup duration",
            unit="ms"
        )
        
        # Monitoring gauges
        active_redis_connections = meter.create_observable_gauge(
            name="url_shortener.redis.active_connections",
            description="Number of active Redis connections",
            unit="1",
            callbacks=[]  # Will be populated when Redis client is available
        )
        
        logger.info("Custom metrics initialized")
    except Exception as e:
        logger.error(f"Failed to initialize custom metrics: {e}")


def _create_sampler(sampler_type: str, sampler_arg: float) -> Union[ParentBasedTraceIdRatio, TraceIdRatioBased]:
    """Create a sampler based on configuration."""
    if sampler_type.lower() == "parentbased_traceidratio":
        return ParentBasedTraceIdRatio(sampler_arg)
    else:
        return TraceIdRatioBased(sampler_arg)


def _parse_resource_attributes(attributes_str: str) -> Dict[str, str]:
    """Parse resource attributes from string format."""
    if not attributes_str:
        return {}
    
    attributes = {}
    for pair in attributes_str.split(","):
        with suppress(ValueError):
            key, value = pair.strip().split("=", 1)
            attributes[key] = value
    
    return attributes


def get_tracer(name: str = None) -> trace.Tracer:
    """Get a tracer for creating spans."""
    name = name or settings.OTEL_SERVICE_NAME
    return trace.get_tracer(name)


def get_meter(name: str = None) -> metrics.Meter:
    """Get a meter for creating metrics."""
    name = name or settings.OTEL_SERVICE_NAME
    return metrics.get_meter(name)
