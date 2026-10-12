import { act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createInstance } from 'i18next';
import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { ApplicationPersonalMCPConfigurationCard } from '../ApplicationPersonalMCPConfigurationCard';
import type { ApplicationCommandStatus } from '@/types/application-commands';
import type { RequestConfig } from '@/lib/api-client';
import en from '../../../../locales/en/translation.json';

const calls = vi.hoisted(() => ({ auth: vi.fn(), get: vi.fn(), post: vi.fn(), publish: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: calls.auth }));
vi.mock('@/lib/api-client', () => ({ default: { get: calls.get, post: calls.post } }));
vi.mock('@/lib/application-resources', () => ({ publishApplicationResources: calls.publish }));
const language = createInstance();
await language.init({ lng: 'en', resources: { en: { translation: en } } });
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: language.t, i18n: language }) }));
const command = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const server = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const check = vi.fn(async () => {});

function waiting(serverId: string | null = null): ApplicationCommandStatus {
  const expires = new Date(Date.now() + 60_000).toISOString();
  const interaction = { interaction_id: command, kind: 'device' as const, expires_at: expires };
  return {
    schema_version: 1,
    command_id: command,
    operation_id: 'personal_mcp.configuration',
    phase: 'waiting',
    expires_at: expires,
    interaction,
    outcome: {
      success: false,
      phase: 'waiting',
      committed: false,
      no_op: false,
      error_code: null,
      interaction,
      values: {
        personal_mcp_configuration: {
          server_id: serverId,
          creating: serverId === null,
          requires_private_browser_form: true,
        },
      },
    },
  };
}

function saved(status: ApplicationCommandStatus): ApplicationCommandStatus {
  return {
    ...status,
    phase: 'committed',
    interaction: null,
    outcome: {
      success: true,
      phase: 'committed',
      committed: true,
      no_op: false,
      error_code: null,
      interaction: null,
      values: {
        personal_mcp_configuration: {
          server_id: server,
          configuration_saved: true,
          connection_verified: false,
        },
      },
    },
  };
}

function source() {
  return {
    id: server,
    name: 'Saved server',
    url: 'https://example.org/mcp?private=value',
    auth_type: 'api_key',
    header_name: 'X-API-Key',
    oauth_scopes: null,
    domain_description: 'Saved description',
    timeout_seconds: 30,
    iterative_mode: false,
    has_credentials: true,
    has_oauth_credentials: false,
  };
}

function render(status = waiting()) {
  return renderWithProviders(
    <ApplicationPersonalMCPConfigurationCard status={status} checkResult={check} readError={null} />
  );
}

async function open(user: ReturnType<typeof render>['user']) {
  await user.click(screen.getByRole('button', { name: 'Open the private form' }));
  return screen.findByRole('textbox', { name: 'Name' });
}

async function fill(user: ReturnType<typeof render>['user']) {
  await user.type(await open(user), 'New server');
  await user.type(screen.getByRole('textbox', { name: 'Server URL' }), 'https://example.org/mcp');
}

beforeEach(() => {
  vi.clearAllMocks();
  calls.auth.mockReturnValue({ user: { id: 'owner' } });
  calls.get.mockResolvedValue({ servers: [source()], total: 1 });
});

