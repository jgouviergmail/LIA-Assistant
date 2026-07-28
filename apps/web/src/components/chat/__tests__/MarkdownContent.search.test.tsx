/**
 * MarkdownContent — search highlight integration (QW-2).
 *
 * The `searchHighlight` prop appends the post-sanitize
 * `rehype-search-highlight` plugin: accent/case-insensitive matches must be
 * wrapped in fixed-class `<mark>` elements while code blocks stay untouched
 * (a mark inside code would break Prism re-tokenization).
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe('MarkdownContent — search highlight', () => {
  it('wraps accent-insensitive matches in fixed-class marks', () => {
    const { container } = render(
      <MarkdownContent content="Note la réunion de demain matin." searchHighlight="reunion" />
    );

    const marks = container.querySelectorAll('mark.lia-search-mark');
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe('réunion');
  });

  it('highlights inside the raw HTML the assistant emits', () => {
    const { container } = render(
      <MarkdownContent
        content={'<div class="lia-response"><p>Pizza margherita commandée</p></div>'}
        searchHighlight="pizza"
      />
    );

    const marks = container.querySelectorAll('mark.lia-search-mark');
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe('Pizza');
  });

  it('never marks inside code blocks', () => {
    const { container } = render(
      <MarkdownContent
        content={'Voici `pizza inline` et :\n\n```python\npizza = 1\n```\n\net pizza en texte.'}
        searchHighlight="pizza"
      />
    );

    const marks = container.querySelectorAll('mark.lia-search-mark');
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent?.toLowerCase()).toBe('pizza');
    expect(container.querySelector('code mark')).toBeNull();
  });

  it('renders without any mark when the prop is absent or empty', () => {
    const { container } = render(
      <MarkdownContent content="Pizza margherita" searchHighlight=" " />
    );
    expect(container.querySelector('mark')).toBeNull();

    const { container: c2 } = render(<MarkdownContent content="Pizza margherita" />);
    expect(c2.querySelector('mark')).toBeNull();
  });
});
