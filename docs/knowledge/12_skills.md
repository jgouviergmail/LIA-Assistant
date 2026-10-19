# Skills

## What is a skill?
A skill is a **SKILL.md** file that extends the assistant's capabilities with expert instructions, structured workflows, or planning templates. They follow the open agentskills.io standard, compatible with 30+ products (Claude Code, Cursor, VS Code, GitHub Copilot...).

**Five skill archetypes:**
- **Prompt expert**: expert instructions without tools (writing, coaching...)
- **Advisory**: methodology + LIA can call its own tools organically
- **Plan template**: deterministic plan with automatic tool calls (briefing, meeting prep...)
- **Visualizer**: Python script emits an interactive iframe (map, dashboard) via the SkillScriptOutput JSON contract
- **Generator**: Python script emits an image artifact (QR code, chart) via the SkillScriptOutput JSON contract

## How do I import a skill?
In **Settings › Features › Extensions & Data › Skills**, click **Import** and select a .md or .zip file. Compatible skills are available on **skillsmp.com** or GitHub — and the public library's **Search** button, in the same section, searches the public **skills.sh** library directly. File sizes and the number of skills per account are bounded by your instance.

## How do I create my own skill?
**The easiest way: just ask LIA!** Say something like "*create a skill for [your need]*" and the built-in **Skill Generator** will guide you step by step: need analysis, archetype selection (any of the 5 archetypes), generation, automatic validation — then a **proposal card** in the chat: you read its name, description and files, and one click on **Install** puts it in **My Skills**, ready to use. Nothing is installed without your click; a ticket or a messaging channel sends you back to the chat, where the card can be shown.

You can also manually create a SKILL.md file with a minimal YAML header (name + description) followed by Markdown instructions. See the **built-in guide** (📖 Guide button in My Skills) for advanced options including full agent & tool catalogue with parameters.

## What is in the built-in skills guide?

The **Guide** button of the Skills section — in its ⋯ menu on a phone — opens the **Skills Guide**, in three tabs:
• **Fundamentals** — what a skill is, the three base types (Prompt Expert, Advisory, Plan Template; the Visualizer and Generator archetypes are covered under **Advanced**), how activation works — names and descriptions first, instructions once the skill is used, files only on demand — and best practices
• **Create a skill** — the SKILL.md format and its header fields, worked examples, the folder structure and how to use its resources
• **Advanced** — plan templates and their automatic trigger, the complete catalogue of agents and tools with their parameters, Python scripts, interactive frames and images, and the conventions that keep a skill in step with your theme and language

Prefer not to write it yourself? Describe your need in the chat:
• *Create a skill that shows a QR code*

## What is the difference between admin skills and my skills?
**Admin skills (built-in)**: shipped with the application, available to all users. You can enable/disable them individually.
**My skills (imported)**: personal skills you import. You can toggle, download, or delete them.
A name is unique within your own skills, not across the instance: another person may keep a skill with the same name as yours. What stays refused is reusing the name of a built-in skill — pick a variant name instead.

## How does LIA decide which skill to use?
Skill activation uses a **hybrid model** with 3 strategies:

1. **QueryAnalyzer detection** (unified) — The `QueryAnalyzer` reads the L1 catalogue (skill names + descriptions) and sets `skill_name` in its output. The response node then activates the skill based on its nature: skills with **scripts** run via a dedicated **ReAct sub-agent** in an isolated loop; skills with **resources only** load them via Python with passive L2 injection (0 extra LLM call); skills with **neither** use L2 passive injection only.

2. **Planner pre-activation** (complementary) — The LLM planner can also include `skill_name` in its JSON output via the L1 catalogue. The response node treats this the same way (scripts → runner, resources → Python, etc.).

3. **Deterministic bypass** (optimization) — Skills with `plan_template.deterministic: true` bypass the LLM planner entirely via `SkillBypassStrategy` whenever the QueryAnalyzer has identified them. The bypass does no domain-overlap matching: it trusts the semantic signal (`detected_skill_name`) produced by the QueryAnalyzer from the skill's description. Steps requiring services the user hasn't connected (e.g., Gmail) are automatically filtered out so the skill still runs with partial data.

