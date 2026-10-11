import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderWithProviders, screen } from '@/__tests__/test-utils';
import { UploadRequest } from '@/__tests__/upload-request';
import { subscribeApplicationResource } from '@/lib/application-resources';
import type { ApplicationCommandStatus } from '@/types/application-commands';
import { createInstance } from 'i18next';
import en from '../../../../locales/en/translation.json';

const auth = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/useAuth', () => ({ useAuth: auth }));
const language = createInstance();
await language.init({ lng: 'en', interpolation: { escapeValue: false }, resources: { en: { translation: en } } });
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: language.t, i18n: language }) }));

const command = '00000000-0000-4000-8000-000000000001';
const pluginId = '00000000-0000-4000-8000-000000000002';
function waiting(): ApplicationCommandStatus {
  const expires = new Date(Date.now() + 60_000).toISOString();
  const interaction = { interaction_id: command, kind: 'device' as const, expires_at: expires };
  return { schema_version: 1, command_id: command, operation_id: 'plugin_file.upload', phase: 'waiting',
    expires_at: expires, interaction,
    outcome: { success: false, phase: 'waiting', committed: false, no_op: false, error_code: null, interaction,
      values: { plugin_file_upload: { request: { replace_plugin_id: null }, previous: null,
        max_file_size_bytes: 524288, max_package_files: 256, max_decompressed_bytes: 8388608,
        max_personal_plugins: 10, allowed_extensions: ['.zip'], browser_file_confirmation_required: true } } } };
}
function committed() {
  return { success: true, phase: 'committed', committed: true, no_op: false, error_code: null, interaction: null,
    values: { plugin_file_upload: { plugin_id: pluginId, name: 'my-plugin', version: '1.0', description: null,
      updated: false, components: [], warnings: [], file_cleanup_pending: false },
      upload_accepted: true, file_cleanup_pending: false, cache_refresh_pending: false } };
}
beforeEach(() => { auth.mockReturnValue({ user: { id: 'owner' } }); UploadRequest.sent = [];
  vi.stubGlobal('XMLHttpRequest', UploadRequest); });

