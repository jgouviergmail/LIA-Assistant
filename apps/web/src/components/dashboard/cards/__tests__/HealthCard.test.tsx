import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { CardSection, HealthData, HealthSummaryItem } from '@/types/briefing';
import { HealthCard } from '../HealthCard';

function section(item: HealthSummaryItem): CardSection<HealthData> {
  return {
    status: 'ok',
    data: { items: [item] },
    generated_at: '2026-10-15T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

function metric(kind: HealthSummaryItem['kind'], value: number | null): HealthSummaryItem {
  return {
    kind,
    value_today: value,
    value_avg_window: 777,
    unit: kind === 'steps' ? 'count' : 'bpm',
    window_days: 14,
    days_with_data: 12,
  };
}

function renderMetric(kind: HealthSummaryItem['kind'], value: number | null) {
  renderWithProviders(
    <HealthCard section={section(metric(kind, value))} isRefreshing={false} onRefresh={() => {}} />
  );
  return within(screen.getByRole('listitem'));
}

describe('HealthCard daily thresholds', () => {
  it.each([
    { kind: 'heart_rate', value: 69, ink: 'text-green-700' },
    { kind: 'heart_rate', value: 70, ink: 'text-green-700' },
    { kind: 'heart_rate', value: 71, ink: 'text-orange-700' },
    { kind: 'heart_rate', value: 89, ink: 'text-orange-700' },
    { kind: 'heart_rate', value: 90, ink: 'text-red-700' },
    { kind: 'heart_rate', value: 91, ink: 'text-red-700' },
    { kind: 'steps', value: 0, ink: 'text-red-700' },
    { kind: 'steps', value: 4999, ink: 'text-red-700' },
    { kind: 'steps', value: 5000, ink: 'text-red-700' },
    { kind: 'steps', value: 5001, ink: 'text-orange-700' },
    { kind: 'steps', value: 9999, ink: 'text-orange-700' },
    { kind: 'steps', value: 10000, ink: 'text-green-700' },
    { kind: 'steps', value: 10001, ink: 'text-green-700' },
  ] satisfies { kind: HealthSummaryItem['kind']; value: number; ink: string }[])(
    'shows $kind today=$value with the requested $ink threshold, keeping the window distinct',
    ({ kind, value, ink }) => {
      const row = renderMetric(kind, value);
      const label = new Intl.NumberFormat('fr').format(value);
      expect(row.getByText(label, { normalizer: text => text })).toHaveClass(ink);
      expect(row.getByText('777')).toHaveClass('text-foreground/80');
      expect(row.getByText(`dashboard.briefing.cards.health.kind_${kind}`)).toBeInTheDocument();
      expect(row.getByText(/dashboard\.briefing\.cards\.health\.today/)).toBeInTheDocument();
      expect(row.getByText(/dashboard\.briefing\.cards\.health\.avg_window/)).toBeInTheDocument();
    }
  );

  it.each([
    { kind: 'heart_rate', value: 70.4, shown: '70', ink: 'text-green-700' },
    { kind: 'heart_rate', value: 70.5, shown: '71', ink: 'text-orange-700' },
    { kind: 'heart_rate', value: 89.5, shown: '90', ink: 'text-red-700' },
    { kind: 'steps', value: 4999.6, shown: '5\u202f000', ink: 'text-red-700' },
    { kind: 'steps', value: 9999.5, shown: '10\u202f000', ink: 'text-green-700' },
  ] satisfies { kind: HealthSummaryItem['kind']; value: number; shown: string; ink: string }[])(
    'applies visual thresholds to the displayed rounded $kind=$shown',
    ({ kind, value, shown, ink }) => {
      const row = renderMetric(kind, value);
      expect(row.getByText(shown, { normalizer: text => text })).toHaveClass(ink);
    }
  );

  it.each(['heart_rate', 'steps'] satisfies HealthSummaryItem['kind'][])(
    'keeps an unknown %s value neutral instead of interpreting it as zero',
    kind => {
      const row = renderMetric(kind, null);
      expect(row.getByText('—')).toHaveClass('text-foreground');
      expect(row.getByText('—')).not.toHaveClass(
        'text-green-700',
        'text-orange-700',
        'text-red-700'
      );
      expect(row.queryByText('0')).not.toBeInTheDocument();
      expect(row.getByText('777')).toBeInTheDocument();
    }
  );
  it('keeps a missing window average unknown while daily zero remains a real red value', () => {
    const item = { ...metric('steps', 0), value_avg_window: null };
    renderWithProviders(
      <HealthCard section={section(item)} isRefreshing={false} onRefresh={() => {}} />
    );
    const row = within(screen.getByRole('listitem'));
    expect(row.getByText('0')).toHaveClass('text-red-700');
    expect(row.getByText('—')).toHaveClass('text-foreground/80');
  });
});
