import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { DiscussionOpeningPage } from '@/types/proactive-discussions';

const { get, useAppConfig } = vi.hoisted(() => ({ get: vi.fn(), useAppConfig: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', timezone: 'UTC' } }),
}));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));
import { DiscussionsHubSection } from '../DiscussionsHubSection';

function capability(enabled: boolean) {
  useAppConfig.mockReturnValue({
    config: { features: {}, capabilities: { proactive_discussions: { enabled } } },
  });
}

const ID = {
  a: '00000000-0000-4000-8000-00000000000a',
  b: '00000000-0000-4000-8000-00000000000b',
  c: '00000000-0000-4000-8000-00000000000c',
};

function opening(name: keyof typeof ID, state: 'pending' | 'engaged') {
  return {
    id: ID[name],
    message_id: ID[name].replace('4000-8000', '4000-9000'),
    created_at: '2026-10-20T12:00:00Z',
    content: `A fictional opening ${name}`,
    state,
    feedback: null,
    evidence: [],
  };
}

function unfold(title: string) {
  const details = screen.getByText(title).closest('details');
  if (!details) throw new Error('Missing native disclosure');
  details.open = true;
  fireEvent(details, new Event('toggle'));
}

const first: DiscussionOpeningPage = {
  items: [opening('a', 'pending'), opening('b', 'engaged')],
  total: 11,
  next_cursor: ID.b,
};

beforeEach(() => {
  vi.clearAllMocks();
  capability(true);
  get.mockResolvedValue(first);
});

it('is absent while the capability is switched off', () => {
  capability(false);
  render(<DiscussionsHubSection total={3} locale="fr-FR" />);
  expect(screen.queryByText('notifications_hub.sections.discussions.title')).toBeNull();
  expect(get).not.toHaveBeenCalled();
});

it('badges the folded section with the hub count and reads no page until it opens', async () => {
  render(<DiscussionsHubSection total={11} locale="fr-FR" />);
  expect(screen.getByText('11')).toBeVisible();
  expect(get).not.toHaveBeenCalled();
  unfold('notifications_hub.sections.discussions.title');
  await waitFor(() => expect(get).toHaveBeenCalled());
  expect(get.mock.lastCall?.[0]).toBe('/proactive-discussions/openings');
  expect(get.mock.lastCall?.[1]?.params).toEqual({ limit: 10 });
});

it('lists each opening, without a state badge, and pages forward and back by cursor', async () => {
  render(<DiscussionsHubSection total={11} locale="fr-FR" />);
  unfold('notifications_hub.sections.discussions.title');
  expect(await screen.findByText('A fictional opening a')).toBeVisible();
  // Owner request 2026-10-21: the date titles the row, the words follow.
  expect(screen.queryByText(/discussions\.states\./)).toBeNull();
  get.mockResolvedValue({ items: [opening('c', 'engaged')], total: 11, next_cursor: null });
  fireEvent.click(screen.getByRole('button', { name: 'common.next' }));
  await waitFor(() =>
    expect(get.mock.lastCall?.[1]?.params).toEqual({ limit: 10, after_id: ID.b })
  );
  expect(await screen.findByText('A fictional opening c')).toBeVisible();
  get.mockResolvedValue(first);
  fireEvent.click(screen.getByRole('button', { name: 'common.previous' }));
  await waitFor(() => expect(get.mock.lastCall?.[1]?.params).toEqual({ limit: 10 }));
  expect(await screen.findByText('A fictional opening a')).toBeVisible();
});

it('says the history could not be read rather than showing an empty one', async () => {
  get.mockResolvedValue({ unexpected: true });
  render(<DiscussionsHubSection total={2} locale="fr-FR" />);
  unfold('notifications_hub.sections.discussions.title');
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'notifications_hub.sections.discussions.error'
  );
  expect(screen.queryByText('notifications_hub.sections.discussions.empty')).toBeNull();
});
