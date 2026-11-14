/**
 * TelephonyConnectorGroup — the telephony group of the connectors section.
 *
 * Two things live here, and the operator's switch treats them apart
 * (ADR-280). Connecting a key is an ACT of the capability — it creates an
 * agent at the vendor — and is offered only where telephony is. A stored key
 * is the person's RECORD: it stays shown and removable under the switch, as
 * long as the deployment mounts telephony at all.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { appConfigFixture } from '@/__tests__/fixtures/app-config';
import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { Accordion } from '@/components/ui/accordion';
import type { AppConfig } from '@/hooks/useAppConfig';

const h = vi.hoisted(() => ({
  config: null as AppConfig | null,
  del: vi.fn(),
  toastError: vi.fn(),
  form: null as null | { onSuccess?: () => void; onCancel?: () => void },
}));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig: () => ({ config: h.config }) }));
vi.mock('@/lib/api-client', () => ({ default: { delete: h.del } }));
vi.mock('sonner', () => ({ toast: { error: h.toastError } }));
vi.mock('../TelephonyConnectorForm', () => ({
  TelephonyConnectorForm: (props: { onSuccess?: () => void; onCancel?: () => void }) => {
    h.form = props;
    return (
      <div data-testid="telephony-form">
        <button type="button" onClick={props.onCancel}>
          cancel
        </button>
      </div>
    );
  },
}));

import { TelephonyConnectorGroup } from '../TelephonyConnectorGroup';

const t = (key: string) => key;

const CONNECTED = 'settings.connectors.connected_telephony';
const AVAILABLE = 'settings.connectors.available_telephony';
// The generic « Connect » and « Disconnect » of the connector cards live under `google`.
const CONNECT = 'settings.connectors.google.connect';
const DISCONNECT = 'settings.connectors.google.disconnect';

/**
 * A configuration that has answered: the operator's verdict on telephony, on a
 * deployment that mounts its routes — or not.
 */
const telephony = (enabled: boolean, mounted = true): AppConfig =>
  appConfigFixture({
    features: { telephony_enabled: mounted },
    capabilities: { telephony: { enabled: enabled && mounted, family: 'media' } },
  });

const connector = (connector_type: string, status = 'active') => ({
  id: `id-${connector_type}`,
  connector_type,
  status,
  created_at: '2026-11-12T00:00:00Z',
});

function render(connectors: ReturnType<typeof connector>[]) {
  const refetch = vi.fn();
  const utils = renderWithProviders(
    <Accordion type="multiple" defaultValue={['connected-telephony', 'available-telephony']}>
      <TelephonyConnectorGroup connectors={connectors} lng="fr" t={t} refetch={refetch} />
    </Accordion>
  );
  return { ...utils, refetch };
}

beforeEach(() => {
  vi.clearAllMocks();
  h.config = telephony(true);
  h.form = null;
  h.del.mockResolvedValue(undefined);
});