describe('approved private MCP browser configuration', () => {
  it('keeps input local and submits exactly once after explicit save, preserving focus while busy', async () => {
    let finish: (value: unknown) => void = () => {};
    calls.post.mockImplementation(
      () =>
        new Promise(resolve => {
          finish = resolve;
        })
    );
    const status = waiting();
    const { user } = render(status);
    await fill(user);
    expect(calls.get).not.toHaveBeenCalled();
    expect(calls.post).not.toHaveBeenCalled();
    const save = screen.getByRole('button', { name: 'Save' });
    save.focus();
    await user.keyboard('{Enter}');
    expect(save).toHaveFocus();
    await user.click(save);
    expect(calls.post).toHaveBeenCalledOnce();
    expect(calls.post.mock.calls[0][0]).toBe(`/application-commands/${command}/personal-mcp`);
    expect(calls.post.mock.calls[0][1]).toEqual({
      values: {
        name: 'New server',
        url: 'https://example.org/mcp',
        auth_type: 'none',
        timeout_seconds: 30,
        iterative_mode: false,
      },
    });
    expect(calls.post.mock.calls[0][2]).toMatchObject({ cache: 'no-store' });
    await act(async () => {
      finish(saved(status));
    });
    expect(
      await screen.findByText('Configuration saved. The connection has not been tested.')
    ).toBeInTheDocument();
    expect(calls.publish).toHaveBeenCalledWith('owner', new Set(['user_mcp']));
    expect(check).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Check result' })).toHaveFocus();
  });
  it('reuses the owned settings read, preserves local edits on status refresh and sends only the changed private field', async () => {
    calls.post.mockResolvedValue(saved(waiting(server)));
    const status = waiting(server);
    const view = render(status);
    const name = await open(view.user);
    expect(name).toHaveValue('Saved server');
    expect(calls.get).toHaveBeenCalledWith(
      '/mcp/servers',
      expect.objectContaining({ cache: 'no-store' })
    );
    const key = screen.getByLabelText('API Key');
    await view.user.type(key, 'private-key');
    view.rerender(
      <ApplicationPersonalMCPConfigurationCard
        status={{ ...status }}
        checkResult={check}
        readError={new Error('temporary read outage')}
      />
    );
    expect(key).toHaveValue('private-key');
    await view.user.click(screen.getByRole('button', { name: 'Save' }));
    expect(calls.post.mock.calls[0][1]).toEqual({ values: { api_key: 'private-key' } });
    expect(screen.queryByDisplayValue('private-key')).not.toBeInTheDocument();
  });
  it('does not offer an unconfirmed, malformed or completed interaction', () => {
    const status = waiting();
    status.phase = 'pending';
    status.interaction = null;
    status.outcome = null;
    const view = render(status);
    expect(screen.queryByRole('button', { name: 'Open the private form' })).not.toBeInTheDocument();
    view.rerender(
      <ApplicationPersonalMCPConfigurationCard
        status={{ ...waiting(), outcome: null }}
        checkResult={check}
        readError={null}
      />
    );
    expect(screen.queryByRole('button', { name: 'Open the private form' })).not.toBeInTheDocument();
    expect(calls.get).not.toHaveBeenCalled();
    expect(calls.post).not.toHaveBeenCalled();
  });
  it('refuses a missing or malformed owned target without exposing provider data', async () => {
    calls.get.mockResolvedValue({ servers: [{ ...source(), id: command }], total: 1 });
    const { user } = render(waiting(server));
    await user.click(screen.getByRole('button', { name: 'Open the private form' }));
    await waitFor(() => expect(screen.getAllByRole('alert')).not.toHaveLength(0));
    expect(screen.queryByRole('textbox', { name: 'Name' })).not.toBeInTheDocument();
    expect(screen.queryByText('private=value', { exact: false })).not.toBeInTheDocument();
    expect(calls.post).not.toHaveBeenCalled();
  });
  it('retires input, aborts transport and ignores late responses after an account change', async () => {
    let finish: (value: unknown) => void = () => {};
    calls.post.mockImplementation(
      () =>
        new Promise(resolve => {
          finish = resolve;
        })
    );
    const status = waiting();
    const view = render(status);
    await fill(view.user);
    await view.user.click(screen.getByRole('button', { name: 'Save' }));
    const request = calls.post.mock.calls[0][2] as RequestConfig;
    calls.auth.mockReturnValue({ user: { id: 'other' } });
    view.rerender(
      <ApplicationPersonalMCPConfigurationCard
        status={status}
        checkResult={check}
        readError={null}
      />
    );
    expect(request.signal?.aborted).toBe(true);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await act(async () => {
      finish(saved(status));
    });
    expect(check).not.toHaveBeenCalled();
    expect(calls.publish).not.toHaveBeenCalled();
  });
  it('never retries an uncertain submission and clears private inputs', async () => {
    calls.post.mockRejectedValue(new Error('network timeout: private-key'));
    const { user } = render();
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(
      await screen.findByText(
        'The result is not yet confirmed. Check it without submitting the action again.'
      )
    ).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open the private form' })).not.toBeInTheDocument();
    expect(screen.queryByText('private-key', { exact: false })).not.toBeInTheDocument();
    expect(calls.post).toHaveBeenCalledOnce();
  });
  it('retires typed secrets when the original confirmation expires', async () => {
    const status = waiting(server);
    const view = render(status);
    await open(view.user);
    await view.user.type(screen.getByLabelText('API Key'), 'private-key');
    view.rerender(
      <ApplicationPersonalMCPConfigurationCard
        status={{ ...status, expires_at: new Date(Date.now() - 1).toISOString() }}
        checkResult={check}
        readError={null}
      />
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.queryByDisplayValue('private-key')).not.toBeInTheDocument();
    expect(calls.post).not.toHaveBeenCalled();
  });
  it('aborts an expired submission and leaves observation available without another write', async () => {
    calls.post.mockImplementation(() => new Promise(() => {}));
    const status = waiting();
    const view = render(status);
    await fill(view.user);
    await view.user.click(screen.getByRole('button', { name: 'Save' }));
    const request = calls.post.mock.calls[0][2] as RequestConfig;
    view.rerender(
      <ApplicationPersonalMCPConfigurationCard
        status={{ ...status, expires_at: new Date(Date.now() - 1).toISOString() }}
        checkResult={check}
        readError={null}
      />
    );
    await waitFor(() => expect(request.signal?.aborted).toBe(true));
    await view.user.click(screen.getByRole('button', { name: 'Check result' }));
    expect(check).toHaveBeenCalledOnce();
    expect(calls.post).toHaveBeenCalledOnce();
  });
  it('can retry only a failed initial private read, without replaying a save', async () => {
    calls.get
      .mockRejectedValueOnce(new Error('private diagnostics'))
      .mockResolvedValueOnce({ servers: [source()], total: 1 });
    const { user } = render(waiting(server));
    await user.click(screen.getByRole('button', { name: 'Open the private form' }));
    await user.click(await screen.findByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('textbox', { name: 'Name' })).toHaveValue('Saved server');
    expect(calls.get).toHaveBeenCalledTimes(2);
    expect(calls.post).not.toHaveBeenCalled();
    expect(screen.queryByText('private diagnostics')).not.toBeInTheDocument();
  });
  it('refuses a committed result belonging to another command', async () => {
    calls.post.mockResolvedValue({ ...saved(waiting()), command_id: server });
    const { user } = render();
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(
      await screen.findByText(
        'The result is not yet confirmed. Check it without submitting the action again.'
      )
    ).toBeInTheDocument();
    expect(calls.publish).not.toHaveBeenCalled();
  });
});
