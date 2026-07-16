/**
 * HueBridgePairingForm — the multi-step pairing wizard driven by the hook's
 * `step`: mode selection (local discovery vs remote OAuth), bridge selection,
 * the press-link pairing action, the success screen, error display, and the
 * cancel/back affordance.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { useHueConnect as useHueConnectFn } from '../hooks/useHueConnect';

const { useHueConnect } = vi.hoisted(() => ({ useHueConnect: vi.fn() }));
vi.mock('../hooks/useHueConnect', () => ({ useHueConnect }));

import { HueBridgePairingForm } from '../HueBridgePairingForm';

type HueHook = ReturnType<typeof useHueConnectFn>;
type Bridge = HueHook['bridges'][number];

function bridge(over: Partial<Bridge> = {}): Bridge {
  return { id: 'bridge-1', internalipaddress: '192.168.1.2', ...over };
}

function hook(over: Partial<HueHook> = {}) {
  return {
    step: 'mode' as HueHook['step'],
    bridges: [] as Bridge[],
    selectedBridge: null as string | null,
    isLoading: false,
    isPairing: false,
    countdown: 30,
    error: null as string | null,
    setSelectedBridge: vi.fn(),
    discoverBridges: vi.fn(),
    startPairing: vi.fn(),
    pairBridge: vi.fn(),
    connectRemote: vi.fn(),
    reset: vi.fn(),
    ...over,
  };
}

beforeEach(() => vi.clearAllMocks());

describe('HueBridgePairingForm — mode step', () => {
  it('discovers local bridges or starts the remote flow', async () => {
    const discoverBridges = vi.fn();
    const connectRemote = vi.fn();
    useHueConnect.mockReturnValue(hook({ step: 'mode', discoverBridges, connectRemote }));
    const { user } = renderWithProviders(<HueBridgePairingForm lng="en" />);
    await user.click(screen.getByRole('button', { name: /mode_local/ }));
    expect(discoverBridges).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: /mode_remote/ }));
    expect(connectRemote).toHaveBeenCalledTimes(1);
  });

  it('cancels from the mode step', async () => {
    const onCancel = vi.fn();
    useHueConnect.mockReturnValue(hook({ step: 'mode' }));
    const { user } = renderWithProviders(<HueBridgePairingForm lng="en" onCancel={onCancel} />);
    await user.click(screen.getByRole('button', { name: 'common.cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

describe('HueBridgePairingForm — discover step', () => {
  it('selects a discovered bridge', async () => {
    const setSelectedBridge = vi.fn();
    useHueConnect.mockReturnValue(
      hook({ step: 'discover', bridges: [bridge()], setSelectedBridge })
    );
    const { user } = renderWithProviders(<HueBridgePairingForm lng="en" />);
    await user.click(screen.getByRole('button', { name: /192\.168\.1\.2/ }));
    expect(setSelectedBridge).toHaveBeenCalledWith('192.168.1.2');
  });

  it('starts pairing once a bridge is selected', async () => {
    const startPairing = vi.fn();
    useHueConnect.mockReturnValue(
      hook({ step: 'discover', bridges: [bridge()], selectedBridge: '192.168.1.2', startPairing })
    );
    const { user } = renderWithProviders(<HueBridgePairingForm lng="en" />);
    await user.click(screen.getByRole('button', { name: /press_button/ }));
    expect(startPairing).toHaveBeenCalledTimes(1);
  });
});

describe('HueBridgePairingForm — pair, success & errors', () => {
  it('pairs with the selected bridge', async () => {
    const pairBridge = vi.fn();
    useHueConnect.mockReturnValue(
      hook({ step: 'pair', selectedBridge: '192.168.1.2', countdown: 20, pairBridge })
    );
    const { user } = renderWithProviders(<HueBridgePairingForm lng="en" />);
    await user.click(screen.getByRole('button', { name: /pair_button/ }));
    expect(pairBridge).toHaveBeenCalledWith('192.168.1.2');
  });

  it('shows the success screen', () => {
    useHueConnect.mockReturnValue(hook({ step: 'success' }));
    renderWithProviders(<HueBridgePairingForm lng="en" />);
    expect(screen.getByText('settings.connectors.hue.pairing_success')).toBeInTheDocument();
  });

  it('surfaces a hook error', () => {
    useHueConnect.mockReturnValue(hook({ step: 'mode', error: 'Bridge unreachable' }));
    renderWithProviders(<HueBridgePairingForm lng="en" />);
    expect(screen.getByText('Bridge unreachable')).toBeInTheDocument();
  });
});
