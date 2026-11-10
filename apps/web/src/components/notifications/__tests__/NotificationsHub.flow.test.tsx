/** The real hub/query lifecycle: criteria never leak into offers or another account. */
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

const { get, useAuth, useAppConfig } = vi.hoisted(() => ({
  get: vi.fn(),
  useAuth: vi.fn(),
  useAppConfig: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig }));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: { get },
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));
import { NotificationsHub } from '../NotificationsHub';

const cut = '2026-11-01T12:00:00Z';
const rows = (content: string) => ({
  reminders: [{ id: content, content, trigger_at: cut }],
  total: 21,
  as_of: cut,
});
const title = (section: string) =>
  screen.getByText(`notifications_hub.sections.${section}.title`, { selector: 'summary span' });

beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'first' } });
  useAppConfig.mockReturnValue({ config: { features: { habits_enabled: true } } });
  get.mockImplementation(async (path: string, options?: { params?: Record<string, unknown> }) => {
    if (path === '/notifications/hub-counts') return { reminders: 21, offers: 0 };
    if (path.startsWith('/habits/proposals'))
      return { proposals: [], total: 0, learning_enabled: false };
    if (path.startsWith('/reminders')) return rows(String(options?.params?.q || 'Original'));
    throw new Error(`Unexpected read ${path}`);
  });
});

it('filters only open histories, retains the two rubrics and leaves proposals independent', async () => {
  const user = userEvent.setup();
  render(<NotificationsHub lng="en" />);
  await waitFor(() => expect(get).toHaveBeenCalledOnce());
  await user.click(title('offers'));
  await user.click(title('reminders'));
  await screen.findByText('Original');
  await user.type(screen.getByRole('searchbox'), 'été');
  await screen.findByText('été');
  await user.selectOptions(
    screen.getByRole('combobox', { name: 'notifications_hub.filter.sort' }),
    'name'
  );
  await waitFor(() => expect(get.mock.lastCall?.[1].params).toEqual({ q: 'été', sort: 'name' }));
  expect(
    get.mock.calls.filter(([path]) => String(path).startsWith('/habits/proposals'))
  ).toHaveLength(1);
  for (const group of ['received', 'upcoming'])
    expect(screen.getByText(`notifications_hub.groups.${group}`)).toBeVisible();
  expect(screen.getByText('notifications_hub.sections.offers.learning_off')).toBeVisible();
  await user.selectOptions(
    screen.getByRole('combobox', { name: 'notifications_hub.filter.category' }),
    'interests'
  );
  expect(title('reminders')).not.toBeVisible();
  const before = get.mock.calls.length;
  await user.clear(screen.getByRole('searchbox'));
  await user.type(screen.getByRole('searchbox'), 'next');
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 350));
  });
  expect(get).toHaveBeenCalledTimes(before);
  expect(
    within(screen.getByRole('combobox', { name: 'notifications_hub.filter.category' })).queryByRole(
      'option',
      { name: 'sms.title' }
    )
  ).toBeNull();
});

it('withdraws private rows and resets the filter/folds when the account changes', async () => {
  const user = userEvent.setup();
  const { rerender } = render(<NotificationsHub lng="en" />);
  await user.click(title('reminders'));
  await screen.findByText('Original');
  await user.type(screen.getByRole('searchbox'), 'first account');
  await screen.findByText('first account');
  useAuth.mockReturnValue({ user: { id: 'second' } });
  rerender(<NotificationsHub lng="en" />);
  expect(screen.queryByText('first account')).toBeNull();
  expect(screen.getByRole('searchbox')).toHaveValue('');
  expect(title('reminders').closest('details')).not.toHaveAttribute('open');
});
