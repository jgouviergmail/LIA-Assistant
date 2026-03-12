<!--
Pull Request Template - LIA
Thank you for contributing to LIA! Please fill in the sections below to facilitate the review.
Delete non-applicable sections and <!-- --> comments before submitting.
-->

## 📝 Description

<!--
Clearly describe the changes in this PR.
What? Why? How?
-->

### Motivation and Context

<!-- What problem does this PR solve? -->

Closes #(issue-number)
<!-- or -->
Related to #(issue-number)

### Summary of Changes

<!-- Bullet list of the main changes -->

-
-
-

---

## 🏷️ Type of Change

<!-- Check the applicable boxes with [x] -->

- [ ] 🐛 **Bug fix** (non-breaking change that fixes an issue)
- [ ] ✨ **New feature** (non-breaking change that adds functionality)
- [ ] 💥 **Breaking change** (change that breaks backward compatibility)
- [ ] 📝 **Documentation** (documentation update only)
- [ ] ♻️ **Refactoring** (refactoring with no behavior change)
- [ ] ⚡ **Performance** (performance optimization)
- [ ] 🔒 **Security** (security improvement)
- [ ] 🧪 **Tests** (adding or modifying tests only)
- [ ] 🔧 **Chore** (maintenance, dependencies, config)

---

## 🎯 Impacted Domain(s)

<!-- Check the relevant DDD domains -->

- [ ] **agents** - LangGraph multi-agent orchestration
- [ ] **auth** - Authentication/Authorization (BFF Pattern)
- [ ] **connectors** - OAuth connectors (Google Contacts, etc.)
- [ ] **conversations** - Conversation management
- [ ] **llm** - LLM providers & pricing
- [ ] **users** - User management
- [ ] **observability** - Metrics, Logs, Traces
- [ ] **security** - Security (PII filtering, rate limiting, etc.)
- [ ] **infrastructure** - Database, Redis, cache
- [ ] **frontend** - React/TypeScript UI
- [ ] **ci/cd** - GitHub Actions workflows
- [ ] **documentation** - Docs, guides, ADRs

---

## ✅ Checklist

### Code Quality

- [ ] My code follows the **project conventions** (see [CONTRIBUTING.md](../CONTRIBUTING.md))
- [ ] I have performed a **self-review** of my code
- [ ] I have added **comments** for complex parts of the code
- [ ] My changes do not generate **any new warnings** (linter, type checker)
- [ ] I have verified that my code complies with **OWASP Top 10** (if applicable)

### Tests

- [ ] I have added **tests** covering my changes
- [ ] All **existing tests** pass locally (`pytest` backend, `pnpm test` frontend)
- [ ] **Test coverage** is maintained or improved (>=80%)
- [ ] I have tested **locally** with the full environment (PostgreSQL + Redis)

### Documentation

- [ ] I have updated the **technical documentation** (if applicable)
  - [ ] Google style docstrings (Python)
  - [ ] JSDoc comments (TypeScript)
  - [ ] Domain README.md
- [ ] I have updated the **user guides** (if applicable)
- [ ] I have created/updated an **ADR** (Architecture Decision Record) if an architectural decision was made
- [ ] I have updated the **CHANGELOG.md** (if feature/breaking change)

### CI/CD

- [ ] All **CI checks** pass (lint, tests, security scan)
- [ ] I have verified that my changes do not **break the build**
- [ ] **Database migrations** (if applicable) are reversible (`alembic downgrade`)
- [ ] New **environment variables** are documented in `.env.example`

### Security

- [ ] No **plaintext secrets** (passwords, API keys, tokens)
- [ ] No **PII** (Personal Identifiable Information) logged without masking
- [ ] **Input validation** with Pydantic (backend) or Zod (frontend)
- [ ] **Rate limiting** added if new public endpoint
- [ ] **Authentication/Authorization** verified if protected endpoint
- [ ] I have checked **OWASP dependencies** (no known CVEs)

---

## 🧪 Tests

### Tests Added/Modified

<!-- Describe the tests added or modified -->

**Unit tests**:
-
-

**Integration tests**:
-
-

**E2E tests** (if applicable):
-
-

### How to Test

<!-- Steps to manually test this PR (if applicable) -->

1.
2.
3.

### Coverage Report

<!--
Paste the output of `pytest --cov=src --cov-report=term-missing` (backend)
or `pnpm test:coverage` (frontend)
-->

