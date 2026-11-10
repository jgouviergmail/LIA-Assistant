/**
 * The chat's habit proposal (ADR-375): shown under the latest answer, decided
 * through the inbox's own door, gone once decided — and the focus the person
 * rested on the card returns to the composer, never to the page's body.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { postMock, push, toast } = vi.hoisted(() => ({
  postMock: vi.fn(),
  push: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post: postMock },
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
vi.mock('sonner', () => ({ toast }));

import { ChatProposalCard } from '@/components/chat/ChatProposalCard';
import type { HabitProposal } from '@/hooks/useHabitProposals';
import type { Message } from '@/types/chat';

import { useChatProposal } from '../useChatProposal';

const PROPOSAL: HabitProposal = {
  id: 'p-1',
  kind: 'review_notifications',
  key: 'heartbeat',
  facts: { sent: 24, window_days: 35 },
  created_at: '2026-11-08T03:00:00Z',
  updated_at: '2026-11-08T03:00:00Z',
};
const ANSWER: Message = {
  id: 'a-1',
  role: 'assistant',
  content: 'ok',
  timestamp: new Date(0),
  metadata: { habit_proposal: PROPOSAL },
};
const CARD = { name: 'habits.proposals.chat_title' };

function Chat({ busy = false }: { busy?: boolean }) {
  const { proposal, decisions } = useChatProposal([ANSWER], busy, 'fr');
  return (
    <>
      {proposal && <ChatProposalCard proposal={proposal} decisions={decisions} />}
      <textarea data-chat-composer aria-label="composer" />
    </>
  );
}

beforeEach(() => {
  postMock.mockReset().mockResolvedValue({});
  push.mockReset();
  toast.success.mockReset();
});

describe('useChatProposal', () => {
  it('shows the latest answer’s proposal, and nothing while the band is busy', () => {
    const { rerender } = renderWithProviders(<Chat />);
    expect(screen.getByRole('region', CARD)).toBeInTheDocument();

    rerender(<Chat busy />);
    expect(screen.queryByRole('region', CARD)).toBeNull();
  });

  it('decides through the proposals route, then hands the focus to the composer', async () => {
    const { user } = renderWithProviders(<Chat />);

    await user.click(
      screen.getByRole('button', { name: 'habits.proposals.review_notifications.accept' })
    );

    await waitFor(() => expect(screen.queryByRole('region', CARD)).toBeNull());
    expect(postMock).toHaveBeenCalledWith('/habits/proposals/p-1/accept');
    expect(toast.success).toHaveBeenCalledWith('habits.proposals.review_notifications.done');
    expect(screen.getByRole('textbox', { name: 'composer' })).toHaveFocus();
  });
});
