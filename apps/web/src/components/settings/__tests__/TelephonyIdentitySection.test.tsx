/**
 * The person's own phone number, declared and verified (phone as a channel).
 *
 * The global i18n stub echoes keys, so every accessible name below IS the key.
 *
 * What the section must guarantee: it exists only when the feature does; the
 * number is shown whole and editable; a refusal is shown as the backend's own
 * sentence next to the field; verification is a two-step (a call, then a
 * code) whose second step appears only while a code is pending; the context
 * switch is a real switch with a translated accessible name.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, userEvent, waitFor } from '@/__tests__/test-utils';
import type { TelephonyIdentity } from '@/types/telephony';

const { useTelephonyIdentity } = vi.hoisted(() => ({ useTelephonyIdentity: vi.fn() }));

vi.mock('@/hooks/useTelephonyIdentity', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hooks/useTelephonyIdentity')>();
  return { ...actual, useTelephonyIdentity };
});

import TelephonyIdentitySection from '../TelephonyIdentitySection';

function identity(overrides: Partial<TelephonyIdentity> = {}): TelephonyIdentity {
  return {
    phone_number: '+33612345678',
    verified: false,
    verified_at: null,
    rich_context_enabled: true,
    disabled_domains: [],
    available_domains: ['email', 'event', 'context'],
    verification_pending: false,
    call_mode: 'delegated',
    call_mode_effective: 'delegated',
    live_available: true,
    live_unavailable_reason: null,
    ...overrides,
  };
}

/** A Live direct identity: the rich-context switch is drawn under it alone. */
function direct(overrides: Partial<TelephonyIdentity> = {}): TelephonyIdentity {
  return identity({ call_mode: 'direct', call_mode_effective: 'direct', ...overrides });
}

function mockHook(value: TelephonyIdentity | null, overrides: Record<string, unknown> = {}) {
  const actions = {
    setNumber: vi.fn().mockResolvedValue(null),
    clearNumber: vi.fn().mockResolvedValue(null),
    startVerification: vi.fn().mockResolvedValue(null),
    confirmCode: vi.fn().mockResolvedValue(null),
    setRichContext: vi.fn().mockResolvedValue(null),
    setDisabledDomains: vi.fn().mockResolvedValue(null),
    setCallMode: vi.fn().mockResolvedValue(null),
    refetch: vi.fn(),
  };
  useTelephonyIdentity.mockReturnValue({
    identity: value,
    isLoading: false,
    isUnavailable: false,
    isBusy: false,
    codeExpiresInSeconds: null,
    ...actions,
    ...overrides,
  });
  return actions;
}

