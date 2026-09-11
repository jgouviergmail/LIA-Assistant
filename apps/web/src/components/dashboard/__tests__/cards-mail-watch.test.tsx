/**
 * The « Watch » chip on a briefing mail (ADR-281, lot 5).
 *
 * Every other action on this card opens the chat prefilled; this one WRITES.
 * It has to: a watch is a CONDITION routine, and `create_scheduled_action_tool`
 * deliberately authors `time` routines only — growing its signature to compose
 * conditions from natural language is a design of its own, deferred in writing.
 *
 * What must hold:
 *  - it posts a condition routine on the SENDER, ending through the
 *    recurrence's own `SeriesEnd` rather than a field of its own;
 *  - a mail whose sender came through as neither an address nor a name offers
 *    NO chip, because the API would refuse the payload and a button whose only
 *    outcome is an error is worse than no button;
 *  - a failure is TOLD; the person pressed a button and silence reads as
 *    success.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { MailsCard } from '../cards/MailsCard';
import { runCardAction, openCardActions } from '../cards/__tests__/card-actions-harness';
import type { CardSection, MailsData } from '@/types/briefing';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/lib/chat-deep-link', () => ({ openChatDeepLink: vi.fn() }));

const success = vi.fn();
const info = vi.fn();
const failure = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (message: string) => success(message),
    info: (message: string) => info(message),
    error: (message: string) => failure(message),
  },
}));

const get = vi.fn();
vi.mock('@/lib/api-client', () => ({
  default: { get: (endpoint: string) => get(endpoint) },
}));

const post = vi.fn();
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({
    mutate: (endpoint: string, data: unknown) => post(endpoint, data),
    loading: false,
    error: null,
    reset: vi.fn(),
    data: null,
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts
        ? `${key}|${Object.entries(opts)
            .map(([k, v]) => `${k}=${v}`)
            .join('|')}`
        : key,
    i18n: { language: 'fr' },
  }),
}));

function section(items: MailsData['items']): CardSection<MailsData> {
  return {
    status: 'ok',
    data: { total_unread_today: items.length, items },
    generated_at: '2026-09-11T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

const NAMED = section([
  {
    sender_name: 'Alice Martin',
    sender_email: 'alice@example.com',
    subject: 'Point projet',
    received_local: '09:12',
  },
]);

const cardProps = { isRefreshing: false, onRefresh: vi.fn(), staggerIndex: 0 };
const WATCH = /watch\.action\|sender=Alice Martin/;

/** A routine the account already holds. */
function routine(overrides: Record<string, unknown> = {}) {
  return {
    id: 'r-0',
    is_enabled: true,
    trigger_kind: 'condition',
    condition_config: { type: 'mail_match', query: 'alice@example.com' },
    ...overrides,
  };
}

beforeEach(() => {
  post.mockReset().mockResolvedValue({ id: 'r-1' });
  get.mockReset().mockResolvedValue({ scheduled_actions: [], total: 0 });
  success.mockClear();
  info.mockClear();
  failure.mockClear();
});

describe('posting a watch', () => {
  it('creates a condition routine on the sender', async () => {
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={NAMED} />);

    await runCardAction(user, WATCH);

    expect(post).toHaveBeenCalledTimes(1);
    const [endpoint, payload] = post.mock.calls[0];
    expect(endpoint).toBe('/scheduled-actions');
    expect(payload.trigger_kind).toBe('condition');
    expect(payload.condition_config).toEqual({
      type: 'mail_match',
      query: 'alice@example.com',
    });
  });

  it('ends through the recurrence, never a field of its own', async () => {
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={NAMED} />);

    await runCardAction(user, WATCH);

    const [, payload] = post.mock.calls[0];
    expect(payload.recurrence.end.kind).toBe('on_date');
    expect(payload.recurrence.end.on_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(payload).not.toHaveProperty('expires_at');
  });

  it('carries wording the person can read, not a generated stub', async () => {
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={NAMED} />);

    await runCardAction(user, WATCH);

    const [, payload] = post.mock.calls[0];
    expect(payload.title).toContain('sender=Alice Martin');
    expect(payload.action_prompt).toContain('watch.prompt');
  });

  it('says so once it is posted', async () => {
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={NAMED} />);

    await runCardAction(user, WATCH);

    expect(success).toHaveBeenCalledWith(expect.stringContaining('watch.created'));
    expect(failure).not.toHaveBeenCalled();
  });
});

