"""A diagnosis nobody can read, built on evidence nobody supplied.

Two defects reported by the owner on 2026-09-01, both visible in one file:

- the diagnostician prompt ends with *"Write in concise technical English (the
  admin UI renders it as-is)"*. Every other string on that page is localised in
  six languages; the one written by the model was not.
- every diagnosis said "Insufficient evidence to determine the exact cause".
  The prompt does instruct the model to say so when the evidence is thin — and
  the evidence pack was three fields: a check id, a number, and a short detail
  string. No logs, no trend, no correlated signal. The model was not being
  evasive, it was being accurate.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

#: The evidence pack (ADR-266) as the pump receives it when a test does not
#: care about its content — shaped like `collect_diagnosis_context` returns it.
_CANNED_PACK: dict[str, object] = {
    "recipe": None,
    "window_minutes": 30,
    "runtime": {"version": "test", "commit": "", "build_date": "", "uptime_seconds": 0},
    "metrics": [],
    "logs": {"status": "skipped"},
}


class TestThePromptDoesNotHardcodeALanguage:
    def test_it_takes_the_language_as_a_placeholder(self) -> None:
        from src.domains.agents.prompts.prompt_loader import load_prompt

        text = str(load_prompt("diagnostician_prompt"))
        assert "{language}" in text

    def test_it_no_longer_pins_english(self) -> None:
        from src.domains.agents.prompts.prompt_loader import load_prompt

        text = str(load_prompt("diagnostician_prompt")).lower()
        assert "technical english" not in text, (
            "The admin panel is localised in six languages; the one string the "
            "model writes must not be the exception."
        )

    def test_it_tells_the_model_how_to_read_the_pack_and_its_blind_spots(self) -> None:
        """The pack is only useful if the model knows to read it before saying
        evidence is missing — and knows an unavailable source is not silence."""
        from src.domains.agents.prompts.prompt_loader import load_prompt

        text = str(load_prompt("diagnostician_prompt")).lower()
        assert "breakdown metrics" in text
        assert "recent log lines" in text
        assert "runtime" in text
        assert "unavailable" in text

    def test_it_still_forbids_inventing_a_cause(self) -> None:
        """The instruction that produced the honest 'insufficient evidence'
        must survive: the fix is more evidence, never a licence to guess."""
        from src.domains.agents.prompts.prompt_loader import load_prompt

        text = str(load_prompt("diagnostician_prompt")).lower()
        assert "rather than inventing" in text


class TestTheEvidencePackCarriesSomethingToReasonFrom:
    @staticmethod
    def _incident(**over: object) -> SimpleNamespace:
        base: dict[str, object] = {
            "correlation_key": "embedding_failure_rate",
            "severity": "warning",
            "title": "Embedding failure rate",
            "evidence": {
                "check_id": "embedding_failure_rate",
                "value": 46.0,
                "detail": "46%",
            },
            "alertname": "EmbeddingOperationsFailing",
        }
        base.update(over)
        return SimpleNamespace(**base)

    def test_the_threshold_that_was_crossed_is_quoted(self) -> None:
        """A number with no threshold beside it cannot be judged: 46 is an
        incident for one check and normal for another."""
        from src.domains.diagnostics.diagnosis import _build_human_message

        message = _build_human_message(
            self._incident(evidence={"check_id": "x", "value": 46.0, "warn": 5.0, "crit": 20.0}),
            runbook="",
        )
        assert "5.0" in message and "20.0" in message

    @staticmethod
    def _context(**over: object) -> dict[str, object]:
        """A pack shaped exactly like `collect_diagnosis_context` returns it —
        the 2026-09-05 incident, as the collector would have seen it."""
        base: dict[str, object] = {
            "recipe": "EmbeddingOperationsFailing",
            "window_minutes": 30,
            "runtime": {
                "version": "1.42.0",
                "commit": "d1bc4743f400",
                "build_date": "2026-09-05T05:59:00Z",
                "uptime_seconds": 2820,
                "window_minutes": 30,
            },
            "metrics": [
                {
                    "query_id": "embedding_failure_rate",
                    "title": "Embedding failure rate",
                    "unit": "percent",
                    "status": "ok",
                    "error": None,
                    "series": [{"labels": {}, "value": 25.0}],
                    "truncated": False,
                },
                {
                    "query_id": "embedding_outcomes_by_result",
                    "title": "Embedding operations by outcome",
                    "unit": "count",
                    "status": "ok",
                    "error": None,
                    "series": [
                        {"labels": {"outcome": "failed"}, "value": 2.0339},
                        {"labels": {"outcome": "succeeded"}, "value": 6.1017},
                    ],
                    "truncated": False,
                },
                {
                    "query_id": "embedding_errors_by_reason",
                    "title": "Embedding provider refusals by classified reason",
                    "status": "unavailable",
                    "error": "circuit_open",
                    "series": [],
                    "truncated": False,
                },
            ],
            "logs": {
                "status": "ok",
                "service": "api",
                "lines_read": 12,
                "lines_kept": 12,
                "counts": [
                    {
                        "event": "gemini_embedding_failed",
                        "level": "error",
                        "head": "Error embedding content: 500 INTERNAL. {'error': {'code': 500",
                        "count": 8,
                    },
                    {
                        "event": "rag_injection_failed",
                        "level": "warning",
                        "head": "Max retries (2) exceeded for embedding_embed_query",
                        "count": 4,
                    },
                ],
                "counts_truncated": False,
                "samples": [
                    {
                        "ts": "2026-09-05T06:10:42+00:00",
                        "level": "error",
                        "event": "gemini_embedding_failed",
                        "operation": "embed_query",
                        "error": "Error embedding content: 500 INTERNAL.",
                    }
                ],
            },
        }
        base.update(over)
        return base

    def test_the_context_pack_is_rendered_as_quoted_data(self) -> None:
        """What was in Loki and Prometheus all along reaches the model — and is
        framed as data, never as instructions it could follow."""
        from src.domains.diagnostics.diagnosis import _build_human_message

        message = _build_human_message(self._incident(), runbook="", context=self._context())

        # Breakdown: labels and exact values, under the query's title — and the
        # unit beside a bare value, or "25" cannot be told from 25 seconds.
        assert "Embedding operations by outcome" in message
        assert "outcome=failed" in message and "2.0339" in message
        assert "25 percent" in message
        # Logs: counts by event with the failure's head, and the sample line.
        assert "8 × gemini_embedding_failed" in message
        assert "500 INTERNAL" in message
        assert "embed_query" in message
        # Runtime: the build and how long it has been up.
        assert "1.42.0" in message and "d1bc4743f400" in message and "2820" in message
        # Every section the model may quote is framed as data.
        assert message.lower().count("quoted data") >= 4

    def test_an_unavailable_source_is_stated_not_silently_absent(self) -> None:
        """A blind source and a quiet source are different facts."""
        from src.domains.diagnostics.diagnosis import _build_human_message

        context = self._context(
            logs={"status": "unavailable", "service": "api", "error": "transport:ConnectError"}
        )
        message = _build_human_message(self._incident(), runbook="", context=context)

        assert "transport:ConnectError" in message
        assert "circuit_open" in message, "an unavailable metric names its reason too"
        assert "unavailable" in message.lower()

    def test_a_skipped_log_source_is_said_in_one_line(self) -> None:
        from src.domains.diagnostics.diagnosis import _build_human_message

        message = _build_human_message(
            self._incident(), runbook="", context=self._context(logs={"status": "skipped"})
        )
        assert "no log excerpt" in message.lower()

    def test_a_pack_that_could_not_be_collected_is_named_not_mistaken_for_no_recipe(self) -> None:
        """The collector failing outright leaves `{"status": "unavailable"}`;
        that must read as a blind pack, not as an incident with no recipe."""
        from src.domains.diagnostics.diagnosis import _build_human_message

        message = _build_human_message(
            self._incident(), runbook="", context={"status": "unavailable", "error": "RuntimeError"}
        )
        assert "UNAVAILABLE" in message and "RuntimeError" in message
        assert "No evidence recipe" not in message

    def test_no_context_still_produces_a_message(self) -> None:
        from src.domains.diagnostics.diagnosis import _build_human_message

        message = _build_human_message(self._incident(), runbook="", context=None)
        assert "Incident:" in message
        assert "Evidence (quoted data)" in message

    def test_an_incident_with_no_extra_evidence_still_produces_a_message(self) -> None:
        """Enrichment is best-effort: a Loki outage must not stop diagnosis."""
        from src.domains.diagnostics.diagnosis import _build_human_message

        message = _build_human_message(self._incident(evidence={}), runbook="")
        assert "Incident:" in message

    def test_the_absence_of_a_runbook_is_stated_rather_than_left_blank(self) -> None:
        from src.domains.diagnostics.diagnosis import _build_human_message

        message = _build_human_message(self._incident(), runbook="")
        assert "No runbook" in message


class TestTheDiagnosisIsStoredPerAdminLanguage:
    """A diagnosis is written once by a scheduler tick, with no reader in sight.

    Generating it in the languages the ADMINS actually read is the only shape
    that satisfies "the language of the admin who displays" without an LLM call
    on every page view. With a single admin — the normal case for a self-hosted
    instance — that is exactly one call, in the right language.
    """

    def test_the_stored_shape_carries_the_language_it_was_written_in(self) -> None:
        from src.domains.diagnostics.diagnosis import build_diagnosis_record

        record = build_diagnosis_record(
            diagnosis="Le fournisseur refuse les appels.",
            probable_cause="Quota par minute atteint.",
            recommended_actions=["Augmenter le quota."],
            language="fr",
            model="m",
            cost_usd=0.0,
            had_runbook=False,
        )
        assert record["language"] == "fr"

    def test_a_reader_gets_their_own_language_when_it_exists(self) -> None:
        from src.domains.diagnostics.diagnosis import diagnosis_for_language

        stored = {
            "language": "en",
            "diagnosis": "English text",
            "by_language": {
                "fr": {
                    "diagnosis": "Texte français",
                    "probable_cause": "c",
                    "recommended_actions": [],
                }
            },
        }
        assert diagnosis_for_language(stored, "fr")["diagnosis"] == "Texte français"

    def test_a_reader_whose_language_is_absent_still_sees_something(self) -> None:
        """Showing nothing because nobody generated German would hide a real
        incident behind a translation gap."""
        from src.domains.diagnostics.diagnosis import diagnosis_for_language

        stored = {"language": "en", "diagnosis": "English text", "probable_cause": "c"}
        resolved = diagnosis_for_language(stored, "de")
        assert resolved["diagnosis"] == "English text"

    def test_a_row_written_before_this_change_is_read_unchanged(self) -> None:
        """Existing incidents have no `language` and no `by_language`; they must
        keep rendering rather than disappear from the panel."""
        from src.domains.diagnostics.diagnosis import diagnosis_for_language

        legacy = {"diagnosis": "old", "probable_cause": "c", "recommended_actions": ["a"]}
        assert diagnosis_for_language(legacy, "fr") == legacy

    def test_the_resolved_shape_does_not_depend_on_the_reader(self) -> None:
        """Metadata must not vanish for the reader whose language MATCHED.

        Resolving to the raw variant would have returned three text fields to a
        French admin and the full record to a German one — the same endpoint
        answering two different shapes depending on who asked.
        """
        from src.domains.diagnostics.diagnosis import diagnosis_for_language

        stored = {
            "language": "en",
            "diagnosis": "English text",
            "probable_cause": "c",
            "model": "gpt-x",
            "cost_usd": 0.02,
            "diagnosed_at": "2026-09-01T00:00:00+00:00",
            "had_runbook": True,
            "by_language": {"fr": {"diagnosis": "Texte", "probable_cause": "cause"}},
        }
        matched = diagnosis_for_language(stored, "fr")
        unmatched = diagnosis_for_language(stored, "de")
        assert set(matched) == set(unmatched)
        for key in ("model", "cost_usd", "diagnosed_at", "had_runbook"):
            assert matched[key] == stored[key]
        # ...and the reader is told which language they are actually reading.
        assert matched["language"] == "fr"
        assert unmatched["language"] == "en"

    def test_the_other_admins_languages_never_leave_the_server(self) -> None:
        """`by_language` grows with every admin; a reader has no use for it."""
        from src.domains.diagnostics.diagnosis import diagnosis_for_language

        stored = {
            "language": "en",
            "diagnosis": "English",
            "by_language": {
                "fr": {"diagnosis": "Texte"},
                "de": {"diagnosis": "Text"},
            },
        }
        for reader in ("fr", "de", "it"):
            assert "by_language" not in diagnosis_for_language(stored, reader)

    def test_no_diagnosis_resolves_to_no_diagnosis(self) -> None:
        from src.domains.diagnostics.diagnosis import diagnosis_for_language

        assert diagnosis_for_language(None, "fr") is None


class TestWhichLanguagesAreGenerated:
    async def test_the_distinct_languages_of_admins_are_used(self) -> None:
        from src.domains.diagnostics.diagnosis import admin_languages

        class _Repo:
            async def distinct_admin_languages(self):
                return ["fr", "fr", "en"]

        assert sorted(await admin_languages(_Repo())) == ["en", "fr"]

    async def test_an_instance_with_no_admin_still_gets_one_diagnosis(self) -> None:
        """A fresh install has no superuser yet; producing nothing would make
        the panel look broken on the very first incident."""
        from src.domains.diagnostics.diagnosis import admin_languages

        class _Repo:
            async def distinct_admin_languages(self):
                return []

        assert await admin_languages(_Repo()) == ["en"]

    async def test_an_unreadable_user_table_does_not_stop_diagnosis(self) -> None:
        from src.domains.diagnostics.diagnosis import admin_languages

        class _Repo:
            async def distinct_admin_languages(self):
                raise RuntimeError("db down")

        assert await admin_languages(_Repo()) == ["en"]


class TestThePumpGeneratesOneVariantPerAdminLanguage:
    """End-to-end over `diagnose_incidents`, because the helpers being right
    proves nothing about the loop that calls them."""

    @pytest.fixture
    def wired(self, monkeypatch: pytest.MonkeyPatch) -> dict:
        from typing import Any
        from unittest.mock import AsyncMock, MagicMock
        from uuid import uuid4

        from src.domains.diagnostics import diagnosis as diag_module
        from src.domains.diagnostics.diagnosis import DiagnosisOutput

        state: dict[str, Any] = {
            "spent": 0.0,
            "stored": [],
            "prompts": [],
            "language_queries": 0,
            "admin_languages": ["fr", "de"],
        }

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=lambda _k: str(state["spent"]))
        redis.incrbyfloat = AsyncMock(
            side_effect=lambda _k, amount: state.__setitem__("spent", state["spent"] + amount)
        )
        redis.expire = AsyncMock()

        async def fake_invoke(
            llm: Any, system: str, human: str
        ) -> tuple[DiagnosisOutput, int, int]:
            state["prompts"].append(system)
            return (
                DiagnosisOutput(
                    diagnosis=f"diagnosis::{len(state['prompts'])}",
                    probable_cause="cause",
                    recommended_actions=["act", "act2", "act3", "act4", "act5", "act6"],
                ),
                100,
                50,
            )

        class _Repo:
            def __init__(self, db: Any) -> None: ...

            async def distinct_admin_languages(self) -> list[str]:
                state["language_queries"] += 1
                return list(state["admin_languages"])

            async def store_diagnosis(self, incident_id: Any, payload: dict) -> None:
                state["stored"].append(payload)

        incident = MagicMock()
        incident.id = uuid4()
        incident.correlation_key = "RedisDown"
        incident.alertname = "RedisDown"
        incident.severity = "critical"
        incident.title = "Redis is down"
        incident.evidence = {"check_id": "redis", "value": 1.0, "warn": 0.5, "crit": 0.9}
        state["incident"] = incident

        monkeypatch.setattr(diag_module, "get_redis_cache", AsyncMock(return_value=redis))
        monkeypatch.setattr(diag_module, "_invoke_diagnostician", fake_invoke)
        monkeypatch.setattr(diag_module, "get_llm", lambda *_a, **_k: MagicMock())
        monkeypatch.setattr(diag_module, "DiagnosticsRepository", _Repo)
        monkeypatch.setattr(diag_module, "get_cached_cost_usd_eur", lambda *a, **k: (0.01, 0.009))
        monkeypatch.setattr(diag_module.settings, "diagnostics_diagnosis_daily_cost_cap_usd", 1.0)
        # A unit test never reaches Prometheus or Loki: canned evidence pack.
        monkeypatch.setattr(
            diag_module, "collect_diagnosis_context", AsyncMock(return_value=_CANNED_PACK)
        )
        state["module"] = diag_module
        return state

    async def _run(self, wired: dict) -> int:
        from unittest.mock import MagicMock

        return await wired["module"].diagnose_incidents(
            [wired["incident"]],
            db=MagicMock(),
            system_prompt="Write in {language}, technical prose.",
        )

    async def test_one_llm_call_per_language_and_both_variants_stored(self, wired: dict) -> None:
        assert await self._run(wired) == 1
        # The model was asked twice, each time in a NAMED language — not once
        # with a list, which is how a single answer ends up half-translated.
        assert len(wired["prompts"]) == 2
        # Sorted, so the order is deterministic run to run: "de" then "fr".
        assert "German" in wired["prompts"][0]
        assert "French" in wired["prompts"][1]
        assert "{language}" not in wired["prompts"][0]

        stored = wired["stored"][0]
        assert set(stored["by_language"]) == {"fr", "de"}
        assert stored["by_language"]["de"]["diagnosis"] == "diagnosis::1"
        assert stored["by_language"]["fr"]["diagnosis"] == "diagnosis::2"

    async def test_the_flat_keys_stay_readable_by_every_existing_reader(self, wired: dict) -> None:
        """An old client, and the list endpoint, read the flat keys."""
        await self._run(wired)
        stored = wired["stored"][0]
        assert stored["diagnosis"] == stored["by_language"]["de"]["diagnosis"]
        assert stored["language"] == "de"  # admin_languages sorts; "de" < "fr"
        assert stored["probable_cause"] and stored["diagnosed_at"]

    async def test_the_action_cap_applies_to_every_language_not_just_the_first(
        self, wired: dict
    ) -> None:
        cap = wired["module"].settings.diagnostics_diagnosis_max_actions
        await self._run(wired)
        for variant in wired["stored"][0]["by_language"].values():
            assert len(variant["recommended_actions"]) == cap

    async def test_the_admin_population_is_queried_once_per_batch(self, wired: dict) -> None:
        from unittest.mock import MagicMock

        await wired["module"].diagnose_incidents(
            [wired["incident"], wired["incident"], wired["incident"]],
            db=MagicMock(),
            system_prompt="Write in {language}.",
        )
        assert wired["language_queries"] == 1

    async def test_an_exhausted_budget_queries_nobody(self, wired: dict) -> None:
        """Resolved lazily: a tick that will produce nothing must not spend a
        query on deciding in which language to produce it."""
        wired["spent"] = 5.0  # over the 1.0 cap
        assert await self._run(wired) == 0
        assert wired["language_queries"] == 0
        assert wired["prompts"] == []


class TestLocaleVariantsGoThroughTheOneChokepoint:
    """`User.language` is read raw, and raw locales come in variants.

    Two admins spelling French `fr` and `fr-FR` would be two languages: the
    tick pays for the same diagnosis twice, then hands each reader only the
    spelling that happened to match theirs. And Chinese has two canonical codes
    by layer — `zh-CN` in the backend — so a table keyed on anything else is
    the recurring bug this repository has a chokepoint for.
    """

    async def test_variants_of_one_language_collapse_to_one_generation(self) -> None:
        from src.domains.diagnostics.diagnosis import admin_languages

        class _Repo:
            async def distinct_admin_languages(self) -> list[str]:
                return ["fr", "fr-FR", "fr_FR"]

        assert await admin_languages(_Repo()) == ["fr"]

    async def test_chinese_variants_land_on_the_backend_canonical_code(self) -> None:
        from src.domains.diagnostics.diagnosis import admin_languages

        class _Repo:
            async def distinct_admin_languages(self) -> list[str]:
                return ["zh", "zh_CN", "zh-CN"]

        assert await admin_languages(_Repo()) == ["zh-CN"]

    def test_a_reader_with_a_raw_locale_still_finds_their_variant(self) -> None:
        """Normalised on BOTH sides, or the lookup is a coin toss."""
        from src.domains.diagnostics.diagnosis import diagnosis_for_language

        stored = {
            "language": "en",
            "diagnosis": "English",
            "by_language": {"zh-CN": {"diagnosis": "中文诊断"}},
        }
        for reader in ("zh", "zh_CN", "zh-CN"):
            resolved = diagnosis_for_language(stored, reader)
            assert resolved is not None
            assert resolved["diagnosis"] == "中文诊断"
            assert resolved["language"] == "zh-CN"


class TestTheDailyCapGatesEveryCallNotEveryIncident:
    """One incident now costs one LLM call per admin language.

    Gating once per incident would let a single incident overshoot the daily cap
    by every language after the first — and this module's contract is that the
    cap gates BEFORE any LLM call, not before most of them.
    """

    @pytest.fixture
    def wired(self, monkeypatch: pytest.MonkeyPatch) -> dict:
        from typing import Any
        from unittest.mock import AsyncMock, MagicMock
        from uuid import uuid4

        from src.domains.diagnostics import diagnosis as diag_module
        from src.domains.diagnostics.diagnosis import DiagnosisOutput

        state: dict[str, Any] = {"spent": 0.0, "calls": 0, "stored": []}

        async def fake_spent(_key: str) -> float:
            return float(state["spent"])

        async def fake_record(_key: str, cost: float) -> None:
            state["spent"] += cost

        async def fake_invoke(*_a: Any) -> tuple[DiagnosisOutput, int, int]:
            state["calls"] += 1
            return (
                DiagnosisOutput(diagnosis="d", probable_cause="c", recommended_actions=[]),
                10,
                5,
            )

        class _Repo:
            def __init__(self, db: Any) -> None: ...

            async def distinct_admin_languages(self) -> list[str]:
                return ["de", "en", "es", "fr", "it"]

            async def store_diagnosis(self, _id: Any, payload: dict) -> None:
                state["stored"].append(payload)

        incident = MagicMock()
        incident.id = uuid4()
        incident.correlation_key = "RedisDown"
        incident.alertname = "RedisDown"
        incident.evidence = {}
        state["incident"] = incident

        monkeypatch.setattr(diag_module, "_spent_today", fake_spent)
        monkeypatch.setattr(diag_module, "_record_spend", fake_record)
        monkeypatch.setattr(diag_module, "_invoke_diagnostician", fake_invoke)
        monkeypatch.setattr(diag_module, "get_llm", lambda *_a, **_k: MagicMock())
        monkeypatch.setattr(diag_module, "DiagnosticsRepository", _Repo)
        # Each call costs a quarter of the cap: the third must not happen.
        monkeypatch.setattr(diag_module, "get_cached_cost_usd_eur", lambda *a, **k: (0.25, 0.22))
        monkeypatch.setattr(diag_module.settings, "diagnostics_diagnosis_daily_cost_cap_usd", 0.5)
        monkeypatch.setattr(diag_module, "get_redis_cache", AsyncMock())
        monkeypatch.setattr(
            diag_module, "collect_diagnosis_context", AsyncMock(return_value=_CANNED_PACK)
        )
        state["module"] = diag_module
        return state

    async def test_the_cap_stops_the_languages_of_a_single_incident(self, wired: dict) -> None:
        from unittest.mock import MagicMock

        await wired["module"].diagnose_incidents(
            [wired["incident"]], db=MagicMock(), system_prompt="Write in {language}."
        )
        # Five languages were on offer; the budget paid for exactly two.
        assert wired["calls"] == 2
        assert wired["spent"] == pytest.approx(0.5)

    async def test_the_languages_that_did_run_are_still_stored(self, wired: dict) -> None:
        """A partial set beats nothing: two admins get their language, and the
        incident is not left NULL to be paid for again tomorrow."""
        from unittest.mock import MagicMock

        await wired["module"].diagnose_incidents(
            [wired["incident"]], db=MagicMock(), system_prompt="Write in {language}."
        )
        stored = wired["stored"][0]
        assert set(stored["by_language"]) == {"de", "en"}
        assert stored["language"] == "de"