**Planner skill guard:** The planner normally detects missing parameters early and asks for clarification (e.g., "send an email" without a subject). When the QueryAnalyzer has identified a skill, this early clarification is skipped so the skill's template or instructions can shape the plan rather than being interrupted by a clarification prompt.

**Skill badge:** when a skill drives an answer, a badge on the assistant message shows which one — visible to every user (it also works when the skill was activated directly during the conversation, without going through the planner).

## Can I download or share a skill?
Yes. Hover over any skill in settings and click the **download** icon (⬇️). You will get a .zip file containing SKILL.md and all associated files (references/, scripts/, assets/). Share this zip with other users or publish it on agentskills.io-compatible marketplaces.

## What is the Skill Generator?
The **Skill Generator** is a built-in system skill that lets you **create your own skills using natural language**. Simply describe your need ("*I want a detailed 5-day weather forecast*") and the assistant guides you through 4 steps:
1. **Need analysis**: clarifying questions about the task, tools, and desired format
2. **Archetype selection**: Prompt Expert, Advisory, Plan Template, Visualizer, or Generator
3. **Generation**: creates the SKILL.md (plus scripts/references if needed) compliant with the agentskills.io standard
4. **Validation & proposal**: automatic format verification, then a **proposal card** in the chat — you review the skill and its files, and one click on **Install** makes it active in **My Skills** (toggle, download, or delete it there like any imported skill)

## What can a skill include besides its instructions?

