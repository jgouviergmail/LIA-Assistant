/**
 * DiscussionHistory — « Recent discussions » in the proactive discussions panel.
 *
 * What a reader would notice being broken (owner request 2026-10-21): each
 * discussion is a panel on the CARD surface, so inside the nested fold the
 * backgrounds alternate and its own « why » fold reads as nested again; and
 * its date and hour are in bold, as every row of the alerts draws them.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { DiscussionOpeningPage } from '@/types/proactive-discussions';

const page: DiscussionOpeningPage = {
  items: [
    {
      id: '10000000-0000-4000-8000-000000000001',
      message_id: '20000000-0000-4000-8000-000000000002',
      created_at: '2026-10-21T08:30:00Z',
      content: 'Tu voulais reprendre le piano : on en parle ?',
      state: 'pending',
      feedback: null,
      evidence: [],
    },
  ],
  total: 1,
  next_cursor: null,
};

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) =>
      options?.count === undefined ? key : `${key}|${options.count}`,
  }),
}));
vi.mock('@/hooks/useApplicationResourceSync', () => ({ useApplicationResourceSync: vi.fn() }));
vi.mock('@/hooks/useApplicationAccountQuery', () => ({
  // The history reads its page; the folded « why » panel reads nothing yet.
  useApplicationAccountQuery: (endpoint: string) => ({
    data: endpoint === '/proactive-discussions/openings' ? page : undefined,
    loading: false,
    error: null,
    refetch: vi.fn(async () => undefined),
    ownerId: 'owner',
  }),
}));
vi.mock('@/components/chat/DiscussionActions', () => ({ DiscussionActions: () => null }));

import { DiscussionHistory } from '../DiscussionHistory';

describe('DiscussionHistory', () => {
  it('draws each discussion on the card surface, its date and hour in bold', () => {
    render(<DiscussionHistory lng="fr" open />);

    const item = screen.getByText('Tu voulais reprendre le piano : on en parle ?').closest('li');
    if (item === null) throw new Error('no discussion row');
    expect(item).toHaveClass('bg-card');

    const time = item.querySelector('time');
    if (time === null) throw new Error('no date');
    expect(time).toHaveAttribute('dateTime', '2026-10-21T08:30:00Z');
    expect(time).toHaveClass('font-bold');
    // The day AND the hour: a medium date and a short time.
    expect(time.textContent).toMatch(/2026/);
    expect(time.textContent).toMatch(/\d{1,2}:\d{2}/);
  });
});
