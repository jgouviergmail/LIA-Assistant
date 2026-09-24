"""Guard for the living maps (``scripts/audit/doc_maps.py``).

The maps are only worth keeping if they cannot drift in silence: an ADR, a
backend domain or an infrastructure module landing without its entry must fail,
and so must a unit of text missing from a language of the site or translated
from a French sentence that has since changed. These tests pin that contract on
a synthetic tree (so each rule is proven to BITE), then run the real check on
the repository, as ``task lint:docs`` does.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "audit" / "doc_maps.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("doc_maps", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["doc_maps"] = module
    spec.loader.exec_module(module)
    return module


doc_maps = _load_module()


def _tree(files: set[str]) -> object:
    dirs: set[str] = set()
    for f in files:
        parts = f.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
    return doc_maps.Tree(root=REPO_ROOT, files=frozenset(files), dirs=frozenset(dirs))


FR_TEXT = {
    "functional": {
        "intro": {"lede": "Ce que LIA sait faire, brique par brique."},
        "groups": {"g.a": {"name": "A", "summary": "Une famille."}},
        "bricks": {"f.one": {"name": "Un", "role": "Le rôle de la brique.", "goal": "Son but."}},
        "flows": {
            "flow.x": {
                "name": "Un parcours",
                "summary": "Deux étapes.",
                "steps": ["Première étape.", "Seconde étape."],
            }
        },
    },
    "technical": {
        "intro": {"lede": "Comment LIA est construite."},
        "layers": {"l.a": {"name": "Couche", "summary": "Une couche."}},
        "bricks": {"t.one": {"name": "Cache", "role": "Retenir.", "stack": ["Redis 7"]}},
        "flows": {},
    },
    "history": {
        "intro": {"lede": "Chaque décision."},
        "themes": {"platform": {"name": "Plateforme", "summary": "Livrer."}},
        "eras": {"first": {"name": "Les débuts", "summary": "Le commencement."}},
        "entries": {"1": {"title": "Un titre", "summary": "Une décision racontée simplement."}},
    },
}

EN_WORDS = {
    "Ce que LIA sait faire, brique par brique.": "What LIA can do, block by block.",
    "Une famille.": "A family.",
    "Un": "One",
    "Le rôle de la brique.": "The role of the block.",
    "Son but.": "Its goal.",
    "Un parcours": "A journey",
    "Deux étapes.": "Two steps.",
    "Première étape.": "First step.",
    "Seconde étape.": "Second step.",
    "Comment LIA est construite.": "How LIA is built.",
    "Couche": "Layer",
    "Une couche.": "A layer.",
    "Retenir.": "Remember.",
    "Chaque décision.": "Every decision.",
    "Plateforme": "Platform",
    "Livrer.": "Ship.",
    "Les débuts": "The start",
    "Le commencement.": "The beginning.",
    "Un titre": "A title",
    "Une décision racontée simplement.": "A decision told plainly.",
}


def _translate(unit: object) -> object:
    if isinstance(unit, dict):
        return {k: _translate(v) for k, v in unit.items()}
    if isinstance(unit, list):
        return [_translate(v) for v in unit]
    return EN_WORDS.get(unit, unit) if isinstance(unit, str) else unit


def _maps(stamped: bool = True) -> object:
    functional = {
        "groups": [{"id": "g.a", "icon": "brain", "tone": "blue"}],
        "bricks": [
            {
                "id": "f.one",
                "group": "g.a",
                "icon": "brain",
                "domains": ["alpha"],
                "surfaces": [],
                "deps": [],
            }
        ],
        "flows": [{"id": "flow.x", "icon": "send", "steps": ["f.one", "f.one"]}],
    }
    technical = {
        "repo": "https://example.test/",
        "layers": [{"id": "l.a", "icon": "cpu", "tone": "amber"}],
        "bricks": [
            {
                "id": "t.one",
                "layer": "l.a",
                "icon": "cpu",
                "paths": ["apps/api/src/infrastructure/cache"],
                "infra": ["cache"],
                "deps": [],
            }
        ],
        "flows": [],
    }
    history = {
        "themes": [{"id": "platform", "icon": "rocket", "tone": "slate"}],
        "eras": [{"id": "first", "from": "2026-01-01", "to": None}],
        "entries": [
            {
                "adr": 1,
                "date": "2026-01-02",
                "theme": "platform",
                "functional": ["f.one"],
                "technical": ["t.one"],
            }
        ],
    }
    fr = copy.deepcopy(FR_TEXT)
    en = _translate(copy.deepcopy(FR_TEXT))
    maps = doc_maps.Maps(functional, technical, history, {"fr": fr, "en": en}, {})
    if stamped:
        source = doc_maps.text_units(maps, "fr")
        for key, unit in doc_maps.text_units(maps, "en").items():
            if unit is not None:
                unit[doc_maps.FINGERPRINT] = doc_maps.fingerprint(source[key])
    icons = {n: [] for n in doc_maps.referenced_icons(maps)}
    return doc_maps.Maps(functional, technical, history, {"fr": fr, "en": en}, icons)


BASE_FILES = {
    "apps/api/src/domains/alpha/__init__.py",
    "apps/api/src/infrastructure/cache/__init__.py",
    "docs/architecture/ADR-001-First.md",
    "apps/web/locales/fr/translation.json",
    "apps/web/locales/en/translation.json",
}


def _findings(maps: object, files: set[str] = BASE_FILES) -> list[str]:
    return doc_maps.check_all(maps, _tree(files))


@pytest.mark.unit
class TestTheMapsCannotDriftInSilence:
    def test_a_consistent_tree_has_no_finding(self) -> None:
        assert _findings(_maps()) == []

    def test_an_adr_without_an_entry_is_a_finding(self) -> None:
        problems = _findings(_maps(), BASE_FILES | {"docs/architecture/ADR-002-Second.md"})
        assert any("ADR-002" in p and "no entry" in p for p in problems)

    def test_a_backend_domain_nobody_claims_is_a_finding(self) -> None:
        problems = _findings(_maps(), BASE_FILES | {"apps/api/src/domains/beta/service.py"})
        assert any("backend domain beta" in p for p in problems)

    def test_an_infrastructure_module_nobody_claims_is_a_finding(self) -> None:
        problems = _findings(_maps(), BASE_FILES | {"apps/api/src/infrastructure/fresh.py"})
        assert any("infrastructure module fresh" in p for p in problems)

    def test_a_path_that_does_not_exist_is_a_finding(self) -> None:
        maps = _maps()
        maps.technical["bricks"][0]["paths"].append("apps/api/src/gone.py")
        assert any("apps/api/src/gone.py" in p for p in _findings(maps))

    def test_an_unknown_brick_in_the_history_is_a_finding(self) -> None:
        maps = _maps()
        maps.history["entries"][0]["functional"].append("f.missing")
        assert any("f.missing" in p for p in _findings(maps))

    def test_an_entry_without_a_file_must_say_why(self) -> None:
        maps = _maps()
        maps.history["entries"].append(
            {
                "adr": 8,
                "date": "2026-01-03",
                "theme": "platform",
                "functional": ["f.one"],
                "technical": [],
            }
        )
        for lang in ("fr", "en"):
            maps.text[lang]["history"]["entries"]["8"] = copy.deepcopy(
                maps.text[lang]["history"]["entries"]["1"]
            )
        assert any("ADR-008" in p and "nofile" in p for p in _findings(maps))
        maps.history["entries"][-1]["nofile"] = "Documented in the ADR index."
        assert _findings(maps) == []

    def test_a_dependency_on_an_unknown_brick_is_a_finding(self) -> None:
        maps = _maps()
        maps.functional["bricks"][0]["deps"].append("f.ghost")
        assert any("f.ghost" in p for p in _findings(maps))


@pytest.mark.unit
class TestEveryLanguageSaysTheSameThing:
    def test_a_unit_missing_from_a_language_is_a_finding(self) -> None:
        maps = _maps()
        del maps.text["en"]["functional"]["bricks"]["f.one"]
        assert "text en: functional/bricks/f.one is missing" in _findings(maps)

    def test_a_language_of_the_site_without_its_files_is_a_finding(self) -> None:
        problems = _findings(_maps(), BASE_FILES | {"apps/web/locales/de/translation.json"})
        assert any("functional.de.json is missing" in p for p in problems)

    def test_text_for_no_language_of_the_site_is_a_finding(self) -> None:
        maps = _maps()
        maps.text["xx"] = copy.deepcopy(maps.text["en"])
        assert "text: xx has map text but is no language of the site" in _findings(maps)

    def test_a_translation_of_a_french_sentence_that_changed_is_stale(self) -> None:
        maps = _maps()
        maps.text["fr"]["history"]["entries"]["1"]["summary"] = "Une décision réécrite depuis."
        problems = _findings(maps)
        assert any("history/entries/1 is stale" in p for p in problems)

    def test_a_translation_never_stamped_is_a_finding(self) -> None:
        maps = _maps(stamped=False)
        assert any("carries no fingerprint" in p for p in _findings(maps))

    def test_a_copied_french_sentence_is_no_translation(self) -> None:
        maps = _maps()
        fr_role = maps.text["fr"]["functional"]["bricks"]["f.one"]["role"]
        long_role = fr_role + " Et une phrase assez longue pour compter."
        maps.text["fr"]["functional"]["bricks"]["f.one"]["role"] = long_role
        maps.text["en"]["functional"]["bricks"]["f.one"]["role"] = long_role
        problems = _findings(maps)
        assert any("f.one role is the French text" in p for p in problems)

    def test_a_journey_must_keep_one_sentence_per_step(self) -> None:
        maps = _maps()
        maps.text["en"]["functional"]["flows"]["flow.x"]["steps"].append("A third step.")
        assert any("lists 3 steps, the source 2" in p for p in _findings(maps))

    def test_the_source_carries_no_fingerprint_and_no_unknown_field(self) -> None:
        maps = _maps()
        maps.text["fr"]["history"]["themes"]["platform"]["src"] = "abc"
        maps.text["en"]["history"]["themes"]["platform"]["tagline"] = "x"
        problems = _findings(maps)
        assert "text fr: history/themes/platform has an unknown field 'src'" in problems
        assert "text en: history/themes/platform has an unknown field 'tagline'" in problems

    def test_an_orphan_unit_names_nothing_in_the_structure(self) -> None:
        maps = _maps()
        maps.text["en"]["history"]["entries"]["99"] = {"title": "t", "summary": "s"}
        assert any("history/entries/99 names nothing" in p for p in _findings(maps))


@pytest.mark.unit
class TestStamping:
    def _write(self, maps: object, data_dir: Path) -> None:
        for lang, docs in maps.text.items():
            for name, doc in docs.items():
                doc_maps.write_json(data_dir / "text" / f"{name}.{lang}.json", doc)

    def test_a_first_translation_is_stamped_a_stale_one_only_on_request(
        self, tmp_path: Path
    ) -> None:
        maps = _maps(stamped=False)
        self._write(maps, tmp_path)
        stamped = doc_maps.stamp_translations(maps, tmp_path, [])
        assert "en:history/entries/1" in stamped
        assert _findings(maps) == []

        maps.text["fr"]["history"]["entries"]["1"]["summary"] = "Une décision réécrite depuis."
        assert doc_maps.stamp_translations(maps, tmp_path, []) == []
        assert any("is stale" in p for p in _findings(maps))

        assert doc_maps.stamp_translations(maps, tmp_path, ["history/entries/1"]) == [
            "en:history/entries/1"
        ]
        assert _findings(maps) == []
        written = json.loads((tmp_path / "text" / "history.en.json").read_text(encoding="utf-8"))
        assert written["entries"]["1"]["src"] == doc_maps.fingerprint(
            maps.text["fr"]["history"]["entries"]["1"]
        )


@pytest.mark.unit
class TestTheDataFilesStayAsPrettierWritesThem:
    def test_short_lists_stay_inline_long_ones_break_objects_expand(self) -> None:
        text = doc_maps.dump_json({"a": ["x", "y"], "b": {"c": 1}, "d": ["w" * 60, "z" * 60]})
        assert text == (
            "{\n"
            '  "a": ["x", "y"],\n'
            '  "b": {\n'
            '    "c": 1\n'
            "  },\n"
            '  "d": [\n'
            f'    "{"w" * 60}",\n'
            f'    "{"z" * 60}"\n'
            "  ]\n"
            "}\n"
        )

    def test_wide_characters_count_twice_in_the_line_width(self) -> None:
        # 45 CJK characters are 90 columns: with the key they no longer fit 100.
        text = doc_maps.dump_json({"stack": ["模" * 45]})
        assert text.startswith('{\n  "stack": [\n')


@pytest.mark.unit
def test_the_repository_maps_are_true_and_up_to_date() -> None:
    """The real maps: every ADR, domain and module claimed, every language, files as rendered."""
    tree = doc_maps.load_tree(REPO_ROOT, include_unstaged=False)
    data_dir = REPO_ROOT / doc_maps.DATA_DIR
    docs_dir = REPO_ROOT / doc_maps.DOCS_DIR
    maps = doc_maps.load_maps(data_dir, docs_dir / "templates" / "icons.json")
    assert doc_maps.check_all(maps, tree) == []
    facts = json.loads((data_dir / "facts.json").read_text(encoding="utf-8"))
    assert facts == doc_maps.site_facts(tree)
    for page, spec in doc_maps.PAGES.items():
        rendered = doc_maps.render(page, maps, tree, docs_dir)
        assert (docs_dir / spec["file"]).read_text(encoding="utf-8") == rendered, spec["file"]
