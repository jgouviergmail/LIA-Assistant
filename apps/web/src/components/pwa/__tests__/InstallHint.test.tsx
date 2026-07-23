/**
 * PWA install hint + share composition (UXR Lot 9, A6-9b) — the pure
 * visibility rule (visits threshold, forever-dismissal, standalone never)
 * and the share-target draft composition (clamped, parts optional).
 */

import { describe, it, expect } from 'vitest';

import { isInstallHintVisible } from '../InstallHint';
import { composeShareDraft } from '@/app/[lng]/share/page';
import { CHAT_INPUT_MAX_LENGTH, PWA_INSTALL_HINT_MIN_VISITS } from '@/lib/constants';

describe('isInstallHintVisible', () => {
  const base = { visits: PWA_INSTALL_HINT_MIN_VISITS, dismissed: false, standalone: false };

  it('shows from the visit threshold onwards', () => {
    expect(isInstallHintVisible(base)).toBe(true);
    expect(isInstallHintVisible({ ...base, visits: PWA_INSTALL_HINT_MIN_VISITS - 1 })).toBe(false);
  });

  it('never shows once dismissed or when already installed (standalone)', () => {
    expect(isInstallHintVisible({ ...base, dismissed: true })).toBe(false);
    expect(isInstallHintVisible({ ...base, standalone: true })).toBe(false);
  });
});

describe('composeShareDraft', () => {
  it('joins the present parts on separate lines', () => {
    expect(composeShareDraft('Titre', 'Un texte', 'https://ex.tld')).toBe(
      'Titre\nUn texte\nhttps://ex.tld'
    );
    expect(composeShareDraft(null, 'Texte seul', null)).toBe('Texte seul');
    expect(composeShareDraft('  ', null, 'https://ex.tld')).toBe('https://ex.tld');
  });

  it('returns empty when nothing was shared', () => {
    expect(composeShareDraft(null, null, null)).toBe('');
  });

  it('clamps at the chat input cap (A7 mirror)', () => {
    const long = 'x'.repeat(CHAT_INPUT_MAX_LENGTH + 500);
    expect(composeShareDraft(null, long, null)).toHaveLength(CHAT_INPUT_MAX_LENGTH);
  });
});
