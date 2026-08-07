# Code defaults vs proven production values

> **APPLIED on 2026-08-06.** Drift went from **94 to 30**, and the 30 that
> remain are legitimate: 7 kept on purpose, 2 deployment identity, 21 pure
> formatting (`0.6` vs `0.60`, Python list vs JSON, an enum member vs its
> value). Every real gap is closed.
>
> Two findings the alignment produced, both worth more than the alignment
> itself:
>
> * **The production stop budget did not fit.** The guard reads the CONSTANT,
>   not the environment, so it had been validating a 45s drain while
>   production ran 60s. Summed sequentially (20 + 60 + 15 + 5 = 100s) that
>   exceeds the 90s `stop_grace_period`: a busy instance was being SIGKILLed
>   mid-drain. `stop_grace_period` raised to 120s.
> * **`PSYCHE_AD_RELAXATION` is 0.0 in production but must not be the code
>   default.** The code documents why it ships at 0.15 (phase-2 measurements:
>   without it the model ratchets arousal up turn after turn). A deployment
>   turning a safeguard off is not a reason to ship it off.
>
> Also excluded during application, on type grounds: the telephony country
> code (`+33` is a string, not a number), `DEVOPS_SERVERS` (an operator's own
> inventory) and `DEFAULT_CURRENCY` (the enum member's value already IS the
> production value).

Compared: 968 variables from `.env.prod`.
Excluded: 35 secrets, 102 infrastructure/identity,
38 not settings at all.

**68 to align**, 7 to keep as-is, 19 pure formatting.

## To align — production is the proven value