describe('TelephonyConnectorGroup', () => {
  it('offers to connect where telephony is offered and nothing is connected', async () => {
    const { user } = render([connector('google_gmail')]);

    expect(screen.getByText(AVAILABLE)).toBeInTheDocument();
    expect(screen.queryByText(CONNECTED)).not.toBeInTheDocument();
    await user.click(screen.getByTitle(CONNECT));

    expect(screen.getByTestId('telephony-form')).toBeInTheDocument();
  });

  it('folds the form back on cancel, and re-reads the list once the activation succeeded', async () => {
    const { user, refetch } = render([]);
    await user.click(screen.getByTitle(CONNECT));

    await user.click(screen.getByRole('button', { name: 'cancel' }));
    expect(screen.queryByTestId('telephony-form')).not.toBeInTheDocument();
    expect(refetch).not.toHaveBeenCalled();

    await user.click(screen.getByTitle(CONNECT));
    h.form?.onSuccess?.();

    await waitFor(() => expect(screen.queryByTestId('telephony-form')).not.toBeInTheDocument());
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('shows the connected connector, and its disconnect goes through the telephony route', async () => {
    // Telephony-specific: the route also deletes the agent LIA created at the vendor.
    const { user, refetch } = render([connector('elevenlabs_telephony')]);

    expect(screen.getByText(CONNECTED)).toBeInTheDocument();
    expect(screen.queryByText(AVAILABLE)).not.toBeInTheDocument();
    await user.click(screen.getByTitle(DISCONNECT));

    expect(h.del).toHaveBeenCalledWith('/telephony/connector');
    await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
  });

  it('offers a connector in error again: only an active one counts as connected', () => {
    render([connector('elevenlabs_telephony', 'error')]);

    expect(screen.getByText(AVAILABLE)).toBeInTheDocument();
    expect(screen.queryByText(CONNECTED)).not.toBeInTheDocument();
  });

  it('recognises the telephony connector whatever the case its type was stored in', () => {
    render([connector('ElevenLabs_Telephony')]);

    expect(screen.getByText(CONNECTED)).toBeInTheDocument();
    expect(screen.queryByText(AVAILABLE)).not.toBeInTheDocument();
  });
});

describe('TelephonyConnectorGroup — a disconnect that fails', () => {
  it('says so, and does not re-read a list that did not change', async () => {
    h.del.mockRejectedValue(new Error('refused'));
    const { user, refetch } = render([connector('elevenlabs_telephony')]);

    await user.click(screen.getByTitle(DISCONNECT));

    await waitFor(() =>
      expect(h.toastError).toHaveBeenCalledWith('settings.connectors.disconnect_error')
    );
    expect(refetch).not.toHaveBeenCalled();
  });
});

describe('TelephonyConnectorGroup — telephony the operator switched off', () => {
  it('keeps a stored key shown and removable: a switch never takes the record', async () => {
    h.config = telephony(false);
    const { user, refetch } = render([connector('elevenlabs_telephony')]);

    expect(screen.getByText(CONNECTED)).toBeInTheDocument();
    expect(screen.queryByText(AVAILABLE)).not.toBeInTheDocument();
    await user.click(screen.getByTitle(DISCONNECT));

    expect(h.del).toHaveBeenCalledWith('/telephony/connector');
    await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
    expect(h.toastError).not.toHaveBeenCalled();
  });

  it.each([
    ['nothing is connected', []],
    ['the stored connector is in error', [connector('elevenlabs_telephony', 'error')]],
  ])('offers no connection, when %s', (_case, connectors) => {
    // Connecting creates an agent at the vendor: an act the switch closed.
    h.config = telephony(false);

    const { container } = render(connectors);

    expect(container.querySelector('[data-state]')).toBeNull();
    expect(screen.queryByText(AVAILABLE)).not.toBeInTheDocument();
    expect(screen.queryByTitle(CONNECT)).not.toBeInTheDocument();
  });
});

describe('TelephonyConnectorGroup — a deployment that mounts no telephony', () => {
  it.each([
    ['nothing is connected', []],
    ['a connector is stored', [connector('elevenlabs_telephony')]],
  ])('renders nothing, when %s', (_case, connectors) => {
    // No route answers there, the removal included: a card would end on a 404.
    h.config = telephony(true, false);

    const { container } = render(connectors);

    expect(container.querySelector('[data-state]')).toBeNull();
    expect(screen.queryByText(AVAILABLE)).not.toBeInTheDocument();
    expect(screen.queryByText(CONNECTED)).not.toBeInTheDocument();
    expect(screen.queryByTitle(CONNECT)).not.toBeInTheDocument();
    expect(screen.queryByTitle(DISCONNECT)).not.toBeInTheDocument();
  });

  it.each([
    ['nothing is connected', []],
    ['a connector is stored', [connector('elevenlabs_telephony')]],
  ])('renders nothing before the configuration has answered, when %s', (_case, connectors) => {
    // Nobody knows yet whether the router is mounted: the door says no.
    h.config = null;

    const { container } = render(connectors);

    expect(container.querySelector('[data-state]')).toBeNull();
  });
});
