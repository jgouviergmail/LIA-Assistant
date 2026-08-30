/**
 * Settings group → its fixed tone, for the two surfaces that LIST sections:
 * the overview cards and the rail rows.
 *
 * ## Why this is a deliberate deviation
 *
 * The rest of the app chrome follows the user's accent: the five themes swap
 * only `--color-primary` (and ring), and the accent reaches liserets, badges,
 * filled buttons and focus rings — nothing else. This table breaks that rule on
 * one surface, on purpose, and it is the second element to do so after the
 * skill badge's fixed cyan.
 *
 * The reason is scanning, not decoration. The settings shell lists 53 sections
 * under 12 group headings; before this table every one of them rendered the
 * same `text-primary` glyph on the same `bg-primary/10` chip, so the page gave
 * the eye a single repeated shape to work with. A tone per GROUP — never per
 * item — teaches the reader where a section lives: 53 hues would be noise, 12
 * are a map. The group headings already exist; this makes them visible from
 * inside the grid.
 *
 * ## What keeps it honest
 *
 * - **The tones are tokens, not utility literals.** They live in `globals.css`
 *   as `--color-settings-*`, which is what puts them INSIDE
 *   `design-contrast.guard.test.ts` — the guard reads `--color-*` pairs, and a
 *   fixed palette expressed as Tailwind literals would have sat outside it
 *   (exactly the hole `badge.tsx` records for the variants it removed).
 * - **Completeness is the `Record` type.** A new group fails to compile until
 *   it has a tone.
 * - **Class names are literal.** Tailwind generates a utility only for strings
 *   it can see, so `text-settings-${key}` would emit nothing at all.
 * - **Contrast is measured, not assumed.** Light and dark carry different
 *   lightness (55% / 72%) because one value cannot clear 3:1 on both a near-
 *   white and a near-black card. The glyph is a non-text graphical object
 *   (WCAG 1.4.11 → 3:1) against the chip it sits on, which is the tone itself
 *   at 12% over the card — so the guard blends before it measures.
 *
 * ## What this must never become
 *
 * Colour here is decoration plus grouping, never state. The active/inactive
 * capability signal next to a card is carried by shape and label
 * (`SectionStatus`), so that a reader who does not see these hues loses
 * nothing (WCAG 1.4.1).
 */

import { SETTINGS_SEARCH_META, type SettingsGroupKey } from '@/lib/settings-search';
import type { SettingsSectionToken } from '@/lib/settings-sections';

/** The two class names a group's tone produces. */
export interface SettingsGroupTone {
  /** Glyph colour — measured against `chip` at 3:1. */
  glyph: string;
  /** Chip background: the same tone at 12%, over the card. */
  chip: string;
}

/**
 * Twelve hues at one OKLCH lightness per mode — that fixed lightness is what
 * keeps no group looking paler than its neighbour.
 *
 * Chroma is PER HUE, and the spacing is not 30°. Both started that way and
 * neither survived measurement: sRGB's gamut is not a cylinder, so a single
 * chroma put six of the twenty-four tones outside it (clamped by the browser,
 * rendering neither the hue nor the chroma written), and even 30° steps left
 * two pairs 0.116 apart — under the distinctness floor the guard enforces.
 * Each hue therefore carries the most chroma sRGB allows it at that lightness,
 * and the twelve angles were searched on the WORSE of the two modes, which
 * raised the closest pair to 0.199. The assignment stays semantic where a
 * convention exists: red for security, orange for automation, teal for AI.
 */
export const SETTINGS_GROUP_TONES: Readonly<Record<SettingsGroupKey, SettingsGroupTone>> = {
  security: {
    glyph: 'text-settings-security',
    chip: 'bg-settings-security/12',
  },
  automation_tracking: {
    glyph: 'text-settings-automation-tracking',
    chip: 'bg-settings-automation-tracking/12',
  },
  system: {
    glyph: 'text-settings-system',
    chip: 'bg-settings-system/12',
  },
  content_extensions: {
    glyph: 'text-settings-content-extensions',
    chip: 'bg-settings-content-extensions/12',
  },
  connections_integrations: {
    glyph: 'text-settings-connections-integrations',
    chip: 'bg-settings-connections-integrations/12',
  },
  extensions_data: {
    glyph: 'text-settings-extensions-data',
    chip: 'bg-settings-extensions-data/12',
  },
  ai_connectors: {
    glyph: 'text-settings-ai-connectors',
    chip: 'bg-settings-ai-connectors/12',
  },
  notifications_communication: {
    glyph: 'text-settings-notifications-communication',
    chip: 'bg-settings-notifications-communication/12',
  },
  identity_memory: {
    glyph: 'text-settings-identity-memory',
    chip: 'bg-settings-identity-memory/12',
  },
  personalization: {
    glyph: 'text-settings-personalization',
    chip: 'bg-settings-personalization/12',
  },
  voice_media: {
    glyph: 'text-settings-voice-media',
    chip: 'bg-settings-voice-media/12',
  },
  users_access: {
    glyph: 'text-settings-users-access',
    chip: 'bg-settings-users-access/12',
  },
};

/** The alpha `chip` applies, restated once so the contrast guard cannot drift from it. */
export const SETTINGS_TONE_CHIP_ALPHA = 0.12;

/**
 * The accent pair every settings icon wore before the tones existed.
 *
 * Kept as the fallback rather than throwing: `SettingsSection.value` is typed
 * `string`, so a caller outside the section table — test scaffolding, a future
 * one-off card — must degrade to the previous look, not crash a settings page.
 */
export const ACCENT_TONE: SettingsGroupTone = {
  glyph: 'text-primary',
  chip: 'bg-primary/10',
};

/**
 * The tone a section's icon wears in the two lists that show it.
 *
 * One function, so the card and the rail row cannot disagree about a section.
 *
 * The OPEN section's header deliberately does NOT use this: `apps/web/CLAUDE.md`
 * carries an owner rule from 2026-08-05 — "a title always carries an icon, and
 * a title icon is never grey… in the THEME colour (`text-primary`)". A section
 * header is a title, so it keeps the accent. The consequence is known and
 * accepted: the glyph changes colour between the list and the opened pane,
 * which are never on screen together.
 *
 * @param token - A section token; anything else falls back to the accent.
 */
export function toneForSection(token: string): SettingsGroupTone {
  const meta = SETTINGS_SEARCH_META[token as SettingsSectionToken];
  return meta ? SETTINGS_GROUP_TONES[meta.group] : ACCENT_TONE;
}
