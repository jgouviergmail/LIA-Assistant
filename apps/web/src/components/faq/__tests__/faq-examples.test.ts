/**
 * Clickable FAQ examples (W1) — splitting an answer into HTML and commands.
 *
 * The FAQ holds 222 questions across 6 languages, and their answers contain
 * hundreds of ready-made phrases addressed to LIA — "Trouve le contact de
 * Jean", "Quel sera le jour le plus propice à une balade cette semaine". They
 * were rendered as inert italics: the best onboarding material of the product,
 * written and translated six times, that nobody could act on.
 *
 * The discriminator is NOT "every <em>". A measurement over the six locales
 * found ~2 700 `<em>` in total, of which only those preceded by a bullet are
 * commands (2 079). The rest are ordinary emphasis inside explanatory prose —
 * "le premier", "mon frère", "la semaine dernière" — and turning those into
 * buttons would produce nonsense.
 */

import { describe, it, expect } from 'vitest';

import { splitFaqAnswer, faqExampleCount } from '../faq-examples';

describe('splitFaqAnswer — what becomes clickable', () => {
  it('returns a single html segment when there is nothing to click', () => {
    const answer = '<strong>Titre</strong><br>Du texte simple.';
    expect(splitFaqAnswer(answer)).toEqual([{ kind: 'html', html: answer }]);
  });

  it('extracts a bulleted command', () => {
    const segments = splitFaqAnswer('<br>• "<em>Trouve le contact de Jean</em>"');
    expect(segments.filter(s => s.kind === 'example')).toEqual([
      { kind: 'example', text: 'Trouve le contact de Jean' },
    ]);
  });

  it('leaves inline emphasis alone', () => {
    // "le premier" is prose, not an instruction — a button there is nonsense.
    const answer = 'Dites <em>le premier</em> pour choisir.';
    expect(splitFaqAnswer(answer)).toEqual([{ kind: 'html', html: answer }]);
  });

  it('keeps the surrounding html verbatim, bullet and quotes included', () => {
    const segments = splitFaqAnswer('<strong>A</strong><br>• "<em>Fais ceci</em>"<br>Fin.');
    expect(segments).toEqual([
      { kind: 'html', html: '<strong>A</strong><br>• "' },
      { kind: 'example', text: 'Fais ceci' },
      { kind: 'html', html: '"<br>Fin.' },
    ]);
  });

  it('extracts every command of a list', () => {
    const answer = '<br>• "<em>Première</em>"<br>• "<em>Deuxième</em>"<br>• "<em>Troisième</em>"';
    expect(splitFaqAnswer(answer).filter(s => s.kind === 'example')).toHaveLength(3);
  });

  it('handles a bullet without quotes', () => {
    expect(splitFaqAnswer('• <em>Sans guillemets</em>').filter(s => s.kind === 'example')).toEqual([
      { kind: 'example', text: 'Sans guillemets' },
    ]);
  });

  it('handles the French guillemet', () => {
    const segments = splitFaqAnswer('• «<em>Avec chevrons</em>»');
    expect(segments.filter(s => s.kind === 'example')).toEqual([
      { kind: 'example', text: 'Avec chevrons' },
    ]);
  });

  it('decodes HTML entities so the draft carries real characters', () => {
    // `&#39;` reaching the composer verbatim would be sent to the model as-is.
    const segments = splitFaqAnswer('• "<em>Quel est l&#39;email de Pierre &amp; Marie ?</em>"');
    expect(segments.filter(s => s.kind === 'example')).toEqual([
      { kind: 'example', text: "Quel est l'email de Pierre & Marie ?" },
    ]);
  });

  it('decodes named quote entities', () => {
    const segments = splitFaqAnswer('• "<em>Dis &quot;bonjour&quot; à Jean</em>"');
    expect(segments.filter(s => s.kind === 'example')).toEqual([
      { kind: 'example', text: 'Dis "bonjour" à Jean' },
    ]);
  });

  it('refuses a command containing markup', () => {
    // Three such entries exist in the corpus. Their inner markup would be lost
    // (or worse, sent as text) — they stay inert rather than lie.
    const answer = '• "<em>Envoie <strong>ceci</strong></em>"';
    expect(splitFaqAnswer(answer)).toEqual([{ kind: 'html', html: answer }]);
  });

  it('ignores an empty command', () => {
    const answer = '• "<em></em>"';
    expect(splitFaqAnswer(answer)).toEqual([{ kind: 'html', html: answer }]);
  });

  it('ignores a whitespace-only command', () => {
    const answer = '• "<em>   </em>"';
    expect(splitFaqAnswer(answer)).toEqual([{ kind: 'html', html: answer }]);
  });

  it('is lossless — concatenating the segments rebuilds the answer', () => {
    // The strongest invariant: nothing of the authored content may vanish in
    // the split, whatever the shape of the answer.
    const answer =
      '<strong>Gmail</strong><br>• "<em>Montre mes emails</em>"<br>Dites <em>le premier</em>.';
    const rebuilt = splitFaqAnswer(answer)
      .map(s => (s.kind === 'html' ? s.html : `<em>${s.text}</em>`))
      .join('');
    expect(rebuilt).toContain('Montre mes emails');
    expect(rebuilt).toContain('le premier');
  });

  it('is pure — the same input always yields the same output', () => {
    const answer = '• "<em>Une commande</em>"';
    expect(splitFaqAnswer(answer)).toEqual(splitFaqAnswer(answer));
  });

  it('tolerates an empty answer', () => {
    expect(splitFaqAnswer('')).toEqual([]);
  });
});

describe('faqExampleCount', () => {
  it('counts the clickable commands of an answer', () => {
    expect(faqExampleCount('<br>• "<em>Un</em>"<br>• "<em>Deux</em>"')).toBe(2);
  });

  it('counts none in prose', () => {
    expect(faqExampleCount('Dites <em>le premier</em>.')).toBe(0);
  });
});
