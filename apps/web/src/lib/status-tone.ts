/**
 * Which badge tone a status deserves — decided once, for the whole app.
 *
 * Three components used to carry their own `Record<string, string>` of Tailwind
 * classes for the same job. Hand-written classes bypass the design-system
 * contrast guard (which covers `Badge`'s variants across five themes × light
 * and dark), and they drifted: `high` and `medium` both rendered as a
 * 10 %-opacity tint of two tokens only 23° apart in OKLCH hue
 * (`--color-destructive` at 27°, `--color-warning` at 50°). Measured on real
 * data — 89 `high` rows and 113 `medium` rows that the reader could not tell
 * apart.
 *
 * So these functions name a TONE and `Badge` renders it. **Density, not hue
 * alone, carries the hierarchy**: `alert` is a SOLID fill, `warning` a tint,
 * `secondary` neutral — a distinction that survives two hues the eye reads as
 * one, and one that still works in monochrome. The first attempt used
 * `destructive`, whose badge ground is itself a pale tint, and the two levels
 * still looked alike on a real screen.
 *
 * Every unknown value returns the NEUTRAL tone. A status the backend adds
 * later must not arrive shouting: rendering an unrecognised level in red would
 * be a claim about urgency nobody made.
 */

/** The `Badge` variants this module is allowed to return. */
export type BadgeTone =
  | 'default'
  | 'alert'
  | 'secondary'
  | 'success'
  | 'destructive'
  | 'warning'
  | 'info'
  | 'outline';

const NEUTRAL: BadgeTone = 'secondary';

/** Priority as the card's leading edge — a ramp, not a binary. */
const PRIORITY_ACCENT: Record<string, string> = {
  urgent: 'border-l-destructive',
  high: 'border-l-warning',
  medium: 'border-l-primary/40',
  low: 'border-l-border',
};

/**
 * Priority level: `low` | `medium` | `high`, plus the workboard's `urgent`.
 *
 * `urgent` shares `alert` with `high` rather than displacing it (ADR-276). The
 * measurement below forbids demoting `high` to a pale tint, and `alert` is the
 * ONLY solid ground the badge offers — so the two top levels share the
 * ATTENTION family and are told apart by their WORD, which the badge carries
 * anyway. Rendering `urgent` on the fallback instead would have painted the
 * most urgent ticket of the board in the grey the owner rule reserves for
 * inactive elements.
 */
const PRIORITY: Record<string, BadgeTone> = {
  urgent: 'alert',
  // SOLID, not the pale `destructive`: measured on screen, a red-100 ground and
  // a warning/10 ground are the same level to the eye.
  high: 'alert',
  medium: 'warning',
  low: NEUTRAL,
};

/** Provenance outcome: what a signal did to a belief. */
const OUTCOME: Record<string, BadgeTone> = {
  origin: 'info',
  evidence: 'success',
  contradiction: 'warning',
};

/** Which way an exchanged message or email travelled. */
const DIRECTION: Record<string, BadgeTone> = {
  sent: 'info',
  received: 'success',
};

/**
 * The lifecycle vocabulary, shared by every domain that reports a state.
 *
 * `error`, `completed`, `active`, `syncing` and `pending` mean the same thing
 * wherever the backend emits them, so they get their tone from ONE table. Each
 * screen deciding for itself is exactly how the same meaning ended up wearing
 * three colours: "running fine" was blue on MCP servers and scheduled actions,
 * green on Drive sources and documents, and plain GREY on recent calls — where
 * `failed` and `completed` were, as a result, the same pill.
 *
 * Five semantic families, and no more:
 *
 *  - `success`     — it worked, or it is working
 *  - `info`        — it is happening right now
 *  - `destructive` — it failed
 *  - `warning`     — it needs attention, but nothing is broken
 *  - `secondary`   — inert: nothing happened, and nothing is wrong
 *
 * `alert` (the solid fill) is deliberately absent: ADR-205 reserves it for the
 * PRIORITY hierarchy, where two pale tints could not be told apart. A lifecycle
 * status is a fact, not an alarm.
 */
