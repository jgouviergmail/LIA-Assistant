/**
 * ChangelogSection — "what just shipped", on the landing page.
 *
 * A visitor decides whether a product is alive by whether it moves. The FAQ
 * has always held the full history, four clicks deep and behind a fold; this
 * section puts the last few releases where someone who has not signed up yet
 * will actually meet them.
 *
 * A SERVER component, like every other band of the page — rendered here by
 * awaiting it, which is what a server component is: a function returning
 * elements.
 *
 * What is pinned: it renders the NEWEST releases (not an arbitrary slice), it
 * reads the same single list every other changelog surface reads, it points at
 * the full history rather than pretending to be it, and a release whose item
 * count is unusable renders no bullet rather than a list of empty ones.
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CHANGELOG_VERSION_KEYS, LANDING_CHANGELOG_COUNT } from '@/lib/changelog';

/**
 * Echo keys, except the counts — which the component genuinely reads as a
 * number, and which the shared stub would make unparseable (hiding every item
 * list behind a vacuously green test).
 */
const count = vi.fn((key: string) => (key.endsWith('.count') ? '2' : key));
vi.mock('@/i18n', () => ({
  initI18next: async () => ({ t: (key: string) => count(key) }),
}));

import { ChangelogSection } from '../ChangelogSection';

async function renderSection() {
  render(await ChangelogSection({ lng: 'en' }));
}

describe('ChangelogSection', () => {
  it('shows the most recent releases, newest first', async () => {
    await renderSection();

    const entries = screen.getAllByRole('article');
    expect(entries).toHaveLength(LANDING_CHANGELOG_COUNT);
    // Titles come from the shared list, in ITS order — never a hand-picked
    // selection that would freeze the day someone forgets to update it.
    CHANGELOG_VERSION_KEYS.slice(0, LANDING_CHANGELOG_COUNT).forEach((version, index) => {
      expect(entries[index]).toHaveTextContent(`faq.changelog.versions.${version}.title`);
    });
  });

  it('dates every release it quotes', async () => {
    await renderSection();

    expect(screen.getAllByRole('article')[0]).toHaveTextContent(
      `faq.changelog.versions.${CHANGELOG_VERSION_KEYS[0]}.date`
    );
  });

  it('shows what changed, not only that something did', async () => {
    await renderSection();

    const [first] = screen.getAllByRole('article');
    const items = within(first).getAllByRole('listitem');
    expect(items).toHaveLength(2); // the mocked `.count`
    expect(items[0]).toHaveTextContent(
      `faq.changelog.versions.${CHANGELOG_VERSION_KEYS[0]}.items.i1`
    );
  });

  it('renders no bullet at all when a release declares an unusable count', async () => {
    // Nothing is honest; an empty bullet is not. A missing or malformed
    // `.count` is the easy way to ship a list of blank dots.
    count.mockImplementation((key: string) => (key.endsWith('.count') ? 'not-a-number' : key));
    await renderSection();

    expect(within(screen.getAllByRole('article')[0]).queryAllByRole('listitem')).toHaveLength(0);
    count.mockImplementation((key: string) => (key.endsWith('.count') ? '2' : key));
  });

  it('sends the reader to the full history rather than claiming to be it', async () => {
    // `/changelog`, NOT `/faq`: the public FAQ carries no changelog (the
    // history lives in the signed-in dashboard FAQ), so the old destination
    // answered the promise with a page that did not have it.
    await renderSection();

    expect(screen.getByRole('link', { name: /landing\.changelog\.all/ })).toHaveAttribute(
      'href',
      '/en/changelog'
    );
  });

  it('carries a heading the page outline can use, and a landmark', async () => {
    await renderSection();

    expect(
      screen.getByRole('heading', { level: 2, name: /landing\.changelog\.title/ })
    ).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /landing\.changelog\.title/ })).toBeInTheDocument();
  });
});
