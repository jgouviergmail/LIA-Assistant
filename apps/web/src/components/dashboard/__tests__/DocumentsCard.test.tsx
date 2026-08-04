/**
 * Documents card (P15 extension) — latest modified Drive files.
 *
 * Rows open the chat with a summarize intent; a separate anchor opens the
 * file in Drive (new tab, noopener — both actions per user arbitration).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { openCardActions } from '../cards/__tests__/card-actions-harness';

import { DocumentsCard } from '../cards/DocumentsCard';
import type { CardSection, DocumentsData } from '@/types/briefing';

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

function section(data: DocumentsData | null, status = 'ok'): CardSection<DocumentsData> {
  return {
    status: status as CardSection<DocumentsData>['status'],
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

const fullData: DocumentsData = {
  items: [
    {
      name: 'Devis plomberie.pdf',
      modified_local: '14:30',
      web_view_link: 'https://drive.google.com/file/d/f1/view',
      mime_type: 'application/pdf',
    },
    {
      name: 'Notes réunion',
      modified_local: '09:12 21/07/2026',
      web_view_link: null,
      mime_type: 'application/vnd.google-apps.document',
    },
  ],
};

describe('DocumentsCard', () => {
  beforeEach(() => {
    openChat.mockClear();
  });

  it('opens the chat with a summarize intent on row click', async () => {
    const { user } = renderWithProviders(
      <DocumentsCard {...cardProps} section={section(fullData)} />
    );

    const row = screen.getByRole('button', {
      name: /intents\.document_summarize\|subject=Devis plomberie\.pdf/,
    });
    await user.click(row);
    expect(openChat).toHaveBeenCalledWith(expect.stringContaining('/fr/dashboard/chat?draft='));
    expect(openChat.mock.calls[0][0]).toContain(encodeURIComponent('Devis plomberie.pdf'));
    expect(screen.getByText('14:30')).toBeInTheDocument();
  });

  it('renders a safe external Drive link only when a link exists', async () => {
    // The link moved INTO the actions menu (2026-08-03): as a fourth icon it
    // was the widest row of the grid. It stays an anchor, with the same safe
    // attributes — only its home changed.
    const { user } = renderWithProviders(
      <DocumentsCard {...cardProps} section={section(fullData)} />
    );

    await openCardActions(user, 0);
    const link = screen.getByRole('menuitem', { name: /cards\.documents\.open_external/ });
    expect(link).toHaveAttribute('href', 'https://drive.google.com/file/d/f1/view');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    await user.keyboard('{Escape}');

    // The linkless row still renders its content, and offers no Drive entry.
    expect(screen.getByText('Notes réunion')).toBeInTheDocument();
    await openCardActions(user, 1);
    expect(screen.queryByRole('menuitem', { name: /cards\.documents\.open_external/ })).toBeNull();
  });

  it('shows the empty state when the section is empty', () => {
    renderWithProviders(<DocumentsCard {...cardProps} section={section(null, 'empty')} />);
    expect(screen.getByText('dashboard.briefing.cards.documents.empty')).toBeInTheDocument();
  });

  it('is hidden entirely when the section is not configured', () => {
    // The card's own named region is the oracle, not `container.firstChild`:
    // the providers wrap the tree, so "nothing rendered" is about the CARD.
    renderWithProviders(<DocumentsCard {...cardProps} section={section(null, 'not_configured')} />);

    expect(screen.queryByRole('region')).toBeNull();
    expect(screen.queryByText('dashboard.briefing.cards.documents.empty')).toBeNull();
  });
});
