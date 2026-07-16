/**
 * AppleCredentialForm — the client-side credential gate (Apple ID must be an
 * email, the app password must match the xxxx-xxxx-xxxx-xxxx shape), the
 * single-click connect wiring (args passed through), the success side effects
 * (toast + reset + onActivated), and the bulk service list.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { useAppleConnect } = vi.hoisted(() => ({ useAppleConnect: vi.fn() }));
vi.mock('../hooks/useAppleConnect', () => ({ useAppleConnect }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { AppleCredentialForm } from '../AppleCredentialForm';

const APPLE_ID = 'settings.connectors.apple.apple_id_placeholder';
const APP_PASSWORD_KEY = 'settings.connectors.apple.app_password_placeholder';
const CONNECT = 'settings.connectors.apple.connect';

const VALID_ID = 'user@icloud.com';
const VALID_PASSWORD_VALUE = 'abcd-efgh-ijkl-mnop';

beforeEach(() => {
  vi.clearAllMocks();
  useAppleConnect.mockReturnValue({ connect: vi.fn(), connecting: false });
});

describe('AppleCredentialForm — credential gate', () => {
  it('keeps connect disabled until both fields are well-formed', () => {
    renderWithProviders(<AppleCredentialForm lng="en" services={['apple_calendar']} />);
    expect(screen.getByRole('button', { name: CONNECT })).toBeDisabled();
  });

  it('rejects an app password that does not match the required shape', async () => {
    const { user } = renderWithProviders(
      <AppleCredentialForm lng="en" services={['apple_calendar']} />
    );
    await user.type(screen.getByPlaceholderText(APPLE_ID), VALID_ID);
    await user.type(screen.getByPlaceholderText(APP_PASSWORD_KEY), 'not-a-valid-pass');
    expect(screen.getByRole('button', { name: CONNECT })).toBeDisabled();
  });
});

describe('AppleCredentialForm — connect', () => {
  it('passes the credentials and target services through to connect', async () => {
    const connect = vi.fn();
    useAppleConnect.mockReturnValue({ connect, connecting: false });
    const { user } = renderWithProviders(
      <AppleCredentialForm lng="en" services={['apple_calendar']} />
    );
    await user.type(screen.getByPlaceholderText(APPLE_ID), VALID_ID);
    await user.type(screen.getByPlaceholderText(APP_PASSWORD_KEY), VALID_PASSWORD_VALUE);
    await user.click(screen.getByRole('button', { name: CONNECT }));
    expect(connect).toHaveBeenCalledWith(VALID_ID, VALID_PASSWORD_VALUE, ['apple_calendar']);
  });

  it('resets and notifies the parent on a successful connection', async () => {
    useAppleConnect.mockImplementation((opts: { onSuccess: () => void }) => ({
      connect: vi.fn(async () => opts.onSuccess()),
      connecting: false,
    }));
    const onActivated = vi.fn();
    const { user } = renderWithProviders(
      <AppleCredentialForm lng="en" services={['apple_calendar']} onActivated={onActivated} />
    );
    await user.type(screen.getByPlaceholderText(APPLE_ID), VALID_ID);
    await user.type(screen.getByPlaceholderText(APP_PASSWORD_KEY), VALID_PASSWORD_VALUE);
    await user.click(screen.getByRole('button', { name: CONNECT }));
    await waitFor(() => expect(onActivated).toHaveBeenCalledTimes(1));
    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(screen.getByPlaceholderText(APPLE_ID)).toHaveValue('');
  });

  it('lists every service to activate in bulk mode', () => {
    renderWithProviders(
      <AppleCredentialForm lng="en" services={['apple_calendar', 'apple_contacts']} />
    );
    expect(screen.getByText('settings.connectors.apple.services_to_activate')).toBeInTheDocument();
  });
});
