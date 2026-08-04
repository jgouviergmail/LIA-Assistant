/**
 * Briefing card immediate actions (QW-24, ADR-173): each item carries named
 * actions that deep-link to `?intent=` — EXECUTED by the chat page, not
 * prefilled — while the item's main button keeps its QW-9 `?draft=` prefill.
 *
 * Since 2026-08-03 those actions sit behind ONE trigger per row instead of a
 * row of icon chips: two or three chips took a quarter to a third of a row's
 * usable width and the item's title `truncate`d to pay for it. What each action
 * DOES is unchanged — only the click that reveals it is new, which is why every
 * assertion below is the one it always was.
 *
 * What must hold:
 *  - the trigger is a SIBLING of the main button (nested buttons are invalid
 *    HTML and unreachable by assistive technology);
 *  - the accessible name of an action IS the full intent it sends;
 *  - `?intent=` URLs are properly encoded;
 *  - the agenda route action exists ONLY when the event has a location;
 *  - the document "ask" action PREFILLS (draft) — a question needs the user's
 *    own words, sending a bare stub would be noise;
 *  - the Drive link is a real anchor, not a click handler.
 *
 * `renderWithProviders` and `userEvent`, never bare `render`/`fireEvent`: the
 * row now carries a Radix tooltip (which requires `TooltipProvider`, supplied
 * by the app layout) and a Radix menu (which opens on POINTER events, not on a
 * synthetic click).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { MailsCard } from '../cards/MailsCard';
import { AgendaCard } from '../cards/AgendaCard';
import { TasksCard } from '../cards/TasksCard';
import { BirthdaysCard } from '../cards/BirthdaysCard';
import { DocumentsCard } from '../cards/DocumentsCard';
import { openCardActions, runCardAction } from '../cards/__tests__/card-actions-harness';
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

  it('summarize executes through ?intent=', async () => {
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={MAIL_SECTION} />);

    await runCardAction(user, /intents_exec\.mail_summarize\|subject=Point projet/);

    expect(lastUrl().startsWith('/fr/dashboard/chat?intent=')).toBe(true);
    expect(decodeURIComponent(lastUrl())).toContain('sender=Alice Martin');
  });

  it('reply executes through ?intent=', async () => {
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={MAIL_SECTION} />);

    await runCardAction(user, /intents_exec\.mail_reply/);

    expect(lastUrl().startsWith('/fr/dashboard/chat?intent=')).toBe(true);
  });

  it('keeps the QW-9 prefill on the main item button', async () => {
    const { user } = renderWithProviders(<MailsCard {...cardProps} section={MAIL_SECTION} />);

    await user.click(screen.getByRole('button', { name: /^dashboard\.briefing\.intents\.mail\|/ }));

    expect(lastUrl().startsWith('/fr/dashboard/chat?draft=')).toBe(true);
  });
});

describe('agenda actions (QW-24)', () => {
  const AGENDA_SECTION = section({
    events: [
      { title: 'Comité', start_local: '14:00', end_local: null, location: 'Salle B' },
      { title: 'Sans lieu', start_local: '16:00', end_local: null, location: null },
    ],
  });

  it('prepare executes through ?intent=', async () => {
    const { user } = renderWithProviders(<AgendaCard {...cardProps} section={AGENDA_SECTION} />);

    await runCardAction(user, /intents_exec\.event_prepare\|title=Comité/);

    expect(lastUrl().startsWith('/fr/dashboard/chat?intent=')).toBe(true);
  });

  it('offers the route only for the event that HAS a location', async () => {
    const { user } = renderWithProviders(<AgendaCard {...cardProps} section={AGENDA_SECTION} />);

    // First row (located): the route is there.
    await openCardActions(user, 0);
    const route = screen.getByRole('menuitem', { name: /intents_exec\.event_route/ });
    await user.click(route);
    expect(decodeURIComponent(lastUrl())).toContain('location=Salle B');

    // Second row (no location): the menu holds "prepare" and nothing else —
    // an action that cannot be honoured is absent, never disabled.
    await openCardActions(user, 1);
    expect(screen.queryByRole('menuitem', { name: /intents_exec\.event_route/ })).toBeNull();
    expect(
      screen.getByRole('menuitem', { name: /intents_exec\.event_prepare/ })
    ).toBeInTheDocument();
  });
});

describe('task actions (QW-24)', () => {
  const TASKS_SECTION = section({
    overdue_count: 0,
    items: [
      { title: 'Payer la facture', due_date_iso: null, days_until_due: null, overdue: false },
    ],
  });

  it('complete and postpone execute through ?intent=', async () => {
    const { user } = renderWithProviders(<TasksCard {...cardProps} section={TASKS_SECTION} />);

    await runCardAction(user, /intents_exec\.task_complete\|subject=Payer la facture/);
    expect(lastUrl().startsWith('/fr/dashboard/chat?intent=')).toBe(true);

    await runCardAction(user, /intents_exec\.task_postpone/);
    expect(lastUrl().startsWith('/fr/dashboard/chat?intent=')).toBe(true);
  });
});

describe('birthday action (QW-24)', () => {
  it('message executes through ?intent=', async () => {
    const { user } = renderWithProviders(
      <BirthdaysCard
        {...cardProps}
        section={section({
          items: [
            { contact_name: 'Gérard Dupont', date_iso: '--07-25', days_until: 3, age_at_next: 42 },
          ],
        })}
      />
    );

    await runCardAction(user, /intents_exec\.birthday_message\|name=Gérard Dupont/);

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

  it('summarize executes through ?intent=', async () => {
    const { user } = renderWithProviders(<DocumentsCard {...cardProps} section={DOCS_SECTION} />);

    await runCardAction(user, /intents_exec\.document_summarize\|subject=Rapport/);

    expect(lastUrl().startsWith('/fr/dashboard/chat?intent=')).toBe(true);
  });

  it('ask-a-question PREFILLS — the question needs the user’s own words', async () => {
    const { user } = renderWithProviders(<DocumentsCard {...cardProps} section={DOCS_SECTION} />);

    await runCardAction(user, /intents_exec\.document_ask_label/);

    expect(lastUrl().startsWith('/fr/dashboard/chat?draft=')).toBe(true);
    expect(decodeURIComponent(lastUrl())).toContain('document_ask_draft');
  });

  it('opens Drive through a real anchor, in a safe new tab', async () => {
    // The Drive entry joined the menu when the chips went away. It stays a
    // LINK: navigation deserves middle-click, the context menu and the
    // status-bar preview, none of which a click handler offers.
    const { user } = renderWithProviders(<DocumentsCard {...cardProps} section={DOCS_SECTION} />);

    await openCardActions(user);

    const link = screen.getByRole('menuitem', { name: /cards\.documents\.open_external/ });
    expect(link).toHaveAttribute('href', 'https://drive.example/x');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('offers no Drive entry when the document carries no link', async () => {
    const { user } = renderWithProviders(
      <DocumentsCard
        {...cardProps}
        section={section({
          items: [
            {
              name: 'Local.txt',
              modified_local: 'hier',
              web_view_link: null,
              mime_type: 'text/plain',
            },
          ],
        })}
      />
    );

    await openCardActions(user);

    expect(screen.queryByRole('menuitem', { name: /cards\.documents\.open_external/ })).toBeNull();
  });
});
