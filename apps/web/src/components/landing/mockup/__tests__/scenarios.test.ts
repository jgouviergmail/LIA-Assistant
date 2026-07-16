/**
 * Data-integrity guards for the hero mockup timelines.
 *
 * The animation is decorative, but its data contract is not: a typo'd i18n
 * key renders as a raw key on the landing page in all 6 languages, and a
 * mis-ordered timeline silently breaks an act. These tests pin:
 *  - timeline monotonicity and the shared step grammar (type → user → … );
 *  - the backstage window (bs … bs_end) and stream windows referencing real steps;
 *  - every referenced i18n key existing in all 6 locales (strict parity);
 *  - the legacy (pre-backstage) key set being fully purged.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  BACKSTAGE_COSTS,
  REDUCED_MOTION_KINDS,
  SCENARIOS,
  SCENARIO_FOOTERS,
} from '../scenarios';

const LANGS = ['en', 'fr', 'de', 'es', 'it', 'zh'] as const;

/** Suffixes referenced by the mockup components (acts, frame, backstage). */
const REFERENCED_KEYS = [
  'aria',
  'online',
  'mood',
  'input_placeholder',
  'btn_send',
  'btn_stop',
  'backstage_label',
  'bs_cost_live',
  'tokens_unit',
  'messages_one',
  'messages_other',
  ...['s1_chip', 's1_user', 's1_wait', 's1_bs_query', 's1_bs_c1', 's1_bs_c1_sub', 's1_bs_c2', 's1_bs_c2_sub', 's1_bs_c3', 's1_bs_c3_sub', 's1_bs_gate', 's1_bs_note', 's1_hitl', 's1_draft_to', 's1_draft_subject', 's1_draft_quote', 's1_approve', 's1_done'],
  ...['s2_chip', 's2_user', 's2_bs_query', 's2_bs_c1', 's2_bs_c1_sub', 's2_bs_c2', 's2_bs_c2_sub', 's2_bs_note', 's2_card_title', 's2_slot1', 's2_slot2', 's2_slot3', 's2_initiative', 's2_approve', 's2_done', 's2_event_title', 's2_event_day', 's2_event_time', 's2_event_dur'],
  ...['s3_chip', 's3_user', 's3_hitl', 's3_approve', 's3_bs_gate', 's3_bs_call', 's3_bs_call_sub', 's3_bs_note', 's3_done', 's3_card_title', 's3_card_day', 's3_card_time', 's3_card_pers'],
  ...['s4_chip', 's4_user', 's4_bs_forge', 's4_bs_forge_sub', 's4_bs_note', 's4_skill_badge', 's4_reply', 's4_widget_title', 's4_widget_btn1', 's4_widget_btn2', 's4_widget_note'],
];

/** Pre-backstage keys that must not survive the redesign. */
const LEGACY_KEYS = [
  'user_message',
  'step_analyze',
  'lia_planning',
  'lia_hitl',
  'user_approve',
  'lia_done',
  'draft_subject',
  'btn_edit',
  'chip_hitl',
  'chip_cards',
  'chip_markdown',
  's2_user_message',
  's2_card_desc',
  's2_slot_morning',
  's3_user_message',
  's3_status',
  's3_md_intro',
  's3_md_walk',
];

function chatMockupBlock(lang: string): Record<string, string> {
  const file = path.join(process.cwd(), 'locales', lang, 'translation.json');
  const data = JSON.parse(readFileSync(file, 'utf8')) as {
    landing: { chat_mockup: Record<string, string> };
  };
  return data.landing.chat_mockup;
}

describe('hero mockup timelines', () => {
  it('exposes the four acts in showcase order', () => {
    expect(SCENARIOS.map(s => s.id)).toEqual(['orchestrate', 'anticipate', 'call', 'create']);
  });

  it.each(SCENARIOS.map(s => [s.id, s] as const))('%s timeline is well-formed', (_id, s) => {
    const kinds = s.steps.map(step => step.kind);
    const times = s.steps.map(step => step.at);

    // Strictly increasing reveal times, unique kinds.
    expect([...times].sort((a, b) => a - b)).toEqual(times);
    expect(new Set(times).size).toBe(times.length);
    expect(new Set(kinds).size).toBe(kinds.length);

    // Shared grammar: typing precedes the user bubble; the act settles before fading.
    expect(kinds.slice(0, 2)).toEqual(['type', 'user']);
    expect(s.holdMs).toBeGreaterThanOrEqual(times[times.length - 1] + 800);

    // Backstage window is present and ordered.
    expect(kinds).toContain('bs');
    expect(kinds).toContain('bs_end');
    expect(kinds.indexOf('bs')).toBeLessThan(kinds.indexOf('bs_end'));

    // Stream windows and the token tick reference real steps of this act.
    for (const [from, to] of s.streamWindows) {
      expect(kinds).toContain(from);
      expect(kinds).toContain(to);
      expect(kinds.indexOf(from)).toBeLessThan(kinds.indexOf(to));
    }
    expect(kinds).toContain(s.tokenbar.tickAt);

    // The token bar honestly starts at zero and ends with a real bill.
    expect(s.tokenbar.start).toEqual({ totalTokens: 0, messages: 0, costEur: 0 });
    expect(s.tokenbar.end.totalTokens).toBeGreaterThan(0);
    expect(s.tokenbar.end.costEur).toBeGreaterThan(0);
  });

  it('covers every act with footers and backstage costs', () => {
    const ids = SCENARIOS.map(s => s.id);
    expect(Object.keys(SCENARIO_FOOTERS).sort()).toEqual([...ids].sort());
    expect(Object.keys(BACKSTAGE_COSTS).sort()).toEqual([...ids].sort());
  });

  it('renders a valid static frame under reduced motion (act 1 subset)', () => {
    const act1Kinds = new Set(SCENARIOS[0].steps.map(step => step.kind));
    for (const kind of REDUCED_MOTION_KINDS) {
      expect(act1Kinds.has(kind)).toBe(true);
    }
    // No backstage in the static frame: the glass never opens.
    expect(REDUCED_MOTION_KINDS.has('bs')).toBe(false);
  });
});

describe('hero mockup i18n contract', () => {
  const blocks = Object.fromEntries(LANGS.map(lang => [lang, chatMockupBlock(lang)]));

  it.each(LANGS)('%s carries every referenced key, non-empty', lang => {
    for (const key of REFERENCED_KEYS) {
      expect(blocks[lang][key], `${lang}:${key}`).toBeTruthy();
    }
  });

  it.each(LANGS)('%s has strict key parity with en', lang => {
    expect(Object.keys(blocks[lang]).sort()).toEqual(Object.keys(blocks.en).sort());
  });

  it.each(LANGS)('%s no longer carries legacy pre-backstage keys', lang => {
    for (const key of LEGACY_KEYS) {
      expect(blocks[lang][key], `${lang}:${key}`).toBeUndefined();
    }
  });

  it('references chip and user keys that exist for every act', () => {
    for (const s of SCENARIOS) {
      expect(blocks.en[s.chipKey], s.chipKey).toBeTruthy();
      expect(blocks.en[s.userKey], s.userKey).toBeTruthy();
    }
  });
});
