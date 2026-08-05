/**
 * UsageStatistics — the "Consommation" disclosure of the dashboard.
 *
 * Results lead the page (ResultsSummary); the volumes live behind this native
 * `<details>`. Owner arbitration 2026-08-05: the disclosure now opens by
 * DEFAULT — the figures are consulted often enough that the extra click cost
 * more than the visual quiet it bought. It remains a real disclosure: the
 * reader can still fold it, and the semantics (summary button, keyboard
 * toggle) come from the platform.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { UsageStatistics } from '../UsageStatistics';

vi.mock('@/hooks/useUserStatistics', () => ({
  useUserStatistics: () => ({
    statistics: {
      current_cycle_start: '2026-08-01T00:00:00Z',
      total_since: '2026-01-01T00:00:00Z',
      cycle_messages: 42,
      total_messages: 420,
      cycle_prompt_tokens: 1000,
      cycle_completion_tokens: 500,
      cycle_cached_tokens: 200,
      total_prompt_tokens: 10_000,
      total_completion_tokens: 5_000,
      total_cached_tokens: 2_000,
      cycle_google_api_requests: 7,
      total_google_api_requests: 70,
      cycle_cost_eur: 1.23,
      total_cost_eur: 12.3,
    },
    isLoading: false,
  }),
}));

vi.mock('@/hooks/useUsageLimits', () => ({
  useUsageLimits: () => ({ limits: null, isLoading: false }),
}));

describe('UsageStatistics — consumption disclosure', () => {
  it('opens by default: the figures are visible without a click', () => {
    renderWithProviders(<UsageStatistics />);

    const details = screen.getByRole('group');
    expect(details).toHaveAttribute('open');
    // The content is genuinely readable, not merely attribute-open.
    expect(screen.getByText('42')).toBeVisible();
  });

  it('remains a real disclosure the reader can fold', () => {
    renderWithProviders(<UsageStatistics />);

    // The platform contract: a <details> without `open` hides its content.
    // Removing the attribute (what a summary click does) folds the block.
    const details = screen.getByRole('group');
    details.removeAttribute('open');
    expect(screen.getByText('42')).not.toBeVisible();
  });
});
