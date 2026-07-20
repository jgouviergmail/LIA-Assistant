/**
 * Tests for the toast preview flattener.
 *
 * Toast descriptions render as escaped React children, so markup shows up as
 * literal text. The 2026-07 regression surfaced exactly the payload asserted
 * below on scheduled-action notifications.
 */

import { describe, it, expect } from 'vitest';
import { toPlainPreview, NOTIFICATION_PREVIEW_MAX_LENGTH } from '@/lib/notification-preview';

describe('toPlainPreview', () => {
  it('flattens the observed regression payload', () => {
    const raw =
      '<div class="lia-response">\n<h2>Technologies 2026 : le monde tourne encore sans IA</h2>\n<p>On respire un peu.</p>\n</div>';

    const out = toPlainPreview(raw);

    expect(out).not.toContain('<');
    expect(out).not.toContain('lia-response');
    expect(out).toBe('Technologies 2026 : le monde tourne encore sans IA On respire un peu.');
  });

  it('leaves prose with bare angle brackets intact', () => {
    // The guard that justifies tag detection: blind stripping would delete
    // "< 5 and y >" from this sentence.
    const text = "x < 5 and y > 3 donc c'est bon";
    expect(toPlainPreview(text)).toBe(text);
  });

  it.each([
    'if x<a and b>c: return True',
    'vérifie que count<b et total>i',
    'vector<i> v; map<p,tr> m;',
  ])('does not treat unpaired angle brackets as markup: %s', prose => {
    // A lone `<tag` is not HTML — single-letter names collide with prose.
    // Detecting these mutilated the text ("if x<a and b>c" -> "if xc").
    expect(toPlainPreview(prose)).toBe(prose);
  });

  it.each(['<p>hello</p>', 'ligne1<br>ligne2', '<div class="lia-response"><p>document tronqué'])(
    'still detects real markup: %s',
    markup => {
      expect(toPlainPreview(markup)).not.toContain('<');
    }
  );

  it('leaves markdown untouched', () => {
    const text = '**Salut** ! Voici # un titre et - une liste';
    expect(toPlainPreview(text)).toBe(text);
  });

  it('drops style block contents entirely', () => {
    const out = toPlainPreview(
      '<div class="lia-response"><style>.x{color:red}</style><p>Bonjour</p></div>'
    );
    expect(out).not.toContain('color');
    expect(out).toBe('Bonjour');
  });

  it('decodes the entities the backend stripper would have decoded', () => {
    expect(toPlainPreview('<p>Caf&eacute;</p>')).toBe('Caf&eacute;'); // unknown entity kept verbatim
    expect(toPlainPreview('<p>Tom &amp; Jerry &lt;3</p>')).toBe('Tom & Jerry <3');
  });

  it('drops Material Symbols ligature names', () => {
    // Regression: a data card read "event Déjeuner avec Marie" in the toast.
    const out = toPlainPreview(
      '<div class="lia-illus"><span class="material-symbols-outlined">event</span></div><p>Déjeuner à 12h30</p>'
    );
    expect(out).toBe('Déjeuner à 12h30');
  });

  it('strips icon spans with either quote style', () => {
    expect(
      toPlainPreview("<span class='material-symbols-outlined'>event</span><p>Bonjour</p>")
    ).toBe('Bonjour');
  });

  it('does not let an unclosed icon span swallow neighbouring prose', () => {
    // `[^<]*` (not `[\s\S]*?`) bounds the match to the span's own text.
    const out = toPlainPreview(
      '<span class="material-symbols-outlined">event<p>Message important</p>'
    );
    expect(out).toContain('Message important');
  });

  it('keeps the same word when it appears in real prose', () => {
    expect(toPlainPreview('<p>Un event important a lieu demain.</p>')).toBe(
      'Un event important a lieu demain.'
    );
  });

  it('collapses to a single line', () => {
    expect(toPlainPreview('<p>Un</p><p>Deux</p><p>Trois</p>')).toBe('Un Deux Trois');
  });

  it('does not truncate when no budget is given', () => {
    const text = 'a'.repeat(500);
    expect(toPlainPreview(text)).toHaveLength(500);
  });

  it('ellipsizes beyond the budget, measured on the flattened text', () => {
    // Regression: slicing the RAW html spent 26 of the budget on the wrapper.
    const raw = `<div class="lia-response"><p>${'a'.repeat(300)}</p></div>`;

    const out = toPlainPreview(raw, NOTIFICATION_PREVIEW_MAX_LENGTH);

    expect(out).toBe(`${'a'.repeat(NOTIFICATION_PREVIEW_MAX_LENGTH)}...`);
  });

  it('does not append an ellipsis at exactly the budget', () => {
    const text = 'a'.repeat(NOTIFICATION_PREVIEW_MAX_LENGTH);
    expect(toPlainPreview(text, NOTIFICATION_PREVIEW_MAX_LENGTH)).toBe(text);
  });

  it('returns an empty string for empty input', () => {
    expect(toPlainPreview('', 10)).toBe('');
  });

  it('stays stable across interleaved calls', () => {
    // The module-level patterns carry the `g` flag, whose `lastIndex` persists
    // between `test`/`exec` calls — a classic source of results that differ on
    // the second invocation. Guards the detection against that regression.
    for (let i = 0; i < 5; i++) {
      expect(toPlainPreview('<p>AAA</p>')).toBe('AAA');
      expect(toPlainPreview('<span class="material-symbols-outlined">mail</span><p>BBB</p>')).toBe(
        'BBB'
      );
      expect(toPlainPreview('prose x<a and b>c')).toBe('prose x<a and b>c');
    }
  });

  it('is idempotent', () => {
    const once = toPlainPreview('<div class="lia-response"><p>Salut</p></div>');
    expect(toPlainPreview(once)).toBe(once);
  });
});
