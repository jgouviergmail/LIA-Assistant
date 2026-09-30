"""Planning and running ONE network sandbox run (ADR-298).

Two steps, deliberately apart:

- :func:`plan_network_run` decides — hosts validated upstream are classified
  against the person's active connectors, the operator's list and the
  person's grants; a credential becomes a per-run token and a secret file
  path; the data scope is the minimum over the hosts. Nothing has started
  and nothing is written: the plan is what a HITL question is built from
  when a host is unknown;
- :func:`execute_network_run` acts — the run is claimed in the effect
  register, published to the proxy, executed on the sandbox network, and
  both are closed from the result.
"""

from __future__ import annotations

import secrets as random_secrets
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog

from src.core.config import get_settings
from src.core.constants import (
    PYTHON_SANDBOX_EGRESS_CA_DIR,
    PYTHON_SANDBOX_EGRESS_CA_FILE,
    PYTHON_SANDBOX_EGRESS_CA_VOLUME,
    PYTHON_SANDBOX_EGRESS_CONFIG_DIR,
    PYTHON_SANDBOX_EGRESS_NETWORK,
    PYTHON_SANDBOX_EGRESS_TOKEN_ENV_PREFIX,
    PYTHON_SANDBOX_EGRESS_TOKEN_PREFIX,
)
from src.domains.agents.effects.in_turn_effects import (
    SANDBOX_NETWORK_CAPABILITY,
    InTurnEffect,
    in_turn_effect,
)
from src.domains.agents.python_sandbox.egress.connectors import (
    ConnectorGate,
    active_connector_hosts,
    real_keys_for,
)
from src.domains.agents.python_sandbox.egress.hosts import (
    ConnectorHost,
    HostDecision,
    HostStatus,
    classify_hosts,
)
from src.domains.agents.python_sandbox.egress.registry import LiveRun, RunCredential
from src.domains.agents.python_sandbox.egress.ruleset import SECRETS_DIRNAME
from src.domains.agents.python_sandbox.egress.service import deployment_publisher
from src.domains.skills.executor import EgressSpec, ScriptResult, SkillScriptExecutor

logger = structlog.get_logger(__name__)

#: The mutation policy the network act is recorded under — the tool's own.
NETWORK_RUN_POLICY = "sandboxed"
TOKEN_RANDOM_BYTES = 24


@dataclass(frozen=True)
class NetworkRunPlan:
    """Everything a permitted network run needs, decided before it starts.

    Attributes:
        run: What the proxy is told.
        secrets: ``{connector: real key}`` — written for the proxy, never handed
            to the sandbox.
        spec: What the sandbox is handed.
        decision: The classification, for the answer and the register.
    """

    run: LiveRun
    secrets: dict[str, str]
    spec: EgressSpec
    decision: HostDecision

    @property
    def share_turn_data(self) -> bool:
        return self.decision.share_turn_data

    @property
    def statuses(self) -> dict[str, HostStatus]:
        return self.decision.statuses


def token_env_name(connector: str) -> str:
    """The env variable a script reads a connector's token from."""
    return f"{PYTHON_SANDBOX_EGRESS_TOKEN_ENV_PREFIX}{connector.upper()}"


def mint_token() -> str:
    """An opaque per-run token: worthless outside the proxy, dead with the run."""
    return f"{PYTHON_SANDBOX_EGRESS_TOKEN_PREFIX}{random_secrets.token_urlsafe(TOKEN_RANDOM_BYTES)}"


async def decide_hosts(
    hosts: tuple[str, ...],
    *,
    user_id: UUID,
    gate: ConnectorGate,
    grants: Mapping[str, bool],
    with_connectors: bool = True,
) -> HostDecision:
    """Classify the declared hosts for this account.

    Args:
        hosts: Normalised declared hosts.
        user_id: The account.
        gate: The tool's connector service.
        grants: ``{host: share_turn_data}`` — the person's past decisions.
        with_connectors: Whether the person's connector hosts are permitted
            with their tokens. False for a skill written elsewhere (ADR-327):
            it never reaches the person's connectors, so such a host is only
            reachable as the operator's or the person's grant, and no token
            travels.

    Returns:
        The decision, ``unknown`` naming what nobody permitted.
    """
    return classify_hosts(
        hosts,
        connectors=await active_connector_hosts(gate, user_id) if with_connectors else {},
        operator_hosts={h.lower() for h in get_settings().python_sandbox_egress_hosts},
        grants=grants,
    )


