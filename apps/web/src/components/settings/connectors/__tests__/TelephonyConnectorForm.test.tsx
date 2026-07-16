/**
 * TelephonyConnectorForm — accessible names for the secret fields (audit
 * F012/F045). The apiKey and webhookSecret inputs used a placeholder as their
 * only name: invisible to voice control, dropped once the field has a value.
 * Both must be reachable via an associated <label>.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

import { TelephonyConnectorForm } from '../TelephonyConnectorForm';

const { mockUseTelephony } = vi.hoisted(() => ({ mockUseTelephony: vi.fn() }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../hooks/useTelephony', () => ({
  useTelephony: mockUseTelephony,
  buildTelephonyWebhookUrl: () => 'https://example.test/api/v1/telephony/webhook',
}));

function telephonyState(step: 'key' | 'number' | 'webhook' | 'success') {
  return {
    step,
    setStep: vi.fn(),
    apiKey: '',
    setApiKey: vi.fn(),
    numbers: [],
    selectedNumberId: null,
    setSelectedNumberId: vi.fn(),
    webhookSecret: '',
    setWebhookSecret: vi.fn(),
    isLoading: false,
    error: null,
    validateKey: vi.fn(),
    activate: vi.fn(),
    reset: vi.fn(),
  };
}

beforeEach(() => {
  mockUseTelephony.mockReset();
});

describe('TelephonyConnectorForm — labelled secret fields', () => {
  it('associates a label with the API key input', () => {
    mockUseTelephony.mockReturnValue(telephonyState('key'));
    const { getByLabelText } = render(<TelephonyConnectorForm lng="fr" />);

    const input = getByLabelText('settings.connectors.telephony.key_label');
    expect(input.tagName).toBe('INPUT');
    expect(input.getAttribute('type')).toBe('password');
  });

  it('associates a label with the webhook secret input', () => {
    mockUseTelephony.mockReturnValue(telephonyState('webhook'));
    const { getByLabelText } = render(<TelephonyConnectorForm lng="fr" />);

    const input = getByLabelText('settings.connectors.telephony.secret_label');
    expect(input.tagName).toBe('INPUT');
    expect(input.getAttribute('type')).toBe('password');
  });

  it('keeps the copy-URL icon button named', () => {
    mockUseTelephony.mockReturnValue(telephonyState('webhook'));
    const { getByLabelText } = render(<TelephonyConnectorForm lng="fr" />);

    expect(getByLabelText('settings.connectors.telephony.copy_url').tagName).toBe('BUTTON');
  });
});
