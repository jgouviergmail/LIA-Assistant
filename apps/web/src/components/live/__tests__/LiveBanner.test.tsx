/**
 * LiveBanner — a status line above the thread (ADR-299, spec A11): a named
 * region, live captions, mute / stop / end reachable by
 * keyboard, nothing while idle, and an unexpected ending told once.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import userEvent from '@testing-library/user-event';

import { act, renderWithProviders, screen } from '@/__tests__/test-utils';
import { useLiveStore } from '@/stores/liveStore';

const toast = vi.hoisted(() => ({ error: vi.fn(), info: vi.fn(), success: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

import { LiveBanner } from '../LiveBanner';

const session = {
  start: vi.fn(async () => {}),
  end: vi.fn(async () => {}),
  toggleMute: vi.fn(),
  extend: vi.fn(async () => true),
  declineExtension: vi.fn(),
};

function live() {
  const store = useLiveStore.getState();
  store.begin('a'.repeat(32));
  store.apply('minted');
  store.apply('setup_complete');
}

describe('LiveBanner', () => {
  beforeEach(() => {
    useLiveStore.getState().reset();
    vi.clearAllMocks();
  });

  it('renders nothing while idle', () => {
    const { container } = renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the state, the last caption, and reachable controls while live', async () => {
    live();
    useLiveStore.getState().pushCaption('user', 'hello', true);
    useLiveStore.getState().pushCaption('assistant', 'hi', true);
    renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(screen.getByRole('region', { name: 'live.captions.title' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('live.status.live');
    // Folded: only the last line.
    expect(screen.getByText('hi')).toBeInTheDocument();
    expect(screen.queryByText('hello')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'live.captions.show' }));
    expect(screen.getByText('hello')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'live.mic.mute' }));
    expect(session.toggleMute).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button', { name: 'live.button.end' }));
    expect(session.end).toHaveBeenCalledWith('ended');
  });

  it('folds the captions behind a named icon button, the meter under the last caption', () => {
    live();
    const store = useLiveStore.getState();
    store.pushCaption('assistant', 'hi', true);
    store.setRates(
      {
        pricing_unit: 'per_1m_tokens',
        input_unit_price: 0.75,
        output_unit_price: 4.5,
        audio_input_unit_price: 3,
        audio_output_unit_price: 12,
        usd_eur_rate: 0.9,
      },
      null
    );
    renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    const fold = screen.getByRole('button', { name: 'live.captions.show' });
    // An icon, like its neighbours: the name is the accessible one, not visible text.
    expect(fold).toHaveTextContent('');
    expect(fold).toHaveAttribute('aria-expanded', 'false');
    expect(fold.querySelector('svg')).not.toBeNull();
    // The meter follows the captions in the band, set off by its bar.
    const banner = screen.getByTestId('live-banner');
    const captions = banner.querySelector('ol');
    const meter = screen.getByTestId('live-meter');
    expect(captions).not.toBeNull();
    expect(
      captions!.compareDocumentPosition(meter) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(meter.className).toContain('border-l-2');
    // A clear gap above, so the figures do not read as part of the exchange.
    expect(meter.className).toContain('mt-2');
  });

  it('marks the muted state with aria-pressed and names the unmute action', () => {
    live();
    useLiveStore.getState().setMuted(true);
    renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'live.mic.unmute' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
  });

  it('offers Stop only while a delegation runs, and it goes through onStopAll', async () => {
    live();
    const onStopAll = vi.fn();
    renderWithProviders(<LiveBanner session={session} onStopAll={onStopAll} />);
    expect(screen.queryByRole('button', { name: 'live.button.stop_all' })).not.toBeInTheDocument();
    act(() => useLiveStore.getState().setDelegating(true));
    expect(screen.getByRole('status')).toHaveTextContent('live.status.delegating');
    await userEvent.click(screen.getByRole('button', { name: 'live.button.stop_all' }));
    expect(onStopAll).toHaveBeenCalledTimes(1);
  });

  it('names a DIRECT session, says LIA is looking up during a lookup, and offers no Stop (ADR-300 wave 4)', () => {
    // A direct session runs no chat turn: nothing to stop, and the wait is a lookup.
    const store = useLiveStore.getState();
    store.begin('a'.repeat(32), 'direct');
    store.apply('minted');
    store.apply('setup_complete');
    renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent('live.status.direct');
    expect(screen.getByRole('status')).toHaveTextContent('live.status.live');
    act(() => useLiveStore.getState().setDelegating(true));
    expect(screen.getByRole('status')).toHaveTextContent('live.status.looking_up');
    expect(screen.getByRole('status')).not.toHaveTextContent('live.status.delegating');
    expect(screen.queryByRole('button', { name: 'live.button.stop_all' })).not.toBeInTheDocument();
    // The notice: LIA keeps nothing of a direct exchange (owner request 2026-09-19).
    expect(screen.getByRole('note')).toHaveTextContent('live.direct_notice');
  });

  it('carries no recording notice on a delegated session, whose exchanges ARE kept', () => {
    live();
    renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });

  it('offers no held-to-talk button: a live session is always automatic', () => {
    live();
    renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(screen.queryByRole('button', { pressed: true })).toBeNull();
    expect(screen.getByRole('button', { name: 'live.mic.mute' })).toBeVisible();
  });

  it('announces the last seconds of a silence in the status line', () => {
    live();
    renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    act(() => useLiveStore.getState().setIdleCountdown(3));
    expect(screen.getByRole('status')).toHaveTextContent('live.status.idle_countdown');
    act(() => useLiveStore.getState().setIdleCountdown(null));
    expect(screen.getByRole('status')).not.toHaveTextContent('live.status.idle_countdown');
  });

  it('offers the extension in a dialog: Extend asks the session, Let it end declines', async () => {
    live();
    useLiveStore.getState().setExtensionMinutes(10);
    useLiveStore.getState().setExpiry(Date.now() + 45_000, 0);
    renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    act(() => useLiveStore.getState().offerExtension(true));
    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent('live.extend.title');
    await userEvent.click(screen.getByRole('button', { name: 'live.extend.confirm' }));
    expect(session.extend).toHaveBeenCalledTimes(1);
    act(() => useLiveStore.getState().offerExtension(true));
    await userEvent.click(screen.getByRole('button', { name: 'live.extend.decline' }));
    expect(session.declineExtension).toHaveBeenCalled();
  });

  it('tells when an extension was refused', async () => {
    live();
    session.extend.mockResolvedValueOnce(false);
    useLiveStore.getState().setExpiry(Date.now() + 45_000, 0);
    renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    act(() => useLiveStore.getState().offerExtension(true));
    await userEvent.click(screen.getByRole('button', { name: 'live.extend.confirm' }));
    expect(toast.error).toHaveBeenCalledWith('live.extend.failed');
  });

  it('tells a failed start once, by its code, and then stays quiet', () => {
    useLiveStore.getState().finish('error', 'connector_missing');
    const { rerender } = renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(toast.error).toHaveBeenCalledWith('live.error.connector_missing');
    expect(useLiveStore.getState().outcome).toBeNull();
    rerender(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(toast.error).toHaveBeenCalledTimes(1);
  });

  it('greets the session once it is live, once per session, like the spoken replies do', () => {
    // Owner decision 2026-09-19: the live entry answers like « Spoken replies »
    // — with a toast — on the session's OWN opening, never on the click.
    const store = useLiveStore.getState();
    store.begin('a'.repeat(32));
    store.apply('minted');
    const { rerender } = renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(toast.success).not.toHaveBeenCalled();
    act(() => store.apply('setup_complete'));
    expect(toast.success).toHaveBeenCalledWith('live.toast.started');
    // A reconnection is the same session: no second greeting.
    act(() => {
      store.apply('socket_closed');
      store.apply('setup_complete');
    });
    rerender(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(toast.success).toHaveBeenCalledTimes(1);
    // A new session greets again.
    act(() => {
      store.finish('ended');
      store.acknowledge();
      store.begin('b'.repeat(32));
      store.apply('minted');
      store.apply('setup_complete');
    });
    expect(toast.success).toHaveBeenCalledTimes(2);
  });

  it('draws the meter in the chat vocabulary: tokens in and out, the cost, the context (ADR-300 wave 3)', () => {
    live();
    const store = useLiveStore.getState();
    store.setRates(
      {
        pricing_unit: 'per_1m_tokens',
        input_unit_price: 0.75,
        output_unit_price: 4.5,
        audio_input_unit_price: 3,
        audio_output_unit_price: 12,
        usd_eur_rate: 0.9,
      },
      null
    );
    store.reportUsage({
      tokens: {
        textIn: 1029,
        audioIn: 198,
        textOut: 20,
        audioOut: 48,
        thoughts: 115,
        context: 1295,
      },
    });
    renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    const meter = screen.getByTestId('live-meter');
    expect(meter).toHaveTextContent('1 227 IN');
    expect(meter).toHaveTextContent('183 OUT');
    expect(meter).toHaveTextContent('live.meter.context');
    // (1029×0.75 + 198×3 + 135×4.5 + 48×12) / 1e6 × 0.9 ≈ 0,0023 €
    expect(meter).toHaveTextContent('0,0023');
    expect(meter).toHaveAttribute('title', 'live.meter.hint');
  });

  it('says the cost is unavailable, never a partial figure, when the audio rate is not declared', () => {
    live();
    const store = useLiveStore.getState();
    store.setRates(
      {
        pricing_unit: 'per_1m_tokens',
        input_unit_price: 0.75,
        output_unit_price: 4.5,
        audio_input_unit_price: null,
        audio_output_unit_price: null,
        usd_eur_rate: 0.9,
      },
      null
    );
    store.reportUsage({
      tokens: { textIn: 100, audioIn: 50, textOut: 10, audioOut: 20, thoughts: 0, context: 180 },
    });
    renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(screen.getByTestId('live-meter')).toHaveTextContent('live.meter.cost_unavailable');
    expect(screen.getByTestId('live-meter')).not.toHaveTextContent('€');
  });

  it('meters a minute-billed session by its clock, corrected upward by the provider', () => {
    vi.useFakeTimers();
    try {
      live();
      const store = useLiveStore.getState();
      store.setRates(
        {
          pricing_unit: 'per_audio_minute',
          input_unit_price: 0.05,
          output_unit_price: 0,
          audio_input_unit_price: null,
          audio_output_unit_price: null,
          usd_eur_rate: 0.9,
        },
        null
      );
      store.markLive(Date.now());
      renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
      act(() => {
        vi.advanceTimersByTime(60_000);
      });
      const meter = screen.getByTestId('live-meter');
      expect(meter).toHaveTextContent('⏱ 1:00');
      expect(meter).toHaveTextContent('0,0450');
      act(() => {
        store.reportUsage({ duration: { seconds: 90, contextRatio: 0.12 } });
      });
      expect(meter).toHaveTextContent('⏱ 1:30');
      expect(meter).toHaveTextContent('live.meter.context');
      expect(meter).not.toHaveTextContent('IN');
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows no meter before the start published the rates', () => {
    live();
    renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(screen.queryByTestId('live-meter')).toBeNull();
  });

  it("tells a provider close as information, with the provider's own word, and says nothing of an ending the person chose", () => {
    useLiveStore.getState().finish('provider_closed', null, 'close 1007: Unsupported voice');
    renderWithProviders(<LiveBanner session={session} onStopAll={vi.fn()} />);
    expect(toast.info).toHaveBeenCalledTimes(1);
    expect(toast.info).toHaveBeenCalledWith(
      'live.captions.title · live.outcome.provider_closed — close 1007: Unsupported voice'
    );
    useLiveStore.getState().finish('ended');
    expect(toast.info).toHaveBeenCalledTimes(1);
    expect(toast.error).not.toHaveBeenCalled();
  });
});
