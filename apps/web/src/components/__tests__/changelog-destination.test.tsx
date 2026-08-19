/**
 * Every surface that promises "the releases" must land on the page that HAS
 * them.
 *
 * The defect this file guards against shipped for real: the landing band's
 * "see the full history" pointed at `/faq`, and the public FAQ carries no
 * changelog — the history only existed in the signed-in dashboard FAQ. Both
 * footers had the same shape of promise pointing at `/#changelog`, i.e. the
 * three-release teaser they were supposed to lead beyond.
 *
 * A label is a claim: a link named after the release history must resolve to
 * `/changelog`, never to a page where it is absent nor to the teaser itself.
 *
 * Scope: the two footers. The landing band's own "see the full history" button
 * is pinned next to the rest of its contract, in
 * `landing/__tests__/ChangelogSection.test.tsx`.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/i18n', () => ({
  initI18next: async () => ({ t: (key: string) => key }),
}));

import { LandingFooter } from '../landing/LandingFooter';
import { PublicFooter } from '../layout/PublicFooter';

describe('changelog destinations', () => {
  it.each([
    ['LandingFooter', LandingFooter],
    ['PublicFooter', PublicFooter],
  ])('%s sends "what is new" to the full history, not to the teaser', async (_name, Footer) => {
    render(await Footer({ lng: 'en' }));

    expect(screen.getByRole('link', { name: 'landing.nav.changelog' })).toHaveAttribute(
      'href',
      '/en/changelog'
    );
  });
});
