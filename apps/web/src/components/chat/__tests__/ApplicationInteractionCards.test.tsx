import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { ApplicationCommandStatus } from '@/types/application-commands';

const { get, post, auth } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  auth: vi.fn(),
}));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { ...original.default, get, post } };
});
vi.mock('@/hooks/useAuth', () => ({ useAuth: auth }));
const language = createInstance();
await language.init({ lng: 'en', resources: { en: { translation: en }, fr: { translation: fr } } });
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: language.t, i18n: language }) }));
vi.mock('@/components/auth/StepUpDialog', () => ({
  StepUpDialog: ({
    open,
    onVerified,
    onCancel,
  }: {
    open: boolean;
    onVerified: () => void;
    onCancel: () => void;
  }) =>
    open ? (
      <div role="dialog" aria-label="Secure authentication">
        <button onClick={onVerified}>Verify identity</button>
        <button onClick={onCancel}>Cancel authentication</button>
      </div>
    ) : null,
}));

import { ApplicationInteractionCards } from '../ApplicationInteractionCards';
import { ApiStepUpError } from '@/lib/api-client';
import {
  registerRecordingDevice,
  type RecordingDeviceState,
} from '@/lib/application-recording-device';

const id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const metadata = { application_interactions: [{ command_id: id }] };
function status(over: Partial<ApplicationCommandStatus> = {}): ApplicationCommandStatus {
  const deadline = new Date(Date.now() + 60_000).toISOString();
  const interaction = { interaction_id: id, kind: 'secure' as const, expires_at: deadline };
  return {
    schema_version: 1,
    command_id: id,
    operation_id: 'device_sessions.revoke_others',
    phase: 'waiting',
    expires_at: deadline,
    interaction,
    outcome: {
      success: false,
      phase: 'waiting',
      committed: false,
      no_op: false,
      values: {},
      error_code: null,
      interaction,
    },
    ...over,
  };
}
const completed = () =>
  status({
    phase: 'committed',
    interaction: null,
    outcome: {
      success: true,
      phase: 'committed',
      committed: true,
      no_op: false,
      values: { revoked_sessions: 2, approved_sessions: 2 },
      error_code: null,
      interaction: null,
    },
  });

beforeEach(async () => {
  vi.resetAllMocks();
  auth.mockReturnValue({ user: { id: 'owner' } });
  get.mockResolvedValue(status());
  post.mockResolvedValue(completed());
  await language.changeLanguage('en');
});

