import { act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createInstance } from 'i18next';
import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { ApplicationPersonalMCPOAuthCard } from '../ApplicationPersonalMCPOAuthCard';
import type { ApplicationCommandStatus } from '@/types/application-commands';
import en from '../../../../locales/en/translation.json';

const calls = vi.hoisted(() => ({ auth: vi.fn(), post: vi.fn(), navigate: vi.fn(), publish: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: calls.auth }));
vi.mock('@/lib/api-client', () => ({ default: { post: calls.post } }));
vi.mock('@/lib/safe-navigation', async () => ({ ...await vi.importActual<typeof import('@/lib/safe-navigation')>('@/lib/safe-navigation'), navigateToAuthorizationUrl: calls.navigate }));
vi.mock('@/lib/application-resources', () => ({ publishApplicationResources: calls.publish }));
const language = createInstance();
await language.init({ lng: 'en', resources: { en: { translation: en } } });
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: language.t, i18n: language }) }));
const command = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const server = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const check = vi.fn(async () => {});

function status(resuming = false): ApplicationCommandStatus {
  const expires = new Date(Date.now() + 60_000).toISOString();
  const interaction = { interaction_id: command, kind: 'device' as const, expires_at: expires };
  const receipt = { success: false, phase: 'waiting' as const, committed: false, no_op: false, error_code: null, interaction,
    values: { personal_mcp_oauth: { id: server, requires_provider_authorization: true, requires_original_browser_completion: true } } };
  return { schema_version: 1, command_id: command, operation_id: 'personal_mcp.oauth_authorize',
    phase: resuming ? 'resuming' : 'waiting', expires_at: expires, interaction: resuming ? null : interaction,
    outcome: resuming ? null : receipt, ...(resuming ? { prior_outcome: receipt } : {}) };
}

function saved(before: ApplicationCommandStatus): ApplicationCommandStatus {
  return { ...before, phase: 'committed', interaction: null, prior_outcome: undefined,
    outcome: { success: true, phase: 'committed', committed: true, no_op: false, error_code: null, interaction: null,
      values: { personal_mcp_oauth: { server_id: server, authorization_saved: true, connection_verified: false } } } };
}

function render(value = status()) {
  return renderWithProviders(<ApplicationPersonalMCPOAuthCard status={value} checkResult={check} readError={null} />);
}

beforeEach(() => { vi.clearAllMocks(); calls.auth.mockReturnValue({ user: { id: 'owner' } }); });

describe('original-browser personal MCP OAuth', () => {
  it('does nothing automatically and opens provider authorization only once on an explicit click', async () => {
    let finish: (value: unknown) => void = () => {};
    calls.post.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const { user } = render();
    expect(calls.post).not.toHaveBeenCalled();
    const button = screen.getByRole('button', { name: 'Open provider authorization' });
    button.focus(); await user.keyboard('{Enter}');
    expect(button).toHaveFocus();
    await user.click(button);
    expect(calls.post).toHaveBeenCalledOnce();
    expect(calls.post.mock.calls[0][0]).toBe(`/application-commands/${command}/personal-mcp-oauth/start`);
    await act(async () => finish({ command_id: command, authorization_url: 'https://provider.example/authorize?state=private' }));
    expect(calls.navigate).toHaveBeenCalledOnce();
    expect(document.body.textContent).not.toContain('private');
    expect(calls.publish).not.toHaveBeenCalled();
  });

  it.each(['javascript:private', 'data:text/html,private'])('rejects unsafe provider URLs without navigation or rendering: %s', async authorization_url => {
    calls.post.mockResolvedValue({ command_id: command, authorization_url });
    const { user } = render();
    await user.click(screen.getByRole('button', { name: 'Open provider authorization' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('not yet confirmed'));
    expect(calls.navigate).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain('private');
  });

  it('discards another command authorization URL', async () => {
    calls.post.mockResolvedValue({ command_id: server, authorization_url: 'https://provider.example/authorize' });
    const { user } = render();
    await user.click(screen.getByRole('button', { name: 'Open provider authorization' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('not yet confirmed'));
    expect(calls.navigate).not.toHaveBeenCalled();
  });

  it('completes only from resuming consent and publishes refresh after a coherent saved receipt', async () => {
    const before = status(true);
    calls.post.mockResolvedValue(saved(before));
    const { user } = render(before);
    expect(calls.post).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Open provider authorization' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Complete authorization' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Authorization saved'));
    expect(calls.post).toHaveBeenCalledOnce();
    expect(calls.publish).toHaveBeenCalledWith('owner', new Set(['user_mcp']));
    expect(screen.getByRole('button', { name: 'Check result' })).toHaveFocus();
  });

  it('permits an explicit pending check again while refusing automatic retries after a lost response', async () => {
    calls.post.mockRejectedValueOnce({ status: 409, data: { detail: { error_code: 'OAUTH_PENDING' } } }).mockRejectedValueOnce(new Error('lost'));
    const { user } = render(status(true));
    await user.click(screen.getByRole('button', { name: 'Complete authorization' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Awaiting provider authorization'));
    await user.click(screen.getByRole('button', { name: 'Complete authorization' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('not yet confirmed'));
    await user.click(screen.getByRole('button', { name: 'Check result' }));
    expect(calls.post).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('button', { name: 'Complete authorization' })).not.toBeInTheDocument();
  });

  it('ignores late authorization URLs after an account change', async () => {
    let finish: (value: unknown) => void = () => {};
    calls.post.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const before = status();
    const { user, rerender } = render(before);
    await user.click(screen.getByRole('button', { name: 'Open provider authorization' }));
    const signal = calls.post.mock.calls[0][2].signal as AbortSignal;
    calls.auth.mockReturnValue({ user: { id: 'other' } });
    rerender(<ApplicationPersonalMCPOAuthCard status={before} checkResult={check} readError={null} />);
    expect(signal.aborted).toBe(true);
    await act(async () => finish({ command_id: command, authorization_url: 'https://provider.example/authorize' }));
    expect(calls.navigate).not.toHaveBeenCalled();
  });

  it('does not grant a retry from an unverified pending error', async () => {
    calls.post.mockRejectedValue({ status: 503, data: { detail: { error_code: 'OAUTH_PENDING' } } });
    const { user } = render(status(true));
    await user.click(screen.getByRole('button', { name: 'Complete authorization' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('not yet confirmed'));
    expect(screen.queryByRole('button', { name: 'Complete authorization' })).not.toBeInTheDocument();
    expect(calls.publish).not.toHaveBeenCalled();
  });

  it('rejects a saved receipt naming another server', async () => {
    const before = status(true); const receipt = saved(before);
    receipt.outcome!.values.personal_mcp_oauth = { server_id: command, authorization_saved: true, connection_verified: false };
    calls.post.mockResolvedValue(receipt);
    const { user } = render(before);
    await user.click(screen.getByRole('button', { name: 'Complete authorization' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('not yet confirmed'));
    expect(calls.publish).not.toHaveBeenCalled();
  });

  it('expired consent offers observation only', () => {
    const before = status(true); before.expires_at = new Date(Date.now() - 1_000).toISOString();
    render(before);
    expect(screen.queryByRole('button', { name: 'Complete authorization' })).not.toBeInTheDocument();
    expect(calls.post).not.toHaveBeenCalled();
  });
});
