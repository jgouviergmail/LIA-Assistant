/**
 * Briefing card immediate actions (QW-24, ADR-173): each item carries named
 * action chips that deep-link to `?intent=` — EXECUTED by the chat page, not
 * prefilled — while the item's main button keeps its QW-9 `?draft=` prefill.
 *
 * What must hold:
 *  - chips are SIBLINGS of the main button (nested buttons are invalid HTML);
 *  - the accessible name of a chip IS the full intent it sends;
 *  - `?intent=` URLs are properly encoded;
 *  - the agenda route chip exists ONLY when the event has a location;
 *  - the document "ask" chip PREFILLS (draft) — a question needs the user's
 *    own words, sending a bare stub would be noise.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { MailsCard } from '../cards/MailsCard';
import { AgendaCard } from '../cards/AgendaCard';
import { TasksCard } from '../cards/TasksCard';
import { BirthdaysCard } from '../cards/BirthdaysCard';
import { DocumentsCard } from '../cards/DocumentsCard';
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
    generated_at: '2026-07-29T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

const cardProps = { isRefreshing: false, onRefresh: vi.fn(), staggerIndex: 0 };

function lastUrl(): string {
  return openChat.mock.calls[openChat.mock.calls.length - 1][0] as string;
}

beforeEach(() => {
  openChat.mockClear();
});

describe('mail actions (QW-24)', () => {
  const MAIL_SECTION = section({
    total_unread_today: 1,
    items: [
      {
        sender_name: 'Alice Martin',
        sender_email: 'alice@example.com',
        subject: 'Point projet',
        received_local: '09:12',
      },
    ],
  });

  it('summarize executes through ?intent=', () => {
    render(<MailsCard {...cardProps} section={MAIL_SECTION} />);
    fireEvent.click(
      screen.getByRole('button', { name: /intents_exec\.mail_summarize\|subject=Point projet/ })
    );
    expect(lastUrl().startsWith('/fr/dashboard/chat?intent=')).toBe(true);
    expect(decodeURIComponent(lastUrl())).toContain('sender=Alice Martin');
  });

  it('reply executes through ?intent=', () => {
    render(<MailsCard {...cardProps} section={MAIL_SECTION} />);
    fireEvent.click(screen.getByRole('button', { name: /intents_exec\.mail_reply/ }));
    expect(lastUrl().startsWith('/fr/dashboard/chat?intent=')).toBe(true);
  });

  it('keeps the QW-9 prefill on the main item button', () => {
    render(<MailsCard {...cardProps} section={MAIL_SECTION} />);
    fireEvent.click(screen.getByRole('button', { name: /^dashboard\.briefing\.intents\.mail\|/ }));
    expect(lastUrl().startsWith('/fr/dashboard/chat?draft=')).toBe(true);
  });
});

describe('agenda actions (QW-24)', () => {
  it('prepare executes; route exists only with a location', () => {
    render(
      <AgendaCard
        {...cardProps}
        section={section({
          events: [
            { title: 'Comité', start_local: '14:00', end_local: null, location: 'Salle B' },
            { title: 'Sans lieu', start_local: '16:00', end_local: null, location: null },
          ],
        })}
      />
    );

    fireEvent.click(
      screen.getByRole('button', { name: /intents_exec\.event_prepare\|title=Comité/ })
    );
    expect(lastUrl().startsWith('/fr/dashboard/chat?intent=')).toBe(true);

    // Route chip: exactly ONE (the located event), none for the second.
    const routeChips = screen.getAllByRole('button', { name: /intents_exec\.event_route/ });
    expect(routeChips).toHaveLength(1);
    fireEvent.click(routeChips[0]);
    expect(decodeURIComponent(lastUrl())).toContain('location=Salle B');
  });
});

describe('task actions (QW-24)', () => {
  const TASKS_SECTION = section({
    overdue_count: 0,
    items: [
      { title: 'Payer la facture', due_date_iso: null, days_until_due: null, overdue: false },
    ],
  });

  it('complete and postpone execute through ?intent=', () => {
    render(<TasksCard {...cardProps} section={TASKS_SECTION} />);

    fireEvent.click(
      screen.getByRole('button', { name: /intents_exec\.task_complete\|subject=Payer la facture/ })
    );
    expect(lastUrl().startsWith('/fr/dashboard/chat?intent=')).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: /intents_exec\.task_postpone/ }));
    expect(lastUrl().startsWith('/fr/dashboard/chat?intent=')).toBe(true);
  });
});

describe('birthday action (QW-24)', () => {
  it('message executes through ?intent=', () => {
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
    fireEvent.click(
      screen.getByRole('button', { name: /intents_exec\.birthday_message\|name=Gérard Dupont/ })
    );
    expect(lastUrl().startsWith('/fr/dashboard/chat?intent=')).toBe(true);
  });
});

describe('document actions (QW-24)', () => {
  const DOCS_SECTION = section({
    items: [
      {
        name: 'Rapport T2.pdf',
        modified_local: 'hier 18:02',
        web_view_link: 'https://drive.example/x',
        mime_type: 'application/pdf',
      },
    ],
  });

  it('summarize executes through ?intent=', () => {
    render(<DocumentsCard {...cardProps} section={DOCS_SECTION} />);
    fireEvent.click(
      screen.getByRole('button', { name: /intents_exec\.document_summarize\|subject=Rapport/ })
    );
    expect(lastUrl().startsWith('/fr/dashboard/chat?intent=')).toBe(true);
  });

  it('ask-a-question PREFILLS — the question needs the user’s own words', () => {
    render(<DocumentsCard {...cardProps} section={DOCS_SECTION} />);
    fireEvent.click(screen.getByRole('button', { name: /intents_exec\.document_ask_label/ }));
    expect(lastUrl().startsWith('/fr/dashboard/chat?draft=')).toBe(true);
    expect(decodeURIComponent(lastUrl())).toContain('document_ask_draft');
  });
});
