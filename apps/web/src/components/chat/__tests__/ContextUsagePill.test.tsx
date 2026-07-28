/**
 * ContextUsagePill — render tests.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ContextUsagePill } from '../ContextUsagePill';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts
        ? `${key}|${Object.entries(opts)
            .map(([k, v]) => `${k}=${v}`)
            .join('|')}`
        : key,
  }),
}));

describe('ContextUsagePill', () => {
  it('renders the percentage with green styling under 50 %', () => {
    render(<ContextUsagePill usage={{ tokens: 5_000, threshold: 20_000, ratio: 0.25 }} />);
    const pill = screen.getByTestId('context-usage-pill');
    expect(pill.textContent).toContain('25%');
    expect(pill.className).toContain('bg-green-100');
  });

  it('shifts to amber between 50 % and 75 %', () => {
    render(<ContextUsagePill usage={{ tokens: 12_000, threshold: 20_000, ratio: 0.6 }} />);
    expect(screen.getByTestId('context-usage-pill').className).toContain('bg-amber-100');
  });

  it('shifts to orange between 75 % and 90 %', () => {
    render(<ContextUsagePill usage={{ tokens: 16_000, threshold: 20_000, ratio: 0.8 }} />);
    expect(screen.getByTestId('context-usage-pill').className).toContain('bg-orange-100');
  });

  it('shifts to rose above 90 %', () => {
    render(<ContextUsagePill usage={{ tokens: 19_000, threshold: 20_000, ratio: 0.95 }} />);
    expect(screen.getByTestId('context-usage-pill').className).toContain('bg-rose-100');
  });

  it('shows the tooltip when clicked', () => {
    render(<ContextUsagePill usage={{ tokens: 12_800, threshold: 51_200, ratio: 0.25 }} />);
    expect(screen.queryByRole('tooltip')).toBeNull();
    fireEvent.click(screen.getByTestId('context-usage-pill'));
    const tooltip = screen.getByRole('tooltip');
    expect(tooltip.textContent).toContain('chat.context_usage.tooltip_compact');
    expect(tooltip.textContent).toContain('percent=25');
  });

  it('uses an aria-label carrying the long tooltip text for accessibility', () => {
    render(<ContextUsagePill usage={{ tokens: 12_800, threshold: 51_200, ratio: 0.25 }} />);
    const pill = screen.getByTestId('context-usage-pill');
    const label = pill.getAttribute('aria-label') ?? '';
    expect(label).toContain('chat.context_usage.tooltip');
    // `toLocaleString` separator is locale-dependent (comma/space/NBSP). Just
    // assert the digits show up so the test passes across CI locales.
    expect(label).toMatch(/12.?800/);
    expect(label).toMatch(/51.?200/);
    expect(label).toContain('percent=25');
  });

  it('clamps the badge label to 100 % when the backend reports overshoot, but keeps the real ratio in the tooltip', () => {
    // 31_000 / 20_000 = 1.55, the reducer clamps this to 1.5 (ratio).
    render(<ContextUsagePill usage={{ tokens: 31_000, threshold: 20_000, ratio: 1.5 }} />);
    const pill = screen.getByTestId('context-usage-pill');
    // Inline label is clamped to 100 % so the badge never shows nonsensical
    // values like "150%".
    expect(pill.textContent).toContain('100%');
    expect(pill.textContent).not.toContain('150%');
    // The aria-label / tooltip route uses the overflow phrasing AND keeps
    // the real percent so the user can still see the actual ratio on hover.
    const label = pill.getAttribute('aria-label') ?? '';
    expect(label).toContain('chat.context_usage.tooltip_overflow');
    expect(label).toContain('percent=150');
  });

  // QW-12: the conversation-totals banner folded into the pill tooltip — one
  // economic surface instead of two. The totals block only exists when the
  // page passes `totals` (tokens_display_enabled gating stays page-side).
  describe('conversation totals in the tooltip', () => {
    const totals = {
      tokensIn: 1_200,
      tokensOut: 800,
      tokensCache: 500,
      googleApiRequests: 3,
      costEur: 0.42,
      userMessageCount: 7,
    };

    it('renders the totals block when totals are provided', () => {
      render(
        <ContextUsagePill
          usage={{ tokens: 5_000, threshold: 20_000, ratio: 0.25 }}
          totals={totals}
        />
      );
      fireEvent.click(screen.getByTestId('context-usage-pill'));

      const block = screen.getByTestId('context-usage-totals');
      // 1200 + 800 + 500 = 2500 TOTAL, then the per-bucket figures.
      expect(block.textContent).toMatch(/2.?500/);
      expect(block.textContent).toContain('IN');
      expect(block.textContent).toContain('OUT');
      expect(block.textContent).toContain('CACHE');
      expect(block.textContent).toContain('GOOGLE');
      expect(block.textContent).toContain('chat.page.message_plural');
      expect(block.textContent).toContain('0,42');
    });

    it('renders no totals block without totals', () => {
      render(<ContextUsagePill usage={{ tokens: 5_000, threshold: 20_000, ratio: 0.25 }} />);
      fireEvent.click(screen.getByTestId('context-usage-pill'));

      expect(screen.getByRole('tooltip')).toBeTruthy();
      expect(screen.queryByTestId('context-usage-totals')).toBeNull();
    });

    it('uses the singular message label for a single message', () => {
      render(
        <ContextUsagePill
          usage={{ tokens: 5_000, threshold: 20_000, ratio: 0.25 }}
          totals={{ ...totals, userMessageCount: 1 }}
        />
      );
      fireEvent.click(screen.getByTestId('context-usage-pill'));

      const block = screen.getByTestId('context-usage-totals');
      expect(block.textContent).toContain('chat.page.message');
      expect(block.textContent).not.toContain('chat.page.message_plural');
    });
  });
});
