import { describe, it, expect, vi } from 'vitest';
import { act, renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { CardSection, SmsData } from '@/types/briefing';
import { SmsCard } from '../SmsCard';
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => '/fr/dashboard',
}));
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
  it('shows ten literal SMS rows in source order and opens the selected message in settings', async () => {
    const items = Array.from({ length: 10 }, (_, index) => ({
      id: `10000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
      sender: '+33612345678',
      display_name: `Camille ${index}`,
      received_at: `2026-10-20T07:${String(59 - index).padStart(2, '0')}:00Z`,
      date_kind: 'received',
      body_excerpt: `<script>private${index}</script>`,
      body_truncated: false,
    }));
    const { user, container } = renderWithProviders(
      <SmsCard
        section={{ ...section, data: { ...section.data!, items } }}
        isRefreshing={false}
        onRefresh={vi.fn()}
      />
    );
    expect(screen.getByText('137')).toBeInTheDocument();
    const rows = screen.getAllByRole('listitem');
    expect(rows).toHaveLength(10);
    items.forEach((item, index) =>
      expect(within(rows[index]).getByText(item.body_excerpt)).toBeVisible()
    );
    expect(container.querySelector('script')).toBeNull();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.queryByText('dashboard.briefing.cards.sms.open')).not.toBeInTheDocument();
    expect(within(rows[0]).getByText(/09:59/)).toBeVisible();
    const target = within(rows[0]).getByRole('button');
    act(() => target.focus());
    await user.keyboard('{Enter}');
    expect(push).toHaveBeenCalledWith(
      '/dashboard/settings?section=sms&message=10000000-0000-4000-8000-000000000001'
    );
  });
  it('accepts an older server bundle with no SMS section', () => {
    const { container } = renderWithProviders(<SmsCard isRefreshing={false} onRefresh={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
  it('keeps a metadata-only server response usable during a rolling upgrade', () => {
    renderWithProviders(<SmsCard section={section} isRefreshing={false} onRefresh={vi.fn()} />);
    expect(screen.getByText('137')).toBeVisible();
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
