/**
 * A code block of an HTML answer reaches the reader whole.
 *
 * The shape is the one measured on the production message of 2026-11-04: a
 * `<pre>` inside the `lia-response` block, with blank lines between functions.
 * CommonMark ended the HTML block at the first of them, the rest of the code
 * became paragraphs, and the last paragraph left the `<code>` when the HTML
 * parser met `</code></pre>`: the block lost its indentation, its blank lines,
 * and its whole tail, `reset();` and `</script>` included. The Copy button
 * handed that over, and a page whose `<script>` never closes runs nothing.
 */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

vi.mock('@/components/chat/CodeBlock', () => ({
  CodeBlock: ({ language, children }: { language: string; children: string }) => (
    <div data-testid="codeblock" data-language={language}>
      {children}
    </div>
  ),
}));

import { MarkdownContent } from '../MarkdownContent';

const CODE = `<!DOCTYPE html>
<html lang="fr">
<body>
<script>
var cells, current, over;

function winLine(p) {
  return lines.find(function (l) {
    return l.every(function (i) { return cells[i] === p; });
  }) || null;
}

function reset() {
  cells = Array(9).fill(null);
  render();
}

document.getElementById('reset').onclick = reset;
reset();
</script>
</body>
</html>`;

const escaped = (code: string) =>
  code.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

const ANSWER = `<div class="lia-response">
<p>Voici le jeu.</p>
<h2>Code complet</h2>
<pre><code class="language-html">${escaped(CODE)}</code></pre>
<h2>Utilisation</h2>
<ol class="lia-steps">
<li>Enregistre le fichier.</li>
</ol>
</div>`;

describe('MarkdownContent — a code block of an HTML answer', () => {
  it('shows the code exactly as stored, tail, indentation and blank lines included', async () => {
    renderWithProviders(<MarkdownContent content={ANSWER} />);
    const block = await screen.findByTestId('codeblock');
    expect(block.getAttribute('data-language')).toBe('html');
    expect(block.textContent).toBe(CODE);
  });

  it('keeps everything that follows the block', async () => {
    renderWithProviders(<MarkdownContent content={ANSWER} />);
    await screen.findByTestId('codeblock');
    expect(screen.getByRole('heading', { name: 'Utilisation' })).toBeTruthy();
    expect(screen.getByText('Enregistre le fichier.')).toBeTruthy();
    expect(screen.getAllByTestId('codeblock')).toHaveLength(1);
  });

  it('shows a block still being streamed, with what has arrived so far', async () => {
    const streamed = ANSWER.slice(0, ANSWER.indexOf('function reset'));
    renderWithProviders(<MarkdownContent content={streamed} />);
    const block = await screen.findByTestId('codeblock');
    expect(block.textContent).toContain(
      'var cells, current, over;\n\nfunction winLine(p) {\n  return'
    );
  });

  it('keeps a regex of the code, never read as a formula', async () => {
    const code = 'const r = /\\(a\\)/;\n\nconst t = /\\[b\\]/;';
    renderWithProviders(
      <MarkdownContent
        content={`<div class="lia-response">\n<pre><code class="language-js">${code}</code></pre>\n</div>`}
      />
    );
    const block = await screen.findByTestId('codeblock');
    expect(block.textContent).toBe(code);
  });

  it('keeps a shell variable of the code, never read as a formula', async () => {
    const code = 'echo "$HOME and $PATH"\n\necho $$';
    renderWithProviders(
      <MarkdownContent
        content={`<div class="lia-response">\n<pre><code class="language-bash">${code}</code></pre>\n</div>`}
      />
    );
    const block = await screen.findByTestId('codeblock');
    expect(block.textContent).toBe(code);
  });
});
