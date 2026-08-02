/**
 * Briefing cards become actionable (QW-9): every item is a real, labelled
 * button that opens the chat prefilled with a contextual intent via the
 * onboarding `?draft=` deep-link pattern (reminders open the chat plainly).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { MailsCard } from '../cards/MailsCard';
import { AgendaCard } from '../cards/AgendaCard';
import { BirthdaysCard } from '../cards/BirthdaysCard';
import { RemindersCard } from '../cards/RemindersCard';
import type { CardSection, SectionData } from '@/types/briefing';

const push = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

// Chat deep links are REAL navigations since 2026-08-01 (ADR-192): the App
// Router restored the search params of the entry it already held, so a second
// deep link in a session left with the FIRST one's URL. The oracle is the same
// href — only the door changed.
const openChat = vi.fn();
vi.mock('@/lib/chat-deep-link', () => ({
  openChatDeepLink: (href: string) => openChat(href),
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

function section<T extends SectionData>(data: T): CardSection<T> {
  return {
    status: 'ok',
    data,
    generated_at: '2026-07-22T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

const cardProps = { isRefreshing: false, onRefresh: vi.fn(), staggerIndex: 0 };

describe('briefing cards — actionable items (QW-9)', () => {
  beforeEach(() => {
    openChat.mockClear();
  });

  it('mail item opens the chat prefilled with the summarize intent', () => {
    render(
      <MailsCard
        {...cardProps}
        section={section({
          total_unread_today: 2,
          items: [
            {
              sender_name: 'Alice Martin',
              sender_email: 'alice@example.com',
              subject: 'Point projet',
              received_local: '09:12',
            },
          ],
        })}
      />
    );

    const item = screen.getByRole('button', { name: /intents\.mail\|subject=Point projet/ });
    fireEvent.click(item);

    expect(openChat).toHaveBeenCalledTimes(1);
    const url = openChat.mock.calls[0][0] as string;
    expect(url.startsWith('/fr/dashboard/chat?draft=')).toBe(true);
    expect(decodeURIComponent(url.split('draft=')[1])).toContain('subject=Point projet');
    expect(decodeURIComponent(url.split('draft=')[1])).toContain('sender=Alice Martin');
  });

  it('agenda item opens the chat prefilled with the prepare intent', () => {
    render(
      <AgendaCard
        {...cardProps}
        section={section({
          events: [
            { title: 'Comité produit', start_local: '14:00', end_local: '15:00', location: null },
          ],
        })}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /intents\.event\|title=Comité produit/ }));

    const url = openChat.mock.calls[0][0] as string;
    expect(decodeURIComponent(url)).toContain('title=Comité produit');
    expect(decodeURIComponent(url)).toContain('time=14:00');
  });

  it('birthday item opens the chat prefilled with the birthday intent', () => {
    render(
      <BirthdaysCard
        {...cardProps}
        section={section({
          items: [
            { contact_name: 'Gérard Dupont', date_iso: '--07-25', days_until: 3, age_at_next: 42 },
          ],
        })}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /intents\.birthday\|name=Gérard Dupont/ }));

    expect(decodeURIComponent(openChat.mock.calls[0][0] as string)).toContain('name=Gérard Dupont');
  });

  it('reminder item opens the chat plainly (no draft)', () => {
    render(
      <RemindersCard
        {...cardProps}
        section={section({
          items: [{ content: 'Appeler le dentiste', trigger_at_local: 'Demain 09:00' }],
        })}
      />
    );

    fireEvent.click(
      screen.getByRole('button', { name: 'dashboard.briefing.intents.reminder_aria' })
    );

    expect(openChat).toHaveBeenCalledWith('/fr/dashboard/chat');
  });
});
