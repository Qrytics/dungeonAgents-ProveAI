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

    otlp_exporter = OTLPSpanExporter(endpoint=exporter_endpoint)
    processor = BatchSpanProcessor(
        otlp_exporter,
        max_export_batch_size=batch_size,
        export_timeout_millis=export_interval_ms,
    )
    provider.add_span_processor(processor)

    # Set as the global provider so opentelemetry.trace.get_tracer() also
    # returns spans from this provider.
    trace.set_tracer_provider(provider)

    tracer: trace.Tracer = provider.get_tracer(LANGFUSE_PROJECT)

    langfuse_cfg = _load_yaml("langfuse.yaml")
    langfuse_host: str = os.environ.get(
        "LANGFUSE_HOST",
        langfuse_cfg.get("host", "https://cloud.langfuse.com"),
    )
    # Resolve ${LANGFUSE_HOST} placeholder that may appear in the YAML file.
    if langfuse_host.startswith("${"):
        langfuse_host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    langfuse_client = Langfuse(
        public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
        secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
        host=langfuse_host,
    )

    _registry[run_id] = (tracer, langfuse_client)
    return tracer, langfuse_client
