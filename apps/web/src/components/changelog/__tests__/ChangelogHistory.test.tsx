/**
 * ChangelogHistory — the full release history, on a public page.
 *
 * This component exists because the landing's "see the full history" button
 * led to `/faq`, and the PUBLIC FAQ (`PublicFAQContent`) carries no changelog
 * at all: the history only ever existed in the signed-in dashboard FAQ, so a
 * visitor who followed the promise met a page without it. What is pinned here
 * is exactly that promise — EVERY release the shared list names is on this
 * page, oldest one included, not a slice of it.
 *
 * A SERVER component, like the landing band it receives the reader from:
 * static editorial text, no client bundle, and release notes rendered on the
 * server are indexable — which is half the point of giving history a URL.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CHANGELOG_VERSION_KEYS, groupChangelogBySeries } from '@/lib/changelog';

/** Echo keys, except the counts — which the component reads as a number. */
const translate = vi.fn((key: string) => (key.endsWith('.count') ? '2' : key));
vi.mock('@/i18n', () => ({
  initI18next: async () => ({ t: (key: string) => translate(key) }),
}));

import { ChangelogHistory } from '../ChangelogHistory';

async function renderHistory() {
  render(await ChangelogHistory({ lng: 'en' }));
}

const titleOf = (version: string) => `faq.changelog.versions.${version}.title`;

describe('ChangelogHistory', () => {
  it('renders the WHOLE history, not a slice of it', async () => {
    await renderHistory();

    const titles = screen.getAllByText(/^faq\.changelog\.versions\..+\.title$/);
    expect(titles).toHaveLength(CHANGELOG_VERSION_KEYS.length);
    // The two ends specifically: a page that stops at the newest few is the
    // very defect this component was written to close.
    expect(screen.getByText(titleOf(CHANGELOG_VERSION_KEYS[0]))).toBeInTheDocument();
    expect(
      screen.getByText(titleOf(CHANGELOG_VERSION_KEYS[CHANGELOG_VERSION_KEYS.length - 1]))
    ).toBeInTheDocument();
  });

  it('dates every release and says what changed', async () => {
    await renderHistory();

    const newest = CHANGELOG_VERSION_KEYS[0];
    expect(screen.getByText(`faq.changelog.versions.${newest}.date`)).toBeInTheDocument();
    expect(screen.getByText(`faq.changelog.versions.${newest}.items.i1`)).toBeInTheDocument();
    expect(screen.getByText(`faq.changelog.versions.${newest}.items.i2`)).toBeInTheDocument();
  });

  it('opens the newest release, and only it', async () => {
    await renderHistory();

    const open = (version: string) =>
      screen.getByText(titleOf(version)).closest('details')?.hasAttribute('open');

    expect(open(CHANGELOG_VERSION_KEYS[0])).toBe(true);
    expect(open(CHANGELOG_VERSION_KEYS[1])).toBe(false);
  });

  it('gives each series a landmark the anchor rail can reach', async () => {
    await renderHistory();

    const series = groupChangelogBySeries(CHANGELOG_VERSION_KEYS);
    expect(screen.getAllByRole('region')).toHaveLength(series.length);
    series.forEach(({ label, id }) => {
      expect(screen.getByRole('heading', { level: 2, name: label })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: label })).toHaveAttribute('href', `#${id}`);
      expect(document.getElementById(id)).not.toBeNull();
    });
  });

  it('renders no bullet at all when a release declares an unusable count', async () => {
    // Same doctrine as the landing band: nothing is honest, an empty bullet
    // is not.
    translate.mockImplementation((key: string) => (key.endsWith('.count') ? '' : key));
    await renderHistory();

    expect(screen.queryByText(/\.items\.i1$/)).toBeNull();
    translate.mockImplementation((key: string) => (key.endsWith('.count') ? '2' : key));
  });
});
