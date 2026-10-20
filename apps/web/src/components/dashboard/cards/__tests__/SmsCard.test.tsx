import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { CardSection, SmsData } from '@/types/briefing';
import { SmsCard } from '../SmsCard';
const section: CardSection<SmsData> = {
  status: 'ok',
  data: {
    timezone: 'Europe/Paris',
    total: 137,
    window_total: 5,
    window_start: '2026-10-19T08:00:00Z',
    as_of: '2026-10-20T08:00:00Z',
    latest_at: '2026-10-20T07:55:00Z',
  },
  generated_at: '2026-10-20T08:00:00Z',
  error_code: null,
  error_message: null,
  from_cache: false,
  stale_generated_at: null,
  last_attempt_at: null,
};
describe('SMS home card', () => {
  it('shows exact archive and rolling-window counts with a local archive link', () => {
    renderWithProviders(<SmsCard section={section} isRefreshing={false} onRefresh={vi.fn()} />);
    expect(screen.getByText('137')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText(/10:00.*10:00/)).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', '/fr/dashboard/sms');
  });
  it('accepts an older server bundle with no SMS section', () => {
    const { container } = renderWithProviders(<SmsCard isRefreshing={false} onRefresh={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
