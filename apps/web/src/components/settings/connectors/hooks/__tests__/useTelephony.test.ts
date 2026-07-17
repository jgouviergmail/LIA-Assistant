/**
 * useTelephony — the per-user telephony connector single-screen form hook.
 *
 * Covers the key-validation branches (valid / invalid / no numbers), the
 * single-number preselection, key-edit invalidation of loaded numbers, the
 * canActivate gate, the activate call payload, and reset. apiClient is a
 * default import → the mock provides `default`.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const h = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('@/lib/api-client', () => ({
  default: { post: (...args: unknown[]) => h.post(...args) },
}));

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

import { useTelephony, buildTelephonyWebhookUrl } from '../useTelephony';

const NUMBERS = [{ phone_number_id: 'pn_1', phone_number: '+33600000000', provider: 'twilio' }];

const TWO_NUMBERS = [
  { phone_number_id: 'pn_1', phone_number: '+33600000000', provider: 'twilio' },
  { phone_number_id: 'pn_2', phone_number: '+33611111111', provider: 'twilio' },
];

beforeEach(() => {
  h.post.mockReset();
});

describe('useTelephony', () => {
  it('validates a key, loads numbers and preselects a single number', async () => {
    h.post.mockResolvedValueOnce({ is_valid: true, message: 'ok', numbers: NUMBERS });
    const { result } = renderHook(() => useTelephony());

    act(() => result.current.setApiKey('sk-testkey'));
    await act(async () => {
      await result.current.validateKey();
    });

    expect(h.post).toHaveBeenCalledWith('/telephony/connector/validate-key', {
      api_key: 'sk-testkey',
    });
    expect(result.current.numbers).toHaveLength(1);
    expect(result.current.selectedNumberId).toBe('pn_1'); // single → preselected
    expect(result.current.error).toBeNull();
  });

  it('does not preselect when several numbers are available', async () => {
    h.post.mockResolvedValueOnce({ is_valid: true, message: 'ok', numbers: TWO_NUMBERS });
    const { result } = renderHook(() => useTelephony());

    act(() => result.current.setApiKey('sk-testkey'));
    await act(async () => {
      await result.current.validateKey();
    });

    expect(result.current.numbers).toHaveLength(2);
    expect(result.current.selectedNumberId).toBeNull();
  });

  it('surfaces an error for an invalid key', async () => {
    h.post.mockResolvedValueOnce({ is_valid: false, message: 'nope', numbers: [] });
    const { result } = renderHook(() => useTelephony());

    act(() => result.current.setApiKey('sk-bad'));
    await act(async () => {
      await result.current.validateKey();
    });

    expect(result.current.numbers).toHaveLength(0);
    expect(result.current.error).toBe('settings.connectors.telephony.invalid_key');
  });

  it('surfaces an error when the workspace has no numbers', async () => {
    h.post.mockResolvedValueOnce({ is_valid: true, message: 'ok', numbers: [] });
    const { result } = renderHook(() => useTelephony());

    act(() => result.current.setApiKey('sk-testkey'));
    await act(async () => {
      await result.current.validateKey();
    });

    expect(result.current.numbers).toHaveLength(0);
    expect(result.current.error).toBe('settings.connectors.telephony.no_numbers');
  });

  it('invalidates loaded numbers when the key is edited', async () => {
    h.post.mockResolvedValueOnce({ is_valid: true, message: 'ok', numbers: NUMBERS });
    const { result } = renderHook(() => useTelephony());

    act(() => result.current.setApiKey('sk-testkey'));
    await act(async () => {
      await result.current.validateKey();
    });
    expect(result.current.numbers).toHaveLength(1);

    act(() => result.current.setApiKey('sk-otherkey'));

    expect(result.current.numbers).toHaveLength(0);
    expect(result.current.selectedNumberId).toBeNull();
    expect(result.current.canActivate).toBe(false);
  });

  it('gates canActivate on key + number + secret', async () => {
    h.post.mockResolvedValueOnce({ is_valid: true, message: 'ok', numbers: NUMBERS });
    const { result } = renderHook(() => useTelephony());

    expect(result.current.canActivate).toBe(false);

    act(() => result.current.setApiKey('sk-testkey'));
    await act(async () => {
      await result.current.validateKey();
    });
    expect(result.current.canActivate).toBe(false); // secret still missing

    act(() => result.current.setWebhookSecret('whsec'));
    expect(result.current.canActivate).toBe(true);
  });

  it('activates with the selected number + webhook secret and calls onSuccess', async () => {
    h.post
      .mockResolvedValueOnce({ is_valid: true, message: 'ok', numbers: NUMBERS })
      .mockResolvedValueOnce({ status: 'active', agent_id: 'ag_1', agent_phone_number_id: 'pn_1' });
    const onSuccess = vi.fn();
    const { result } = renderHook(() => useTelephony({ onSuccess }));

    act(() => result.current.setApiKey('sk-testkey'));
    await act(async () => {
      await result.current.validateKey();
    });
    act(() => {
      result.current.setWebhookSecret('whsec');
    });
    await act(async () => {
      await result.current.activate();
    });

    expect(h.post).toHaveBeenLastCalledWith('/telephony/connector/activate', {
      api_key: 'sk-testkey',
      agent_phone_number_id: 'pn_1',
      webhook_secret: 'whsec',
      caller_number_display: '+33600000000',
    });
    expect(result.current.activated).toBe(true);
    expect(onSuccess).toHaveBeenCalledOnce();
  });

  it('resets the whole form', async () => {
    h.post.mockResolvedValueOnce({ is_valid: true, message: 'ok', numbers: NUMBERS });
    const { result } = renderHook(() => useTelephony());

    act(() => result.current.setApiKey('sk-testkey'));
    await act(async () => {
      await result.current.validateKey();
    });
    act(() => result.current.reset());

    expect(result.current.apiKey).toBe('');
    expect(result.current.numbers).toHaveLength(0);
    expect(result.current.activated).toBe(false);
  });
});

describe('buildTelephonyWebhookUrl', () => {
  it('appends the webhook path to the API base URL', () => {
    expect(buildTelephonyWebhookUrl().endsWith('/api/v1/telephony/webhook')).toBe(true);
  });
});
