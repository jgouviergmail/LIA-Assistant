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
