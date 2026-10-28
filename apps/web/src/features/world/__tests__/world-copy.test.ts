import { createInstance, type TFunction } from 'i18next';
import { describe, expect, it } from 'vitest';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import de from '../../../../locales/de/translation.json';
import es from '../../../../locales/es/translation.json';
import itLocale from '../../../../locales/it/translation.json';
import zh from '../../../../locales/zh/translation.json';
import { EMOTES } from '../emote-catalogue';

const LOCALES = { en, fr, de, es, it: itLocale, zh } as const;
type Lang = keyof typeof LOCALES;
const LANGS = Object.keys(LOCALES) as Lang[];
async function translator(lng: Lang): Promise<TFunction> {
  const instance = createInstance();
  await instance.init({
    lng,
    interpolation: { escapeValue: false },
    resources: { [lng]: { translation: LOCALES[lng] } },
  });
  return instance.t;
}
function leaves(node: unknown, prefix: string): [string, string][] {
  if (typeof node === 'string') return [[prefix, node]];
  if (!node || typeof node !== 'object') return [];
  return Object.entries(node).flatMap(([key, value]) => leaves(value, prefix + '.' + key));
}

describe('World copy resolved by the real i18next', () => {
  it.each(LANGS)('pluralises the board progress in %s', async lng => {
    const t = await translator(lng);
    const one = t('world.arcade.progress', { count: 1 });
    const many = t('world.arcade.progress', { count: 5 });
    expect(one).toContain('1');
    expect(many).toContain('5');
    expect(one).not.toBe('world.arcade.progress');
    if (lng !== 'zh') expect(one.replace('1', '5')).not.toBe(many);
  });
  it.each(LANGS)('never reads a counted Leave as the other-cabinet action in %s', async lng => {
    const t = await translator(lng);
    expect(t('world.arcade.leave', { count: 2 })).toBe(LOCALES[lng].world.arcade.leave);
    expect(t('world.arcade.leave_other_cabinet')).toBe(
      LOCALES[lng].world.arcade.leave_other_cabinet
    );
  });
  it.each(LANGS)('announces every gesture as a sentence about its author in %s', async lng => {
    const t = await translator(lng);
    for (const kind of EMOTES) {
      const sentence = t('world.emotes.announcements.' + kind, { alias: 'Léa' });
      expect(sentence).toContain('Léa');
      expect(sentence).not.toMatch(/[:：]/);
      // Chinese verbs do not inflect; elsewhere the menu's infinitive is never pasted in.
      if (lng !== 'zh') expect(sentence).not.toContain(LOCALES[lng].world.emotes[kind]);
    }
  });
  it.each(LANGS)('gives the computer sentences of its own in %s', async lng => {
    const t = await translator(lng);
    const words = LOCALES[lng].world.arcade;
    expect(t('world.arcade.computer_turn')).not.toBe(
      t('world.arcade.other_turn', { player: words.computer_name })
    );
    expect(t('world.arcade.computer_won')).not.toBe(
      t('world.arcade.other_won', { player: words.computer_name })
    );
  });
});

it('keeps the World in its informal register: tu, du and 你, never vous, Sie or 您', () => {
  // Addressing both players at once is a genuine plural, not the formal register.
  const plural = new Set(['world.arcade.games.tic_tac_toe.rules']);
  const formal = {
    fr: /\b(vous|votre|vos)\b/i,
    de: /\b(Sie|Ihr|Ihre|Ihren|Ihrem|Ihrer|Ihres|Ihnen)\b/,
    zh: /您/,
  } as const;
  for (const lng of ['fr', 'de', 'zh'] as const) {
    const found = leaves(LOCALES[lng].world, 'world').filter(
      ([key, value]) => !plural.has(key) && formal[lng].test(value)
    );
    expect(found).toEqual([]);
  }
});
