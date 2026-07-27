/**
 * Expiry notice on generated images (N2).
 *
 * A generated image is an attachment with an `expires_at`, purged by a
 * scheduler. The card offered a download button and no reason to press it: the
 * image simply disappeared from the history a day later.
 *
 * The notice must be honest in both directions — warn when it knows, say
 * nothing when it does not — and it must never invent a duration of its own.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { Message } from '@/types/chat';

const { translate } = vi.hoisted(() => {
  const content: Record<string, string> = {
    'chat.image_expiry.until': "Disponible jusqu'au {{date}} — téléchargez-la pour la conserver",
    'chat.image_expiry.soon_one': 'Expire dans {{count}} heure — téléchargez-la pour la conserver',
    'chat.image_expiry.soon_other':
      'Expire dans {{count}} heures — téléchargez-la pour la conserver',
    'chat.image_expiry.expired': "Cette image a expiré et n'est plus disponible",
  };
  return {
    translate: (key: string, params?: Record<string, unknown>) => {
      const count = params?.count;
      const resolved =
        key === 'chat.image_expiry.soon' && typeof count === 'number'
          ? `${key}_${count === 1 ? 'one' : 'other'}`
          : key;
      const value = resolved in content ? content[resolved] : (content[key] ?? key);
      return params
        ? value.replace(/\{\{(\w+)\}\}/g, (_m, name: string) => String(params[name] ?? ''))
        : value;
    },
  };
});

vi.mock('react-i18next', async importOriginal => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: translate,
      i18n: { language: 'fr', changeLanguage: vi.fn() },
    }),
  };
});

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { tokens_display_enabled: false } }),
}));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate: vi.fn() }) }));

import { ChatMessage } from '../ChatMessage';

const NOW = new Date('2026-07-26T12:00:00Z');

function withImage(expiresAt?: string | null): Message {
  return {
    id: 'm1',
    role: 'assistant',
    content: 'Voici votre image',
    timestamp: NOW,
    generatedImages: [{ url: '/api/v1/attachments/abc', alt: 'un chat', expires_at: expiresAt }],
  } as Message;
}

/** An ISO instant `hours` away from NOW. */
function inHours(hours: number): string {
  return new Date(NOW.getTime() + hours * 3_600_000).toISOString();
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('generated image expiry notice', () => {
  it('warns with the backend deadline', () => {
    renderWithProviders(<ChatMessage isUser={false} message={withImage(inHours(20))} />);
    expect(screen.getByText(/Disponible jusqu'au/)).toBeInTheDocument();
  });

  it('escalates when the deadline is close', () => {
    renderWithProviders(<ChatMessage isUser={false} message={withImage(inHours(2))} />);
    expect(screen.getByText(/Expire dans 2 heures/)).toBeInTheDocument();
  });

  it('uses the singular on the last hour', () => {
    renderWithProviders(<ChatMessage isUser={false} message={withImage(inHours(0.5))} />);
    expect(screen.getByText(/Expire dans 1 heure —/)).toBeInTheDocument();
  });

  it('says nothing when the backend sent no deadline', () => {
    // History predating N2: silence beats a guessed duration.
    renderWithProviders(<ChatMessage isUser={false} message={withImage(null)} />);
    expect(screen.queryByText(/Disponible|Expire/)).not.toBeInTheDocument();
  });

  it('never renders an invalid date', () => {
    renderWithProviders(<ChatMessage isUser={false} message={withImage('not-a-date')} />);
    expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Disponible/)).not.toBeInTheDocument();
  });

  it('states plainly that an elapsed image is gone', () => {
    renderWithProviders(<ChatMessage isUser={false} message={withImage(inHours(-2))} />);
    expect(screen.getByText(/a expiré/)).toBeInTheDocument();
  });

  it('keeps the download button available next to the warning', () => {
    // The warning is only useful because the way out is one click away.
    renderWithProviders(<ChatMessage isUser={false} message={withImage(inHours(3))} />);
    expect(screen.getByText(/Expire dans 3 heures/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'common.download' })).toBeInTheDocument();
  });
});
