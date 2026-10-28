"""
Модуль розподіленого трасування (OpenTelemetry / Jaeger).

Підтримує:
- Ініціалізацію TracerProvider та експорт спанів через OTLP gRPC/HTTP
- Семантичні атрибути згідно зі специфікацією OpenTelemetry
- W3C TraceContext інжекцію та екстракцію (прокидання traceparent)
- Безпечний fallback на локальний консольний трейсер, якщо OpenTelemetry SDK відсутній
"""

import os
import sys
import time
import logging
from contextlib import contextmanager
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("telemetry")

# Спроба завантажити офіційний OpenTelemetry SDK
_HAS_OTEL = False
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.trace import Status, StatusCode

    # OTLP exporter (gRPC або HTTP)
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    except ImportError:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        except ImportError:
            OTLPSpanExporter = None

    _HAS_OTEL = True
except ImportError:
    trace = None
    TracerProvider = None
    BatchSpanProcessor = None
    ConsoleSpanExporter = None
    Resource = None
    TraceContextTextMapPropagator = None
    Status = None
    StatusCode = None
    OTLPSpanExporter = None


import atexit

_TRACER = None
_PROVIDER = None
_PROPAGATOR = TraceContextTextMapPropagator() if _HAS_OTEL else None


def init_tracer(service_name: str = "monte-carlo-worker",
                endpoint: Optional[str] = None) -> Any:
    """
    Ініціалізує TracerProvider з OTLP експортером у Jaeger або ConsoleSpanExporter.
    """
    global _TRACER, _PROVIDER

    if not _HAS_OTEL:
        logger.warning("OpenTelemetry SDK не встановлено. Використовується вбудований Fallback-трейсер.")
        _TRACER = FallbackTracer(service_name)
        return _TRACER

    otlp_endpoint = endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
    resource = Resource.create({"service.name": service_name, "environment": "production"})
    provider = TracerProvider(resource=resource)

    exporter = None
    if OTLPSpanExporter and otlp_endpoint:
        try:
            insecure = not otlp_endpoint.startswith("https://")
            is_grpc = "grpc" in getattr(OTLPSpanExporter, "__module__", "")
            if is_grpc:
                endpoint_clean = otlp_endpoint.replace("http://", "").replace("https://", "")
                exporter = OTLPSpanExporter(endpoint=endpoint_clean, insecure=insecure)
                logger.info("OpenTelemetry OTLP gRPC експортер підключено до %s", endpoint_clean)
            else:
                endpoint_url = otlp_endpoint if otlp_endpoint.startswith("http") else f"http://{otlp_endpoint}"
                exporter = OTLPSpanExporter(endpoint=endpoint_url)
                logger.info("OpenTelemetry OTLP HTTP експортер підключено до %s", endpoint_url)
        except Exception as e:
            logger.warning("Не вдалося підключити OTLP експортер (%s). Використовуємо ConsoleSpanExporter.", e)
            exporter = ConsoleSpanExporter()
    else:
        logger.info("OTLP експортер недоступний. Використовується ConsoleSpanExporter.")
        exporter = ConsoleSpanExporter()

    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    _PROVIDER = provider
    _TRACER = trace.get_tracer(service_name)
    atexit.register(flush_telemetry)
    return _TRACER


def flush_telemetry(timeout_sec: float = 2.0):
    """Примусово скидає буферизовані спани в OTLP експортер перед виходом."""
    global _PROVIDER
    if _PROVIDER and hasattr(_PROVIDER, "force_flush"):
        try:
            _PROVIDER.force_flush(int(timeout_sec * 1000))
        except Exception as e:
            logger.debug("Помилка force_flush: %s", e)
    time.sleep(0.5)


def mark_span_error(span: Any, message: str = "Error"):
    """Позначає спан як аварійний (статус ERROR для підсвічування червоним у Jaeger UI)."""
    if span is None:
        return
    if Status and StatusCode and hasattr(span, "set_status"):
        span.set_status(Status(StatusCode.ERROR, message))
    if hasattr(span, "set_attribute"):
        span.set_attribute("error", True)
        span.set_attribute("exception.type", message)


def get_tracer(service_name: str = "monte-carlo-worker") -> Any:
    """Повертає поточний активний трейсер."""
    global _TRACER
    if _TRACER is None:
        _TRACER = init_tracer(service_name)
    return _TRACER


@contextmanager
def start_span(name: str, attributes: Optional[Dict[str, Any]] = None, parent_context: Optional[Dict[str, str]] = None):
    """
    Контекстний менеджер для створення спану (працює як з OTel, так і з FallbackTracer).
    """
    tracer = get_tracer()

    if _HAS_OTEL and hasattr(tracer, "start_as_current_span"):
        ctx = None
        if parent_context and _PROPAGATOR:
            ctx = _PROPAGATOR.extract(carrier=parent_context)

        with tracer.start_as_current_span(name, context=ctx) as span:
            if attributes:
                for k, v in attributes.items():
                    span.set_attribute(k, v)
            try:
                yield span
            except Exception as exc:
                span.record_exception(exc)
                if Status and StatusCode:
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
    else:
        with tracer.start_span(name, attributes=attributes) as span:
            yield span


def inject_trace_context(carrier: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Інжектує поточний TraceContext (W3C traceparent) у словник заголовків."""
    if carrier is None:
        carrier = {}
    if _HAS_OTEL and _PROPAGATOR:
        _PROPAGATOR.inject(carrier=carrier)
    else:
        carrier["traceparent"] = f"00-{os.urandom(16).hex()}-{os.urandom(8).hex()}-01"
    return carrier


def extract_trace_context(carrier: Dict[str, str]) -> Any:
    """Витягує TraceContext із заголовків (carrier)."""
    if _HAS_OTEL and _PROPAGATOR:
        return _PROPAGATOR.extract(carrier=carrier)
    return carrier


class FallbackSpan:
    """Імітація спану для середовищ без встановленого OpenTelemetry."""
    def __init__(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        self.name = name
        self.attributes = attributes or {}
        self.start_time = 0.0
        self.duration_ms = 0.0
        self.trace_id = os.urandom(16).hex()
        self.span_id = os.urandom(8).hex()

    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    def record_exception(self, exc: Exception):
        self.attributes["error"] = True
        self.attributes["exception.message"] = str(exc)

    def set_status(self, status: Any):
        pass


class FallbackTracer:
    """Легкий трейсер, що виводить спани у структурованому форматі в stdout."""
    def __init__(self, service_name: str):
        self.service_name = service_name

    @contextmanager
    def start_span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        span = FallbackSpan(name, attributes)
        span.start_time = time.perf_counter()
        logger.info("[SPAN START] service=%s name='%s' trace_id=%s attributes=%s",
                    self.service_name, span.name, span.trace_id, span.attributes)
        try:
            yield span
        finally:
            span.duration_ms = (time.perf_counter() - span.start_time) * 1000.0
            logger.info("[SPAN END]   service=%s name='%s' duration=%.2fms trace_id=%s attributes=%s",
                        self.service_name, span.name, span.duration_ms, span.trace_id, span.attributes)