describe('a plugin ZIP belongs to one explicitly consenting browser lifetime', () => {
  it('chooses without sending and confirms exactly once', async () => {
    const { ApplicationPluginFileUploadCard } = await import('../ApplicationPluginFileUploadCard');
    const { user } = renderWithProviders(<ApplicationPluginFileUploadCard status={waiting()} checkResult={vi.fn(async () => {})} readError={null} />);
    const file = new File(['private ZIP bytes'], 'local.zip', { type: 'application/zip' });
    await user.upload(screen.getByLabelText('Choose a plugin ZIP'), file);
    expect(UploadRequest.sent).toHaveLength(0);
    const confirm = screen.getByRole('button', { name: 'Import this plugin' });
    await user.click(confirm); await user.click(confirm);
    expect(UploadRequest.sent).toHaveLength(1);
    expect(UploadRequest.sent[0].open).toHaveBeenCalledWith('POST', expect.stringContaining(`/application-commands/${command}/plugin-upload`));
    expect(UploadRequest.sent[0].setRequestHeader).toHaveBeenCalledWith('x-lia-file-confirmed', 'true');
    expect(UploadRequest.sent[0].data?.get('file')).toBe(file);
  });

  it('refreshes all three owned menus and preserves keyboard focus after acceptance', async () => {
    const { ApplicationPluginFileUploadCard } = await import('../ApplicationPluginFileUploadCard');
    const mine = [vi.fn(), vi.fn(), vi.fn()]; const foreign = vi.fn();
    const stop = [subscribeApplicationResource('owner', 'plugins', mine[0]),
      subscribeApplicationResource('owner', 'skills', mine[1]), subscribeApplicationResource('owner', 'user_mcp', mine[2]),
      subscribeApplicationResource('other', 'plugins', foreign)];
    try {
      const { user } = renderWithProviders(<ApplicationPluginFileUploadCard status={waiting()} checkResult={vi.fn(async () => {})} readError={null} />);
      await user.upload(screen.getByLabelText('Choose a plugin ZIP'), new File(['bytes'], 'local.zip'));
      screen.getByRole('button', { name: 'Import this plugin' }).focus(); await user.keyboard('{Enter}');
      act(() => { const request = UploadRequest.sent[0]; request.responseText = JSON.stringify(committed()); request.onload?.(); });
      expect(screen.getByText('The plugin was imported.')).toBeInTheDocument();
      expect((screen.getByLabelText('Choose a plugin ZIP') as HTMLInputElement).files).toHaveLength(0);
      for (const read of mine) expect(read).toHaveBeenCalledOnce();
      expect(foreign).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'Check result' })).toHaveFocus();
    } finally { stop.forEach(read => read()); }
  });

  it('never retries an uncertain upload', async () => {
    const { ApplicationPluginFileUploadCard } = await import('../ApplicationPluginFileUploadCard');
    const { user } = renderWithProviders(<ApplicationPluginFileUploadCard status={waiting()} checkResult={vi.fn(async () => {})} readError={null} />);
    await user.upload(screen.getByLabelText('Choose a plugin ZIP'), new File(['bytes'], 'local.zip'));
    await user.click(screen.getByRole('button', { name: 'Import this plugin' }));
    act(() => UploadRequest.sent[0].onerror?.());
    await user.click(screen.getByRole('button', { name: 'Import this plugin' }));
    expect(UploadRequest.sent).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Import this plugin' })).toHaveAttribute('aria-disabled', 'true');
  });

  it('shows translated skipped outcomes without rendering private debug details', async () => {
    const { ApplicationPluginFileUploadCard } = await import('../ApplicationPluginFileUploadCard');
    const { user } = renderWithProviders(<ApplicationPluginFileUploadCard status={waiting()} checkResult={vi.fn(async () => {})} readError={null} />);
    await user.upload(screen.getByLabelText('Choose a plugin ZIP'), new File(['bytes'], 'local.zip'));
    await user.click(screen.getByRole('button', { name: 'Import this plugin' }));
    const result = committed();
    const component = { kind: 'mcp_server', key: 'local-command', status: 'skipped',
      issues: [{ code: 'server_transport_unsupported', field: null, detail: 'PRIVATE DEBUG AND COMMAND' }] };
    // Serialize a real backend-shaped report rather than weakening the fixture's narrow inferred array type.
    act(() => { const request = UploadRequest.sent[0]; request.responseText = JSON.stringify({ ...result,
      values: { ...result.values, plugin_file_upload: { ...result.values.plugin_file_upload, components: [component] } } }); request.onload?.(); });
    expect(screen.getByText('local-command')).toBeInTheDocument();
    expect(screen.queryByText('PRIVATE DEBUG AND COMMAND')).not.toBeInTheDocument();
    expect(screen.getByText('The plugin was imported.')).toBeInTheDocument();
  });

  it('retires private file selection on a switch away and back to the account', async () => {
    const { ApplicationPluginFileUploadCard } = await import('../ApplicationPluginFileUploadCard');
    const status = waiting(); const check = vi.fn(async () => {});
    const view = renderWithProviders(<ApplicationPluginFileUploadCard status={status} checkResult={check} readError={null} />);
    await view.user.upload(screen.getByLabelText('Choose a plugin ZIP'), new File(['bytes'], 'private-name.zip'));
    auth.mockReturnValue({ user: { id: 'other' } });
    view.rerender(<ApplicationPluginFileUploadCard status={status} checkResult={check} readError={null} />);
    auth.mockReturnValue({ user: { id: 'owner' } });
    view.rerender(<ApplicationPluginFileUploadCard status={status} checkResult={check} readError={null} />);
    expect(screen.queryByText('private-name.zip', { exact: false })).not.toBeInTheDocument();
    await view.user.click(screen.getByRole('button', { name: 'Import this plugin' }));
    expect(UploadRequest.sent).toHaveLength(0);
  });
});