```
# Example:
---------- coverage: platform linux, python 3.12.1-final-0 -----------
Name                                    Stmts   Miss  Cover   Missing
---------------------------------------------------------------------
src/domains/agents/service.py             120      5    96%   45-47, 89, 112
src/domains/agents/registry.py            85      0   100%
---------------------------------------------------------------------
TOTAL                                    4523    215    95%
```

---

## 📊 Performance

<!-- If performance changes (optimizations or potential regressions) -->

### Benchmarks

<!-- Benchmark results (before/after) -->

**Before**:
-

**After**:
-

**Improvement**:
-

### Memory Impact

<!-- If impact on memory usage -->

-

---

## 📸 Screenshots / Videos

<!-- If UI/UX changes, add screenshots or GIFs -->

### Before

<!-- Screenshot before the changes -->

### After

<!-- Screenshot after the changes -->

---

## 💥 Breaking Changes

<!-- If Breaking Change (backward compatibility breakage), fill in this section -->

### What breaks?

<!-- Description of breaking changes -->

### Migration Path

<!-- How should users migrate? -->

**Migration steps**:
1.
2.
3.

**Code example** (before -> after):

```python
# ❌ Before (deprecated)


# ✅ After (new)

```

### Migration Guide

<!-- Link to detailed migration guide if applicable -->

See: [docs/migrations/MIGRATION_vX.X.X.md](../docs/migrations/)

---

## 🔗 Dependencies

### Related PRs

<!-- Link to other PRs that must be merged before/after this one -->

**Must be merged before**:
-

**Must be merged after**:
-

### Related Issues

<!-- Issues that will be closed or impacted by this PR -->

**Closes**:
- Closes #

**Related**:
- Related to #

---

## 📝 Notes for Reviewers

<!-- Additional information to facilitate the review -->

### Specific Points of Attention

<!-- Parts of the code requiring special attention -->

-
-

### Architectural Decisions

<!-- Important decisions made in this PR -->

-
-

### Open Questions

<!-- Questions/doubts you have about your implementation -->

-
-

### Additional Context

<!-- Other useful context for understanding this PR -->

-

---

## 🚀 Deployment Notes

<!-- If this PR requires special actions at deployment -->

### Pre-deployment Steps

<!-- Actions to take BEFORE deployment -->

- [ ]
- [ ]

### Post-deployment Steps

<!-- Actions to take AFTER deployment -->

- [ ]
- [ ]

### Configuration Changes

<!-- New environment variables or config changes -->

**New environment variables**:
```bash
# .env
NEW_VAR_NAME=default_value  # Description
```

**External services**:
-
-

---

## 📋 Reviewers Checklist

<!-- For reviewers - Do not fill in as contributor -->

<details>
<summary>Checklist for reviewers (click to expand)</summary>

### Code Review

- [ ] Code is readable and maintainable
- [ ] No duplicated code (DRY principle)
- [ ] Architectural patterns respected (DDD, SOLID)
- [ ] Appropriate error handling
- [ ] Appropriate logs (DEBUG/INFO/WARNING/ERROR level)
- [ ] No magic numbers (named constants used)

### Security Review

- [ ] No OWASP Top 10 vulnerabilities
- [ ] Complete input validation
- [ ] Output encoding/escaping
- [ ] Correct authentication/authorization
- [ ] No SQL injection (ORM used correctly)
- [ ] No plaintext secrets

### Performance Review

- [ ] No N+1 queries (SQLAlchemy eager loading)
- [ ] Appropriate database indexes
- [ ] Caching used where relevant
- [ ] No memory leaks (sessions and files properly closed)
- [ ] Async/await used correctly

### Tests Review

- [ ] Tests cover happy path + edge cases
- [ ] Unit tests are isolated (mocks used)
- [ ] Integration tests for critical flows
- [ ] Clear and specific assertions
- [ ] No flaky tests

### Documentation Review

- [ ] Complete and clear docstrings
- [ ] Technical documentation updated
- [ ] ADR created if architectural decision
- [ ] Relevant comments (not redundant)

</details>

---

## 🔍 Additional Information

### Related Documentation

<!-- Links to relevant documentation -->

- [ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [docs/technical/](../docs/technical/)
- [docs/guides/](../docs/guides/)

### References

<!-- External references (articles, RFCs, etc.) -->

-
-

---

<!--
Thank you for your contribution to LIA! 🎉

Need help?
- Check CONTRIBUTING.md: https://github.com/jgouviergmail/LIA-Assistant/blob/main/CONTRIBUTING.md
- Open a discussion: https://github.com/jgouviergmail/LIA-Assistant/discussions

Code of Conduct: https://github.com/jgouviergmail/LIA-Assistant/blob/main/CODE_OF_CONDUCT.md
-->
