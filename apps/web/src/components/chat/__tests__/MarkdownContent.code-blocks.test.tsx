/**
 * MarkdownContent — every block of code reaches CodeBlock.
 *
 * A fence with no language, a 4-space-indented block and a raw
 * `<pre><code>` used to fall through to the INLINE code branch (the routing
 * keyed on a `language-*` class alone): a 12 px chip inside a bare <pre> with
 * no header, no copy button and no scroll container — measured 2026-09-17 on
 * the running app. The block is the unit, whatever announced its language.
 */
import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

vi.mock('@/components/chat/CodeBlock', () => ({
  CodeBlock: ({ language, children }: { language: string; children: string }) => (
    <div data-testid="codeblock" data-language={language}>
      {children}
    </div>
  ),
}));

import { MarkdownContent } from '../MarkdownContent';

const render = (content: string) => renderWithProviders(<MarkdownContent content={content} />);

const LONG_LINE = 'def very_long_function_name(argument_one, argument_two, argument_three):';

describe('MarkdownContent — code block routing', () => {
  it('routes a fence with no language to CodeBlock as text', async () => {
    render('Voici :\n\n```\n' + LONG_LINE + '\n    return 1\n```\n');
    const block = await screen.findByTestId('codeblock');
    expect(block.getAttribute('data-language')).toBe('text');
    expect(block.textContent).toBe(LONG_LINE + '\n    return 1');
  });

  it('routes a 4-space-indented block to CodeBlock, indentation intact', async () => {
    render('Voici :\n\n    ' + LONG_LINE + '\n        return 1\n');
    const block = await screen.findByTestId('codeblock');
    expect(block.getAttribute('data-language')).toBe('text');
    expect(block.textContent).toBe(LONG_LINE + '\n    return 1');
  });

  it('routes a raw <pre><code> with no class to CodeBlock', async () => {
    render('Voici :\n\n<pre><code>' + LONG_LINE + '\n    return 1\n</code></pre>\n');
    const block = await screen.findByTestId('codeblock');
    expect(block.getAttribute('data-language')).toBe('text');
    expect(block.textContent).toBe(LONG_LINE + '\n    return 1');
  });

  it('routes an HTML-mode <pre><code> with no class to CodeBlock', async () => {
    render(
      '<div class="lia-response"><p>Voici.</p><pre><code>' +
        LONG_LINE +
        '\n</code></pre></div>'
    );
    const block = await screen.findByTestId('codeblock');
    expect(block.getAttribute('data-language')).toBe('text');
    expect(block.textContent).toBe(LONG_LINE);
  });

  it('keeps the language of a classed fence', async () => {
    render('```python\nprint("x")\n```\n');
    const block = await screen.findByTestId('codeblock');
    expect(block.getAttribute('data-language')).toBe('python');
  });

  it('leaves inline code inline (control)', () => {
    const { container } = render('Tape `npm test` puis Entrée.');
    expect(screen.queryByTestId('codeblock')).toBeNull();
    const inline = container.querySelector('code');
    expect(inline?.textContent).toBe('npm test');
    expect(inline?.closest('pre')).toBeNull();
  });

  it('renders no bare <pre> once the block is routed', async () => {
    const { container } = render('```\n' + LONG_LINE + '\n```\n');
    await screen.findByTestId('codeblock');
    expect(container.querySelector('pre')).toBeNull();
  });
});
