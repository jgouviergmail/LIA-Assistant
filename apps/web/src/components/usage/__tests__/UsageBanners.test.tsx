/**
 * The quota surface of the chat (A5) — one banner at a time.
 *
 * The rule these tests protect is a UX one: the warning is the FORECAST of the
 * wall, so showing both would tell the user twice about the same limit at the
 * moment they can least afford noise. It lives in one component precisely so it
 * cannot drift back into two independent conditions in the page.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { UserUsageLimitResponse, LimitDetail } from '@/types/usage-limits';

const { translate } = vi.hoisted(() => {
  const content: Record<string, string> = {
    'usage_limits.blocked.title': 'Limite atteinte',
    'usage_limits.blocked.message': 'Contactez votre administrateur.',
    'usage_limits.warning.warning': 'Vous avez utilisé {{percent}} % de votre quota.',
    'usage_limits.warning.critical': 'Vous êtes à {{percent}} % de votre quota.',
    'usage_limits.warning.resets_on': 'réinitialisation le {{date}}',
    'usage_limits.warning.dimension.cycle_tokens': 'tokens sur ce cycle',
  };
  return {
    translate: (key: string, params?: Record<string, unknown>) => {
      const value = key in content ? content[key] : key;
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

import { UsageBanners } from '../UsageBanners';

function detail(pct: number | null): LimitDetail {
  return {
    current: pct ?? 0,
    limit: pct === null ? null : 100,
    usage_pct: pct,
    exceeded: pct !== null && pct >= 100,
  };
}

function limits(overrides: Partial<UserUsageLimitResponse> = {}): UserUsageLimitResponse {
  return {
    status: 'ok',
    is_blocked: false,
    blocked_reason: null,
    cycle_tokens: detail(null),
    cycle_messages: detail(null),
    cycle_cost: detail(null),
    absolute_tokens: detail(null),
    absolute_messages: detail(null),
    absolute_cost: detail(null),
    cycle_start: '2026-07-01T00:00:00Z',
    cycle_end: '2026-08-01T00:00:00Z',
    ...overrides,
  } as UserUsageLimitResponse;
}

describe('UsageBanners', () => {
  it('shows nothing on a healthy account', () => {
    const { container } = renderWithProviders(
      <UsageBanners
        limits={limits({ cycle_tokens: detail(12) })}
        isBlocked={false}
        blockReason={null}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the warning before the wall', () => {
    renderWithProviders(
      <UsageBanners
        limits={limits({ status: 'warning', cycle_tokens: detail(84) })}
        isBlocked={false}
        blockReason={null}
      />
    );
    expect(screen.getByText(/84 % de votre quota/)).toBeInTheDocument();
    expect(screen.queryByText('Limite atteinte')).not.toBeInTheDocument();
  });

  it('shows the wall once blocked', () => {
    renderWithProviders(
      <UsageBanners
        limits={limits({ status: 'blocked_limit', is_blocked: true, cycle_tokens: detail(100) })}
        isBlocked
        blockReason="Quota dépassé"
      />
    );
    expect(screen.getByText('Limite atteinte')).toBeInTheDocument();
    expect(screen.getByText('Quota dépassé')).toBeInTheDocument();
  });

  it('never shows both at once', () => {
    // The core invariant. Even with a payload that still grades as critical,
    // a blocked account gets exactly ONE message.
    renderWithProviders(
      <UsageBanners
        limits={limits({ status: 'critical', cycle_tokens: detail(99) })}
        isBlocked
        blockReason={null}
      />
    );
    expect(screen.getByText('Limite atteinte')).toBeInTheDocument();
    expect(screen.queryByText(/votre quota\./)).not.toBeInTheDocument();
  });

  it('still reports a block when the feature payload is missing', () => {
    // `limits` can be null (feature disabled / 404) while the session is
    // blocked for another reason — the wall must still be announced.
    renderWithProviders(<UsageBanners limits={null} isBlocked blockReason="Blocage manuel" />);
    expect(screen.getByText('Limite atteinte')).toBeInTheDocument();
  });

  it('shows nothing without a payload and without a block', () => {
    const { container } = renderWithProviders(
      <UsageBanners limits={null} isBlocked={false} blockReason={null} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