A skill imported as a **.zip** keeps its **SKILL.md** and can bring folders of its own:
• **references/** — text documents LIA reads only when needed: detailed guides, templates, reference data
• **scripts/** — Python scripts run in an isolated sandbox, and the commands its instructions ask to run (shell, Node, Python)
• **assets/** — static files: templates, images, configuration; an **assets/preview.png** becomes the thumbnail of its card
• **translations.json** — its description in the six languages

These files are loaded on demand, so a large skill costs nothing until it is used. File sizes and the number of skills per account are bounded by your instance, and the **Guide** describes each folder.

The skills that ship with LIA all have a preview: a sketch of what the skill produces — a month grid, a QR code, weather cards — rather than a generic icon. A skill without that file simply shows a placeholder.

## How isolated is a skill script?

When the script sandbox is enabled (the default sandbox mode), each run gets its **own throwaway container**, removed as soon as the script ends:
• no network — unless the script names hosts that you or your administrator allowed, reached through a dedicated proxy
• a read-only system, apart from a small temporary space
• an unprivileged identity with no special rights, and bounded memory, processes and time
• nothing of LIA's inside — neither its code nor your credentials: the script receives the input it is given (plus, for a command, the files you attached) and returns its result

A generic installation runs without the sandbox. If that container cannot be started, the script **does not run**: LIA never falls back silently to a weaker mode. A script that overruns its time is removed rather than left behind. Every run starts from a sandbox image of its own: Python, Node and the command-line tools skills call, and nothing that could reach the rest of the machine.

In short, you install a skill for what it produces, without having to trust whoever wrote it with your data.

**⚙️ For administrators:** the container is the default sandbox mode. An operator can deliberately select the older in-process mode (`SKILLS_SCRIPT_SANDBOX`), which only isolates when the API itself runs as root; the scripts LIA writes on its own always refuse that mode.

## Can a skill run programs and hand me files?
Yes. Many skills written for other assistants say to **run a command**: a Python, shell or Node script, a PDF or spreadsheet tool. LIA runs it in a **copy of the skill's folder**, in the same throwaway container — no access to your mailbox, calendar or connectors, nothing of LIA's own. The files you attached to your message travel in with it, and every file it writes in its `out/` folder comes back as a **generated file**: shown under the answer and kept in your gallery for the usual time.

What comes back is checked before it reaches you. A document or an image keeps its type only if its content matches it; a page the skill wrote (Markdown, HTML, SVG) comes back as plain text; anything else is left out, and the answer says so. A command has a time budget and size limits.

A command runs **offline by default**. One that must install a package or fetch a repository names the hosts it reaches (npm, pip, git…) and goes out through a dedicated proxy: HTTPS only, to those hosts and nowhere else, and only once your administrator or you have allowed them — LIA asks you in ReAct mode, and you can allow a host yourself in **Settings › Skill permissions**. A skill written elsewhere never receives your connectors or their keys.

## Rich outputs (frames + images)

Since **v1.16.8**, skills can return interactive content beyond text by writing
a JSON object on stdout matching the `SkillScriptOutput` contract:

```json
{
  "text": "Required caption (voice, LLM, accessibility).",
  "frame": {
    "url": "https://...",
    "link_url": "https://...",
    "title": "...",
    "aspect_ratio": 1.333
  },
  "image": { "url": "data:image/png;base64,...", "alt": "..." }
}
```

- `text` is always required. `frame` and `image` are independent and
  combinable (text alone, text+frame, text+image, or all three).
- `frame.html` (inline via srcDoc) and `frame.url` (external via src) are
  mutually exclusive; `frame.html` is bounded by `SKILLS_FRAME_MAX_HTML_BYTES`
  (200 KB).
- `frame.link_url` (optional, https-only) is the **user-facing** URL used by
  the frontend fallback card ("open in browser") when the frame cannot render.
  Provide it whenever `frame.url` is embed-only — e.g. the Google Maps embed
  endpoint refuses top-level rendering (ADR-136).
- User-skill `frame.html` automatically receives a strict CSP (`connect-src none`,
  `frame-src none`) to prevent exfiltration. System skills are trusted and
  skip CSP injection.
- All frames render inside an iframe sandbox without `allow-same-origin` —
  parent cookies and storage are unreachable.

**Seven built-in rich skills** ship with v1.16.8: `interactive-map`,
`weather-dashboard`, `calendar-month`, `qr-code`, `pomodoro-timer`,
`unit-converter`, `dice-roller`.

### Runtime conventions

When a script emits a `frame`, the runtime provides a number of behaviours
automatically:

- **`_lang` and `_tz` auto-injection** — `run_skill_script` automatically adds
  the user's language code (ISO 639-1) and IANA timezone to `parameters`.
  Scripts should read these rather than calling `locale.setlocale()` (not
  available in the container) — inline translation tables for
  weekdays/months are the canonical approach.
- **Theme and locale sync** — the host pushes `ui/initialize`,
  `ui/theme-changed` and `ui/locale-changed` `postMessage` events to every
  frame. Scripts listen and flip CSS via `html[data-theme="dark"]` selectors
  (not `prefers-color-scheme`) for consistency with the app.
- **Auto-resize** — frames are auto-sized by the host via
  `ui/notifications/size-changed` events emitted from an injected snippet that
  measures `document.body.getBoundingClientRect().bottom`. The iframe grows or
  shrinks to fit content.
- **Client-side interactivity** — the CSP forbids `onclick` inline handlers;
  use `addEventListener` inside a `<script>` element instead. Use
  `crypto.getRandomValues` for randomness, not `Math.random`.
- **Durability** — widgets are persisted with the message that displays them:
  a conversation reopened after a reload, or on another device, renders its
  maps, games and diagrams again instead of grey "unavailable" boxes.
- **Failure states** — a frame the browser cannot display, or that never
  loads, shows an actionable card (explanation, Retry, open in a new tab via
  the skill's `link_url`) instead of a blank rectangle.

See the **Skills Guide** in Settings (Advanced tab → "Localization, theming
and runtime conventions") for copy-paste examples.

See `docs/technical/SKILLS_INTEGRATION.md` § Rich Outputs for the full
registry flow (SKILL_APP registry item → sentinel HTML → SkillAppWidget).

## What does the skills gallery show?
**Settings › Features › Extensions & Data › Skills** displays your skills as **cards**. Opening one shows its localized description, a **preview image** when the skill bundles one, its declared **output channels** (text, interactive frame, image) and the actions (enable/disable, download, delete). A skill you imported yourself carries a **provenance warning**: its instructions run with access to your connected data, so only keep skills whose source you trust. A skill **written elsewhere** — installed from an address, the library or a plugin — wears a badge (« Library », « From an address », « Plugin ») and its detail says what it may do here (see below).

## Can I install a skill directly from a URL?
Yes — the **URL** button of the Skills section (in its **More actions** menu (⋯) on a phone) opens **Install a skill from a URL**. Paste an **https** address serving a SKILL.md file or a .zip package. The server validates everything: https only, no private/internal addresses, no redirects, size cap, and the **same strict import pipeline** as a file upload (name conflicts, quota, content validation). Failed attempts are rate-limited per user. A skill installed from an address is treated as **written elsewhere** (see below).

## Can I find skills in a public library?
Yes — the library's **Search** button, in the Skills section, searches **skills.sh**, the public skill library, or reads any GitHub address you paste (`owner/repo`, or a github.com link to a repository or to one skill's folder). You read a skill **before** installing it: where it comes from, the exact commit, every file with its size, and what the published audits say. A skill an audit rates at or above the instance's refusal level (high risk by default) is refused. A skill the portal lists on a website rather than on GitHub is shown but cannot be installed.

What is installed is exactly what you read: the install sends back the commit the preview showed, and every file is checked against GitHub's own fingerprint. The **Installed** tab says which skills have an update (their folder changed at the source), and « Review the update » lists the files it adds, changes and removes before anything is replaced. A library skill never takes the name of a built-in skill, and is removed like any of your skills.

## What may a skill written elsewhere do?

A skill installed **from an address**, from the **library** or by a **plugin** was written by someone else, so LIA reads it as data, never as orders. Its card carries a badge — **From an address**, **Library** or **Plugin** — and its detail says what it may do here:
• its description is only a label in LIA's catalogue; it never runs a built-in plan and never loads itself into every conversation
• its instructions run **apart**, with its own files and the ones you attach — never your mailbox, calendar or other connectors
• its scripts and commands run in the isolated sandbox, reach the network only through the proxy to allowed hosts, and never receive your connector keys
• its answers show no image loaded from the web and no raw page code, and it draws no interactive frame
• it follows its source: update it rather than ask LIA to rewrite it

A skill you import from your own file is different: it runs with access to your connected data, so keep only those you trust.

A skill received from an accepted LIA connection is an explicit exception: its copy arrives disabled and without credentials; after you enable it, it uses the same execution policy as your own skills. Review its instructions first. The sender badge is informational; uploaded metadata cannot grant this policy.

## Can I have an existing skill modified?
Yes, by talking to LIA: "*adjust my X skill*", "*add a section to it*", "*fix the wording*". LIA re-reads the complete skill — its manifest, its scripts, its reference documents — applies your request, then **regenerates the whole thing** rather than patching one spot: that is what keeps the description, the scripts and the resources consistent with each other.

Nothing is written directly: LIA proposes the new version on a card showing **exactly what will be replaced, added and removed**. Only your click on **Install** applies it, and if your skill changed in the meantime, the card says so instead of overwriting it. **There is no version history** — once replaced, the previous version cannot be recovered, so read the summary. The gallery thumbnail, however, is preserved automatically: chat can only carry text, so the server copies bundled images back from the version being replaced.

Three cases are refused: **system** skills (maintained by the administrator, no fork offered), skills **installed from the library or brought by a plugin** (they follow their source — update them instead), and your own ones that are **disabled** — re-enable it first in the Skills section.

A regenerated package is also checked for internal consistency: a skill declaring an interactive output with no script, or advertising a resource it does not ship, is rejected rather than stored broken.

## Can I manage skills, plugins and MCP servers through conversation?

Offered commands can read and prepare authorised operations on your existing skills, plugins, personal MCP servers and channels. File imports and keys continue in the secure interface; installation, deletion and sensitive changes retain confirmation. Asking does not create a new messaging adapter. If Docker refuses a skill sandbox, the operation is reported unavailable rather than run outside the container.
