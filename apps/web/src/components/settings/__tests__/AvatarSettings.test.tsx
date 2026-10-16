import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent } from '@testing-library/react';
import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { AvatarPreferenceSaveProvider } from '@/components/avatars/AvatarPreferenceSaveProvider';
import { AvatarSettings } from '../AvatarSettings';
import type { AvatarConfig } from '@/lib/avatars/types';

const h = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  refreshUser: vi.fn(),
  available: true,
  userId: 'account-1',
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: h.userId }, refreshUser: h.refreshUser }),
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
    h.userId = 'account-1';
    h.refreshUser.mockResolvedValue(undefined);
    h.get.mockImplementation(async (path: string) => (path === '/avatars/config' ? config : []));
    h.put.mockImplementation(async (_path, target) => ({ ...config, ...target }));
  });

  it('browses faces without opening a paid session and saves the account opt-in', async () => {
    renderWithProviders(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    const face = await screen.findByLabelText('settings.avatar.face_custom');
    expect(face).toHaveValue(config.face_id);
    fireEvent.click(screen.getByRole('switch', { name: 'settings.avatar.enabled' }));
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
    renderWithProviders(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    fireEvent.change(await screen.findByLabelText('settings.avatar.face_custom'), {
      target: { value: 'invalid' },
    });
    fireEvent.blur(screen.getByLabelText('settings.avatar.face_custom'));
    expect(await screen.findByRole('alert')).toHaveTextContent('settings.avatar.error');
    expect(h.put).not.toHaveBeenCalled();
  });

  it('uses refreshed connector availability after returning from another section', async () => {
    h.get.mockResolvedValueOnce({ ...config, connected: false });
    const view = renderWithProviders(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    await screen.findByRole('link', { name: 'settings.avatar.connect' });
    view.rerender(
      <AvatarPreferenceSaveProvider>
        <p>Connectors</p>
      </AvatarPreferenceSaveProvider>
    );
    view.rerender(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    await waitFor(() =>
      expect(
        screen.queryByRole('link', { name: 'settings.avatar.connect' })
      ).not.toBeInTheDocument()
    );
    expect(await screen.findByLabelText('settings.avatar.face_custom')).toHaveValue(config.face_id);
  });

  it('shows a static preview, handles a broken image and clears it for an unknown custom face', async () => {
    h.get.mockImplementation(async (path: string) =>
      path === '/avatars/config'
        ? config
        : [
            {
              id: config.face_id,
              name: 'Impressed Tiger',
              source: 'private',
              preview_image_url: 'https://mintcdn.com/simli/catalogue/images/tina.png',
            },
          ]
    );
    renderWithProviders(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    const image = await screen.findByRole('img', { name: 'Impressed Tiger' });
    expect(image).toHaveAttribute('referrerPolicy', 'no-referrer');
    fireEvent.error(image);
    expect(await screen.findByText('settings.avatar.preview_unavailable')).toBeVisible();
    fireEvent.change(screen.getByLabelText('settings.avatar.face_custom'), {
      target: { value: '00000000-0000-4000-8000-000000000099' },
    });
    expect(screen.queryByRole('img')).toBeNull();
    expect(h.put).not.toHaveBeenCalled();
    expect(
      h.get.mock.calls.every(([path]) => ['/avatars/config', '/avatars/faces'].includes(path))
    ).toBe(true);
  });

  it('serializes changes and retains focus while a save is pending', async () => {
    let resolve: (value: AvatarConfig) => void = () => {};
    h.put.mockImplementationOnce(
      () =>
        new Promise<AvatarConfig>(done => {
          resolve = done;
        })
    );
    renderWithProviders(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    await screen.findByLabelText('settings.avatar.face_custom');
    const toggle = screen.getByRole('switch');
    toggle.focus();
    fireEvent.click(toggle);
    fireEvent.click(toggle);
    expect(h.put).toHaveBeenCalledTimes(1);
    expect(toggle).toHaveFocus();
    await act(async () => resolve({ ...config, enabled: true }));
    await waitFor(() => expect(h.put).toHaveBeenCalledTimes(2));
    expect(h.put.mock.calls[1][1]).toEqual({ enabled: false, face_id: config.face_id });
    expect(screen.queryByRole('button', { name: 'settings.avatar.save' })).not.toBeInTheDocument();
  });

  it('keeps a pending write alive when route content unmounts', async () => {
    let resolve: (value: AvatarConfig) => void = () => {};
    h.put.mockImplementationOnce(
      () =>
        new Promise<AvatarConfig>(done => {
          resolve = done;
        })
    );
    const view = renderWithProviders(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    await screen.findByLabelText('settings.avatar.face_custom');
    fireEvent.click(screen.getByRole('switch'));
    const options = h.put.mock.calls[0][2] as { signal: AbortSignal };
    view.rerender(
      <AvatarPreferenceSaveProvider>
        <p>Other route</p>
      </AvatarPreferenceSaveProvider>
    );
    expect(options.signal.aborted).toBe(false);
    await act(async () => resolve({ ...config, enabled: true }));
    view.rerender(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    expect(await screen.findByRole('switch')).toBeChecked();
  });

  it('rolls back a failed save and retries the full desired preference', async () => {
    h.put.mockRejectedValueOnce(new Error('response lost'));
    h.put.mockResolvedValueOnce({ ...config, enabled: true });
    renderWithProviders(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    await screen.findByLabelText('settings.avatar.face_custom');
    fireEvent.click(screen.getByRole('switch'));
    await screen.findByRole('alert');
    expect(screen.getByRole('switch')).not.toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'common.retry' }));
    await waitFor(() => expect(screen.getByRole('switch')).toBeChecked());
    expect(h.put.mock.calls[1][1]).toEqual({ enabled: true, face_id: config.face_id });
  });

  it.each(['success', 'failure', 'moved-focus'] as const)(
    'keeps the retry target stable and restores focus only when it still owns it (%s)',
    async outcome => {
      const retry = Promise.withResolvers<AvatarConfig>();
      h.put.mockRejectedValueOnce(new Error('initial response lost'));
      h.put.mockReturnValueOnce(retry.promise);
      renderWithProviders(
        <AvatarPreferenceSaveProvider>
          <AvatarSettings lng="en" />
        </AvatarPreferenceSaveProvider>
      );
      const field = await screen.findByLabelText('settings.avatar.face_custom');
      fireEvent.click(screen.getByRole('switch'));
      const retryButton = await screen.findByRole('button', { name: 'common.retry' });
      retryButton.focus();
      fireEvent.click(retryButton);
      expect(retryButton).toHaveFocus();
      expect(retryButton).toBeInTheDocument();
      expect(retryButton).toHaveAttribute('aria-busy', 'true');
      expect(retryButton).toHaveTextContent('common.retry');
      fireEvent.click(retryButton);
      expect(h.put).toHaveBeenCalledTimes(2);
      if (outcome === 'moved-focus') field.focus();
      await act(async () => {
        if (outcome === 'failure') retry.reject(new Error('retry response lost'));
        else retry.resolve({ ...config, enabled: true });
      });
      if (outcome === 'failure') {
        expect(screen.getByRole('button', { name: 'common.retry' })).toBe(retryButton);
        expect(retryButton).toHaveFocus();
        expect(retryButton).not.toHaveAttribute('aria-busy', 'true');
      } else {
        await waitFor(() =>
          expect(screen.queryByRole('button', { name: 'common.retry' })).not.toBeInTheDocument()
        );
        expect(outcome === 'moved-focus' ? field : screen.getByRole('switch')).toHaveFocus();
      }
    }
  );

  it('returns retry focus to the connector link when disabling a disconnected avatar leaves no usable face control', async () => {
    const disconnected = { ...config, connected: false, enabled: true };
    h.get.mockImplementation(async (path: string) =>
      path === '/avatars/config' ? disconnected : []
    );
    h.put.mockRejectedValueOnce(new Error('disable response lost'));
    h.put.mockResolvedValueOnce({ ...disconnected, enabled: false });
    renderWithProviders(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    fireEvent.click(await screen.findByRole('switch'));
    const retry = await screen.findByRole('button', { name: 'common.retry' });
    retry.focus();
    fireEvent.click(retry);
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'common.retry' })).not.toBeInTheDocument()
    );
    expect(screen.getByRole('switch')).toBeDisabled();
    expect(screen.queryByLabelText('settings.avatar.face_custom')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'settings.avatar.connect' })).toHaveFocus();
  });

  it('keeps retry saving alive after SPA navigation without restoring focus into the departed form', async () => {
    const retry = Promise.withResolvers<AvatarConfig>();
    h.put.mockRejectedValueOnce(new Error('initial response lost'));
    h.put.mockReturnValueOnce(retry.promise);
    const view = renderWithProviders(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    await screen.findByLabelText('settings.avatar.face_custom');
    fireEvent.click(screen.getByRole('switch'));
    const retryButton = await screen.findByRole('button', { name: 'common.retry' });
    retryButton.focus();
    fireEvent.click(retryButton);
    const { signal } = h.put.mock.calls[1][2] as { signal: AbortSignal };
    view.rerender(
      <AvatarPreferenceSaveProvider>
        <button>Other route</button>
      </AvatarPreferenceSaveProvider>
    );
    const destination = screen.getByRole('button', { name: 'Other route' });
    destination.focus();
    expect(signal.aborted).toBe(false);
    await act(async () => retry.resolve({ ...config, enabled: true }));
    expect(destination).toHaveFocus();
    view.rerender(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    expect(await screen.findByRole('switch')).toBeChecked();
  });

  it('reconciles a lost response before rolling back a save that reached the server', async () => {
    h.put.mockImplementationOnce(async () => {
      h.get.mockImplementation(async (path: string) =>
        path === '/avatars/config' ? { ...config, enabled: true } : []
      );
      throw new Error('response lost after commit');
    });
    renderWithProviders(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    await screen.findByLabelText('settings.avatar.face_custom');
    fireEvent.click(screen.getByRole('switch'));
    await waitFor(() => expect(h.refreshUser).toHaveBeenCalled());
    expect(screen.getByRole('switch')).toBeChecked();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(h.put).toHaveBeenCalledOnce();
    expect(
      h.get.mock.calls.filter(([path]) => path === '/avatars/config').length
    ).toBeGreaterThanOrEqual(2);
  });

  it('abandons the old queue and ignores its response when the account changes', async () => {
    let settle: (value: AvatarConfig) => void = () => {};
    h.put.mockImplementationOnce(
      () =>
        new Promise<AvatarConfig>(resolve => {
          settle = resolve;
        })
    );
    const view = renderWithProviders(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    await screen.findByLabelText('settings.avatar.face_custom');
    fireEvent.click(screen.getByRole('switch'));
    fireEvent.click(screen.getByRole('switch'));
    const { signal } = h.put.mock.calls[0][2] as { signal: AbortSignal };
    h.userId = 'account-2';
    view.rerender(
      <AvatarPreferenceSaveProvider>
        <AvatarSettings lng="en" />
      </AvatarPreferenceSaveProvider>
    );
    expect(signal.aborted).toBe(true);
    await act(async () => settle({ ...config, enabled: true }));
    await waitFor(() => expect(screen.getByRole('switch')).not.toBeChecked());
    expect(h.put).toHaveBeenCalledOnce();
    expect(h.refreshUser).not.toHaveBeenCalled();
  });
});
