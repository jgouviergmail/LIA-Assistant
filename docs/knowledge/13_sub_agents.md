# Sub-Agents

## What are sub-agents?
Sub-agents are **specialized ephemeral assistants** that the principal LIA assistant can delegate tasks to. When your request requires deep research, multi-source analysis, or specialized expertise, the assistant can spawn one or more experts to work in parallel.

**🤖 Two modes of operation:**
• **Automatic delegation**: During a conversation, LIA decides to delegate when a task benefits from parallel expert work. LIA asks for your confirmation before launching experts.
• **Manual execution**: You can directly create, configure, and execute sub-agents from **Settings > Features > Sub-Agents**.

**📋 Management interface (Settings > Features > Sub-Agents):**
• **List**: View all your sub-agents with their status (idle, executing, error)
• **Create**: Build a custom sub-agent from scratch (name, instructions, tools, model)
• **Templates**: Create from **pre-defined templates** — pre-configured expert archetypes with suggested tools and skills
• **Edit**: Update name, instructions, allowed/blocked tools, model, and settings
• **Toggle**: Enable/disable individual sub-agents without deleting them
• **Delete**: Permanently remove a sub-agent
• **Execute**: Run a sub-agent manually with custom instructions (sync or background mode)
• **Cancel**: Stop a running execution if needed

**💡 Tip:** You can also explicitly ask LIA to use experts, for example: *"Use specialized experts to handle my request"*.

## When does LIA use sub-agents?
LIA decides to call on experts when:

• Your request involves **parallel research** across several areas (e.g., comparing transport options)
• A topic benefits from **deep specialized analysis** (e.g., technical audit, market research)
• Multiple independent **expert viewpoints** are needed at the same time

Simple questions are always handled directly — experts are only called in when they add real value.

**You stay in control:** before launching the experts, LIA asks for your confirmation. If you decline, it automatically switches to a standard plan without sub-agents.

## Can I disable sub-agents?
Yes. Go to **Settings > Features > Sub-Agents** and toggle the main switch off. The assistant will then use direct tools (web search, etc.) instead of delegating.

You can also disable individual sub-agents while keeping the feature active — useful to control which experts are available.

## Do sub-agents cost more tokens?
Yes — each sub-agent performs its own LLM calls (planning + tool execution + synthesis). A delegation with 3 experts can cost 3-5x more tokens than a single direct search.

**🛡️ Guard-rails:**
• Per-execution token budget
• Daily budget per user
• Auto-disable after consecutive failures
• All sub-agent costs are tracked and visible in your usage statistics (tokens used, duration)
