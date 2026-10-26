import { afterEach, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorldProof } from '../WorldProof';

vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery: () => ({ data: undefined }) }));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate: vi.fn(), loading: false, error: null }),
}));
vi.mock('../WorldShared', () => ({ WorldShared: () => null }));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
afterEach(() => vi.restoreAllMocks());

it('uses the application language names even when an engine supplies different Intl display text', () => {
  const unstable = vi
    .spyOn(Intl.DisplayNames.prototype, 'of')
    .mockReturnValue('ENGINE-SPECIFIC-LABEL');
  render(<WorldProof lng="it" />);
  expect(screen.getAllByRole('button', { name: /Français/ })).toHaveLength(2);
  expect(screen.queryByText(/ENGINE-SPECIFIC/)).not.toBeInTheDocument();
  expect(unstable).not.toHaveBeenCalled();
});
