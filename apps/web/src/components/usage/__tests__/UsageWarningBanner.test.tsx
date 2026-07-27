/**
 * Quota warning banner (A5).
 *
 * The point of this banner is to exist before the wall does. What it must never
 * do is mislead: promise a reset date for a limit that never resets, print a
 * raw ISO timestamp, or shout as loudly as the blocking banner when nothing is
 * broken yet.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { UsageWarning } from '@/lib/usage-warning';

const { translate } = vi.hoisted(() => {
  const content: Record<string, string> = {
    'usage_limits.warning.warning': 'Vous avez utilisé {{percent}} % de votre quota.',
    'usage_limits.warning.critical': 'Vous êtes à {{percent}} % de votre quota.',
    'usage_limits.warning.resets_on': 'réinitialisation le {{date}}',
    'usage_limits.warning.dimension.cycle_tokens': 'tokens sur ce cycle',
    'usage_limits.warning.dimension.absolute_cost': 'coût total',
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

import { UsageWarningBanner } from '../UsageWarningBanner';

const CYCLE: UsageWarning = {
  level: 'warning',
  dimension: 'cycle_tokens',
  usagePct: 84,
  cycleEnd: '2026-08-01T00:00:00Z',
};

describe('UsageWarningBanner', () => {
  it('states how much of the quota is gone', () => {
    renderWithProviders(<UsageWarningBanner warning={CYCLE} />);
    expect(screen.getByText(/84 % de votre quota/)).toBeInTheDocument();
  });

  it('names the dimension that will actually block', () => {
    renderWithProviders(<UsageWarningBanner warning={CYCLE} />);
    expect(screen.getByText(/tokens sur ce cycle/)).toBeInTheDocument();
  });

  it('says when the limit lifts, in a readable form', () => {
    renderWithProviders(<UsageWarningBanner warning={CYCLE} />);
    // Localized, never the raw ISO instant.
    expect(screen.getByText(/réinitialisation le/)).toBeInTheDocument();
    expect(screen.queryByText(/2026-08-01T00:00:00Z/)).not.toBeInTheDocument();
  });

  it('promises no reset for an absolute limit', () => {
    // Absolute limits never reset; a date here would be a lie users plan on.
    renderWithProviders(
      <UsageWarningBanner
        warning={{ level: 'warning', dimension: 'absolute_cost', usagePct: 90, cycleEnd: null }}
      />
    );
    expect(screen.getByText(/coût total/)).toBeInTheDocument();
    expect(screen.queryByText(/réinitialisation/)).not.toBeInTheDocument();
  });

  it('escalates its wording at the critical grade', () => {
    renderWithProviders(
      <UsageWarningBanner warning={{ ...CYCLE, level: 'critical', usagePct: 97 }} />
    );
    expect(screen.getByText(/Vous êtes à 97 %/)).toBeInTheDocument();
  });

  it('announces politely rather than interrupting', () => {
    // The user is mid-task and nothing is broken: `status`, not `alert`.
    renderWithProviders(<UsageWarningBanner warning={CYCLE} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('never leaks a translation key', () => {
    renderWithProviders(<UsageWarningBanner warning={CYCLE} />);
    expect(screen.getByRole('status').textContent).not.toContain('usage_limits.');
  });
});
