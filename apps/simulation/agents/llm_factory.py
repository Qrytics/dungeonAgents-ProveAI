"""LLM factory for the dungeon simulation (shared across agent modules).

Provides :func:`build_llm` which returns an appropriate LangChain chat model
based on the model name string:

* Model names that start with ``"gemini-"`` → :class:`~langchain_google_genai.ChatGoogleGenerativeAI`,
  chosen automatically:

  - If ``GOOGLE_APPLICATION_CREDENTIALS`` is set (service-account JSON path),
    Vertex AI mode is used (``vertexai=True``).
    You must also set ``VERTEXAI_PROJECT`` and ``VERTEXAI_LOCATION``
    (e.g. ``us-central1``).
  - Otherwise the public Gemini API is used (requires ``GOOGLE_API_KEY``).

* All other model names → :class:`~langchain_openai.ChatOpenAI`
  (reads ``OPENAI_API_KEY`` from the environment).

Usage example::

    from apps.simulation.agents.llm_factory import build_llm

    llm = build_llm("gemini-2.5-flash-lite")
    llm_with_tools = llm.bind_tools(tools, tool_choice="required")
"""

from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel


def _resolve_gemini_provider() -> str:
    """Return ``"vertex_ai"`` when a service-account credential file is
    configured, otherwise ``"gemini_api"``.

    The detection is based on the ``GOOGLE_APPLICATION_CREDENTIALS``
    environment variable, which points to a service-account JSON key file
    used by the Vertex AI provider.  When it is absent the standard Gemini
    API (``GOOGLE_API_KEY``) is used instead.
    """
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return "vertex_ai"
    return "gemini_api"


def build_llm(model_name: str, **kwargs) -> BaseChatModel:
    """Return a LangChain chat model for *model_name*.

    Detects the provider from the model name prefix and constructs the
    correct LangChain integration class.  Extra keyword arguments are
    forwarded to the underlying constructor (e.g. ``temperature``).

    For Gemini model names the provider is chosen automatically based on the
    ``GOOGLE_APPLICATION_CREDENTIALS`` environment variable (see module
    docstring).

    Args:
        model_name: LLM model identifier, e.g. ``"gpt-4o-mini"``,
            ``"gemini-2.0-flash"``, or ``"gemini-2.5-flash-lite"``.
        **kwargs: Additional arguments forwarded to the model constructor.

    Returns:
        A :class:`~langchain_core.language_models.chat_models.BaseChatModel`
        instance ready to call.

    Raises:
        ImportError: If the required provider package is not installed.
    """
    if model_name.startswith("gemini-"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "Gemini models require 'langchain-google-genai'. "
                "Install it with:  pip install langchain-google-genai"
            ) from exc
        if _resolve_gemini_provider() == "vertex_ai":
            project = os.environ.get("VERTEXAI_PROJECT")
            location = os.environ.get("VERTEXAI_LOCATION", "us-central1")
            return ChatGoogleGenerativeAI(
                model=model_name, vertexai=True, project=project, location=location, **kwargs
            )
        return ChatGoogleGenerativeAI(model=model_name, **kwargs)

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model_name, **kwargs)


def get_model_identifier(llm: BaseChatModel) -> str:
    """Return the model identifier string from any LangChain chat model.

    ``ChatOpenAI`` exposes ``.model_name``; ``ChatGoogleGenerativeAI``
    exposes ``.model``.  This helper normalises both.

    Args:
        llm: Any LangChain chat model instance.

    Returns:
        Model identifier string, or ``"unknown"`` if neither attribute
        is present.
    """
    return getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
