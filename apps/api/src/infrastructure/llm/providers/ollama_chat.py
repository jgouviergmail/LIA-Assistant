"""The native Ollama chat client: the traced subclass and its construction (ADR-267).

Ollama used to be served through ``ChatOpenAI`` pointed at its OpenAI-compatible
bridge. The bridge cannot express what the native API offers -- ``think`` (switch
thinking off, or ask for a depth), ``num_ctx`` (the context window LIA requests
AND accounts with), the thinking trace separated from the answer -- and the gap
read as a model defect: twelve output tokens requested, twelve tokens of
thinking, an empty answer (production, 2026-09-05).

This module owns both halves of the native client, because they are one unit and
because ``adapter.py`` sits at its size cap:

- :class:`ChatOllamaTraced` -- ``ChatOllama`` publishing what it SENDS, so the
  Article-12 register can read the call (ADR-263 lot 7). Stock ``ChatOllama``
  publishes only ``_type`` and ``stop`` as invocation parameters (measured on
  1.1.0): temperature, cap, window and ``think`` all travel inside the request
  and never reach a callback, so an Ollama call would have entered the register
  as a provider name and nothing else.
- :func:`create_ollama_llm` -- the construction, fed by what the server said
  about the model at discovery (``ModelCapabilitiesCache``'s discovered layer).

The credential is NOT resolved here: the adapter passes the base URL in, which
keeps this module free of any import back into ``adapter``.
"""

from __future__ import annotations

from typing import Any

from langchain_ollama import ChatOllama

from src.core.constants import CAPABILITY_PROVENANCE_DISCOVERED
from src.infrastructure.llm.model_profiles import ModelProfile
from src.infrastructure.llm.reasoning.translate import kwargs_for as reasoning_kwargs_for
from src.infrastructure.observability.logging import get_logger

__all__ = ["ChatOllamaTraced", "create_ollama_llm"]

logger = get_logger(__name__)

#: Sampling parameters with no native equivalent. ``repeat_penalty`` is a
#: different knob, not a translation, so nothing is mapped: the discovered
#: profile declares these unsupported and the admin UI stops offering them.
_NOT_EXPRESSIBLE = ("frequency_penalty", "presence_penalty")


