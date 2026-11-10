/** Real producer titles keep their presentation when their source becomes a native tool. */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { act, render as renderRaw, screen, fireEvent } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import apiClient from '@/lib/api-client';
import { MarkdownContent } from '../MarkdownContent';
import { CardToolsAvailable } from './card-target-fixtures';
const render = (ui: ReactElement) => renderRaw(ui, { wrapper: CardToolsAvailable });

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
const samples = references.filter(
  value => value.language === 'en' && ['enveloppes', 'native_details'].includes(value.id)
);

describe('native item navigation on actual card HTML', () => {
  it.each(samples)('$id preserves source labels, icons and contextual links', reference => {
    const original = new DOMParser().parseFromString(reference.html, 'text/html');
    const sources = original.querySelectorAll<HTMLAnchorElement>(
      '.lia-contact a.lia-card-top__title, .lia-event a.lia-card-top__title, .lia-task a.lia-card-top__title, .lia-file a.lia-card-top__title, .lia-email a.lia-email__subject'
    );
    expect(sources.length).toBeGreaterThan(0);
    const { container } = render(<MarkdownContent content={reference.html} />);
    for (const collection of container.querySelectorAll<HTMLDetailsElement>(
      '.lia-card-collection'
    )) {
      act(() => {
        collection.open = true;
        fireEvent(collection, new Event('toggle'));
      });
    }
    for (const source of sources) {
      const title = screen.getByRole('button', { name: source.textContent ?? '' });
      expect(title).toHaveClass(...source.classList);
      expect(title).not.toHaveAttribute('href');
      expect(title).toHaveTextContent(source.textContent ?? '');
      const sourceAction = source
        .closest('.lia-card')
        ?.querySelector<HTMLAnchorElement>('[data-card-open="true"]');
      if (sourceAction) {
        const nativeAction = title.closest('.lia-card')?.querySelector('button.lia-action-btn');
        expect(nativeAction).toHaveAccessibleName('card_tools.open_item');
        expect(nativeAction?.querySelector('.lia-action-btn__icon')?.textContent).toBe(
          sourceAction.querySelector('.lia-action-btn__icon')?.textContent
        );
      }
    }
    for (const contextual of original.querySelectorAll<HTMLAnchorElement>(
      'a[href^="mailto:"], a[href^="tel:"], a[href*="meet.google.com"], a[href*="maps.google.com"]'
    )) {
      const retained = [...container.querySelectorAll('a')].find(
        link => link.getAttribute('href') === contextual.getAttribute('href')
      );
      expect(retained).toBeDefined();
    }
  });

  it('keeps a supplied title and accessible name through keyboard-equivalent conversion', () => {
    const post = vi.spyOn(apiClient, 'post');
    render(
      <MarkdownContent
        content={
          '<div class="lia-card lia-contact"><a class="lia-card-top__title" title="Full supplied name" aria-label="Read full contact" style="font-weight:700" href="https://contacts.google.com/person/old">Short name</a></div>'
        }
      />
    );
    const title = screen.getByRole('button', { name: 'Read full contact' });
    expect(title).toHaveAttribute('title', 'Full supplied name');
    expect(title).toHaveStyle({ fontWeight: '700' });
    fireEvent.click(title);
    expect(screen.getByRole('status')).toHaveTextContent('card_tools.historical');
    expect(post).not.toHaveBeenCalled();
    post.mockRestore();
  });
});
