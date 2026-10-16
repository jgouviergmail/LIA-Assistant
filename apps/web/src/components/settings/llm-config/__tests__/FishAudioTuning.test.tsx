/**
 * Fish Audio tuning (ADR-345): every option the form offers is one the client
 * accepts, and a public voice is pinned only once it was read AND the
 * administrator attested holding the right to use it. The pins are ONE list
 * for every voice slot (amendment 2026-10-14): each act goes to the server at
 * once, and the page says why when it refused one.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { FishAudioTuning, FishPinnedVoices } from '../FishAudioTuning';
import type { VoiceOption } from '@/types/llm-config';
import type { PinnedVoices } from '@/types/voice-library';

const lookups = vi.hoisted(() => ({
  current: {} as Record<string, { data?: unknown; loading?: boolean; error?: Error | null }>,
  asked: [] as string[],
}));

vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (url: string, options: { enabled?: boolean }) => {
    if (options.enabled) lookups.asked.push(url);
    return options.enabled
      ? { data: undefined, loading: false, error: null, ...lookups.current[url] }
      : { data: undefined, loading: false, error: null };
  },
}));

const shared = vi.hoisted(() => ({
  state: {
    pins: undefined as PinnedVoices | undefined,
    loading: false,
    error: null as Error | null,
  },
  pin: vi.fn(),
  unpin: vi.fn(),
}));

vi.mock('@/hooks/useFishPins', () => ({
  useFishPins: () => ({ ...shared.state, pin: shared.pin, unpin: shared.unpin }),
}));

const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key} ${JSON.stringify(options)}` : key;

const PINNED = 'b'.repeat(32);
const FOUND: VoiceOption = {
  voice_id: PINNED,
  label: 'Narrator',
  gender: 'male',
  language: 'en',
  source: 'pinned',
};

function refusal(detail: Record<string, unknown>): Error {
  return Object.assign(new Error('refused'), { status: 409, data: { detail } });
}

function renderPins({ voices = [] as VoiceOption[] } = {}) {
  const onPinsChanged = vi.fn();
  render(<FishPinnedVoices lng="en" voices={voices} onPinsChanged={onPinsChanged} t={t} />);
  return onPinsChanged;
}

function findVoice(voiceId: string = PINNED) {
  lookups.current[`/admin/voice/fishaudio/voices/${voiceId}`] = {
    data: { ...FOUND, voice_id: voiceId },
  };
  fireEvent.change(screen.getByLabelText('settings.admin.llmConfig.voiceTts.pinnedVoiceId'), {
    target: { value: ` ${voiceId.toUpperCase()} ` },
  });
  fireEvent.click(screen.getByRole('button', { name: /pinnedLookup/ }));
}

beforeEach(() => {
  lookups.current = {};
  lookups.asked = [];
  shared.state = { pins: { voice_ids: [], max_pins: 20 }, loading: false, error: null };
  shared.pin.mockReset().mockResolvedValue(undefined);
  shared.unpin.mockReset().mockResolvedValue(undefined);
});

describe('FishAudioTuning', () => {
  it('names every control by its visible label and bounds the rate to the vendor range', () => {
    const setKey = vi.fn();
    render(<FishAudioTuning providerConfig={{ speed: 1.25 }} setKey={setKey} t={t} />);
    const rate = screen.getByRole('slider', { name: 'settings.admin.llmConfig.voiceTts.speed' });
    expect(rate).toHaveAttribute('min', '0.5');
    expect(rate).toHaveAttribute('max', '2');
    expect(screen.getByText('1.25x')).toBeInTheDocument();
    fireEvent.change(rate, { target: { value: '0.75' } });
    expect(setKey).toHaveBeenCalledWith('speed', 0.75);
    expect(
      screen.getByRole('combobox', { name: 'settings.admin.llmConfig.voiceTts.outputFormat' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('combobox', { name: 'settings.admin.llmConfig.voiceTts.latency' })
    ).toBeInTheDocument();
  });

  it('travels over HTTP unless the slot asks for the socket, and says what the socket measured', () => {
    const { rerender } = render(<FishAudioTuning providerConfig={{}} setKey={vi.fn()} t={t} />);
    const transport = screen.getByRole('combobox', {
      name: 'settings.admin.llmConfig.voiceTts.transport',
    });
    expect(transport).toHaveAccessibleDescription(
      'settings.admin.llmConfig.voiceTts.transportHint'
    );
    expect(transport).toHaveTextContent('settings.admin.llmConfig.voiceTts.transportOptions.http');

    rerender(
      <FishAudioTuning providerConfig={{ transport: 'websocket' }} setKey={vi.fn()} t={t} />
    );
    expect(transport).toHaveTextContent(
      'settings.admin.llmConfig.voiceTts.transportOptions.websocket'
    );
  });
});

describe('FishPinnedVoices', () => {
  it('pins a voice at once, only after it was read and the right to it attested', async () => {
    const onPinsChanged = renderPins();
    findVoice();
    expect(lookups.asked).toContain(`/admin/voice/fishaudio/voices/${PINNED}`);
    expect(screen.getByText(/pinnedFound/)).toHaveTextContent('Narrator · en');

    const pin = screen.getByRole('button', { name: /pinnedAdd/ });
    expect(pin).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(pin); // refused by the guard: nothing attested yet
    expect(shared.pin).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText('settings.admin.llmConfig.voiceTts.pinnedAttestation'));
    fireEvent.click(screen.getByRole('button', { name: /pinnedAdd/ }));

    expect(shared.pin).toHaveBeenCalledWith(PINNED, true);
    // Pinned: the catalogue is read again and the lookup starts over.
    await waitFor(() => expect(onPinsChanged).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/pinnedFound/)).not.toBeInTheDocument();
  });

  it('says why the server refused a pin, and keeps the voice to pin', async () => {
    shared.pin.mockRejectedValue(refusal({ code: 'fishaudio_pins_full', max_pins: 20 }));
    const onPinsChanged = renderPins();
    findVoice();
    fireEvent.click(screen.getByLabelText('settings.admin.llmConfig.voiceTts.pinnedAttestation'));
    fireEvent.click(screen.getByRole('button', { name: /pinnedAdd/ }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('settings.admin.voiceLibrary.errors.fishaudio_pins_full');
    expect(alert).toHaveTextContent('"max":20');
    expect(onPinsChanged).not.toHaveBeenCalled();
    expect(screen.getByText(/pinnedFound/)).toBeInTheDocument();
  });

  it('offers no pin past the ceiling the server published, and says so', () => {
    shared.state.pins = { voice_ids: ['c'.repeat(32)], max_pins: 1 };
    renderPins();
    findVoice();
    fireEvent.click(screen.getByLabelText('settings.admin.llmConfig.voiceTts.pinnedAttestation'));

    const pin = screen.getByRole('button', { name: /pinnedAdd/ });
    expect(pin).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(pin);
    expect(shared.pin).not.toHaveBeenCalled();
    expect(screen.getByText(/pinnedFull/)).toHaveTextContent('"max":1');
  });

  it('never asks the vendor for a malformed id, and says why', () => {
    renderPins();
    fireEvent.change(screen.getByLabelText('settings.admin.llmConfig.voiceTts.pinnedVoiceId'), {
      target: { value: 'not-a-voice' },
    });
    expect(
      screen.getByText('settings.admin.llmConfig.voiceTts.pinnedMalformed')
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /pinnedLookup/ }));
    expect(lookups.asked).toEqual([]);
  });

  it('says a voice the vendor does not serve is unavailable', () => {
    const refused = Object.assign(new Error('refused'), {
      data: { detail: { type: 'fishaudio_voice_unavailable' } },
    });
    lookups.current[`/admin/voice/fishaudio/voices/${PINNED}`] = { error: refused };
    renderPins();
    fireEvent.change(screen.getByLabelText('settings.admin.llmConfig.voiceTts.pinnedVoiceId'), {
      target: { value: PINNED },
    });
    fireEvent.click(screen.getByRole('button', { name: /pinnedLookup/ }));
    expect(screen.getByRole('alert')).toHaveTextContent(
      'settings.admin.llmConfig.voiceTts.pinnedUnavailable'
    );
    expect(screen.queryByRole('button', { name: /pinnedAdd/ })).not.toBeInTheDocument();
  });

  it('lists the shared pins with the label the catalogue serves, and unpins one at once', async () => {
    const missing = 'c'.repeat(32);
    shared.state.pins = { voice_ids: [PINNED, missing], max_pins: 20 };
    const onPinsChanged = renderPins({ voices: [FOUND] });
    expect(screen.getByText('Narrator · en')).toBeInTheDocument();
    // A pin the catalogue no longer serves stays visible, named by its id.
    expect(screen.getByText(missing)).toBeInTheDocument();
    expect(
      screen.getByText('settings.admin.llmConfig.voiceTts.pinnedNotOffered')
    ).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: /pinnedRemove .*Narrator · en/ })[0]);

    expect(shared.unpin).toHaveBeenCalledWith(PINNED);
    await waitFor(() => expect(onPinsChanged).toHaveBeenCalledTimes(1));
  });

  it('says why an unpin was refused — a slot still speaks with the voice', async () => {
    shared.state.pins = { voice_ids: [PINNED], max_pins: 20 };
    shared.unpin.mockRejectedValue(
      refusal({ code: 'fishaudio_voice_in_use', slots: ['radio_voice'] })
    );
    renderPins({ voices: [FOUND] });

    fireEvent.click(screen.getAllByRole('button', { name: /pinnedRemove/ })[0]);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('settings.admin.voiceLibrary.errors.fishaudio_voice_in_use');
    expect(alert).toHaveTextContent('settings.admin.voiceLibrary.slots.radio_voice');
  });

  it('says the list is being read, and why it could not be', () => {
    shared.state = { pins: undefined, loading: true, error: null };
    const { unmount } = render(
      <FishPinnedVoices lng="en" voices={[]} onPinsChanged={vi.fn()} t={t} />
    );
    expect(screen.getByText('common.loading')).toBeInTheDocument();
    unmount();

    shared.state = { pins: undefined, loading: false, error: new Error('down') };
    renderPins();
    expect(screen.getByRole('alert')).toHaveTextContent(
      'settings.admin.voiceLibrary.errors.generic'
    );
  });
});
