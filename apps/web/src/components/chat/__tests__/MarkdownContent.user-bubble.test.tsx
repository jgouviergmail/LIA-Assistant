/**
 * A person's bubble shows what they typed.
 *
 * `pas </script>, </body> et </html>` reached the bubble as `pas ,  et ` while
 * the database and the model held it whole (production, 2026-11-04): the bubble
 * went through the pipeline built for LIA's HTML answers, and six of the 733
 * messages stored there lost words that way, generics like `<ScoreService>`
 * among them.
 */
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/__tests__/test-utils';

import { MarkdownContent } from '../MarkdownContent';

const bubble = (content: string) =>
  renderWithProviders(<MarkdownContent content={content} isUser />).container;

describe('MarkdownContent — a person bubble', () => {
  it.each([
    ['closing tags', 'pas </script>, </body> et </html>'],
    ['quoted closing tags', '"pas de </script>, </body> et </html>"'],
    ['a comparison the parser reads as a tag', 'if a<b and c>d'],
    ['generics', 'Mock<ScoreService> et List<WorkboardTicket>'],
    ['an opening tag', 'la balise <img src=x onerror=alert(1)> casse'],
    ['a comment', 'avant <!-- note --> après'],
  ])('keeps %s word for word', (_name, typed) => {
    expect(bubble(typed).textContent).toBe(typed);
  });

  it('keeps a pasted block, on its own lines', () => {
    const typed = '<div>\n  <p>texte</p>\n</div>';
    const container = bubble(typed);
    expect(container.textContent).toBe(typed);
    expect(container.querySelector('p')?.className).toContain('whitespace-pre-wrap');
  });

  it('creates no element from what was typed', () => {
    const container = bubble('<script>alert(1)</script> <img src=x onerror=alert(1)> <b>gras</b>');
    expect(container.querySelector('script, img, b')).toBeNull();
  });

  it('keeps reading Markdown: the bubble is not plain text', () => {
    const container = bubble('**gras** et `code` et [lien](https://example.org)');
    expect(container.querySelector('strong')?.textContent).toBe('gras');
    expect(container.querySelector('code')?.textContent).toBe('code');
    expect(container.querySelector('a')?.getAttribute('href')).toBe('https://example.org');
  });

  it('keeps an autolink, which the Markdown parser reads before any tag', () => {
    expect(bubble('<https://example.org>').querySelector('a')).not.toBeNull();
  });

  it('keeps a fenced block verbatim', () => {
    const container = bubble('```html\n<b>x</b>\n```');
    expect(container.textContent).toContain('<b>x</b>');
  });

  it('changes nothing for an answer of LIA: its HTML stays HTML', () => {
    const { container } = renderWithProviders(
      <MarkdownContent content={'<div class="lia-response"><p><strong>oui</strong></p></div>'} />
    );
    expect(container.querySelector('.lia-response strong')?.textContent).toBe('oui');
  });
});
