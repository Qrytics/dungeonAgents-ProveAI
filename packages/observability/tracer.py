"""Tracer initialization for the observability package (M-13).

Provides ``init_tracer``, a singleton factory that creates an OTel
``TracerProvider`` backed by an OTLP HTTP exporter and a ``Langfuse``
client.  Both are keyed by ``run_id`` so that a single simulation run
shares the same provider and Langfuse session.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from langfuse import Langfuse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from packages.shared.constants import LANGFUSE_PROJECT
from packages.shared.types import RunID

# ---------------------------------------------------------------------------
# Internal singleton registry: run_id -> (Tracer, Langfuse)
# ---------------------------------------------------------------------------
_registry: dict[str, tuple[trace.Tracer, Langfuse]] = {}

_CONFIGS_DIR: Path = Path(__file__).resolve().parents[2] / "configs"


def _load_yaml(filename: str) -> dict[str, Any]:
    path = _CONFIGS_DIR / filename
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def init_tracer(run_id: RunID) -> tuple[trace.Tracer, Langfuse]:
    """Initialize the OTel TracerProvider and Langfuse client.

    Reads ``LANGFUSE_PUBLIC_KEY``, ``LANGFUSE_SECRET_KEY``, and
    ``LANGFUSE_HOST`` from the process environment.  Configuration for
    the OTLP exporter is loaded from ``configs/otel.yaml``.

    The returned pair is cached so that subsequent calls with the same
    *run_id* return the same objects (singleton per run).

    Args:
        run_id: Unique identifier for the current simulation run.

    Returns:
        A ``(Tracer, Langfuse)`` tuple ready for use by agent and game-loop
        components.
    """
    if run_id in _registry:
        return _registry[run_id]

    otel_cfg = _load_yaml("otel.yaml")

    service_name: str = otel_cfg.get("service_name", LANGFUSE_PROJECT)
    exporter_endpoint: str = otel_cfg.get(
        "exporter_endpoint", "http://localhost:4318/v1/traces"
    )
    batch_size: int = int(otel_cfg.get("batch_size", 512))
    export_interval_ms: int = int(otel_cfg.get("export_interval_ms", 1000))

    resource = Resource.create({"service.name": service_name, "run_id": run_id})
    provider = TracerProvider(resource=resource)

    # Only attach the OTLP exporter when the endpoint is explicitly overridden
    # via the environment, or the otel.yaml points to a non-localhost collector.
    # This avoids noisy connection-refused errors when no local collector runs.
    _otlp_endpoint: str = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", exporter_endpoint)
    _is_localhost = "localhost" in _otlp_endpoint or "127.0.0.1" in _otlp_endpoint
    _otlp_explicitly_set = "OTEL_EXPORTER_OTLP_ENDPOINT" in os.environ
    if not _is_localhost or _otlp_explicitly_set:
        otlp_exporter = OTLPSpanExporter(endpoint=_otlp_endpoint)
        processor = BatchSpanProcessor(
            otlp_exporter,
            max_export_batch_size=batch_size,
            schedule_delay_millis=export_interval_ms,
        )
        provider.add_span_processor(processor)

    # Set as the global provider so opentelemetry.trace.get_tracer() also
    # returns spans from this provider.
    trace.set_tracer_provider(provider)

    tracer: trace.Tracer = provider.get_tracer(LANGFUSE_PROJECT)

    langfuse_cfg = _load_yaml("langfuse.yaml")
    # Environment variable always takes precedence.  The YAML value may
    # contain an unresolved placeholder such as "${LANGFUSE_HOST}", so we
    # only use it as a fallback when it is a plain URL string.
    _yaml_host: str = langfuse_cfg.get("host", "")
    if _yaml_host.startswith("${") or not _yaml_host:
        _yaml_host = "https://cloud.langfuse.com"
    langfuse_host: str = os.environ.get("LANGFUSE_HOST", _yaml_host)

    langfuse_client = Langfuse(
        public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
        secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
        host=langfuse_host,
    )

    _registry[run_id] = (tracer, langfuse_client)
    return tracer, langfuse_client
