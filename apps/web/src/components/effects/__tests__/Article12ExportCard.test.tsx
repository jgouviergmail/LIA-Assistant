/**
 * Article12ExportCard — the reader's own unified extraction (ADR-263).
 *
 * Three properties, and each is a decision rather than a detail:
 *
 * - the link names NO account, because the route declares none: the scope is
 *   the session, not a default a query string could override;
 * - it is an anchor with `download`, never a button — a download is a
 *   navigation, and a same-site GET carries the session cookie by itself;
 * - the hint is reachable programmatically, not only as a `title`: what the
 *   file holds decides whether it is safe to send to someone.
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Article12ExportCard } from '@/components/effects/Article12ExportCard';

const dictionary: Record<string, string> = {
  'registers.article12.title': 'Everything recorded about you',
  'registers.article12.description': 'All five records in one file.',
  'registers.article12.action': 'Unified extraction',
  'registers.article12.hint': 'JSON Lines, no content, identifiers replaced by a handle.',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => dictionary[key] ?? key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiEndpointUrl: (endpoint: string) => `https://api.test/api/v1${endpoint}`,
}));

describe('Article12ExportCard', () => {
  it('links to the reader-scoped route, naming no account', () => {
    render(<Article12ExportCard />);
    const link = screen.getByRole('link', { name: /Unified extraction/ });

    expect(link).toHaveAttribute('href', 'https://api.test/api/v1/effects/export/article12');
    expect(link.getAttribute('href')).not.toContain('user_id');
  });

  it('downloads rather than navigating away', () => {
    render(<Article12ExportCard />);

    expect(screen.getByRole('link', { name: /Unified extraction/ })).toHaveAttribute('download');
  });

  it('says what the file holds, to a screen reader too', () => {
    // A `title` alone reaches neither a screen reader nor a finger, and what
    // the file holds is what decides whether it can be handed on.
    render(<Article12ExportCard />);
    const link = screen.getByRole('link', { name: /Unified extraction/ });

    expect(link).toHaveAccessibleDescription(dictionary['registers.article12.hint']);
    expect(link).toHaveAttribute('title', dictionary['registers.article12.hint']);
  });

  it('explains why it exists beside the per-register exports', () => {
    render(<Article12ExportCard />);

    expect(screen.getByText('Everything recorded about you')).toBeInTheDocument();
    expect(screen.getByText('All five records in one file.')).toBeInTheDocument();
  });
});