| Variable | Code default | Production |
|---|---|---|
| `ACCOUNT_EXPORT_ENABLED` | `false` | `true` |
| `BACKGROUND_RUNS_ACTIVE_TTL_SECONDS` | `15` | `30` |
| `BACKGROUND_RUNS_DRAIN_TIMEOUT_SECONDS` | `45` | `60` |
| `BACKGROUND_RUNS_ENABLED` | `false` | `true` |
| `BACKGROUND_RUNS_HEARTBEAT_SECONDS` | `5` | `10` |
| `BACKGROUND_RUNS_STREAM_TTL_SECONDS` | `3600` | `1800` |
| `BRIEFING_MAX_BIRTHDAYS_HORIZON_DAYS` | `14` | `7` |
| `BRIEFING_MAX_BIRTHDAYS_ITEMS` | `5` | `10` |
| `BRIEFING_MAX_MAILS_ITEMS` | `5` | `10` |
| `BRIEFING_MAX_OPEN_LOOPS_ITEMS` | `3` | `10` |
| `BRIEFING_MAX_REMINDERS_ITEMS` | `5` | `10` |
| `BRIEFING_MAX_TASKS_ITEMS` | `5` | `10` |
| `BROWSER_ACCESSIBILITY_MAX_DEPTH` | `8` | `10` |
| `BROWSER_AX_TREE_MAX_TOKENS` | `15000` | `30000` |
| `BROWSER_MEMORY_LIMIT_MB` | `512` | `1024` |
| `BROWSER_PAGE_LOAD_TIMEOUT_SECONDS` | `30` | `10` |
| `BROWSER_RATE_LIMIT_READ_CALLS` | `20` | `40` |
| `BROWSER_RATE_LIMIT_WRITE_CALLS` | `20` | `40` |
| `BROWSER_REACT_MAX_ITERATIONS` | `15` | `50` |
| `BROWSER_SSRF_ENFORCE` | `false` | `true` |
| `CONTACTS_TOOL_DEFAULT_MAX_RESULTS` | `10` | `20` |
| `DEFAULT_CURRENCY` | `SupportedCurrency.USD` | `EUR` |
| `DEVOPS_SERVERS` | `[]` | `[{"name":"prod","host":"local","working_directory":"/opt/claude-workspace","description":"Local prod container — read-only investigation","allowed_claude_tools":["Read","Grep","Glob","Bash(docker logs *)","Bash(docker ps *)","Bash(docker stats --no-stream *)","Bash(docker inspect *)","Bash(docker compose * ps *)","Bash(docker compose * logs *)","Bash(docker top *)","Bash(df *)","Bash(free *)","Bash(uptime *)","Bash(journalctl *)","Bash(curl *localhost*)","Bash(ss *)","Bash(cat /proc/*)","Bash(top -bn1 *)","Bash(lsof *)"],"disallowed_claude_tools":["Edit","Write","Bash(docker restart *)","Bash(docker stop *)","Bash(docker start *)","Bash(docker rm *)","Bash(docker rmi *)","Bash(docker exec *)","Bash(docker compose * up *)","Bash(docker compose * down *)","Bash(docker compose * restart *)","Bash(docker prune *)","Bash(docker volume rm *)","Read(.env*)","Read(*secret*)","Read(*credential*)","Read(*password*)","Bash(cat *.env*)","Bash(cat *secret*)","Bash(printenv *)","Bash(env *)","Bash(rm *)","Bash(mv *)","Bash(cp *)","Bash(chmod *)","Bash(chown *)","Bash(systemctl *)","Bash(reboot *)","Bash(shutdown *)","Bash(kill *)","Bash(apt *)","Bash(pip *)","Bash(npm *)"]}]` |
| `DRIVE_TOOL_DEFAULT_MAX_RESULTS` | `10` | `20` |
| `EMAILS_BODY_MAX_LENGTH` | `500` | `20000` |
| `EMAILS_TOOL_DEFAULT_MAX_RESULTS` | `10` | `20` |
| `EMAILS_URL_SHORTEN_THRESHOLD` | `50` | `20` |
| `FIREBASE_PROJECT_ID` | `` | `compagnonnotif` |
| `GOOGLE_REDIRECT_URI` | `` | `https://lia-back.jeyswork.com/api/v1/auth/google/callback` |
| `HABITS_ENABLED` | `false` | `true` |
| `HABITS_TICK_SCORING_ENABLED` | `false` | `true` |
| `HEARTBEAT_DEPARTURE_ENABLED` | `false` | `true` |
| `HSTS_MAX_AGE` | `86400` | `2592000` |
| `HTTP_LOG_EXCLUDE_PATHS` | `['/metrics', '/health', '/ready']` | `/metrics,/health,/ready` |
| `INITIATIVE_REACT_ENABLED` | `false` | `true` |
| `MCP_MAX_SERVERS` | `10` | `20` |
| `MCP_REACT_MAX_ITERATIONS` | `10` | `50` |
| `MCP_SERVERS_CONFIG` | `{}` | `{"excalidraw":{"transport":"streamable_http","url":"https://mcp.excalidraw.com","timeout_seconds":60,"enabled":true,"hitl_required":false,"iterative_mode":true,"description":"Provides interactive hand-drawn diagram creation and sharing using Excalidraw element format. It can render streaming, animated diagrams from element definitions, upload finished diagrams to Excalidraw and return shareable URLs, and save/restore user-edited diagram states. Call the element format reference before first render."}}` |
| `MCP_USER_MAX_SERVERS_PER_USER` | `5` | `20` |
| `OPENAI_ORGANIZATION_ID` | `` | `org-OnXqR6efQ6MlqGP4A1XuFUqo` |
| `OPEN_LOOPS_ENABLED` | `false` | `true` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | `http://tempo:4317` |
| `PERPLEXITY_SEARCH_MODEL` | `sonar` | `sonar-pro` |
| `PLACES_TOOL_DEFAULT_MAX_RESULTS` | `10` | `20` |
| `PLANNER_SEMANTIC_LEAK_MODE` | `observe` | `autocorrect` |
| `PSYCHE_AD_RELAXATION` | `0.15` | `0.0` |
| `REACT_AGENT_MAX_ITERATIONS` | `15` | `90` |
| `REACT_AGENT_TIMEOUT_SECONDS` | `120` | `300` |
| `RECURRENCE_SUGGESTION_ENABLED` | `false` | `true` |
| `SEMANTIC_EXPANSION_EVIDENCE_DRIVEN_ENABLED` | `false` | `true` |
| `SESSION_COOKIE_DOMAIN` | `None` | `.jeyswork.com` |
| `SUBAGENT_DEFAULT_MAX_ITERATIONS` | `10` | `20` |
| `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED` | `3000` | `10000` |
| `SUBAGENT_RESEARCH_TOOLS_WHITELIST` | `brave_search_tool,fetch_web_page_tool` | `perplexity_search_tool,brave_search_tool,fetch_web_page_tool` |
| `SUBAGENT_TOOL_TIMEOUT_SECONDS` | `180.0` | `300.0` |
| `TASKS_TOOL_DEFAULT_MAX_RESULTS` | `10` | `20` |
| `TELEGRAM_BOT_USERNAME` | `None` | `@LIA_mybot` |
| `TELEPHONY_AGENT_LLM_MODEL` | `gpt-4o-mini` | `gpt-5.4-mini` |
| `TELEPHONY_AGENT_TTS_MODEL_ID` | `eleven_flash_v2_5` | `eleven_turbo_v2_5` |
| `TELEPHONY_AGENT_VOICE_ID` | `` | `nr2EGJNe96rzn9FRlTId` |
| `TELEPHONY_DEFAULT_COUNTRY_CODE` | `` | `+33` |
| `TOKEN_THRESHOLD_CRITICAL` | `40000` | `85000` |
| `TOKEN_THRESHOLD_MAX` | `50000` | `100000` |
| `TOKEN_THRESHOLD_SAFE` | `20000` | `50000` |
| `TOKEN_THRESHOLD_WARNING` | `30000` | `65000` |
| `V3_DISPLAY_MAX_ITEMS_PER_DOMAIN` | `5` | `10` |
| `VOICE_CHAT_MODE_MAX_SENTENCES` | `3` | `15` |
| `WEB_CONCURRENCY` | `1` | `4` |

