/**
 * TelephonyConnectorForm — accessible names for the secret fields (audit
 * F012/F045). The apiKey and webhookSecret inputs used a placeholder as their
 * only name: invisible to voice control, dropped once the field has a value.
 * Both must be reachable via an associated <label>. The form is single-screen:
 * every section renders at once, and `activated` switches to the success view.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

import { TelephonyConnectorForm } from '../TelephonyConnectorForm';

import type { useTelephony } from '../hooks/useTelephony';

type TelephonyState = ReturnType<typeof useTelephony>;

const { mockUseTelephony } = vi.hoisted(() => ({ mockUseTelephony: vi.fn() }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../hooks/useTelephony', () => ({
  useTelephony: mockUseTelephony,
  buildTelephonyWebhookUrl: () => 'https://example.test/api/v1/telephony/webhook',
}));

function telephonyState(overrides: Partial<TelephonyState> = {}): TelephonyState {
  return {
    apiKey: '',
    setApiKey: vi.fn(),
    numbers: [],
    selectedNumberId: null,
    setSelectedNumberId: vi.fn(),
    webhookSecret: '',
    setWebhookSecret: vi.fn(),
    isValidating: false,
    isActivating: false,
    activated: false,
    canActivate: false,
    error: null,
    validateKey: vi.fn(),
    activate: vi.fn(),
    reset: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  mockUseTelephony.mockReset();
});

describe('TelephonyConnectorForm — labelled secret fields', () => {
  it('associates a label with the API key input', () => {
    mockUseTelephony.mockReturnValue(telephonyState());
    const { getByLabelText } = render(<TelephonyConnectorForm lng="fr" />);

    const input = getByLabelText('settings.connectors.telephony.step_key');
    expect(input.tagName).toBe('INPUT');
    expect(input.getAttribute('type')).toBe('password');
  });

  it('associates a label with the webhook secret input', () => {
    mockUseTelephony.mockReturnValue(telephonyState());
    const { getByLabelText } = render(<TelephonyConnectorForm lng="fr" />);

    const input = getByLabelText('settings.connectors.telephony.secret_label');
    expect(input.tagName).toBe('INPUT');
    expect(input.getAttribute('type')).toBe('password');
  });

  it('keeps the copy-URL icon button named', () => {
    mockUseTelephony.mockReturnValue(telephonyState());
    const { getByLabelText } = render(<TelephonyConnectorForm lng="fr" />);

    expect(getByLabelText('settings.connectors.telephony.copy_url').tagName).toBe('BUTTON');
  });

  it('switches to the success view once activated', () => {
    mockUseTelephony.mockReturnValue(telephonyState({ activated: true }));
    const { getByText, queryByLabelText } = render(<TelephonyConnectorForm lng="fr" />);

    expect(getByText('settings.connectors.telephony.activated')).toBeTruthy();
    expect(queryByLabelText('settings.connectors.telephony.step_key')).toBeNull();
  });
});