describe('TelephonyIdentitySection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when the feature is off', () => {
    mockHook(null, { isUnavailable: true });
    const { container } = renderWithProviders(<TelephonyIdentitySection lng="fr" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the declared number whole, in a tel field', () => {
    mockHook(identity());
    renderWithProviders(<TelephonyIdentitySection lng="fr" />);
    const field = screen.getByRole('textbox', { name: 'settings.telephony.identity.number_label' });
    expect(field).toHaveValue('+33612345678');
    expect(field).toHaveAttribute('inputmode', 'tel');
    expect(field).toHaveAttribute('autocomplete', 'tel');
  });

  it('saves what was typed and shows the backend sentence when refused', async () => {
    const actions = mockHook(identity({ phone_number: null }));
    actions.setNumber.mockResolvedValueOnce('Ce numéro n’est pas un numéro de téléphone valide.');
    renderWithProviders(<TelephonyIdentitySection lng="fr" />);

    const field = screen.getByRole('textbox', { name: 'settings.telephony.identity.number_label' });
    await userEvent.type(field, 'Marie');
    await userEvent.click(screen.getByRole('button', { name: 'common.save' }));

    expect(actions.setNumber).toHaveBeenCalledWith('Marie');
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Ce numéro n’est pas un numéro de téléphone valide.'
    );
    expect(field).toHaveAttribute('aria-invalid', 'true');
  });

  it('offers the verification call while the number is unverified', async () => {
    const actions = mockHook(identity());
    renderWithProviders(<TelephonyIdentitySection lng="fr" />);

    expect(
      screen.queryByRole('textbox', { name: 'settings.telephony.identity.code_label' })
    ).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole('button', { name: 'settings.telephony.identity.verify_by_call' })
    );

    expect(actions.startVerification).toHaveBeenCalledTimes(1);
  });

  it('asks for the code only while a verification is pending, then confirms it', async () => {
    const actions = mockHook(identity({ verification_pending: true }), {
      codeExpiresInSeconds: 600,
    });
    renderWithProviders(<TelephonyIdentitySection lng="fr" />);

    const code = screen.getByRole('textbox', { name: 'settings.telephony.identity.code_label' });
    expect(code).toHaveAttribute('inputmode', 'numeric');
    expect(code).toHaveAttribute('autocomplete', 'one-time-code');
    await userEvent.type(code, '4719');
    await userEvent.click(
      screen.getByRole('button', { name: 'settings.telephony.identity.confirm_code' })
    );

    await waitFor(() => expect(actions.confirmCode).toHaveBeenCalledWith('4719'));
  });

  it('says the number is verified and keeps no verification button', () => {
    mockHook(identity({ verified: true, verified_at: '2026-09-16T10:00:00Z' }));
    renderWithProviders(<TelephonyIdentitySection lng="fr" />);

    expect(screen.getByText('settings.telephony.identity.verified')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'settings.telephony.identity.verify_by_call' })
    ).not.toBeInTheDocument();
  });

  it('the context switch is a switch with a translated name and persists', async () => {
    const actions = mockHook(direct({ verified: true }));
    renderWithProviders(<TelephonyIdentitySection lng="fr" />);

    const toggle = screen.getByRole('switch', {
      name: 'settings.telephony.identity.rich_context_label',
    });
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);

    expect(actions.setRichContext).toHaveBeenCalledWith(false);
  });

  it('offers one switch per domain the phone may read, on unless switched off', async () => {
    // Lot 8: the server publishes the domains it offers and the ones the
    // person switched off; the memories domain wears its own name.
    const actions = mockHook(direct({ disabled_domains: ['email'] }));
    renderWithProviders(<TelephonyIdentitySection lng="fr" />);

    const email = screen.getByRole('switch', { name: 'treatments.domains.email' });
    const event = screen.getByRole('switch', { name: 'treatments.domains.event' });
    const memory = screen.getByRole('switch', {
      name: 'settings.telephony.identity.domain_memory',
    });
    expect(email).not.toBeChecked();
    expect(event).toBeChecked();
    expect(memory).toBeChecked();

    await userEvent.click(event);
    expect(actions.setDisabledDomains).toHaveBeenLastCalledWith(['email', 'event']);
    await userEvent.click(email);
    expect(actions.setDisabledDomains).toHaveBeenLastCalledWith([]);
  });

  it('removing the number asks nothing else of the hook', async () => {
    const actions = mockHook(identity());
    renderWithProviders(<TelephonyIdentitySection lng="fr" />);

    await userEvent.click(
      screen.getByRole('button', { name: 'settings.telephony.identity.remove' })
    );

    expect(actions.clearNumber).toHaveBeenCalledTimes(1);
  });

  // --- the call mode (ADR-301) ----------------------------------------------

  it('offers Live and Live direct as one glyph list, Live by default, and persists the choice', async () => {
    const actions = mockHook(identity());
    renderWithProviders(<TelephonyIdentitySection lng="fr" />);

    const list = screen.getByRole('combobox', {
      name: 'settings.telephony.identity.call_mode.label',
    });
    expect(list).toHaveTextContent('settings.telephony.identity.call_mode.delegated');
    expect(list).not.toBeDisabled();
    expect(screen.getByText('settings.telephony.identity.call_mode.help_delegated')).toBeTruthy();

    await userEvent.click(list);
    await userEvent.click(
      await screen.findByRole('option', { name: 'settings.telephony.identity.call_mode.direct' })
    );
    expect(actions.setCallMode).toHaveBeenCalledWith('direct');
  });

  it('under Live, the phone context switch is gone but the domain switches stay', async () => {
    // A Live call reads nothing itself, so the phone's rich-context switch
    // has no object; the DOMAIN switches govern every direct voice surface —
    // the browser's direct session reads them too (ADR-300 wave 4) — and a
    // person on Live must still be able to tune them (ADR-301 review).
    const actions = mockHook(identity({ disabled_domains: ['event'] }));
    renderWithProviders(<TelephonyIdentitySection lng="fr" />);

    expect(
      screen.queryByRole('switch', { name: 'settings.telephony.identity.rich_context_label' })
    ).toBeNull();
    const email = screen.getByRole('switch', { name: 'treatments.domains.email' });
    expect(email).toBeChecked();
    expect(screen.getByRole('switch', { name: 'treatments.domains.event' })).not.toBeChecked();
    await userEvent.click(email);
    expect(actions.setDisabledDomains).toHaveBeenLastCalledWith(['email', 'event']);
  });

  it('when Live cannot run here, the list is disabled and says which mode a call will run', () => {
    mockHook(
      identity({
        call_mode: 'delegated',
        call_mode_effective: 'direct',
        live_available: false,
        live_unavailable_reason: 'callback_not_public',
      })
    );
    renderWithProviders(<TelephonyIdentitySection lng="fr" />);

    expect(
      screen.getByRole('combobox', { name: 'settings.telephony.identity.call_mode.label' })
    ).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent(
      'settings.telephony.identity.call_mode.unavailable'
    );
    // The call runs direct, so the direct panels are drawn.
    expect(
      screen.getByRole('switch', { name: 'settings.telephony.identity.rich_context_label' })
    ).toBeTruthy();
  });
});
