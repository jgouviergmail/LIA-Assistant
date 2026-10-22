import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import AccountInactivePage from '../page';

const { push, logout } = vi.hoisted(() => ({ push: vi.fn(), logout: vi.fn() }));

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: {
      id: 'inactive-user',
      full_name: 'Test Account',
      email: 'test@example.test',
      picture_url: 'https://lh3.googleusercontent.com/fictional-account-photo',
      is_active: false,
    },
    isLoading: false,
    logout,
  }),
}));
vi.mock('@/hooks/useLocalizedRouter', () => ({ useLocalizedRouter: () => ({ push }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

describe('inactive account page', () => {
  it('shows account initials without requesting an image from an active-account endpoint', () => {
    render(<AccountInactivePage />);

    expect(screen.getByText('Test Account')).toBeVisible();
    expect(screen.getByText('T')).toBeVisible();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
