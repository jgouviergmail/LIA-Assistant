/**
 * An unread mail the person already answered says so on the home card (ADR-379).
 *
 * The card lists UNREAD mail, and unread is not unanswered: a message answered from a
 * phone's notification stays unread. Until 2026-11-11 such a row kept its « reply
 * expected » badge, on the very screen the person reads to know what is left to do.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { MailsCard } from '../cards/MailsCard';
import type { ReplyState } from '@/lib/mail-reply-state';
import type { CardSection, MailItem, MailsData } from '@/types/briefing';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/lib/chat-deep-link', () => ({ openChatDeepLink: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get: vi.fn() } }));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({
    mutate: vi.fn(),
    loading: false,
    error: null,
    reset: vi.fn(),
    data: null,
  }),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'fr' } }),
}));

const NOW = Date.now();

function mail(subject: string, replyStatus?: ReplyState['status']): MailItem {
  return {
    id: subject,
    sender_name: 'Marc Dupont',
    sender_email: 'marc@example.org',
    subject,
    received_local: '09:12',
    classification: {
      version: 'email-event-v2-reply',
      kind: 'email',
      category: 'professional',
      priority: 'normal',
      reply_expected: true,
      evidence_scope: 'snippet',
      evaluated_at: new Date(NOW).toISOString(),
      valid_until: new Date(NOW + 300_000).toISOString(),
    },
    reply_state: replyStatus ? { version: 'mail-reply-state-v1', status: replyStatus } : null,
  };
}

function section(items: MailItem[]): CardSection<MailsData> {
  return {
    status: 'ok',
    data: { total_unread_today: items.length, items },
    generated_at: new Date(NOW).toISOString(),
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

describe('the home mail card and a mail already answered', () => {
  it('marks the answered mail and keeps asking for the other', () => {
    renderWithProviders(
      <MailsCard
        section={section([mail('Devis toiture', 'answered'), mail('Facture')])}
        isRefreshing={false}
        onRefresh={vi.fn()}
        staggerIndex={0}
      />
    );
    const [answered, waiting] = screen.getAllByRole('listitem');
    expect(within(answered).getByText('mail_reply_state.answered')).toBeInTheDocument();
    expect(within(answered).queryByText('classification.reply_expected')).not.toBeInTheDocument();
    expect(within(waiting).getByText('classification.reply_expected')).toBeInTheDocument();
    expect(within(waiting).queryByText('mail_reply_state.answered')).not.toBeInTheDocument();
  });
});
