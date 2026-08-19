/**
 * One release's bullets, rendered the same way everywhere.
 *
 * Three surfaces quote a release — the landing band, the public history page
 * and the dashboard FAQ — and all three had their own copy of this list. Copies
 * of a rule drift: the doctrine "an unusable count renders NO bullet rather
 * than a row of empty ones" was enforced in two of them and the decorative
 * bullet glyph was hidden from assistive technology in only two as well.
 *
 * `t` is a PROP, not a hook: the landing band and the history page are server
 * components resolving translations through `initI18next`, while the dashboard
 * FAQ is a client component using `useTranslation`. Taking the resolver keeps
 * one implementation usable by both, the same reason `Skeleton` takes its label.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ChangelogItems } from '../ChangelogItems';

/** Echo keys, and declare `count` bullets for the release under test. */
function translator(count: string) {
  return vi.fn((key: string) => (key.endsWith('.count') ? count : key));
}

describe('ChangelogItems', () => {
  it('renders exactly the bullets the release declares, in order', () => {
    render(<ChangelogItems version="v1_30_9" t={translator('3')} />);

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent('faq.changelog.versions.v1_30_9.items.i1');
    expect(items[2]).toHaveTextContent('faq.changelog.versions.v1_30_9.items.i3');
  });

  it('renders no bullet at all when the count is unusable', () => {
    // Nothing is honest; an empty bullet is not. Malformed and missing counts
    // are the easy way to ship a column of blank dots.
    ['', 'not-a-number', '0', '-2'].forEach(count => {
      const { unmount } = render(<ChangelogItems version="v1_30_9" t={translator(count)} />);
      expect(screen.queryAllByRole('listitem')).toHaveLength(0);
      unmount();
    });
  });

  it('hides the decorative bullet glyph from assistive technology', () => {
    const { container } = render(<ChangelogItems version="v1_30_9" t={translator('1')} />);

    expect(container.querySelectorAll('[aria-hidden="true"]')).toHaveLength(1);
    // The bullet must not reach the accessible name — a screen reader saying
    // "bullet" 800 times across the history is the failure this prevents.
    expect(screen.getByRole('listitem')).toHaveAccessibleName('');
  });

  it('renders the authored emphasis of an item, not its markup', () => {
    // Locale bodies carry <b> and <br>: app-controlled editorial text compiled
    // from the repo, never user or model output.
    const t = vi.fn((key: string) => (key.endsWith('.count') ? '1' : 'a <b>bold</b> claim'));
    render(<ChangelogItems version="v1_30_9" t={t} />);

    expect(screen.getByText('bold').tagName).toBe('B');
  });

  it('lets a surface tune its own spacing without forking the list', () => {
    const { container } = render(
      <ChangelogItems version="v1_30_9" t={translator('1')} className="space-y-2.5 mt-4" />
    );

    const list = container.querySelector('ul');
    // tailwind-merge keeps the caller's spacing and drops the default one.
    expect(list?.className).toContain('space-y-2.5');
    expect(list?.className).not.toContain('space-y-2 ');
    expect(list?.className).toContain('text-muted-foreground');
  });
});