async def plan_network_run(
    decision: HostDecision, *, run_id: str, user_id: UUID, gate: ConnectorGate
) -> NetworkRunPlan:
    """Turn a decision with no unknown host into a runnable plan.

    Args:
        decision: The classification; every host permitted.
        run_id: The run's identity — its registry entry and its secrets directory.
        user_id: The account.
        gate: The tool's connector service, for the real keys.

    Returns:
        The plan.
    """
    keys = await real_keys_for(gate, user_id, decision.credentials)
    credentials: list[RunCredential] = []
    tokens: dict[str, str] = {}
    for spec in decision.credentials:
        if spec.connector not in keys:
            continue  # deactivated meanwhile: reached without a credential
        token = mint_token()
        credentials.append(_credential(spec, token, run_id))
        tokens[token_env_name(spec.connector)] = token
    settings = get_settings()
    run = LiveRun(
        run_id=run_id,
        user_id=str(user_id),
        hosts=tuple(decision.statuses),
        credentials=tuple(credentials),
    )
    egress = EgressSpec(
        network=PYTHON_SANDBOX_EGRESS_NETWORK,
        proxy_url=settings.python_sandbox_egress_proxy_url,
        ca_volume=PYTHON_SANDBOX_EGRESS_CA_VOLUME,
        ca_dir=PYTHON_SANDBOX_EGRESS_CA_DIR,
        ca_file=PYTHON_SANDBOX_EGRESS_CA_FILE,
        tokens=tokens,
    )
    return NetworkRunPlan(
        run=run,
        secrets={c: keys[c] for c in keys if any(cr.connector == c for cr in credentials)},
        spec=egress,
        decision=decision,
    )


def _credential(spec: ConnectorHost, token: str, run_id: str) -> RunCredential:
    return RunCredential(
        connector=spec.connector,
        host=spec.host,
        token=token,
        auth_method=spec.auth_method,
        auth_name=spec.auth_name,
        secret_path=f"{PYTHON_SANDBOX_EGRESS_CONFIG_DIR}/{SECRETS_DIRNAME}/{run_id}/{spec.connector}.key",
    )


@asynccontextmanager
async def serving(plan: NetworkRunPlan, *, capability: str) -> AsyncIterator[InTurnEffect]:
    """Claim the network act, publish the run to the proxy, and hold both open.

    Whatever runs inside reaches exactly the plan's hosts; the effect closes
    from what the caller sets on it, and the proxy forgets the run on exit.

    Args:
        plan: The decided run.
        capability: What the register records it as — a script's run or a
            skill's command.

    Yields:
        The claimed effect; the caller sets ``succeeded``.

    Raises:
        EgressProxyUnavailable: When the proxy could not serve the run — the
            effect closes as a failure and nothing runs.
    """
    arguments = {
        "hosts": list(plan.run.hosts),
        "turn_data_shared": plan.share_turn_data,
        "authorizations": {host: status.value for host, status in plan.statuses.items()},
    }
    async with in_turn_effect(
        tool_name=capability, policy=NETWORK_RUN_POLICY, arguments=arguments
    ) as effect:
        publisher = await deployment_publisher()
        async with publisher.serve(plan.run, plan.secrets):
            yield effect


async def execute_network_run(
    plan: NetworkRunPlan, *, source: str, payload: dict[str, Any], user_id: UUID
) -> ScriptResult:
    """Claim, publish, run, close.

    Args:
        plan: The decided run.
        source: The model's script.
        payload: What the script reads on stdin (already narrowed by the plan).
        user_id: The account, for the audit trail.

    Returns:
        The script's result.

    Raises:
        EgressProxyUnavailable: When the proxy could not serve the run — no
            container is launched against an unpublished ruleset, and the
            effect closes as a failure.
    """
    settings = get_settings()
    async with serving(plan, capability=SANDBOX_NETWORK_CAPABILITY) as effect:
        result = await SkillScriptExecutor.execute_source(
            source=source,
            payload=payload,
            label="ephemeral",
            timeout_seconds=settings.python_sandbox_network_timeout_seconds,
            user_id=str(user_id),
            egress=plan.spec,
        )
        effect.succeeded = bool(result.success)
    return result


__all__ = [
    "NETWORK_RUN_POLICY",
    "NetworkRunPlan",
    "decide_hosts",
    "execute_network_run",
    "mint_token",
    "plan_network_run",
    "serving",
    "token_env_name",
]
