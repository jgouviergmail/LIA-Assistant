/**
 * GeolocationPrompt — the visibility rules (only when a location phrase is
 * present, coordinates are missing and permission isn't denied), the enable
 * success/failure branches, the retry mode, and session dismissal.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { useGeolocation as useGeolocationFn } from '@/hooks/useGeolocation';

const { useGeolocation } = vi.hoisted(() => ({ useGeolocation: vi.fn() }));
vi.mock('@/hooks/useGeolocation', () => ({ useGeolocation }));
// Deterministic phrase detection: LOCPHRASE is a "current location" phrase,
// QUERYPHRASE a "where am I" one; nothing else matches. Keeps the test
// independent of the NLP rules.
vi.mock('@/lib/location-detection', () => ({
  containsCurrentLocationPhrase: (msg: string) => msg.includes('LOCPHRASE'),
  containsHomeLocationPhrase: () => false,
  containsLocationQueryPhrase: (msg: string) => msg.includes('QUERYPHRASE'),
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() },
}));

import { GeolocationPrompt } from '../GeolocationPrompt';

type Coords = { lat: number; lon: number; accuracy: number | null; timestamp: number };
type GeoHook = ReturnType<typeof useGeolocationFn>;

function geo(over: Partial<GeoHook> = {}) {
  return {
    isEnabled: false,
    permission: 'prompt' as const,
    enable: vi.fn().mockResolvedValue({ lat: 1, lon: 2, accuracy: 5, timestamp: 0 } as Coords),
    isLoading: false,
    coordinates: null as Coords | null,
    refresh: vi.fn().mockResolvedValue(undefined),
    disable: vi.fn(),
    error: null,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useGeolocation.mockReturnValue(geo());
});

describe('GeolocationPrompt — visibility', () => {
  it('renders nothing without a location phrase', () => {
    const { container } = renderWithProviders(<GeolocationPrompt currentMessage="just chatting" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when permission was denied even with a phrase', () => {
    useGeolocation.mockReturnValue(geo({ permission: 'denied' }));
    const { container } = renderWithProviders(
      <GeolocationPrompt currentMessage="what is near LOCPHRASE" />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when already enabled with coordinates', () => {
    useGeolocation.mockReturnValue(
      geo({ isEnabled: true, coordinates: { lat: 1, lon: 2, accuracy: 5, timestamp: 0 } })
    );
    const { container } = renderWithProviders(
      <GeolocationPrompt currentMessage="near LOCPHRASE" />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('prompts to enable when a phrase is present and coordinates are missing', async () => {
    renderWithProviders(<GeolocationPrompt currentMessage="near LOCPHRASE" />);
    expect(await screen.findByText('chat.geolocation.prompt_title')).toBeInTheDocument();
  });

  it('prompts on a "where am I" query phrase too (the category that was missing)', async () => {
    renderWithProviders(<GeolocationPrompt currentMessage="show me QUERYPHRASE" />);
    expect(await screen.findByText('chat.geolocation.prompt_title')).toBeInTheDocument();
  });
});

describe('GeolocationPrompt — actions', () => {
  it('enables geolocation and notifies on success', async () => {
    const onGeolocationEnabled = vi.fn();
    const { user } = renderWithProviders(
      <GeolocationPrompt
        currentMessage="near LOCPHRASE"
        onGeolocationEnabled={onGeolocationEnabled}
      />
    );
    await user.click(await screen.findByRole('button', { name: /enable_button/ }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
    expect(onGeolocationEnabled).toHaveBeenCalledTimes(1);
  });

  it('reports an error when enabling is refused', async () => {
    useGeolocation.mockReturnValue(geo({ enable: vi.fn().mockResolvedValue(null) }));
    const { user } = renderWithProviders(<GeolocationPrompt currentMessage="near LOCPHRASE" />);
    await user.click(await screen.findByRole('button', { name: /enable_button/ }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });

  it('uses refresh (not enable) in retry mode', async () => {
    const refresh = vi.fn().mockResolvedValue({ lat: 1, lon: 2, accuracy: 5, timestamp: 0 });
    useGeolocation.mockReturnValue(geo({ isEnabled: true, coordinates: null, refresh }));
    const { user } = renderWithProviders(<GeolocationPrompt currentMessage="near LOCPHRASE" />);
    await user.click(await screen.findByRole('button', { name: /retry_button/ }));
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('hides the prompt once dismissed', async () => {
    const { user } = renderWithProviders(<GeolocationPrompt currentMessage="near LOCPHRASE" />);
    await screen.findByText('chat.geolocation.prompt_title');
    await user.click(screen.getByRole('button', { name: 'chat.geolocation.dismiss_button' }));
    await waitFor(() =>
      expect(screen.queryByText('chat.geolocation.prompt_title')).not.toBeInTheDocument()
    );
  });
});
