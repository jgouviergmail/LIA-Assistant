import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { makeUser } from '@/__tests__/factories';
import apiClient from '@/lib/api-client';
import type { IconStyleUpdate } from '@/lib/icon-style';
import type { Language } from '@/i18n/settings';
import { Calendar } from '@/lib/icons';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { IconStyleProvider } from '../IconStyleProvider';
import { IconStyleSelector } from '../IconStyleSelector';

const { auth } = vi.hoisted(() => ({ auth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: auth }));
vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: string) => ({
    t: (key: string) => {
      const icons = (lng === 'fr' ? fr : en).settings.theme.icons;
      return (
        Object.entries(icons).find(([name]) => `settings.theme.icons.${name}` === key)?.[1] ?? key
      );
    },
  }),
}));

beforeEach(() => {
  vi.restoreAllMocks();
  auth.mockReturnValue({
    user: makeUser({ icon_style: 'fluent' }),
    applyUserUpdate: () => false,
  });
});

function renderAccountSelector(lng: Language) {
  const content = () => (
    <IconStyleProvider>
      <Calendar aria-label="Navigation calendar" />
      <IconStyleSelector lng={lng} />
    </IconStyleProvider>
  );
  const applyUserUpdate = (updated: IconStyleUpdate) => {
    auth.mockReturnValue({ user: makeUser(updated), applyUserUpdate });
    view.rerender(content());
    return true;
  };
  auth.mockReturnValue({ user: makeUser({ icon_style: 'fluent' }), applyUserUpdate });
  const view = render(content());
  return view;
}

describe('Appearance icon selector', () => {
  it.each(['en', 'fr'] as const)('names the native group and all choices in %s', lng => {
    render(
      <IconStyleProvider>
        <IconStyleSelector lng={lng} />
      </IconStyleProvider>
    );
    const title = (lng === 'fr' ? fr : en).settings.theme.icons.title;
    expect(screen.getByRole('group', { name: title })).toBeInTheDocument();
    for (const name of ['Lucide', 'Fluent Color', 'Streamline Flex']) {
      expect(screen.getByRole('radio', { name })).toBeInTheDocument();
    }
    expect(screen.getByRole('radio', { name: 'Fluent Color' })).toBeChecked();
  });

  it('changes icons outside the panel, keeps focus, and sends the account preference', async () => {
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue(makeUser({ icon_style: 'flex' }));
    const user = userEvent.setup();
    renderAccountSelector('fr');
    const flex = screen.getByRole('radio', { name: 'Streamline Flex' });
    await user.click(flex);
    await waitFor(() => expect(flex).toBeChecked());
    expect(flex).toHaveFocus();
    expect(screen.getByLabelText('Navigation calendar')).toHaveAttribute('data-icon-style', 'flex');
    expect(patch).toHaveBeenCalledWith(
      '/users/u1',
      { icon_style: 'flex' },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('drops the old account choice on sign-out and another account sign-in', async () => {
    vi.spyOn(apiClient, 'patch').mockResolvedValue(makeUser({ icon_style: 'lucide' }));
    const user = userEvent.setup();
    const { rerender } = renderAccountSelector('en');
    await user.click(screen.getByRole('radio', { name: 'Lucide' }));
    expect(screen.getByRole('radio', { name: 'Lucide' })).toBeChecked();
    auth.mockReturnValue({ user: null, applyUserUpdate: () => false });
    rerender(
      <IconStyleProvider>
        <IconStyleSelector lng="en" />
      </IconStyleProvider>
    );
    expect(screen.getByRole('radio', { name: 'Fluent Color' })).toBeChecked();
    auth.mockReturnValue({
      user: makeUser({ id: 'u2', icon_style: 'flex' }),
      applyUserUpdate: () => false,
    });
    rerender(
      <IconStyleProvider>
        <IconStyleSelector lng="en" />
      </IconStyleProvider>
    );
    expect(screen.getByRole('radio', { name: 'Streamline Flex' })).toBeChecked();
  });
});