describe('when it cannot be posted', () => {
  it('tells the person rather than failing in silence', async () => {
    post.mockRejectedValue(new Error('boom'));
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={NAMED} />);

    await runCardAction(user, WATCH);

    expect(failure).toHaveBeenCalledWith('dashboard.briefing.watch.failed');
    expect(success).not.toHaveBeenCalled();
  });

  it('treats an empty response as a failure, not a success', async () => {
    // `useApiMutation` resolves to undefined when the request did not land.
    post.mockResolvedValue(undefined);
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={NAMED} />);

    await runCardAction(user, WATCH);

    expect(failure).toHaveBeenCalled();
    expect(success).not.toHaveBeenCalled();
  });
});

describe('when there is nothing to watch for', () => {
  it('offers no chip at all', async () => {
    const anonymous = section([
      {
        sender_name: null,
        sender_email: null,
        subject: 'Point projet',
        received_local: '09:12',
      },
    ]);
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={anonymous} />);

    await openCardActions(user);

    expect(screen.queryByRole('menuitem', { name: /watch\.action/ })).toBeNull();
    expect(post).not.toHaveBeenCalled();
  });

  it('but still offers the two chips that only open the chat', async () => {
    const anonymous = section([
      { sender_name: null, sender_email: null, subject: 'Point', received_local: '09:12' },
    ]);
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={anonymous} />);

    await openCardActions(user);

    expect(screen.getByRole('menuitem', { name: /mail_summarize/ })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /mail_reply/ })).toBeInTheDocument();
  });
});

describe('asking before writing', () => {
  it('reads what the account already holds, once, on the click', async () => {
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={NAMED} />);

    await runCardAction(user, WATCH);

    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith('/scheduled-actions');
  });

  it('refuses a second watch on the same person', async () => {
    // Two mails from one sender is ordinary; two watches would announce one
    // awaited reply twice, which is the irritation this programme avoids.
    get.mockResolvedValue({ scheduled_actions: [routine()], total: 1 });
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={NAMED} />);

    await runCardAction(user, WATCH);

    expect(post).not.toHaveBeenCalled();
    expect(info).toHaveBeenCalledWith(expect.stringContaining('watch.already'));
    expect(failure).not.toHaveBeenCalled();
  });

  it('says so rather than reporting a failure', async () => {
    get.mockResolvedValue({ scheduled_actions: [routine()], total: 1 });
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={NAMED} />);

    await runCardAction(user, WATCH);

    expect(success).not.toHaveBeenCalled();
  });

  it('a paused watch does not block a new one', async () => {
    // Pausing is a decision to stop being told; arming afresh is the answer.
    get.mockResolvedValue({ scheduled_actions: [routine({ is_enabled: false })], total: 1 });
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={NAMED} />);

    await runCardAction(user, WATCH);

    expect(post).toHaveBeenCalledTimes(1);
  });

  it('a watch on somebody else does not block this one', async () => {
    get.mockResolvedValue({
      scheduled_actions: [
        routine({ condition_config: { type: 'mail_match', query: 'bob@example.com' } }),
      ],
      total: 1,
    });
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={NAMED} />);

    await runCardAction(user, WATCH);

    expect(post).toHaveBeenCalledTimes(1);
  });

  it('a routine of another kind does not block it either', async () => {
    get.mockResolvedValue({
      scheduled_actions: [routine({ trigger_kind: 'time', condition_config: null })],
      total: 1,
    });
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={NAMED} />);

    await runCardAction(user, WATCH);

    expect(post).toHaveBeenCalledTimes(1);
  });

  it('a listing that fails is told, and nothing is posted blindly', async () => {
    get.mockRejectedValue(new Error('offline'));
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={NAMED} />);

    await runCardAction(user, WATCH);

    expect(post).not.toHaveBeenCalled();
    expect(failure).toHaveBeenCalled();
  });
});
