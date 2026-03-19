# Sub-Agents

## What are sub-agents?
Sub-agents are **specialized ephemeral assistants** that the principal LIA assistant can delegate tasks to. When your request requires deep research, multi-source analysis, or specialized expertise, the assistant can spawn one or more experts to work in parallel.Sub-agents are **invisible** — you interact only with the principal assistant, which synthesizes their findings into a natural response.

## When does LIA use sub-agents?
LIA decides to call on experts when:Your request involves **parallel research** across several areas (e.g., comparing transport options)A topic benefits from **deep specialized analysis** (e.g., technical audit, market research)Multiple independent **expert viewpoints** are needed at the same timeSimple questions are always handled directly — experts are only called in when they add real value.**You stay in control:** before launching the experts, LIA asks for your confirmation. If you decline, it automatically switches to a standard plan without sub-agents.**Tip:** you can also explicitly ask LIA to use experts, for example: *"Use specialized experts to handle my request"*.

## Can I disable sub-agents?
Yes. Go to **Settings > Features > Sub-Agents** and toggle the switch off. The assistant will then use direct tools (web search, etc.) instead of delegating.

## Do sub-agents cost more tokens?
Yes — each sub-agent performs its own LLM calls (planning + tool execution + synthesis). A delegation with 3 experts can cost 3-5x more tokens than a single direct search.Token guard-rails are in place: per-execution budget, daily budget per user, and auto-disable after consecutive failures. All sub-agent costs are tracked and visible in your usage statistics.
