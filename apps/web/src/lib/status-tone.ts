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

/** Heartbeat notification priority: `low` | `medium` | `high`. */
const PRIORITY: Record<string, BadgeTone> = {
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
  // Failed.
  error: 'destructive',
  failed: 'destructive',
  // Needs attention, but not broken.
  auth_required: 'warning',
  partial: 'warning',
  degraded: 'warning',
  // Inert. A call nobody answered is not an incident, and an export past its
  // shelf life is not one either — grey is the tone of the INACTIVE.
  inactive: NEUTRAL,
  disabled: NEUTRAL,
  idle: NEUTRAL,
  cancelled: NEUTRAL,
  no_answer: NEUTRAL,
  voicemail: NEUTRAL,
  expired: NEUTRAL,
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
