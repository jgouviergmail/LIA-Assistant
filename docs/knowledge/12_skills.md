# Skills

## What is a skill?
A skill is a **SKILL.md** file that extends the assistant's capabilities with expert instructions, structured workflows, or planning templates. They follow the open agentskills.io standard, compatible with 30+ products (Claude Code, Cursor, VS Code, GitHub Copilot...).Three skill types:**Prompt expert**: expert instructions without tools (writing, coaching...)**Advisory**: methodology + LIA can call its own tools**Plan template**: deterministic plan with automatic tool calls (briefing, meeting prep...)

## How do I import a skill?
In **Settings > Features > My Skills**, click **Import skill** and select a .md or .zip file. Compatible skills are available on **skillsmp.com** or GitHub.

## How do I create my own skill?
**The easiest way: just ask LIA!** Say something like "*create a skill for [your need]*" and the built-in **Skill Generator** will guide you step by step: need analysis, archetype selection (Prompt Expert, Advisory or Plan Template), SKILL.md generation, and automatic validation.You can also manually create a SKILL.md file with a minimal YAML header (name + description) followed by Markdown instructions. See the **built-in guide** (📖 button in My Skills) for advanced options.

## What is the difference between admin skills and my skills?
**Admin skills (built-in)**: shipped with the application, available to all users. You can enable/disable them individually.**My skills (imported)**: personal skills you import. You can toggle, download, or delete them.If you import a skill with the same name as an admin skill, yours overrides it (override semantics).

## How does LIA decide which skill to use?
Skill activation is **model-driven** — the LLM reads the L1 catalogue (names + descriptions) and decides which skill matches your request.For skills with a deterministic plan_template, an optimization mechanism (*SkillBypassStrategy*) can trigger the skill directly without consulting the LLM planner.

## Can I download or share a skill?
Yes. Hover over any skill in settings and click the **download** icon (⬇️). You will get a .zip file containing SKILL.md and all associated files (references/, scripts/, assets/).Share this zip with other users or publish it on agentskills.io-compatible marketplaces.

## What is the Skill Generator?
The **Skill Generator** is a built-in system skill that lets you **create your own skills using natural language**. Simply describe your need ("*I want a detailed 5-day weather forecast*") and the assistant guides you through 4 steps:**Need analysis**: clarifying questions about the task, tools, and desired format**Archetype selection**: Prompt Expert, Advisory, or Plan Template**Generation**: creates a SKILL.md file compliant with the agentskills.io standard**Validation**: automatic format verification via a built-in scriptThe generated file is ready to import in **Settings > Features > My Skills**.