## To keep — the default differs on purpose

| Variable | Code default | Production | Why the default stays |
|---|---|---|---|
| `APPLICATION_SMTP_FROM` | `noreply@lia-assistant.com` | `lia@jeyswork.com` | deployment identity, never a code default |
| `MFA_ENABLED` | `false` | `true` | requires an enrolment flow the operator must choose to run |
| `PEERS_ENABLED` | `false` | `true` | cross-instance federation: opt-in, needs a reachable peer |
| `PEER_CONTEXT_INJECTION_ENABLED` | `false` | `true` | follows PEERS_ENABLED |
| `PRODUCT_ANALYTICS_ENABLED` | `false` | `true` | telemetry is opt-in — a fresh install must not emit by default |
| `SESSION_COOKIE_SECURE` | `false` | `true` | true would break local development over http://localhost |
| `TELEPHONY_ENABLED` | `false` | `true` | paid outbound calls: opt-in per deployment, off on the demonstrator |

## Formatting only — same value, different spelling

`APPROVAL_AUTO_APPROVE_ROLES`, `APPROVAL_COST_THRESHOLD_USD`, `APPROVAL_SENSITIVE_CLASSIFICATIONS`, `COMPACTION_GLOBAL_TIMEOUT_SECONDS`, `COMPACTION_PER_CHUNK_TIMEOUT_SECONDS`, `HABITS_CAPTURE_MIN`, `HABITS_EXIT_CAPTURE`, `HABITS_RECENT_MIN`, `HABITS_SPARSE_ACTIVE_DAYS_MIN`, `INTEREST_CONTENT_SIMILARITY_THRESHOLD`, `MEMORY_MIN_SEARCH_SCORE`, `PLAN_PATTERN_MIN_CONF_BYPASS`, `RESPONSE_CONTEXT_PREFETCH_AWAIT_TIMEOUT_SECONDS`, `SEMANTIC_TOOL_SELECTOR_HARD_THRESHOLD`, `SEMANTIC_TOOL_SELECTOR_SOFT_THRESHOLD`, `SEMANTIC_VALIDATION_CONFIDENCE_THRESHOLD`, `SUPPORTED_LANGUAGES`, `TOOL_EMBEDDINGS_CACHE_CLAIM_TIMEOUT_SECONDS`, `V3_DOMAIN_SECONDARY_THRESHOLD`
