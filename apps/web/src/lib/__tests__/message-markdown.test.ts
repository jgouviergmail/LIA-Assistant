/**
 * message-markdown — the `.md` an assistant answer is downloaded and e-mailed as.
 *
 * An answer is Markdown, a `lia-response` HTML document, or Markdown followed
 * by the HTML the response node appends (data cards, widget sentinels). Only
 * the HTML is rewritten: the model's Markdown — fenced code quoting HTML
 * included — reaches the file byte for byte.
 */
import { describe, expect, it } from 'vitest';

import { messageToMarkdown } from '../message-markdown';
import {
  ARCHIVED_HTML_ANSWER,
  EVENT_CARD,
  MARKDOWN_WITH_SKILL_WIDGET,
} from './fixtures/assistant-html-corpus';

const OPTIONS = { labelSeparator: ': ' };

function convert(content: string): string {
  return messageToMarkdown(content, OPTIONS);
}

describe('a Markdown answer', () => {
  it('is returned untouched', () => {
    const answer = '# Été\n\nRéponse **markdown**  \navec un saut.\n\n    code indenté\n';

    expect(convert(answer)).toBe(answer);
  });

  it('keeps a fenced block that QUOTES HTML exactly as written', () => {
    const answer = [
      'Voici le composant :',
      '',
      '```html',
      '<div class="lia-card">',
      '  <p>Bonjour</p>',
      '</div>',
      '```',
      '',
      'Et la suite **en gras**.',
    ].join('\n');

    expect(convert(answer)).toBe(answer);
  });

  it('keeps prose that merely compares values', () => {
    expect(convert('if x<a and b>c then 3 < 4')).toBe('if x<a and b>c then 3 < 4');
  });
});

describe('an HTML answer', () => {
  it('is converted whole even when its document spans blank lines', () => {
    const out = convert(ARCHIVED_HTML_ANSWER);

    expect(out).toContain('## 6. Tendances et direction stratégique');
    expect(out).toContain('| Tendance | Direction observée |');
    expect(out).not.toMatch(/<\/?(div|p|h\d|ul|li|table|tr|td|strong|code|blockquote)\b/);
  });

  it('survives a document cut before its end', () => {
    expect(convert('<div class="lia-response"><h2>Titre</h2><p>Coupé en plein')).toBe(
      '## Titre\n\nCoupé en plein'
    );
  });
});

describe('Markdown followed by the HTML the response node appends', () => {
  it('keeps the Markdown verbatim and drops a widget that exists only on screen', () => {
    const markdown = MARKDOWN_WITH_SKILL_WIDGET.slice(
      0,
      MARKDOWN_WITH_SKILL_WIDGET.indexOf('<div')
    ).trimEnd();

    const out = convert(MARKDOWN_WITH_SKILL_WIDGET);

    expect(out).toBe(markdown);
    // The hard breaks of the haiku are the Markdown's own: two trailing spaces.
    expect(out).toContain('> **Mock et stub dansent**  \n> **Sur la scène du test blanc**');
    expect(out).not.toContain('Chargement');
  });

  it('writes the cards after the Markdown, without a rule before them', () => {
    const out = convert(`Ton prochain rendez-vous :\n\n${EVENT_CARD}`);

    expect(out.startsWith('Ton prochain rendez-vous :\n\n### [Revue de sprint](')).toBe(true);
  });

  it('keeps Markdown that follows an HTML block', () => {
    expect(convert('<div class="lia-response"><p>Un</p></div>\n\n**Deux**\n\n- a\n- b')).toBe(
      'Un\n\n**Deux**\n\n- a\n- b'
    );
  });

  it('reads an HTML line inside a fence as code, and one outside as markup', () => {
    const answer = '```\n<p>code</p>\n```\n\n<p>Vrai <em>HTML</em></p>';

    expect(convert(answer)).toBe('```\n<p>code</p>\n```\n\nVrai *HTML*');
  });

  it('answers nothing for an answer that is only a widget', () => {
    expect(
      convert(
        '<div class="lia-skill-app" data-registry-id="x"><div class="lia-skill-app__loading">Chargement…</div></div>'
      )
    ).toBe('');
  });
});
