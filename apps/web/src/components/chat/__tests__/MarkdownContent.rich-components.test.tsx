/**
 * MarkdownContent — rich-HTML component vocabulary (ADR-177).
 *
 * Pins that every component the HTML response directive advertises renders as
 * real DOM with its classes intact (classes drive all styling), that the
 * language-* code path reaches CodeBlock, and that a truncated stream never
 * leaks raw tag source as visible text.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { markImageLoaded, isImageLoaded } = vi.hoisted(() => ({
  markImageLoaded: vi.fn(),
  isImageLoaded: vi.fn(() => false),
}));
vi.mock('@/lib/image-cache', () => ({ markImageLoaded, isImageLoaded }));
// Alias specifier on purpose: MarkdownContent lazy-imports
// '@/components/chat/CodeBlock' — mocking the same specifier guarantees the
// resolution matches (pattern of the sibling tests mocking '@/lib/image-cache').
vi.mock('@/components/chat/CodeBlock', () => ({
  CodeBlock: ({ language, children }: { language: string; children: string }) => (
    <div data-testid="codeblock" data-language={language}>
      {children}
    </div>
  ),
}));

import { MarkdownContent } from '../MarkdownContent';

const render = (content: string) => renderWithProviders(<MarkdownContent content={content} />);

beforeEach(() => {
  vi.clearAllMocks();
  isImageLoaded.mockReturnValue(false);
});

const RICH_FIXTURE = [
  '<div class="lia-response">',
  '<h2>Synthèse</h2>',
  '<div class="lia-callout lia-callout-success">',
  '<p class="lia-callout__title">Tout est prêt</p>',
  '<p>Corps du callout.</p>',
  '</div>',
  '<p>Statut : <span class="lia-chip lia-chip--green">' +
    '<span class="material-symbols-outlined">check_circle</span>Confirmé</span></p>',
  '<dl class="lia-kv"><dt>Date</dt><dd><strong>12 août</strong></dd>' +
    '<dt>Lieu</dt><dd>Paris</dd></dl>',
  '<div class="lia-columns"><div><h3>Option A</h3><p>a</p></div>' +
    '<div><h3>Option B</h3><p>b</p></div></div>',
  '<ol class="lia-steps"><li>Préparer</li><li>Envoyer</li></ol>',
  '<div class="lia-stats"><div class="lia-stat">' +
    '<span class="lia-stat__value">12</span>' +
    '<span class="lia-stat__label">rendez-vous</span></div></div>',
  '<details class="lia-collapsible" open><summary>Détails</summary><p>corps</p></details>',
  '<p>Raccourci <kbd>Ctrl</kbd>+<kbd>K</kbd>, point <mark>décisif</mark>, ' +
    '<abbr title="Application Programming Interface">API</abbr>.</p>',
  '<pre><code class="language-python">print("x")</code></pre>',
  '</div>',
].join('\n');

describe('MarkdownContent — rich component vocabulary', () => {
  it('renders every advertised component with its classes intact', () => {
    const { container } = render(RICH_FIXTURE);

    expect(screen.getByRole('heading', { name: 'Synthèse', level: 2 })).toBeTruthy();
    expect(
      container.querySelector('.lia-callout.lia-callout-success .lia-callout__title')
        ?.textContent
    ).toBe('Tout est prêt');
    expect(container.querySelector('.lia-chip.lia-chip--green')).not.toBeNull();
    expect(container.querySelector('.lia-chip .material-symbols-outlined')?.textContent).toBe(
      'check_circle'
    );

    const kv = container.querySelector('dl.lia-kv');
    expect(kv?.querySelectorAll('dt')).toHaveLength(2);
    expect(kv?.querySelectorAll('dd')).toHaveLength(2);

    expect(container.querySelectorAll('.lia-columns > div')).toHaveLength(2);
    expect(container.querySelectorAll('ol.lia-steps > li')).toHaveLength(2);
    expect(container.querySelector('.lia-stat .lia-stat__value')?.textContent).toBe('12');
    expect(container.querySelector('.lia-stat .lia-stat__label')?.textContent).toBe(
      'rendez-vous'
    );

    const details = container.querySelector('details.lia-collapsible');
    expect(details?.hasAttribute('open')).toBe(true);
    expect(details?.querySelector('summary')?.textContent).toBe('Détails');

    expect(container.querySelectorAll('kbd')).toHaveLength(2);
    expect(container.querySelector('mark')?.textContent).toBe('décisif');
    expect(container.querySelector('abbr')?.getAttribute('title')).toContain('Programming');
  });

  it('routes language-classed code blocks to CodeBlock', async () => {
    render(RICH_FIXTURE);
    const block = await screen.findByTestId('codeblock');
    expect(block.getAttribute('data-language')).toBe('python');
    expect(block.textContent).toContain('print("x")');
  });

  it('never leaks raw tag source when the stream is cut mid-tag', () => {
    // Simulates an SSE snapshot ending in the middle of an opening tag: the
    // HTML tokenizer must drop the incomplete tag, not print it as text.
    const truncated = RICH_FIXTURE.slice(0, RICH_FIXTURE.indexOf('lia-callout-success') + 8);
    const { container } = render(truncated);
    expect(container.textContent).not.toMatch(/<(?:div|p|h2|span)/);
  });

  it('leaves markdown-mode content untouched (control)', () => {
    const { container } = render('**gras** et une liste :\n\n- item');
    expect(container.querySelector('.lia-response')).toBeNull();
    expect(screen.getByText('gras').tagName).toBe('STRONG');
  });
});
