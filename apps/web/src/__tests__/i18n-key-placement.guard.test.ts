/**
 * i18n key PLACEMENT guard.
 *
 * ## Why this exists
 *
 * The pre-commit parity check compares the KEY SETS of the six locales against
 * `en`. It is blind to a key that lands in the wrong section: an insertion that
 * misfires the same way in all six files keeps perfect parity while the UI
 * renders `usage_limits.warning.warning` verbatim on screen.
 *
 * That happened during the A5 lot: a text-anchored insertion matched a nested
 * `"usage_limits"` and dropped a whole block into the `interests` section. All
 * six locales agreed, parity was green, and only a browser run showed raw keys
 * to the user.
 *
 * ## What it checks
 *
 * That the keys the components actually call resolve to a non-empty STRING at
 * the exact path, in every locale — and that a key expecting a placeholder
 * still carries it. Cheap, and it fails on the real failure mode.
 *
 * Add an entry whenever a component starts calling a new key whose absence
 * would be visible rather than fatal.
 */

import { describe, it, expect } from 'vitest';

// Suffixed on purpose: a bare `it` import would shadow vitest's own `it`.
import enDict from '../../locales/en/translation.json';
import frDict from '../../locales/fr/translation.json';
import deDict from '../../locales/de/translation.json';
import esDict from '../../locales/es/translation.json';
import itDict from '../../locales/it/translation.json';
import zhDict from '../../locales/zh/translation.json';

const LOCALES: Record<string, unknown> = {
  en: enDict,
  fr: frDict,
  de: deDict,
  es: esDict,
  it: itDict,
  zh: zhDict,
};

/**
 * Keys whose absence degrades silently (the UI prints the key) rather than
 * crashing. Each entry may pin the placeholders the caller passes.
 */
const PINNED: ReadonlyArray<{ key: string; placeholders?: readonly string[] }> = [
  // W1 — clickable FAQ examples
  { key: 'faq.try_example', placeholders: ['example'] },
  // W7 — unconfigured briefing cards
  { key: 'dashboard.briefing.not_configured_intro_one' },
  { key: 'dashboard.briefing.not_configured_intro_other', placeholders: ['count'] },
  { key: 'dashboard.briefing.not_configured_cta', placeholders: ['card'] },
  { key: 'dashboard.briefing.all_hidden' },
  { key: 'dashboard.briefing.all_hidden_cta' },
  // W8 — empty-chat starters
  { key: 'chat.starters.label' },
  { key: 'chat.starters.capabilities' },
  { key: 'chat.starters.reminder' },
  { key: 'chat.starters.explain' },
  // N2 — generated image expiry
  { key: 'chat.image_expiry.until', placeholders: ['date'] },
  { key: 'chat.image_expiry.soon_one', placeholders: ['count'] },
  { key: 'chat.image_expiry.soon_other', placeholders: ['count'] },
  { key: 'chat.image_expiry.expired' },
  // A5 — quota warning
  { key: 'usage_limits.warning.warning', placeholders: ['percent'] },
  { key: 'usage_limits.warning.critical', placeholders: ['percent'] },
  { key: 'usage_limits.warning.resets_on', placeholders: ['date'] },
  { key: 'usage_limits.warning.dimension.cycle_tokens' },
  { key: 'usage_limits.warning.dimension.cycle_messages' },
  { key: 'usage_limits.warning.dimension.cycle_cost' },
  { key: 'usage_limits.warning.dimension.absolute_tokens' },
  { key: 'usage_limits.warning.dimension.absolute_messages' },
  { key: 'usage_limits.warning.dimension.absolute_cost' },
  // A6 — telephony. Built by interpolation (`chat.active_call.${status}`,
  // `settings.telephony.calls.status.${status}`), so a missing entry does not
  // fail anywhere: it simply prints the key next to the callee's name. Only the
  // two IN-FLIGHT statuses reach the banner, the seven reach the settings list.
  { key: 'chat.active_call.dialing', placeholders: ['name'] },
  { key: 'chat.active_call.in_progress', placeholders: ['name'] },
  { key: 'chat.active_call.details' },
  { key: 'settings.telephony.calls.title' },
  { key: 'settings.telephony.calls.description' },
  { key: 'settings.telephony.calls.in_flight' },
  { key: 'settings.telephony.calls.status.dialing' },
  { key: 'settings.telephony.calls.status.in_progress' },
  { key: 'settings.telephony.calls.status.completed' },
  { key: 'settings.telephony.calls.status.no_answer' },
  { key: 'settings.telephony.calls.status.voicemail' },
  { key: 'settings.telephony.calls.status.failed' },
  { key: 'settings.telephony.calls.status.cancelled' },
  { key: 'settings.telephony.calls.outcome.objective_met' },
  { key: 'settings.telephony.calls.outcome.partial' },
  { key: 'settings.telephony.calls.outcome.declined' },
  { key: 'settings.telephony.calls.outcome.unreachable' },
  // W3 — retry affordance on a failed turn.
  { key: 'chat.message.retry' },
  // A2 — the logo-as-menu trigger; an unnamed button is a dead end.
  { key: 'common.menu' },
];

/** Resolve a dotted path, or undefined. */
function resolve(dictionary: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((node, part) => {
    if (node && typeof node === 'object' && part in (node as Record<string, unknown>)) {
      return (node as Record<string, unknown>)[part];
    }
    return undefined;
  }, dictionary);
}

describe('i18n key placement', () => {
  for (const [locale, dictionary] of Object.entries(LOCALES)) {
    describe(locale, () => {
      it.each(PINNED.map(entry => [entry.key, entry] as const))(
        '%s resolves to a real string',
        (key, entry) => {
          const value = resolve(dictionary, key);
          expect(typeof value, `${locale}: ${key} is not a string`).toBe('string');
          expect((value as string).trim().length, `${locale}: ${key} is empty`).toBeGreaterThan(0);
          for (const placeholder of entry.placeholders ?? []) {
            expect(value as string, `${locale}: ${key} lost {{${placeholder}}}`).toContain(
              `{{${placeholder}}}`
            );
          }
        }
      );
    });
  }

  it('keeps the pinned list free of duplicates', () => {
    const keys = PINNED.map(entry => entry.key);
    expect(new Set(keys).size).toBe(keys.length);
  });
});
