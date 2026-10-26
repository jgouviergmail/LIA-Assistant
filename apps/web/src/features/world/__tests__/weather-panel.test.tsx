import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import apiClient from '@/lib/api-client';
import { WorldWeatherPanel } from '../WorldWeatherPanel';

const auth = vi.hoisted(() => ({ user: { id: 'owner', timezone: 'Asia/Shanghai' } }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => auth }));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: { get: vi.fn() },
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/components/dashboard/cards/WeatherCard', () => ({
  WeatherContent: ({ data }: { data: { location_city: string } }) => <p>{data.location_city}</p>,
}));
afterEach(() => {
  vi.clearAllMocks();
  auth.user = { id: 'owner', timezone: 'Asia/Shanghai' };
});

it('reads only the existing weather cache and drafts an update only on demand', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({
    status: 'ok',
    generated_at: '2026-10-25T00:00:00Z',
    data: { location_city: 'PRIVATE-FORECAST' },
  });
  const ask = vi.fn();
  render(<WorldWeatherPanel lng="en" ownerId="owner" onAsk={ask} />);
  expect(await screen.findByText('PRIVATE-FORECAST')).toBeVisible();
  expect(apiClient.get).toHaveBeenCalledExactlyOnceWith(
    '/briefing/cached-weather',
    expect.anything()
  );
  expect(ask).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'world.lia_menu.conversation' }));
  expect(ask).toHaveBeenCalledTimes(1);
});
it('keeps a cache miss useful without filling any provider and removes a foreign account view', async () => {
  vi.mocked(apiClient.get).mockResolvedValue(null);
  const view = render(<WorldWeatherPanel lng="en" ownerId="owner" onAsk={vi.fn()} />);
  expect(await screen.findByText('dashboard.briefing.cards.weather.empty')).toBeVisible();
  expect(apiClient.get).toHaveBeenCalledTimes(1);
  auth.user = { id: 'other', timezone: 'Asia/Shanghai' };
  view.rerender(<WorldWeatherPanel lng="en" ownerId="owner" onAsk={vi.fn()} />);
  expect(screen.queryByRole('button')).toBeNull();
});

it('displays the forecast timestamp in the configured LIA timezone rather than the device timezone', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({
    status: 'ok',
    generated_at: '2026-10-25T00:00:00Z',
    data: { location_city: 'Shanghai' },
  });
  render(<WorldWeatherPanel lng="fr" ownerId="owner" onAsk={vi.fn()} />);
  await screen.findByText('Shanghai');
  expect(screen.getByText(/08:00/).tagName).toBe('TIME');
});

it.each(['2026-10-24T21:00:00Z', null])(
  'keeps failed refreshes explicit and dates only the displayed stale observation (%s)',
  async stale => {
    vi.mocked(apiClient.get).mockResolvedValue({
      status: 'error',
      generated_at: '2026-10-25T00:00:00Z',
      stale_generated_at: stale,
      error_message: 'Weather source unavailable',
      data: { location_city: 'LAST-OBSERVATION' },
    });
    const view = render(<WorldWeatherPanel lng="en" ownerId="owner" onAsk={vi.fn()} />);
    await screen.findByText('LAST-OBSERVATION');
    expect(screen.getByRole('status')).toHaveTextContent('Weather source unavailable');
    const time = view.container.querySelector('time');
    if (stale) {
      expect(time).toHaveAttribute('datetime', stale);
      expect(time).toHaveTextContent('5:00 AM');
    } else expect(time).toBeNull();
    expect(apiClient.get).toHaveBeenCalledExactlyOnceWith(
      '/briefing/cached-weather',
      expect.anything()
    );
  }
);

it('keeps a failed forecast without stale data actionable without inventing a timestamp', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({
    status: 'error',
    generated_at: '2026-10-25T00:00:00Z',
    data: null,
    error_message: 'No cached observation available',
  });
  const ask = vi.fn();
  const view = render(<WorldWeatherPanel lng="en" ownerId="owner" onAsk={ask} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('No cached observation available');
  expect(view.container.querySelector('time')).toBeNull();
  expect(ask).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'world.lia_menu.conversation' }));
  expect(ask).toHaveBeenCalledTimes(1);
});