class ChatOllamaTraced(ChatOllama):
    """``ChatOllama`` whose invocation parameters name what it sends."""

    def _get_invocation_params(
        self, stop: list[str] | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        params = super()._get_invocation_params(stop=stop, **kwargs)
        sent = {
            "model": self.model,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "num_predict": self.num_predict,
            "num_ctx": self.num_ctx,
            "reasoning": kwargs.get("reasoning", self.reasoning),
        }
        # A parameter that was not set was not sent: keep the record honest.
        params.update({key: value for key, value in sent.items() if value is not None})
        return params


def _drop_inexpressible(model: str, kwargs: dict[str, Any]) -> None:
    """Remove the sampling parameters the native client cannot express."""
    for param in _NOT_EXPRESSIBLE:
        value = kwargs.pop(param, None)
        if value:
            logger.debug("ollama_param_not_expressible", model=model, param=param, value=value)


def _client_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Build the httpx client kwargs, honouring the escape hatch first.

    ADR-221: the per-slot transport timeout is the timeout the client applies;
    ``client_kwargs`` is shared by the sync and async httpx clients.
    """
    explicit: dict[str, Any] = dict(kwargs.pop("client_kwargs", None) or {})
    timeout = kwargs.pop("timeout", None)
    if timeout is not None:
        explicit.setdefault("timeout", timeout)
    return explicit


def _context_window(model: str, caps: ModelProfile | None, configured: int | None) -> int | None:
    """The ``num_ctx`` to request: what LIA accounts with is what LIA requests.

    The discovered profile's ``max_input_tokens`` IS the window the discovery
    decided (``OLLAMA_NUM_CTX``, else the model's maximum capped) -- the number
    ``get_effective_context_window`` hands the compaction threshold and the
    ReAct budget. A tag nobody discovered gets no request: the server picks its
    VRAM tier and truncates a longer prompt in silence, so the gap is logged.

    Args:
        model: The Ollama tag.
        caps: Its profile, when one is known.
        configured: ``settings.ollama_num_ctx``, the fallback for an unknown tag.

    Returns:
        The window to request, or None to leave the choice to the server.
    """
    if caps is not None and caps.capability_provenance == CAPABILITY_PROVENANCE_DISCOVERED:
        return caps.max_input_tokens
    if configured is None:
        logger.warning(
            "ollama_context_window_unknown",
            model=model,
            msg="Tag not discovered and OLLAMA_NUM_CTX unset: the server picks its VRAM "
            "tier and LIA accounts with its generic default",
        )
    return configured


def _reasoning_kwargs(model: str, stored: Any, caps: ModelProfile | None) -> dict[str, Any]:
    """Translate the stored intent into ``think``, through the ADR-245 seam.

    The ladder is the one the server declared at discovery, so a positive depth
    only ever reaches a model that can think and ``none`` reaches any of them.
    When nothing is asked and the model IS a thinking model, the server default
    is made EXPLICIT: that is the only way ``langchain-ollama`` separates the
    trace into ``reasoning_content`` instead of dropping it. The server would
    think either way; this is what lets LIA see it.

    That last assertion requires the SERVER's word (``discovered``), not any
    profile: the catalogue's four static Ollama rows are guesses an admin can
    edit, and ``think=true`` on a model without the capability is a 400 on every
    call. Absent the server's word LIA sends nothing -- the model behaves as it
    would have, only its trace stays folded into the response.
    """
    translated = reasoning_kwargs_for("ollama", model, stored)
    server_says_thinking = (
        caps is not None
        and caps.capability_provenance == CAPABILITY_PROVENANCE_DISCOVERED
        and caps.is_reasoning_model
    )
    if "reasoning" not in translated and server_says_thinking:
        return {"reasoning": True}
    return translated


def _drop_unknown(model: str, kwargs: dict[str, Any]) -> None:
    """Report and remove ``provider_config`` keys the client does not define.

    ``ChatOllama`` ignores unknown fields in silence (pydantic ``extra="ignore"``),
    and a silently ignored ``num_ctx`` typo is the failure this guard exists for.
    """
    unknown = sorted(key for key in kwargs if key not in ChatOllamaTraced.model_fields)
    for key in unknown:
        kwargs.pop(key)
    if unknown:
        logger.warning(
            "ollama_provider_config_keys_ignored",
            model=model,
            keys=unknown,
            msg="provider_config keys ChatOllama does not define were dropped",
        )


def create_ollama_llm(
    *,
    model: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
    configured_num_ctx: int | None,
    caps: ModelProfile | None,
    **kwargs: Any,
) -> ChatOllamaTraced:
    """Build the native Ollama client for one slot.

    What the native client carries that the OpenAI-compatible shim could not:
    ``think`` (through the one ADR-245 seam), ``num_ctx``, ``num_predict`` (the
    slot's output cap under the name the server reads), ``format`` for
    grammar-constrained JSON, the thinking trace in ``reasoning_content``, and
    usage on every response.

    Args:
        model: Ollama tag (e.g. ``qwen3.8:27b``).
        base_url: The server root, already normalised by the caller.
        temperature: Sampling temperature.
        max_tokens: Output cap, sent as ``num_predict``.
        configured_num_ctx: ``settings.ollama_num_ctx``.
        caps: What the server said about this tag, when it was discovered.
        **kwargs: ``top_p``, ``timeout`` and the ``provider_config`` escape
            hatch (``num_ctx``, ``keep_alive``, ``top_k``, ``seed``, ...).

    Returns:
        The configured client.
    """
    _drop_inexpressible(model, kwargs)
    top_p = kwargs.pop("top_p", None)
    client_kwargs = _client_kwargs(kwargs)
    num_ctx = kwargs.pop("num_ctx", None)
    if num_ctx is None:
        num_ctx = _context_window(model, caps, configured_num_ctx)
    reasoning_kwargs = _reasoning_kwargs(model, kwargs.pop("reasoning_effort", None), caps)
    _drop_unknown(model, kwargs)

    logger.info(
        "ollama_llm_configured",
        model=model,
        base_url=base_url,
        num_ctx=num_ctx,
        num_predict=max_tokens,
        reasoning=reasoning_kwargs.get("reasoning"),
        capability_known=caps is not None,
    )

    # The provider_config escape hatch wins over every derived parameter (same
    # precedence as ``timeout``): ``{"num_predict": 2048}`` there is the
    # operator's explicit cap, not a duplicate of the slot's max_tokens.
    params: dict[str, Any] = {
        "model": model,
        "base_url": base_url,
        "temperature": temperature,
        "num_predict": max_tokens,
        "top_p": top_p,
        "num_ctx": num_ctx,
        "client_kwargs": client_kwargs,
        **reasoning_kwargs,
    }
    params.update(kwargs)
    return ChatOllamaTraced(**params)
