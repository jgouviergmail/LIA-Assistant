/**
 * A Markdown file laid out (ADR-369, lot 14): its author's words as React draws them, so nothing
 * in it runs; nothing in it reaches a third party when it opens, which is why a picture is its
 * caption; and a link opens in a tab that cannot reach back.
 */
import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';

import { MarkdownViewer } from '../MarkdownViewer';

function show(text: string) {
  return renderWithProviders(<MarkdownViewer text={text} name="notes.md" />);
}

describe('MarkdownViewer', () => {
  it('lays out headings, lists and tables', () => {
    show('# Title\n\n- one\n\n| A | B |\n|---|---|\n| 1 | 2 |\n');

    expect(screen.getByRole('heading', { level: 1, name: 'Title' })).toBeInTheDocument();
    expect(screen.getByRole('listitem')).toHaveTextContent('one');
    expect(within(screen.getByRole('table')).getByText('2')).toBeInTheDocument();
  });

  it('can be reached and scrolled by the keyboard', () => {
    show('# Title');

    expect(screen.getByRole('region', { name: 'notes.md' })).toHaveAttribute('tabindex', '0');
  });

  it('opens a link in a tab that cannot reach back', () => {
    show('[site](https://example.org/)');

    const link = screen.getByRole('link', { name: 'site' });
    expect(link).toHaveAttribute('href', 'https://example.org/');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('keeps the words of a link that may not be followed', () => {
    show('[trap](javascript:alert(1))');

    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('trap')).toBeInTheDocument();
  });

  it('keeps the words of a link that hides where it goes', () => {
    show('[bank](https://bank.example@evil.example/)');

    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('bank')).toBeInTheDocument();
  });

  it('draws a picture as its caption, and asks nobody for it', () => {
    show('![A tracker](https://tracker.example/p.gif)');

    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getByText('A tracker')).toBeInTheDocument();
  });

  it('never runs what the file writes as HTML', () => {
    const { container } = show('<script>alert(1)</script><img src=x onerror=alert(1)>\n\nHello');

    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(container).not.toHaveTextContent('onerror');
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });
});
