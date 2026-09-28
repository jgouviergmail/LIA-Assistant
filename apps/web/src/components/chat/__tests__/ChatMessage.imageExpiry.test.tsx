/**
 * Expiry notice on generated images (N2).
 *
 * A generated image is an attachment with an `expires_at`, purged by a
 * scheduler. The card offered a download button and no reason to press it: the
 * image simply disappeared from the history a day later.
 *
 * The notice must be honest in both directions — warn when it knows, say
 * nothing when it does not — and it must never invent a duration of its own.
 *
 * Since ADR-319 the history restates the card from the file's row: a KEPT image
 * says it has no deadline any more, and a GONE one says it is no longer there
 * rather than promising a date that already passed for it.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { Message } from '@/types/chat';

const { translate } = vi.hoisted(() => {
  const content: Record<string, string> = {
    'chat.image_expiry.until':
      "Disponible jusqu'au {{date}} — à conserver dans « Mes fichiers générés » ou à télécharger",
    'chat.image_expiry.soon_one':
      'Expire dans {{count}} heure — à conserver dans « Mes fichiers générés » ou à télécharger',
    'chat.image_expiry.soon_other':
      'Expire dans {{count}} heures — à conserver dans « Mes fichiers générés » ou à télécharger',
    'chat.image_expiry.expired': "Cette image a expiré et n'est plus disponible",
    'chat.image_expiry.kept': 'Conservée : jamais supprimée automatiquement',
    'chat.image_expiry.gone': "Cette image n'est plus disponible",
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

function withImage(
  expiresAt?: string | null,
  restated: { kept?: boolean; gone?: boolean } = {}
): Message {
  return {
    id: 'm1',
    role: 'assistant',
    content: 'Voici votre image',
    timestamp: NOW,
    generatedImages: [
      { url: '/api/v1/attachments/abc', alt: 'un chat', expires_at: expiresAt, ...restated },
    ],
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

  it('says a kept image is kept — no deadline, no countdown', () => {
    renderWithProviders(<ChatMessage isUser={false} message={withImage(null, { kept: true })} />);
    expect(screen.getByText(/Conservée/)).toBeInTheDocument();
    expect(screen.queryByText(/Disponible|Expire/)).not.toBeInTheDocument();
  });

  it('says a gone image is gone, whatever deadline the card was written with', () => {
    // The card was written with a deadline still in the future; the person
    // deleted the file since. « Available until … » would be a lie.
    renderWithProviders(
      <ChatMessage isUser={false} message={withImage(inHours(20), { gone: true })} />
    );
    expect(screen.getByText(/n'est plus disponible/)).toBeInTheDocument();
    expect(screen.queryByText(/Disponible jusqu'au/)).not.toBeInTheDocument();
    // Nothing that would load or save an error page is offered.
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'common.download' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'common.expand_image' })).not.toBeInTheDocument();
  });

  it('keeps the download button available next to the warning', () => {
    // The warning is only useful because the way out is one click away.
    renderWithProviders(<ChatMessage isUser={false} message={withImage(inHours(3))} />);
    expect(screen.getByText(/Expire dans 3 heures/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'common.download' })).toBeInTheDocument();
  });
});
