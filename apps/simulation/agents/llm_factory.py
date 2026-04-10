"""LLM factory for the dungeon simulation (shared across agent modules).

Provides :func:`build_llm` which returns an appropriate LangChain chat model
based on the model name string:

* Model names that start with ``"gemini-"`` → :class:`~langchain_google_genai.ChatGoogleGenerativeAI`
  (reads ``GOOGLE_API_KEY`` from the environment).
* All other model names → :class:`~langchain_openai.ChatOpenAI`
  (reads ``OPENAI_API_KEY`` from the environment).

Usage example::

    from apps.simulation.agents.llm_factory import build_llm

    llm = build_llm("gemini-2.0-flash")
    llm_with_tools = llm.bind_tools(tools, tool_choice="required")
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel


def build_llm(model_name: str, **kwargs) -> BaseChatModel:
    """Return a LangChain chat model for *model_name*.

    Detects the provider from the model name prefix and constructs the
    correct LangChain integration class.  Extra keyword arguments are
    forwarded to the underlying constructor (e.g. ``temperature``).

    Args:
        model_name: LLM model identifier, e.g. ``"gpt-4o-mini"`` or
            ``"gemini-2.0-flash"``.
        **kwargs: Additional arguments forwarded to the model constructor.

    Returns:
        A :class:`~langchain_core.language_models.chat_models.BaseChatModel`
        instance ready to call.

    Raises:
        ImportError: If ``langchain-google-genai`` is not installed and a
            Gemini model is requested.
    """
    if model_name.startswith("gemini-"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "Gemini models require 'langchain-google-genai'. "
                "Install it with:  pip install langchain-google-genai"
            ) from exc
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
