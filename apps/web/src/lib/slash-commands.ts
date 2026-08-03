/**
 * Slash-command registry (UXR Lot 8, A4).
 *
 * Two kinds (visually distinguished in the menu):
 * - `local`: executed client-side (navigation, open the search) — the page
 *   owns the handlers;
 * - `conversational`: PREFILLS the input with `insertText` (localized by the
 *   page) — never auto-sent (arbitration 3a; `/resume` inserts its literal
 *   text, the backend compaction node consumes it on the next send).
 *
 * Dialogue skills (ADR-118, `dialogue: true` served by GET /skills) are
 * appended as conversational commands namespaced `skill:<name>`.
 */

import { normalizeSearchText } from '@/lib/utils';

export type SlashCommandKind = 'local' | 'conversational';

export interface SlashCommand {
  /** Stable id — also the match target ("resume", "skill:quiz"). */
  id: string;
  kind: SlashCommandKind;
  /** Already-localized label ("/resume — …" is composed by the menu). */
  label: string;
  /** Already-localized one-line description. */
  description: string;
  /** conversational only: the text inserted into the input. */
  insertText?: string;
}

/**
 * The whole input value IS a command token being typed: a leading slash then
 * letters/digits/hyphens/colons only. Any space (or emptied value) closes
 * the menu — `/resume extra` is a normal message.
 */
export function isSlashTrigger(value: string): boolean {
  return /^\/[\p{L}\p{N}:-]*$/u.test(value);
}

/**
 * Declarative table of the STATIC commands (SLASH admin lot). The chat page
 * used to inline these ten objects; the user-shortcut settings form needs
 * the same id list to refuse collisions, and two copies would drift — the
 * copy that drifted being the validation one, silently.
 */
export interface StaticSlashCommandDef {
  id: string;
  kind: SlashCommandKind;
  labelKey: string;
  descriptionKey: string;
  /** conversational: i18n key of the inserted intent… */
  insertKey?: string;
  /** …or a literal inserted verbatim (`/resume` — the backend consumes it). */
  insertLiteral?: string;
}

export const STATIC_SLASH_COMMANDS: readonly StaticSlashCommandDef[] = [
  {
    id: 'resume',
    kind: 'conversational',
    labelKey: 'chat.slash.resume_label',
    descriptionKey: 'chat.slash.resume_description',
    insertLiteral: '/resume',
  },
  {
    id: 'briefing',
    kind: 'local',
    labelKey: 'chat.slash.briefing_label',
    descriptionKey: 'chat.slash.briefing_description',
  },
  {
    id: 'agenda',
    kind: 'conversational',
    labelKey: 'chat.slash.agenda_label',
    descriptionKey: 'chat.slash.agenda_description',
    insertKey: 'chat.slash.agenda_intent',
  },
  {
    id: 'search',
    kind: 'local',
    labelKey: 'chat.slash.search_label',
    descriptionKey: 'chat.slash.search_description',
  },
  // Everyday conversational shortcuts (QA feedback 2026-07-23): each
  // prefills a localized intent — never auto-sent (A4 contract).
  {
    id: 'emails',
    kind: 'conversational',
    labelKey: 'chat.slash.emails_label',
    descriptionKey: 'chat.slash.emails_description',
    insertKey: 'chat.slash.emails_intent',
  },
  {
    id: 'weather',
    kind: 'conversational',
    labelKey: 'chat.slash.weather_label',
    descriptionKey: 'chat.slash.weather_description',
    insertKey: 'chat.slash.weather_intent',
  },
  {
    id: 'weather-weekend',
    kind: 'conversational',
    labelKey: 'chat.slash.weather_weekend_label',
    descriptionKey: 'chat.slash.weather_weekend_description',
    insertKey: 'chat.slash.weather_weekend_intent',
  },
  {
    id: 'tasks',
    kind: 'conversational',
    labelKey: 'chat.slash.tasks_label',
    descriptionKey: 'chat.slash.tasks_description',
    insertKey: 'chat.slash.tasks_intent',
  },
  {
    id: 'reminders',
    kind: 'conversational',
    labelKey: 'chat.slash.reminders_label',
    descriptionKey: 'chat.slash.reminders_description',
    insertKey: 'chat.slash.reminders_intent',
  },
  {
    id: 'news',
    kind: 'conversational',
    labelKey: 'chat.slash.news_label',
    descriptionKey: 'chat.slash.news_description',
    insertKey: 'chat.slash.news_intent',
  },
  // The rail covered "what do I have" and none of the everyday CREATIONS.
  // Both resolve on any account — reminders live in local tables and routines
  // are created through the automation tool — so neither can turn into the
  // broken promise `chat-starters` documents (offering an intent that needs a
  // connector the account may not have).
  {
    id: 'new-reminder',
    kind: 'conversational',
    labelKey: 'chat.slash.new_reminder_label',
    descriptionKey: 'chat.slash.new_reminder_description',
    insertKey: 'chat.slash.new_reminder_intent',
  },
  {
    id: 'new-routine',
    kind: 'conversational',
    labelKey: 'chat.slash.new_routine_label',
    descriptionKey: 'chat.slash.new_routine_description',
    insertKey: 'chat.slash.new_routine_intent',
  },
  // A navigation, not a request: the knowledge spaces have their own page, and
  // asking the model to "open" it would be prose for something the browser
  // does directly.
  {
    id: 'spaces',
    kind: 'local',
    labelKey: 'chat.slash.spaces_label',
    descriptionKey: 'chat.slash.spaces_description',
  },
];

