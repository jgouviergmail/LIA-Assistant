/**
 * APIKeyConnectorForm — the client-side format gate (short/placeholder keys
 * keep the actions disabled), server validation (valid message vs error), the
 * activation submit (success calls onSuccess; failure surfaces the error and
 * does not), and cancel.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
// Only the default client is stubbed — `ApiError` stays real so the error
// shape the form reads is the one the client actually throws.
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { ApiError } from '@/lib/api-client';

import APIKeyConnectorForm from '../APIKeyConnectorForm';

const KEY_INPUT = 'settings.connectors.apiKey.api_key_placeholder';
const VALIDATE = 'settings.connectors.apiKey.validate';
const ACTIVATE = 'settings.connectors.apiKey.activate';

function renderForm(props: Partial<React.ComponentProps<typeof APIKeyConnectorForm>> = {}) {
  return renderWithProviders(
    <APIKeyConnectorForm lng="en" connectorType="brave" connectorLabel="Brave Search" {...props} />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  post.mockResolvedValue({ is_valid: true, message: 'Valid key', masked_key: 'sk-…ij' });
});

describe('APIKeyConnectorForm — format gate', () => {
  it('keeps validate and activate disabled until a plausible key is entered', () => {
    renderForm();
    expect(screen.getByRole('button', { name: VALIDATE })).toBeDisabled();
    expect(screen.getByRole('button', { name: ACTIVATE })).toBeDisabled();
  });

  it('rejects obvious placeholder keys', async () => {
    const { user } = renderForm();
    await user.type(screen.getByPlaceholderText(KEY_INPUT), 'your_api_key_here');
    expect(screen.getByRole('button', { name: ACTIVATE })).toBeDisabled();
  });
});

describe('APIKeyConnectorForm — validation', () => {
  it('validates a plausible key against the server and shows the result', async () => {
    const { user } = renderForm();
    await user.type(screen.getByPlaceholderText(KEY_INPUT), 'sk-abcdefghij');
    await user.click(screen.getByRole('button', { name: VALIDATE }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/connectors/api-key/validate', {
        api_key: 'sk-abcdefghij',
        api_secret: null,
        connector_type: 'brave',
      })
    );
    expect(await screen.findByText('Valid key')).toBeInTheDocument();
  });

  it('surfaces a validation error when the request fails', async () => {
    post.mockRejectedValue(new Error('down'));
    const { user } = renderForm();
    await user.type(screen.getByPlaceholderText(KEY_INPUT), 'sk-abcdefghij');
    await user.click(screen.getByRole('button', { name: VALIDATE }));
    expect(
      await screen.findByText('settings.connectors.apiKey.error_validation')
    ).toBeInTheDocument();
  });

  it("shows the backend's own reason instead of the generic wording", async () => {
    post.mockRejectedValue(
      new ApiError('irrelevant', 502, { detail: 'Brave rejected the key: quota exhausted' })
    );
    const { user } = renderForm();
    await user.type(screen.getByPlaceholderText(KEY_INPUT), 'sk-abcdefghij');
    await user.click(screen.getByRole('button', { name: VALIDATE }));
    expect(await screen.findByText('Brave rejected the key: quota exhausted')).toBeInTheDocument();
    expect(
      screen.queryByText('settings.connectors.apiKey.error_validation')
    ).not.toBeInTheDocument();
  });
});

describe('APIKeyConnectorForm — activation', () => {
  it('activates the connector and reports success', async () => {
    post.mockResolvedValue({});
    const onSuccess = vi.fn();
    const { user } = renderForm({ onSuccess });
    await user.type(screen.getByPlaceholderText(KEY_INPUT), 'sk-abcdefghij');
    await user.click(screen.getByRole('button', { name: ACTIVATE }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/connectors/api-key/activate', {
        api_key: 'sk-abcdefghij',
        api_secret: null,
        key_name: null,
        connector_type: 'brave',
      })
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('surfaces an activation error and does not report success', async () => {
    post.mockRejectedValue(new Error('nope'));
    const onSuccess = vi.fn();
    const { user } = renderForm({ onSuccess });
    await user.type(screen.getByPlaceholderText(KEY_INPUT), 'sk-abcdefghij');
    await user.click(screen.getByRole('button', { name: ACTIVATE }));
    expect(
      await screen.findByText('settings.connectors.apiKey.error_activation')
    ).toBeInTheDocument();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("surfaces the backend's activation reason verbatim", async () => {
    post.mockRejectedValue(
      new ApiError('irrelevant', 409, { detail: 'A brave connector is already active' })
    );
    const onSuccess = vi.fn();
    const { user } = renderForm({ onSuccess });
    await user.type(screen.getByPlaceholderText(KEY_INPUT), 'sk-abcdefghij');
    await user.click(screen.getByRole('button', { name: ACTIVATE }));
    expect(await screen.findByText('A brave connector is already active')).toBeInTheDocument();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('cancels via the provided handler', async () => {
    const onCancel = vi.fn();
    const { user } = renderForm({ onCancel });
    await user.click(screen.getByRole('button', { name: 'common.cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