describe('approved secure application continuation', () => {
  it.each(['en', 'fr'])(
    'executes one confirmed device action through its original owner (%s)',
    async lng => {
      await language.changeLanguage(lng);
      const current = status();
      const interaction = {
        interaction_id: id,
        kind: 'device' as const,
        expires_at: current.expires_at,
      };
      get.mockResolvedValue({
        ...current,
        operation_id: 'meeting_device.control',
        interaction,
        outcome: { ...current.outcome, interaction },
      });
      const meetingId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
      let observed: RecordingDeviceState = { phase: 'idle', meeting_id: null, supported: true };
      const execute = vi.fn(async () => {
        observed = { ...observed, phase: 'recording', meeting_id: meetingId };
      });
      const withdraw = registerRecordingDevice('owner', { snapshot: () => observed, execute });
      post.mockImplementation(async (endpoint: string) =>
        endpoint.endsWith('/claim')
          ? {
              command_id: id,
              claim_token: meetingId,
              expires_at: current.expires_at,
              intent: { action: 'start', phase: 'idle', meeting_id: null },
            }
          : { ...completed(), operation_id: 'meeting_device.control' }
      );
      try {
        renderWithProviders(<ApplicationInteractionCards metadata={metadata} />);
        const button = await screen.findByRole('button', {
          name: lng === 'fr' ? 'Exécuter sur cet appareil' : 'Execute on this device',
        });
        expect(post).not.toHaveBeenCalled();
        expect(get).toHaveBeenCalledTimes(1);
        await userEvent.click(button);
        await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
        await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
        expect(post).toHaveBeenLastCalledWith(
          `/application-commands/${id}/device/ack`,
          expect.objectContaining({
            result: 'completed',
            phase: 'recording',
            meeting_id: meetingId,
          })
        );
        expect(
          await screen.findByText(
            lng === 'fr'
              ? fr.settings.application_tools.device_recording_done
              : en.settings.application_tools.device_recording_done
          )
        ).toBeInTheDocument();
        await waitFor(() => expect(screen.getByRole('button', {
          name: lng === 'fr' ? 'Vérifier le résultat' : 'Check result',
        })).toHaveFocus());
      } finally {
        withdraw();
      }
    }
  );

  it('never executes or retries an unknown device claim', async () => {
    const current = status();
    const interaction = {
      interaction_id: id,
      kind: 'device' as const,
      expires_at: current.expires_at,
    };
    get.mockResolvedValue({
      ...current,
      operation_id: 'meeting_device.control',
      interaction,
      outcome: { ...current.outcome, interaction },
    });
    const execute = vi.fn(async () => undefined);
    const withdraw = registerRecordingDevice('owner', {
      snapshot: () => ({ phase: 'idle', meeting_id: null, supported: true }),
      execute,
    });
    post.mockRejectedValue(new Error('Lost claim response'));
    try {
      renderWithProviders(<ApplicationInteractionCards metadata={metadata} />);
      await userEvent.click(await screen.findByRole('button', { name: 'Execute on this device' }));
      await waitFor(() =>
        expect(
          screen.queryByRole('button', { name: 'Execute on this device' })
        ).not.toBeInTheDocument()
      );
      await userEvent.click(screen.getByRole('button', { name: 'Check result' }));
      expect(execute).not.toHaveBeenCalled();
      expect(post).toHaveBeenCalledTimes(1);
    } finally {
      withdraw();
    }
  });
  it('routes OAuth consent to the provider card without automatic mutation or account-security authentication', async () => {
    const current = status();
    const interaction = {
      interaction_id: id,
      kind: 'device' as const,
      expires_at: current.expires_at,
    };
    get.mockResolvedValue({
      ...current,
      operation_id: 'personal_mcp.oauth_authorize',
      interaction,
      outcome: {
        ...current.outcome,
        interaction,
        values: {
          personal_mcp_oauth: {
            id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
            requires_provider_authorization: true,
            requires_original_browser_completion: true,
          },
        },
      },
    });
    renderWithProviders(<ApplicationInteractionCards metadata={metadata} />);
    expect(
      await screen.findByRole('button', { name: 'Open provider authorization' })
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Verify identity' })).not.toBeInTheDocument();
  });
  it('routes an approved private MCP command to its form without secure-auth or automatic mutation', async () => {
    const current = status();
    const interaction = {
      interaction_id: id,
      kind: 'device' as const,
      expires_at: current.expires_at,
    };
    get.mockResolvedValue({
      ...current,
      operation_id: 'personal_mcp.configuration',
      interaction,
      outcome: {
        ...current.outcome,
        interaction,
        values: {
          personal_mcp_configuration: {
            server_id: null,
            creating: true,
            requires_private_browser_form: true,
          },
        },
      },
    });
    renderWithProviders(<ApplicationInteractionCards metadata={metadata} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Open the private form' }));
    expect(await screen.findByRole('textbox', { name: 'Name' })).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Verify identity' })).not.toBeInTheDocument();
  });
  it('preserves a committed export request when its final projection fails', async () => {
    get.mockResolvedValue(
      status({
        operation_id: 'account_export.request',
        phase: 'failed',
        interaction: null,
        outcome: {
          success: false,
          phase: 'failed',
          committed: true,
          no_op: false,
          values: {},
          error_code: 'POST_COMMIT_FAILURE',
          interaction: null,
        },
      })
    );
    renderWithProviders(<ApplicationInteractionCards metadata={metadata} />);
    expect(await screen.findByRole('status')).toHaveTextContent(
      'The export request was saved, but its status could not be confirmed. Check it in settings.'
    );
    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Continue securely' })).not.toBeInTheDocument();
  });
  it('queues an export after secure confirmation without claiming the archive is ready', async () => {
    get.mockResolvedValue(status({ operation_id: 'account_export.request' }));
    post.mockResolvedValue({
      ...completed(),
      operation_id: 'account_export.request',
      outcome: { ...completed().outcome, values: { export_job_id: id, export_status: 'pending' } },
    });
    renderWithProviders(<ApplicationInteractionCards metadata={metadata} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Continue securely' }));
    expect(
      await screen.findByRole('region', { name: 'Finish requesting your account export' })
    ).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(
      'Export requested. Preparation runs in the background; check its status in settings.'
    );
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
  it.each([
    ['en', 'Continue securely'],
    ['fr', 'Poursuivre en sécurité'],
  ])('has a localized keyboard action in %s', async (locale, name) => {
    await language.changeLanguage(locale);
    renderWithProviders(<ApplicationInteractionCards metadata={metadata} />);
    const button = await screen.findByRole('button', { name });
    button.focus();
    await userEvent.keyboard('{Enter}');
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenCalledWith(`/application-commands/${id}/resume`);
    await waitFor(() =>
      expect(
        screen.getByRole('button', {
          name: locale === 'en' ? 'Check result' : 'Vérifier le résultat',
        })
      ).toHaveFocus()
    );
  });

  it('reauthenticates through the existing guard and retries only that unclaimed challenge', async () => {
    post.mockRejectedValueOnce(new ApiStepUpError());
    renderWithProviders(<ApplicationInteractionCards metadata={metadata} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Continue securely' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Verify identity' }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(JSON.stringify(post.mock.calls)).not.toContain('owner');
    expect(await screen.findByRole('status')).toHaveTextContent('2 sessions');
  });

  it('retains focus and refuses duplicate submissions while the request is running', async () => {
    let finish: ((value: ApplicationCommandStatus) => void) | undefined;
    post.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finish = resolve;
        })
    );
    renderWithProviders(<ApplicationInteractionCards metadata={metadata} />);
    const button = await screen.findByRole('button', { name: 'Continue securely' });
    button.focus();
    await userEvent.keyboard('{Enter}{Enter}');
    expect(post).toHaveBeenCalledTimes(1);
    expect(button).toHaveFocus();
    await act(async () => {
      finish?.(completed());
    });
  });

  it('withdraws the old account action and cannot resume a parked A-B-A challenge', async () => {
    post.mockRejectedValueOnce(new ApiStepUpError());
    const view = renderWithProviders(<ApplicationInteractionCards metadata={metadata} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Continue securely' }));
    await screen.findByRole('dialog');
    auth.mockReturnValue({ user: { id: 'other' } });
    view.rerender(<ApplicationInteractionCards metadata={metadata} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    auth.mockReturnValue({ user: { id: 'owner' } });
    view.rerender(<ApplicationInteractionCards metadata={metadata} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('refuses malformed references and never posts an expired confirmation', async () => {
    const view = renderWithProviders(
      <ApplicationInteractionCards
        metadata={{ application_interactions: [{ command_id: '../auth' }] }}
      />
    );
    expect(get).not.toHaveBeenCalled();
    get.mockResolvedValue(
      status({
        expires_at: new Date(Date.now() - 1000).toISOString(),
        phase: 'expired',
        interaction: null,
        outcome: null,
      })
    );
    view.rerender(<ApplicationInteractionCards metadata={metadata} />);
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: 'Continue securely' })).not.toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('offers observation after a lost response without automatically replaying the action', async () => {
    post.mockRejectedValueOnce(new Error('private diagnostic'));
    renderWithProviders(<ApplicationInteractionCards metadata={metadata} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Continue securely' }));
    const read = await screen.findByRole('button', { name: 'Check result' });
    get.mockResolvedValueOnce(completed());
    await userEvent.click(read);
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('private diagnostic')).not.toBeInTheDocument();
    expect(await screen.findByRole('status')).toHaveTextContent('2 sessions');
  });

  it('cannot apply a late completion from the previous account after A-B-A', async () => {
    let finish: ((value: ApplicationCommandStatus) => void) | undefined;
    post.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finish = resolve;
        })
    );
    const view = renderWithProviders(<ApplicationInteractionCards metadata={metadata} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Continue securely' }));
    auth.mockReturnValue({ user: { id: 'other' } });
    view.rerender(<ApplicationInteractionCards metadata={metadata} />);
    auth.mockReturnValue({ user: { id: 'owner' } });
    view.rerender(<ApplicationInteractionCards metadata={metadata} />);
    await screen.findByRole('button', { name: 'Continue securely' });
    await act(async () => {
      finish?.(completed());
    });
    expect(screen.getByRole('status')).not.toHaveTextContent('2 sessions');
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('refuses another command in the POST response and requires observation before another action', async () => {
    post.mockResolvedValueOnce({
      ...completed(),
      command_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    });
    renderWithProviders(<ApplicationInteractionCards metadata={metadata} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Continue securely' }));
    await screen.findByRole('button', { name: 'Check result' });
    expect(screen.queryByRole('button', { name: 'Continue securely' })).not.toBeInTheDocument();
    expect(screen.getByRole('status')).not.toHaveTextContent('2 sessions');
    expect(post).toHaveBeenCalledTimes(1);
  });
});
