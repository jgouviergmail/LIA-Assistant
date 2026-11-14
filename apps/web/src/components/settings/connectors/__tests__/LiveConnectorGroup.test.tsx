/**
 * LiveConnectorGroup — the « Live » group of the connectors section (ADR-299;
 * wave 2 A10, the category is additive): absent without the instance
 * capability; the connected cards with their disconnect; an available card
 * per provider NOT yet set up, each unfolding into its own form, folding back
 * on cancel, and re-reading the list once an activation succeeded.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { act, renderWithProviders, screen } from '@/__tests__/test-utils';
import { Accordion } from '@/components/ui/accordion';

const h = vi.hoisted(() => ({
  liveEnabled: true,
  form: null as null | { onSuccess?: () => void },
}));
/** What the operator switched off: absent, the deployment flag alone decides. */
const operator = vi.hoisted(() => ({
  capabilities: undefined as Record<string, { enabled: boolean; family: string }> | undefined,
}));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({
    config: { features: { live_enabled: h.liveEnabled }, capabilities: operator.capabilities },
  }),
}));
vi.mock('../LiveConnectorForm', () => ({
  LiveConnectorForm: (props: {
    provider: string;
    onSuccess?: () => void;
    onCancel?: () => void;
  }) => {
    h.form = props;
    return (
      <div data-testid="live-form" data-provider={props.provider}>
        <button type="button" onClick={props.onCancel}>
          cancel
        </button>
      </div>
    );
  },
}));

import { LiveConnectorGroup } from '../LiveConnectorGroup';

const t = (key: string) => key;

function render(connectors: Array<{ id: string; connector_type: string; status: string }>) {
  const refetch = vi.fn();
  const onDisconnect = vi.fn();
  const utils = renderWithProviders(
    <Accordion type="multiple" defaultValue={['connected-live', 'available-live']}>
      <LiveConnectorGroup
        connectors={connectors.map(c => ({ ...c, created_at: '2026-09-18T00:00:00Z' }))}
        lng="fr"
        t={t}
        refetch={refetch}
        onDisconnect={onDisconnect}
      />
    </Accordion>
  );
  return { ...utils, refetch, onDisconnect };
}

describe('LiveConnectorGroup', () => {
  beforeEach(() => {
    h.liveEnabled = true;
    h.form = null;
  });

  it('renders nothing when the instance does not publish the capability', () => {
    h.liveEnabled = false;
    const { container } = render([{ id: 'c1', connector_type: 'gemini_live', status: 'active' }]);
    expect(container.querySelector('[data-state]')).toBeNull();
    expect(screen.queryByText('settings.connectors.connected_live')).not.toBeInTheDocument();
  });

  it('shows the connected group with a disconnect, and the OTHER providers stay available', async () => {
    const { user, onDisconnect } = render([
      { id: 'c1', connector_type: 'gemini_live', status: 'active' },
      { id: 'c2', connector_type: 'google_gmail', status: 'active' },
    ]);
    expect(screen.getByText('settings.connectors.connected_live')).toBeInTheDocument();
    // The category is additive: the providers not yet set up are offered beside the connected one.
    expect(screen.getByText('settings.connectors.available_live')).toBeInTheDocument();
    expect(screen.getAllByTitle('settings.connectors.live.connect')).toHaveLength(2);
    await user.click(screen.getAllByTitle('settings.connectors.live.connect')[0]);
    expect(screen.getByTestId('live-form')).toHaveAttribute('data-provider', 'openai');
    await user.click(screen.getByTitle('settings.connectors.google.disconnect'));
    expect(onDisconnect).toHaveBeenCalledWith('c1');
  });

  it('offers nothing more once every provider is set up', () => {
    render([
      { id: 'c1', connector_type: 'gemini_live', status: 'active' },
      { id: 'c3', connector_type: 'gpt_live', status: 'active' },
      { id: 'c4', connector_type: 'elevenlabs_live', status: 'active' },
    ]);
    expect(screen.getByText('settings.connectors.connected_live')).toBeInTheDocument();
    expect(screen.queryByText('settings.connectors.available_live')).not.toBeInTheDocument();
  });

  it('offers the available card, unfolds the form, folds it on cancel and re-reads on success', async () => {
    const { user, refetch } = render([
      { id: 'c3', connector_type: 'gemini_live', status: 'error' },
    ]);
    expect(screen.getByText('settings.connectors.available_live')).toBeInTheDocument();
    expect(screen.queryByTestId('live-form')).not.toBeInTheDocument();
    // Every provider is offered (the broken gemini key is not an active one).
    expect(screen.getAllByTitle('settings.connectors.live.connect')).toHaveLength(3);
    await user.click(screen.getAllByTitle('settings.connectors.live.connect')[0]);
    // The form is told WHICH provider it sets up.
    expect(screen.getByTestId('live-form')).toHaveAttribute('data-provider', 'gemini');
    await user.click(screen.getByRole('button', { name: 'cancel' }));
    expect(screen.queryByTestId('live-form')).not.toBeInTheDocument();
    await user.click(screen.getAllByTitle('settings.connectors.live.connect')[0]);
    act(() => h.form?.onSuccess?.());
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('live-form')).not.toBeInTheDocument();
  });
});

describe('LiveConnectorGroup under the operator switch', () => {
  it('offers no connection: discovering models and activating a key are refused', () => {
    // Connecting is an ACT of the capability — its routes refuse under the
    // switch — where a stored key is a record (ADR-280).
    h.liveEnabled = true;
    operator.capabilities = { live: { enabled: false, family: 'media' } };
    render([{ id: 'c1', connector_type: 'gemini_live', status: 'active' }]);
    operator.capabilities = undefined;

    expect(screen.getByText('settings.connectors.connected_live')).toBeInTheDocument();
    expect(screen.queryByText('settings.connectors.available_live')).not.toBeInTheDocument();
    expect(screen.queryByTitle('settings.connectors.live.connect')).not.toBeInTheDocument();
  });

  it('renders nothing where no key is stored', () => {
    h.liveEnabled = true;
    operator.capabilities = { live: { enabled: false, family: 'media' } };
    const { container } = render([]);
    operator.capabilities = undefined;

    expect(container.querySelector('[data-state]')).toBeNull();
  });

  it('keeps a stored key removable: it is the person’s own record', async () => {
    h.liveEnabled = true;
    operator.capabilities = { live: { enabled: false, family: 'media' } };
    const { user, onDisconnect } = render([
      { id: 'c1', connector_type: 'gemini_live', status: 'active' },
    ]);
    operator.capabilities = undefined;

    expect(screen.getByText('settings.connectors.connected_live')).toBeInTheDocument();
    await user.click(screen.getByTitle('settings.connectors.google.disconnect'));
    expect(onDisconnect).toHaveBeenCalledWith('c1');
  });
});
