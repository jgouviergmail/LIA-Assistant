/**
 * The data cards an answer ends on, told apart from the words before them.
 *
 * The oracle is the server's own output: every entry of the card reference
 * corpus (`card_reference_corpus.json`, rendered by the backend's card
 * components) is appended to an answer exactly the way the response node does
 * it — `final_content + "\n\n" + cards` — and must come back whole, the words
 * untouched. The rest pins the refusals: whatever the split cannot recognise
 * with certainty renders as before.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { splitTrailingCards } from '../trailing-cards';

interface Reference {
  id: string;
  language: string;
  html: string;
}

const references: Reference[] = JSON.parse(
  readFileSync(
    join(process.cwd(), '../api/tests/unit/domains/agents/display/card_reference_corpus.json'),
    'utf8'
  )
);

const PROSE = 'Voici ce que j’ai trouvé pour toi.';
const BINDING =
  '<div class="lia-card-binding" data-card-ref="m1"><hr class="lia-response-separator">' +
  '<div class="lia-response-wrapper" data-card-version="2"><div class="lia-card lia-email">' +
  '<p>Votre réservation est confirmée.</p></div></div></div>';

describe('splitTrailingCards', () => {
  it.each(references.map(reference => [reference.id, reference.language, reference]))(
    'returns the server-rendered cards of %s (%s) whole',
    (_id, _language, reference) => {
      const split = splitTrailingCards(`${PROSE}\n\n${reference.html}`);
      expect(split).toEqual({ prose: PROSE, cards: reference.html });
    }
  );

  it('folds bound cards, one per line, with the overflow collection on the last line', () => {
    const cards =
      `${BINDING}\n${BINDING}<details class="lia-card-collection" data-card-version="2">` +
      `<summary>Voir plus <span>(1)</span></summary>` +
      `<div class="lia-card-collection__content">${BINDING}</div></details>`;
    expect(splitTrailingCards(`${PROSE}\n\n${cards}`)).toEqual({ prose: PROSE, cards });
  });

  it('keeps an html_cards answer document as the words', () => {
    const prose =
      '<div class="lia-response">\n<p>Ton agenda de demain.</p>\n\n<ul>\n<li>9 h</li>\n</ul>\n</div>';
    expect(splitTrailingCards(`${prose}\n\n${BINDING}`)).toEqual({ prose, cards: BINDING });
  });

  it('leaves the interactive widgets before the cards, outside the fold', () => {
    const prose = `${PROSE}\n\n<div class="lia-mcp-app" data-registry-id="w1"></div>`;
    expect(splitTrailingCards(`${prose}\n\n${BINDING}`)).toEqual({ prose, cards: BINDING });
  });

  it('does not fold a message made of cards alone: nothing would stay visible', () => {
    expect(splitTrailingCards(BINDING)).toBeNull();
    expect(splitTrailingCards(`\n\n  \n${BINDING}`)).toBeNull();
  });

  it('never folds a HITL draft card or an executed draft', () => {
    const draft = '<div class="lia-card lia-draft"><p>À : camille@example.test</p></div>';
    expect(splitTrailingCards(`${draft}\n\n---\n\nJe l’envoie ?`)).toBeNull();
    expect(splitTrailingCards(`${PROSE}\n\n${draft}`)).toBeNull();
    expect(
      splitTrailingCards(`${PROSE}\n\n<div class="lia-card lia-draft-result"><p>Envoyé</p></div>`)
    ).toBeNull();
  });

  it('does not fold when words follow the cards', () => {
    expect(splitTrailingCards(`${PROSE}\n\n${BINDING}\n\nAutre chose ?`)).toBeNull();
  });

  it('does not fold a tail that also holds something other than cards', () => {
    expect(
      splitTrailingCards(`${PROSE}\n\n${BINDING}\n<div class="lia-skill-app"></div>`)
    ).toBeNull();
  });

  it('does not take card markup quoted in an open code fence for cards', () => {
    expect(splitTrailingCards(`${PROSE}\n\n\`\`\`html\n${BINDING}`)).toBeNull();
  });

  it('does not cut a card nested inside another block', () => {
    const outer = `${PROSE}\n\n<div class="lia-response">\n${BINDING}\n</div>`;
    expect(splitTrailingCards(outer)).toBeNull();
  });

  it('refuses a card tail it cannot balance', () => {
    expect(splitTrailingCards(`${PROSE}\n\n${BINDING}</div>`)).toBeNull();
    expect(splitTrailingCards(`${PROSE}\n\n<div class="lia-card-binding"><p>open`)).toBeNull();
  });

  it('leaves an answer without cards alone', () => {
    expect(splitTrailingCards(PROSE)).toBeNull();
    expect(splitTrailingCards('')).toBeNull();
  });

  it('reads a long hostile answer in linear time', () => {
    const hostile = `${PROSE}\n\n${'<div class="lia-card-binding">\n'.repeat(20_000)}`;
    const started = performance.now();
    expect(splitTrailingCards(hostile)).toBeNull();
    expect(performance.now() - started).toBeLessThan(500);
  });
});
