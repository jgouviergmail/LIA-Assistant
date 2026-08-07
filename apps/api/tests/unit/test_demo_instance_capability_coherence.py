"""A capability switched ON must be able to reach what it needs.

Three declarations have to agree for a demonstrator feature to work, and they
live in three files nobody edits together:

1. the capability flag in ``.env.demo-instance.example`` (ADR-217);
2. the egress allowlist in ``infrastructure/demo-instance/squid.conf``, which
   is the ONLY way anything in the envelope reaches the Internet;
3. the provider key, when the capability needs one.

Measured 2026-08-07 on the running instance, through the proxy:

    CONNECT api.elevenlabs.io:443         403 Forbidden   (dictation, ON)
    CONNECT speech.platform.bing.com:443  403 Forbidden   (speech, ON)
    CONNECT api.perplexity.ai:443         403 Forbidden   (an offered agent)

Two capabilities were advertised to visitors and could not work at all. That
is not a vulnerability, it is worse for a demonstrator: the microphone button
was there and did nothing.

This guard RECALCULATES the requirement from the flags rather than pinning
today's allowlist (the lot-6 doctrine, ADR-218): switching a capability on
without opening its host fails here, and so does removing a host some enabled
capability still needs. The mapping below is the declaration — every entry
names what the host is FOR, because a hostname alone is unreviewable.
"""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

ROOT = repo_root_or_skip()
SQUID = ROOT / "infrastructure/demo-instance/squid.conf"
ENV_TEMPLATE = ROOT / ".env.demo-instance.example"

#: Hosts each capability must reach when its flag is true. A capability with
#: no entry reaches nothing outside (attachments, spaces, skills, MCP) or is
#: refused at the router anyway.
CAPABILITY_OUTBOUND_HOSTS: dict[str, tuple[tuple[str, ...], str]] = {
    "WEB_SEARCH_ENABLED": (
        ("api.search.brave.com",),
        "the search agent is the demonstrator's headline feature",
    ),
    "VOICE_TTS_ENABLED": (
        ("speech.platform.bing.com",),
        "Edge speech synthesis — free, no key, but it is still a host on the "
        "Internet and the API reaches nothing that is not listed",
    ),
    "VOICE_STT_ENABLED": (
        ("api.elevenlabs.io",),
        "ElevenLabs transcription; needs a key as well as a route",
    ),
    "IMAGE_GENERATION_ENABLED": (
        ("api.openai.com",),
        "image generation calls the OpenAI image endpoint",
    ),
}

#: Hosts nothing switches off, so the allowlist must always carry them.
ALWAYS_REQUIRED: dict[str, str] = {
    "openaipublic.blob.core.windows.net": (
        "tiktoken downloads its encoding on first use; without it the token "
        "counter raises and takes the WHOLE answer stream down (measured "
        "2026-08-06: the first real message returned a stream_error)"
    ),
    "generativelanguage.googleapis.com": (
        "memory and interests embed through Gemini; the embedding model is "
        "not in LLM_TYPES_REGISTRY and no capability switch covers it"
    ),
}

#: Provider key each LLM provider needs, so "route open, key absent" is caught
#: as loudly as "key present, route closed".
PROVIDER_HOSTS: dict[str, str] = {
    "deepseek": "api.deepseek.com",
    "openai": "api.openai.com",
    "anthropic": "api.anthropic.com",
    "gemini": "generativelanguage.googleapis.com",
}


def _allowlisted_hosts() -> set[str]:
    """Hosts the egress proxy will CONNECT to, read from its own config."""
    body = SQUID.read_text(encoding="utf-8")
    match = re.search(r"^acl\s+provider_hosts\s+dstdomain\s+(.+)$", body, re.M)
    assert match, "the allowlist ACL disappeared from squid.conf"
    return set(match.group(1).split())


def _template_flags() -> dict[str, str]:
    """Every ``KEY=value`` the demonstrator template declares."""
    flags: dict[str, str] = {}
    for line in ENV_TEMPLATE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        flags[key.strip()] = value.strip()
    return flags


class TestTheGuardReadsSomething:
    def test_the_allowlist_parses(self) -> None:
        """A parser that matches nothing would pass every assertion below."""
        hosts = _allowlisted_hosts()

        assert len(hosts) >= 3, f"only parsed {hosts}"
        assert all("." in host for host in hosts), hosts

    def test_the_template_parses(self) -> None:
        assert _template_flags().get("DEMO_MODE_ENABLED") == "true"


class TestEveryEnabledCapabilityCanReachItsProvider:
    @pytest.mark.parametrize("flag", sorted(CAPABILITY_OUTBOUND_HOSTS))
    def test_an_enabled_capability_has_its_hosts_open(self, flag: str) -> None:
        flags = _template_flags()
        if flags.get(flag) != "true":
            pytest.skip(f"{flag} is off in the template — nothing to reach")

        hosts, reason = CAPABILITY_OUTBOUND_HOSTS[flag]
        missing = sorted(set(hosts) - _allowlisted_hosts())

        assert not missing, (
            f"{flag}=true but {missing} is not on the egress allowlist, so the "
            f"capability is advertised to visitors and cannot work. Reason it "
            f"needs the host: {reason}. Either open it in squid.conf or switch "
            f"the capability off — a dead button is worse than an absent one."
        )

    def test_the_allowlist_carries_nothing_no_enabled_capability_needs(self) -> None:
        """Narrower is not safer, but wider is not free either."""
        flags = _template_flags()
        justified = set(ALWAYS_REQUIRED)
        for flag, (hosts, _) in CAPABILITY_OUTBOUND_HOSTS.items():
            if flags.get(flag) == "true":
                justified |= set(hosts)
        provider = flags.get("DEMO_INSTANCE_LLM_PROVIDER", "")
        if provider in PROVIDER_HOSTS:
            justified.add(PROVIDER_HOSTS[provider])

        unjustified = sorted(_allowlisted_hosts() - justified)

        assert not unjustified, (
            f"{unjustified} can be reached by a public instance and no enabled "
            "capability needs it. Every host is a destination a compromised "
            "process could talk to: remove it, or declare which capability "
            "requires it and why."
        )


class TestTheHostsNothingSwitchesOff:
    @pytest.mark.parametrize("host", sorted(ALWAYS_REQUIRED))
    def test_it_is_always_on_the_allowlist(self, host: str) -> None:
        assert host in _allowlisted_hosts(), f"{host} is missing: {ALWAYS_REQUIRED[host]}"


class TestTheConfiguredProviderIsReachable:
    def test_the_llm_provider_host_is_open(self) -> None:
        flags = _template_flags()
        provider = flags.get("DEMO_INSTANCE_LLM_PROVIDER", "")

        assert provider in PROVIDER_HOSTS, (
            f"DEMO_INSTANCE_LLM_PROVIDER={provider!r} has no declared host; "
            "a provider the allowlist cannot name is a provider the instance "
            "cannot call"
        )
        assert PROVIDER_HOSTS[provider] in _allowlisted_hosts(), (
            f"every LLM type is pointed at {provider}, whose host is not on "
            "the allowlist: the first message would fail"
        )
