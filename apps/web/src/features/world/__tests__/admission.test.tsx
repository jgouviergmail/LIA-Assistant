import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import apiClient from '@/lib/api-client';
import { WorldShared } from '../WorldShared';
import { DEFAULT_AVATAR } from '../avatar-protocol';
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: { get: vi.fn() },
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../WorldAvatarPreview', () => ({ WorldAvatarPreview: () => <div /> }));
it('keeps an unsent appearance draft usable during slow focus revalidation', async () => {
  const owner = '11111111-1111-4111-8111-111111111111';
  const get = vi.mocked(apiClient.get);
  get.mockResolvedValueOnce({
    owner_id: owner,
    public_name: 'Native name',
    needs_setup: true,
    needs_reset: false,
    preferences: { version: 1, revision: 0, appearance: DEFAULT_AVATAR },
  });
  render(<WorldShared lng="en" ownerId={owner} />);
  const hair = await screen.findByRole('combobox', { name: 'world.avatar.hair' });
  await waitFor(() => expect(hair).toBeVisible());
  get.mockImplementationOnce(() => new Promise(() => {}));
  act(() => {
    hair.focus();
    window.dispatchEvent(new Event('focus'));
  });
  fireEvent.change(hair, { target: { value: 'long' } });
  expect(hair).toHaveValue('long');
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'world.session.enter' })).toBeDisabled();
});
