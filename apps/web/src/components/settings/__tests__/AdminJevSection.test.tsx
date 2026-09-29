import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import apiClient from '@/lib/api-client';
import type { JevSettings } from '@/types/jev';
import AdminJevSection from '../AdminJevSection';

const endpoint = '/admin/llm-config/jev';
const localLabel = 'settings.admin.jev.usages.meeting_template';
const globalLabel = 'settings.admin.jev.globalLabel';
function settings(over: Partial<JevSettings> = {}): JevSettings {
  return {
    enabled: false,
    usages: [
      {
        usage: 'meeting_template',
        label_key: localLabel,
        llm_type: 'meeting_template_selection',
        enabled: true,
        effective: false,
        readiness: 'ready',
      },
    ],
    ...over,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('Jev administration', () => {
  it('recovers from an initial failed read without guessing a switch state', async () => {
    const get = vi
      .spyOn(apiClient, 'get')
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue(settings());
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('settings.admin.jev.loadError');
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'settings.admin.jev.refresh' }));
    expect(await screen.findByRole('switch', { name: localLabel })).toBeChecked();
    expect(get).toHaveBeenCalledTimes(2);
  });
  it('does not claim OFF while the first read is pending', () => {
    vi.spyOn(apiClient, 'get').mockReturnValue(new Promise(() => {}));
    renderWithProviders(<AdminJevSection lng="en" />);
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('common.loading');
  });

  it('keeps a local preference visible when the global circuit is off', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue(settings());
    renderWithProviders(<AdminJevSection lng="en" />);
    expect(await screen.findByRole('switch', { name: localLabel })).toBeChecked();
    expect(screen.getByRole('switch', { name: globalLabel })).not.toBeChecked();
    expect(screen.getByText('settings.admin.jev.existing')).toBeInTheDocument();
  });

  it('writes only the selected switch and renders the server response', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue(settings());
    const response = settings();
    response.usages[0].enabled = false;
    const save = vi.spyOn(apiClient, 'patch').mockResolvedValue(response);
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    const control = await screen.findByRole('switch', { name: localLabel });
    await user.click(control);
    await waitFor(() => expect(control).not.toBeChecked());
    expect(save).toHaveBeenCalledWith(
      endpoint,
      { usage: 'meeting_template', enabled: false },
      undefined
    );
    expect(control).toHaveFocus();
  });

  it('keeps the previous state and focus after a rejected save', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue(settings());
    vi.spyOn(apiClient, 'patch').mockRejectedValue(new Error('unavailable'));
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    const control = await screen.findByRole('switch', { name: localLabel });
    await user.click(control);
    expect(await screen.findByRole('alert')).toHaveTextContent('settings.admin.jev.saveError');
    expect(control).toBeChecked();
    expect(control).toHaveFocus();
  });

  it('suppresses duplicate toggles while a save is pending', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue(settings());
    const save = vi.spyOn(apiClient, 'patch').mockReturnValue(new Promise(() => {}));
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    const control = await screen.findByRole('switch', { name: globalLabel });
    await user.click(control);
    await user.click(control);
    expect(save).toHaveBeenCalledTimes(1);
    expect(control).toHaveAttribute('aria-disabled', 'true');
    expect(control).toHaveFocus();
  });

  it('allows switching OFF even when configuration became unavailable', async () => {
    const initial = settings({ enabled: true });
    initial.usages[0].readiness = 'missing_key';
    vi.spyOn(apiClient, 'get').mockResolvedValue(initial);
    const save = vi.spyOn(apiClient, 'patch').mockResolvedValue(settings());
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    await user.click(await screen.findByRole('switch', { name: globalLabel }));
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith(endpoint, { usage: null, enabled: false }, undefined)
    );
  });
});
