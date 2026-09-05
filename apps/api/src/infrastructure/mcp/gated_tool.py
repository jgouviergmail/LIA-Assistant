"""Self-gating for the MCP tool adapters (ADR-263).

Every other capability in the codebase is a ``StructuredTool`` whose
``coroutine`` the registry replaces with a gated one. The two MCP adapters
cannot be gated that way, for two independent reasons measured 2026-09-04:

1. Their ``coroutine`` is a read-only ``@property`` — assigning to it raises
   ``AttributeError``, which would have broken the registration of every user's
   MCP server the first time one loaded.
2. They are reached through THREE doors: ``.coroutine(...)`` (the pipeline's
   direct path), ``ainvoke(...)`` → ``_arun`` (the sub-agent runner) and
   ``_inner._arun(...)`` (``_MCPReActWrapper``, the ReAct loop). A gate on one
   door is not a gate.

So the adapters gate themselves at the single point all three doors reach.
Each one keeps its own server call, renamed ``_call_server``; this mixin owns
the wrapping, memoised per instance so the wrapper — and the policy it
resolves — is built once.

This is the only self-gating family, and it stays honest with the rest: the
wrapper carries the same marker the boot assert reads, so a registry-wide check
sees no exception here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any


class EffectGatedMCPTool:
    """Mixin installing the effect gate inside an MCP adapter's own call path.

    The concrete adapter must implement :meth:`_call_server` — its real
    dialogue with the MCP server — and inherit this mixin BEFORE ``BaseTool``
    so ``_arun`` and ``coroutine`` resolve here.
    """

    #: Memoised gated wrapper. Declared as a ``PrivateAttr`` by each concrete
    #: adapter — pydantic only collects private attributes from the classes it
    #: builds, so a mixin that is not a model can annotate it but not create it.
    _gated_call: Callable[..., Awaitable[Any]] | None

    if TYPE_CHECKING:
        # Provided by ``BaseTool``. Declared for the type checker only: a live
        # annotation here would be collected by pydantic as a FIELD of every
        # adapter that mixes this class in.
        name: str

    async def _call_server(self, **kwargs: Any) -> Any:
        """Talk to the MCP server. Implemented by each adapter."""
        raise NotImplementedError

    def _effect_gated_call(self) -> Callable[..., Awaitable[Any]]:
        """Return the gated call, building it once per instance.

        Rebuilt when the instance is RENAMED: ``model_copy(update={"name": …})``
        carries private attributes over, and a copy acting under the original's
        name would be policed by the wrong policy and recorded as another tool.
        The registry relies on this too — it skips an instance already gated
        under its own name, which is what keeps it from assigning to this
        read-only property.

        Returns:
            The adapter's ``_call_server`` wrapped by the effect gate, under
            the registered (prefixed) tool name — the name the ledger, the
            catalogue and the user's confirmation card all use.
        """
        from src.domains.agents.effects.runtime import EFFECT_GATED_NAME_ATTR, gated

        current = self._gated_call
        if current is None or getattr(current, EFFECT_GATED_NAME_ATTR, None) != self.name:
            current = gated(self.name, self._call_server)
            self._gated_call = current
        return current

    @property
    def coroutine(self) -> Callable[..., Awaitable[Any]]:
        """Expose the gated call for the executor's direct path.

        Without this, ``BaseTool`` subclasses fall to ``ainvoke()``, which
        stringifies the result through ``ToolMessage(content=str(result))`` and
        loses the ``UnifiedToolOutput``.
        """
        return self._effect_gated_call()

    async def _arun(self, **kwargs: Any) -> Any:
        """Every framework path lands here, and here the gate is.

        Args:
            **kwargs: The tool arguments, as the model chose them.

        Returns:
            Whatever the gate returns: the server's result, a confirmation
            draft, a refusal, or the record of an effect already performed.
        """
        return await self._effect_gated_call()(**kwargs)