const LIFECYCLE: Record<string, BadgeTone> = {
  // The workboard's columns (ADR-276). Four of them were unknown to this
  // table and fell to the neutral fallback, so three LIVE states — « à faire »,
  // « en attente », « en validation » — wore the badge the owner rule reserves
  // for inactive elements. Declared here rather than left to the fallback:
  // `idea` IS inert, and that must read as a decision. The `cancelled` entry
  // further down belongs to telephony and the exports — never a board column,
  // which is why dropping « Annulé » from the board leaves it standing.
  idea: NEUTRAL,
  // Live work with no semantic family of its own: the theme colour, per the
  // owner rule on active traits.
  todo: 'default',
  // It waits for the person; nothing is broken.
  waiting: 'warning',
  // LIA prepared an action and needs the person's go: the same wait, sharper.
  confirming: 'warning',
  // A run produced a result nobody has read yet — it just happened.
  validating: 'info',
  // Succeeded, or running normally.
  active: 'success',
  completed: 'success',
  connected: 'success',
  succeeded: 'success',
  ready: 'success',
  done: 'success',
  // In flight.
  dialing: 'info',
  in_progress: 'info',
  executing: 'info',
  syncing: 'info',
  processing: 'info',
  reindexing: 'info',
  pending: 'info',
  queued: 'info',
  running: 'info',
  claimed: 'info',
  // Failed.
  error: 'destructive',
  failed: 'destructive',
  // The effect register's own three (ADR-263). They lived in a per-screen
  // map inside `EffectsJournal` — the very thing this module exists to end —
  // where « succeeded » rendered as the theme colour rather than as success,
  // and « in progress » as grey rather than as in-flight.
  // `refused` is NEUTRAL on the habits precedent: a refusal is a decision,
  // not an incident. `abandoned` (« Interrupted ») is the one that needs
  // attention without anything being broken — the record is incomplete.
  // Needs attention, but not broken.
  auth_required: 'warning',
  partial: 'warning',
  degraded: 'warning',
  abandoned: 'warning',
  // Inert. A call nobody answered is not an incident, and an export past its
  // shelf life is not one either — grey is the tone of the INACTIVE.
  inactive: NEUTRAL,
  disabled: NEUTRAL,
  idle: NEUTRAL,
  cancelled: NEUTRAL,
  no_answer: NEUTRAL,
  voicemail: NEUTRAL,
  expired: NEUTRAL,
  refused: NEUTRAL,
  // Habits (ADR-214): a paused habit is dormant and a blocked one is the
  // user's never-relearn tombstone — both INACTIVE by the owner rule, told
  // apart by their label, never by an alarm colour (a refusal is not an
  // incident).
  paused: NEUTRAL,
  blocked: NEUTRAL,
};

/** What a finished call achieved. */
const CALL_OUTCOME: Record<string, BadgeTone> = {
  objective_met: 'success',
  partial: 'warning',
  // A callee who declines, or a line nobody picks up, is a normal outcome of a
  // phone call. Red would report a malfunction where none occurred.
  declined: NEUTRAL,
  unreachable: NEUTRAL,
};

/**
 * Priority as a card ACCENT: the coloured edge a board is read by.
 *
 * Deliberately a four-level RAMP where `priorityTone` has three: the badge
 * marks the exception (`high` and `urgent` are both simply « loud », which is
 * why they share `alert`), while the edge RANKS — an edge that painted high
 * and urgent the same would carry no information at all. Read together on one
 * card they agree: the badge says « above the default », the edge says how far.
 *
 * Args:
 *   priority: `low`, `medium`, `high` or `urgent`.
 *
 * Returns:
 *   The border class for the card's leading edge; the neutral border for
 *   anything this build does not know.
 */
export function priorityAccent(priority: string): string {
  return PRIORITY_ACCENT[priority] ?? 'border-l-border';
}

/**
 * The INK of a priority's mark — the edge's own tone, one entry per edge
 * entry above, so a list item and the card it ranks can never disagree
 * (ADR-276, D81). `medium` takes the accent at full strength: a dimmed ink
 * is refused by the text guard, and a 3.5 px glyph carries no wash.
 */
const PRIORITY_INK: Record<string, string> = {
  urgent: 'text-destructive',
  high: 'text-warning',
  medium: 'text-primary',
  low: 'text-muted-foreground',
};

export function priorityInk(priority: string): string {
  return PRIORITY_INK[priority] ?? 'text-muted-foreground';
}

/**
 * The GROUND a card sits on, for the one priority that must be seen across a
 * whole board rather than read on one card.
 *
 * `urgent` and `high` share the same badge tone (both are alert red: measured,
 * a red-100 ground and a warning/10 ground are the same level to the eye), so
 * the edge alone was the only thing telling them apart — four pixels. A pastel
 * ground separates them at a glance without shouting: everything else keeps the
 * card's normal surface.
 */
export function priorityGround(priority: string): string {
  return priority === 'urgent' ? 'bg-rose-50 dark:bg-rose-950/40' : '';
}

/**
 * Tone for a notification priority.
 *
 * Args:
 *   priority: The raw value, as the backend published it.
 *
 * Returns:
 *   The badge variant; neutral for anything this build does not know.
 */
export function priorityTone(priority: string): BadgeTone {
  return PRIORITY[priority] ?? NEUTRAL;
}

/**
 * Tone for a provenance outcome.
 *
 * Args:
 *   outcome: `origin`, `evidence` or `contradiction`.
 *
 * Returns:
 *   The badge variant; neutral for anything this build does not know.
 */
