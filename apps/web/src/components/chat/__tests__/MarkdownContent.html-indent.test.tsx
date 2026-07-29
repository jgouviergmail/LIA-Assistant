/**
 * MarkdownContent — pretty-printed HTML card must render as HTML, not raw text.
 *
 * Root cause measured on prod (2026-07-29, two consecutive replies with the
 * identical `<div class="lia-response">` wrapper): the model intermittently
 * indents its card by 4 spaces AND leaves a blank line between blocks. A
 * CommonMark HTML block (type 6) ends at the first blank line; the next
 * 4-space-indented `<h2>` is then parsed as an INDENTED CODE block, so the rest
 * of the card renders as raw `<h2>…` TEXT. `stripHtmlBlockIndent` de-indents
 * the structural lines so every block tag restarts an HTML block.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { markImageLoaded, isImageLoaded } = vi.hoisted(() => ({
  markImageLoaded: vi.fn(),
  isImageLoaded: vi.fn(() => false),
}));
vi.mock('@/lib/image-cache', () => ({ markImageLoaded, isImageLoaded }));

import { MarkdownContent } from '../MarkdownContent';

const render = (content: string) => renderWithProviders(<MarkdownContent content={content} />);

beforeEach(() => {
  vi.clearAllMocks();
  isImageLoaded.mockReturnValue(false);
});

// The exact shape captured from prod: wrapper, then 4-space-indented tags with
// a blank line between the <p> and the <h2>.
const INDENTED_CARD = [
  '<div class="lia-response">',
  '    <p>Message reçu cinq sur cinq.</p>',
  '',
  '    <h2>Les derniers e-mails</h2>',
  '    <ul><li>Premier message</li></ul>',
  '</div>',
].join('\n');

describe('MarkdownContent — pretty-printed HTML card', () => {
  it('renders an indented card as HTML, never as raw text', () => {
    render(INDENTED_CARD);

    // The heading is a real level-2 heading, not text trapped in a code block.
    const heading = screen.getByRole('heading', { name: 'Les derniers e-mails', level: 2 });
    expect(heading.closest('pre')).toBeNull();
    expect(heading.closest('code')).toBeNull();

    // The list item rendered as a list item, not literal source.
    expect(screen.getByText('Premier message')).toBeTruthy();

    // The literal tag source must appear nowhere as visible text.
    expect(screen.queryByText(/<h2>Les derniers e-mails<\/h2>/)).toBeNull();
  });

  it('leaves a column-0 card untouched (control)', () => {
    render('<div class="lia-response">\n<p>Bonjour</p>\n\n<h2>Titre</h2>\n</div>');
    expect(screen.getByRole('heading', { name: 'Titre', level: 2 })).toBeTruthy();
  });

  it('never de-indents a Markdown answer with a legitimate indented code block', () => {
    // Does NOT start with a block-level HTML tag → the 4-space-indented code
    // block must survive as a code block, its indentation intact.
    render('Un exemple de code :\n\n    const x = 1;\n    return x;\n');
    const code = screen.getByText(/const x = 1;/);
    expect(code.closest('pre')).not.toBeNull();
  });
});