/** The ids a user-defined shortcut may NOT take (statics win, deterministically). */
export const STATIC_SLASH_COMMAND_IDS: ReadonlySet<string> = new Set(
  STATIC_SLASH_COMMANDS.map(command => command.id)
);

/** Localize the static table into menu-ready commands (the page's `t`). */
export function buildStaticSlashCommands(t: (key: string) => string): SlashCommand[] {
  return STATIC_SLASH_COMMANDS.map(def => ({
    id: def.id,
    kind: def.kind,
    label: t(def.labelKey),
    description: t(def.descriptionKey),
    insertText: def.insertLiteral ?? (def.insertKey ? t(def.insertKey) : undefined),
  }));
}

/** A user-defined shortcut, as served by GET /chat/shortcuts. */
export interface UserChatShortcut {
  id: string;
  text: string;
}

/** Mirror of the backend slug rule (apps/api domains/chat/shortcuts.py). */
const SHORTCUT_ID_RE = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/;

/** Refusal reasons of the settings form, i18n-suffix-shaped. */
export type ShortcutIdError = 'invalid_id' | 'reserved' | 'duplicate' | null;

/**
 * Pure validation of a new shortcut id (SLASH admin lot). Mirrors the
 * backend shape rule and adds the one rule the backend deliberately does
 * not know: ids of the STATIC commands are reserved — the registry lives
 * here, so the collision is refused here.
 */
export function validateShortcutId(
  id: string,
  existingIds: readonly string[],
  maxLength: number
): ShortcutIdError {
  if (!SHORTCUT_ID_RE.test(id) || id.length > maxLength) return 'invalid_id';
  if (STATIC_SLASH_COMMAND_IDS.has(id)) return 'reserved';
  if (existingIds.includes(id)) return 'duplicate';
  return null;
}

/**
 * User shortcuts → menu commands. Statics win on id collision (legacy data
 * from before the settings form enforced the reserved list); `skill:` ids
 * are unreachable by construction (the backend slug charset has no colon).
 */
export function userShortcutCommands(shortcuts: readonly UserChatShortcut[]): SlashCommand[] {
  return shortcuts
    .filter(shortcut => !STATIC_SLASH_COMMAND_IDS.has(shortcut.id))
    .map(shortcut => ({
      id: shortcut.id,
      kind: 'conversational' as const,
      label: shortcut.id,
      description: shortcut.text,
      insertText: shortcut.text,
    }));
}

/**
 * Commands whose id or label contains the typed query (sans slash).
 *
 * Normalization is delegated to `normalizeSearchText`, the single accent- and
 * case-insensitive matcher the whole search stack shares (FAQ, search excerpt,
 * highlight, settings search). This module used to carry a private copy that
 * stripped diacritics BEFORE lowercasing instead of after — equivalent on every
 * script the app ships, but a duplicate is a divergence waiting to happen.
 */
export function filterSlashCommands(
  commands: readonly SlashCommand[],
  value: string
): SlashCommand[] {
  const query = normalizeSearchText(value.replace(/^\//, ''));
  if (!query) return [...commands];
  return commands.filter(
    command =>
      normalizeSearchText(command.id).includes(query) ||
      normalizeSearchText(command.label).includes(query)
  );
}
