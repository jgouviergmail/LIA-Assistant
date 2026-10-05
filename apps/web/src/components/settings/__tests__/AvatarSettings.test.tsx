import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent } from '@testing-library/react';
import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { AvatarSettings } from '../AvatarSettings';
import type { AvatarConfig } from '@/lib/avatars/types';

const h = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), refreshUser: vi.fn(), available: true }));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'account-1' }, refreshUser: h.refreshUser }),
}));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({ config: { features: { avatar_enabled: h.available } } }),
}));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: { get: h.get, put: h.put },
}));

const config: AvatarConfig = {
  available: true,
  enabled: false,
  connected: true,
  face_id: '00000000-0000-4000-8000-000000000001',
  connector_version: 'v1',
  session_length_seconds: 3600,
  connect_timeout_seconds: 15,
};

describe('AvatarSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.available = true;
    h.get.mockImplementation(async (path: string) => (path === '/avatars/config' ? config : []));
    h.put.mockResolvedValue(config);
  });

  it('browses faces without opening a paid session and saves the account opt-in', async () => {
    renderWithProviders(<AvatarSettings lng="en" />);
    const face = await screen.findByLabelText('settings.avatar.face_custom');
    expect(face).toHaveValue(config.face_id);
    fireEvent.click(screen.getByRole('switch', { name: 'settings.avatar.enabled' }));
    fireEvent.click(screen.getByRole('button', { name: 'settings.avatar.save' }));
    await waitFor(() =>
      expect(h.put).toHaveBeenCalledWith(
        '/avatars/settings',
        {
          enabled: true,
          face_id: config.face_id,
        },
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      )
    );
    expect(
      h.get.mock.calls.every(([path]) => path === '/avatars/config' || path === '/avatars/faces')
    ).toBe(true);
    expect(h.refreshUser).toHaveBeenCalledOnce();
  });

  it('refuses malformed face identities before any write', async () => {
    renderWithProviders(<AvatarSettings lng="en" />);
    fireEvent.change(await screen.findByLabelText('settings.avatar.face_custom'), {
      target: { value: 'invalid' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'settings.avatar.save' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('settings.avatar.error');
    expect(h.put).not.toHaveBeenCalled();
  });

  it('shows a static preview, handles a broken image and clears it for an unknown custom face', async () => {
    h.get.mockImplementation(async (path: string) => path === '/avatars/config' ? config : [{
      id: config.face_id, name: 'Impressed Tiger', source: 'private',
      preview_image_url: 'https://mintcdn.com/simli/catalogue/images/tina.png',
    }]);
    renderWithProviders(<AvatarSettings lng="en" />);
    const image = await screen.findByRole('img', { name: 'Impressed Tiger' });
    expect(image).toHaveAttribute('referrerPolicy', 'no-referrer');
    fireEvent.error(image);
    expect(await screen.findByText('settings.avatar.preview_unavailable')).toBeVisible();
    fireEvent.change(screen.getByLabelText('settings.avatar.face_custom'), { target: { value: '00000000-0000-4000-8000-000000000099' } });
    expect(screen.queryByRole('img')).toBeNull();
    expect(h.put).not.toHaveBeenCalled();
    expect(h.get.mock.calls.every(([path]) => ['/avatars/config', '/avatars/faces'].includes(path))).toBe(true);
  });

  it('keeps the save control focused and prevents a second request during saving', async () => {
    let resolve: (value: AvatarConfig) => void = () => {};
    h.put.mockImplementation(() => new Promise<AvatarConfig>(done => { resolve = done; }));
    renderWithProviders(<AvatarSettings lng="en" />);
    await screen.findByLabelText('settings.avatar.face_custom');
    const save = screen.getByRole('button', { name: 'settings.avatar.save' });
    save.focus(); fireEvent.click(save);
    expect(save).not.toBeDisabled(); expect(save).toHaveFocus();
    expect(save).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(save); expect(h.put).toHaveBeenCalledTimes(1);
    await act(async () => resolve(config));
    expect(save).toHaveFocus(); expect(save).toHaveAttribute('aria-disabled', 'false');
  });

  it('cancels an in-flight preference save at unmount and ignores its late result', async () => {
    let resolve: (value: AvatarConfig) => void = () => {};
    h.put.mockImplementation(() => new Promise<AvatarConfig>(done => { resolve = done; }));
    const { unmount } = renderWithProviders(<AvatarSettings lng="en" />);
    await screen.findByLabelText('settings.avatar.face_custom');
    fireEvent.click(screen.getByRole('button', { name: 'settings.avatar.save' }));
    const options = h.put.mock.calls[0][2] as { signal: AbortSignal };
    unmount(); expect(options.signal.aborted).toBe(true);
    await act(async () => resolve(config));
    expect(h.refreshUser).not.toHaveBeenCalled();
  });
});
