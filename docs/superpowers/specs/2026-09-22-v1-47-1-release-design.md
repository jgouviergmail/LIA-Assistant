# LIA v1.47.1 — release design

**Date:** 2026-09-22
**Scope:** the 221 files already staged on `main` at `v1.47.0`, plus the release-specific code, documentation, editorial and verification changes described here.
**Status:** design and autonomous execution approved in chat.

## Goal and editorial contract

Ship an installable, verified v1.47.1 and explain its real user value consistently across the public site, the application, the README and documentation. The public pages address prospective non-specialists: they must be clear, balanced, attractive and credible. Story, Philosophy/Why and Technical/How present durable capabilities and design choices, never an incident log or a detailed bug chronology. The changelogs alone enumerate release changes.

This release's candidate themes come from the staged implementation: grouped Google/Microsoft OAuth consent and reconnection; a more contextual expressive companion; tool/skill selection and execution corrections; and reliability/security fixes. A theme is published only where current code, tests and relevant ADRs support its exact claim. The README and landing should explain what a person can do, how consent and approval work, and what remains under their control. Technical detail lives behind links or in the Technical page.

## Source of truth and claim discipline

1. Treat current code, tests, migrations, Compose and installer behavior as authority. ADRs and docs explain intent but do not prove the current build. Preserve the existing staged work and review its diff before extending it.
2. Use `task release:bump -- 1.47.1` for mechanical version surfaces. Write the CHANGELOG, README release theme and FAQ changelog by hand. Give the landing release entry its true publication date and time; do not invent a deployment timestamp in advance.
3. Recount public metrics from their declared source (`LANDING_STATS` comments, registered tools/agents/metrics, collected tests, ADR files and CHANGELOG entries). Round down where the metric's contract requires it. Reconcile every duplicate in README, public guides, blog, FAQ, structured data and `llms.txt`. Do not restate a stale count merely to make pages agree.
4. Distinguish implemented interoperability and design standards (for example MCP, plugin interfaces, OAuth/PKCE, accessibility practices) from formal certification. Describe GDPR/RGPD and EU AI Act measures only to the precision justified by current product behavior and authoritative legal sources; do not claim blanket legal compliance or certification. The published technical audit excludes security, so its 8.3/10 score cannot be presented as a security score.
5. Maintain all six application and landing locales (`en`, `fr`, `de`, `es`, `it`, `zh`). Keep section numbering, FAQ references, translated accessible names and key parity. When content is not relevant to end users or administrators, keep it in technical docs rather than the FAQ or public copy.

## Content surfaces

- `README.md`, `CHANGELOG.md`, release/version surfaces, `docs/GETTING_STARTED.md`, affected `docs/technical/`, `docs/guides/`, `docs/knowledge/`, and documentation indexes: update only claims touched by implemented changes. Generate `AGENTS.md` from `CLAUDE.md` if the latter changes.
- Application FAQ and its changelog in `apps/web/locales/{en,fr,de,es,it,zh}/translation.json`, their wiring in `apps/web/src/components/faq/`, the settings search lexicon, and the knowledge files: add end-user/admin answers with stable numbering and source-aligned text. Balance the length of the “How LIA works” explanations where touched.
- Public landing home, Philosophy/Why, Technical/How, Story, More, blog, public FAQ, New and history pages: place new capabilities where they answer a visitor's question, refresh metrics everywhere, and keep the narrative pages timeless. Animation, if justified, must respect reduced motion and existing accessibility rules.
- Review existing blog articles for factual drift; do not insert the release note into every article. The authenticated FAQ URL is not publicly accessible to the read-only web tool, so verify its local source and tests, then confirm in the deployed application if access permits.

## Self-host installation decision

Diff the release against v1.47.0 for mandatory settings/default changes, optional integrations, Compose services, seeds and boot changes. Edit `scripts/install/envgen.py`, `questions.py`, `compose.py`, `deploy.py`, `.env.min.prod.example` and the installation guide only when the corresponding case is real. Grouped OAuth needs careful migration and configuration review; it must not silently make an optional provider mandatory. The read-only defaults-to-`Settings` contract and `task test:install` must pass before tagging. Also run the larger hermetic installer gate and Compose matrix where the change warrants them.

## Verification and publication

Before commit: inspect `git diff --check`, staged and unstaged status; run targeted tests for changed behavior and content, `task lint:i18n`, documentation preview/index checks, `task release:check`, `task test:install`, the defaults-to-`Settings` guard, `task ci:fast`, and the relevant service/browser gates from `task ci` where applicable. Fix all findings introduced or exposed by this release, without ratchet relaxation or `--no-verify`. Record exact commands, counts and any residual warnings. A sandbox-only Git configuration warning is not evidence of a product defect; determine its cause before changing project files.

After green gates: commit the reviewed release content and staged implementation, push, run `task deploy:prod`, then `task demo:prod:down`, `task demo:prod:up`, `task demo:prod:verify` in that order. Verify production readiness, public pages, application FAQ and observability before creating/pushing tag `v1.47.1` and publishing the release with a concise human-facing summary. Do not infer deployment success from a disconnected SSH session; inspect remote state. Preserve rollback ability to the previously deployed image/commit and stop publication if installation, readiness, demo isolation, critical user flows or monitoring fail.

## Acceptance criteria

- Every public or user-facing claim can be traced to current code, test, metric source or authoritative standard; no unsupported compliance or certification claim.
- Six-locale parity and section/FAQ numbering checks pass; the public narrative is understandable without reading the changelog.
- Mechanical version surfaces and all release references say v1.47.1; published date/time reflects actual publication.
- A fresh self-host install remains possible; installer tests and defaults-to-`Settings` guard are green before the tag.
- Required CI, deployment, demonstrator and production verification produce fresh passing evidence, with no ignored warning or skipped hook.