export function outcomeTone(outcome: string): BadgeTone {
  return OUTCOME[outcome] ?? NEUTRAL;
}

/**
 * Tone for the direction of an exchange.
 *
 * Args:
 *   direction: `sent` or `received`.
 *
 * Returns:
 *   The badge variant; neutral for anything this build does not know.
 */
export function directionTone(direction: string): BadgeTone {
  return DIRECTION[direction] ?? NEUTRAL;
}

/**
 * Tone for a lifecycle status, whatever domain reports it.
 *
 * Args:
 *   status: The raw value, as the backend published it.
 *
 * Returns:
 *   The badge variant; neutral for anything this build does not know.
 */
export function lifecycleTone(status: string): BadgeTone {
  return LIFECYCLE[status] ?? NEUTRAL;
}

/**
 * Tone for the outcome of a finished call.
 *
 * Args:
 *   outcome: `objective_met`, `partial`, `declined` or `unreachable`.
 *
 * Returns:
 *   The badge variant; neutral for anything this build does not know.
 */
export function callOutcomeTone(outcome: string): BadgeTone {
  return CALL_OUTCOME[outcome] ?? NEUTRAL;
}

/** Typed traits a skill card can wear. */
export type SkillTrait =
  | 'category'
  | 'always_loaded'
  | 'has_scripts'
  | 'dialogue'
  | 'has_plan_template'
  | 'channel';

/**
 * Skill trait badges, toned by TYPE — the same label was drifting between the
 * user gallery and the admin section before this table existed.
 */
const SKILL_TRAIT: Record<SkillTrait, BadgeTone> = {
  // Identity: the primary tint, so it follows the active theme.
  category: 'default',
  // Cost signal: an always-loaded skill occupies context permanently.
  always_loaded: 'warning',
  // Plain capabilities: facts about the skill, nothing to notice.
  has_scripts: 'secondary',
  dialogue: 'secondary',
  has_plan_template: 'secondary',
  channel: 'secondary',
};

/** Who filled a catalogue row's capabilities (ADR-244). */
export type CapabilityProvenance = 'declared' | 'imported' | 'verified';

/**
 * Provenance badges, toned by how much the row can be TRUSTED.
 *
 * `declared` is the column defaults nobody curated — the state that made
 * ``gpt-5.2`` answer 8 192 against a real 272 000, and the reason
 * ``get_effective_context_window`` refuses to trust it. It needs attention
 * without anything being broken, which is exactly `warning`; red would report
 * a malfunction where there is only an absence of evidence.
 *
 * `imported` (corroborated by two public registries) and `verified` (a human
 * edited a registry-owned capability) are both facts about a healthy row, so
 * they take the theme tint rather than an alarm colour.
 */
const CAPABILITY_PROVENANCE: Record<CapabilityProvenance, BadgeTone> = {
  declared: 'warning',
  imported: 'info',
  verified: 'success',
};

/**
 * Tone for a capability-provenance badge.
 *
 * Args:
 *   provenance: The raw value, as the backend published it.
 *
 * Returns:
 *   The badge variant. An unrecognised value falls to the neutral tone —
 *   a provenance nobody defined must not arrive claiming to be trustworthy.
 */
export function capabilityProvenanceTone(provenance: string): BadgeTone {
  return CAPABILITY_PROVENANCE[provenance as CapabilityProvenance] ?? NEUTRAL;
}

/**
 * Tone for a skill trait badge.
 *
 * Args:
 *   trait: Which trait the badge names.
 *
 * Returns:
 *   The badge variant for that trait type.
 */
export function skillTraitTone(trait: SkillTrait): BadgeTone {
  return SKILL_TRAIT[trait];
}

/** Self-diagnostics health verdicts (spec 2026-08-27). */
const HEALTH: Record<string, BadgeTone> = {
  ok: 'success',
  degraded: 'warning',
  critical: 'alert',
  // Blindness is an indeterminate state, not a dormant one — `secondary`
  // would claim "inactive", which unknown precisely is not.
  unknown: 'outline',
};

/**
 * Tone for a platform health verdict (check or snapshot).
 *
 * Args:
 *   status: `ok` | `degraded` | `critical` | `unknown` as the API reports it.
 *
 * Returns:
 *   The badge variant; an unrecognised value reads as indeterminate.
 */
export function healthTone(status: string): BadgeTone {
  return HEALTH[status] ?? 'outline';
}

/** Incident lifecycle: open incidents wear their severity, resolved is done. */
export function incidentTone(status: string, severity: string): BadgeTone {
  if (status === 'resolved') {
    return 'success';
  }
  return severity === 'critical' ? 'alert' : 'warning';
}
