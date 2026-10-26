import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { useWorldSound } from '../useWorldSound';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import type { DecodedSound, SoundVoice } from '../audio/soundscape';
import type { SoundId } from '../audio/catalogue';
const events = vi.hoisted(() => ({
  loads: [] as SoundId[],
  voices: [] as { id: SoundId; stopped: boolean }[],
  destroyed: 0,
  levels: [] as number[],
  current: true,
  isCurrent: () => events.current,
}));
vi.mock('@/hooks/useApplicationAccountLifetime', () => ({
  useApplicationAccountLifetime: () => ({ isCurrent: events.isCurrent }),
}));
vi.mock('../audio/browser-audio', () => ({
  BrowserWorldAudio: class {
    activate = async () => true;
    setVolume(level: number) {
      events.levels.push(level);
    }
    load = async (id: SoundId, signal: AbortSignal): Promise<DecodedSound> => {
      events.loads.push(id);
      return {
        bytes: 1000,
        duration: 30,
        start: () => {
          if (signal.aborted) throw new Error('Cancelled');
          const state = { id, stopped: false };
          events.voices.push(state);
          const voice: SoundVoice = {
            fade: () => {},
            stop: () => {
              state.stopped = true;
            },
          };
          return voice;
        },
      };
    };
    suspend() {}
    destroy() {
      events.destroyed++;
    }
  },
}));
function Harness({
  active = true,
  zone = 'garden',
  owner = 'owner',
}: {
  active?: boolean;
  zone?: string;
  owner?: string;
}) {
  const sound = useWorldSound(owner, active, zone, { ...NEUTRAL_ATMOSPHERE, phase: 'noon' });
  return (
    <>
      <button onClick={sound.toggle}>{sound.enabled ? 'mute' : 'enable'}</button>
      <input
        type="range"
        aria-label="World volume"
        min="0"
        max="1"
        step=".01"
        value={sound.volume}
        onChange={event => sound.setVolume(Number(event.target.value))}
      />
    </>
  );
}
beforeEach(() => {
  localStorage.clear();
  events.loads = [];
  events.levels = [];
  events.voices = [];
  events.destroyed = 0;
  events.current = true;
  useEyesSignalsStore.getState().setAudioPlaying(false);
});
it('waits for a gesture, follows the room, and yields to native speech before resuming', async () => {
  const view = render(<Harness />);
  expect(events.loads).toEqual([]);
  fireEvent.click(screen.getByRole('button', { name: 'enable' }));
  await waitFor(() => expect(events.voices.at(-1)?.id).toBe('birds'));
  view.rerender(<Harness zone="gym" />);
  await waitFor(() => expect(events.voices.at(-1)?.id).toBe('gym'));
  act(() => useEyesSignalsStore.getState().setAudioPlaying(true));
  expect(events.voices.every(v => v.stopped)).toBe(true);
  act(() => useEyesSignalsStore.getState().setAudioPlaying(false));
  await waitFor(() => expect(events.voices.at(-1)?.stopped).toBe(false));
  view.rerender(<Harness zone="gym" active={false} />);
  expect(events.voices.every(v => v.stopped)).toBe(true);
  view.unmount();
  expect(events.destroyed).toBe(1);
});
it('survives StrictMode effect replay and releases the last owner sound on unmount', async () => {
  const view = render(
    <StrictMode>
      <Harness />
    </StrictMode>
  );
  fireEvent.click(screen.getByRole('button', { name: 'enable' }));
  await waitFor(() => expect(events.voices).toHaveLength(1));
  view.unmount();
  expect(events.voices.every(v => v.stopped)).toBe(true);
  expect(events.destroyed).toBe(2);
});
it('cannot start after the native account lifetime has expired', async () => {
  render(<Harness />);
  events.current = false;
  fireEvent.click(screen.getByRole('button', { name: 'enable' }));
  await act(async () => {
    await Promise.resolve();
  });
  expect(events.loads).toEqual([]);
});

it('restores and changes only the current owner volume without opting into audio', () => {
  localStorage.setItem('lia-world-sound-volume:owner', '.31');
  localStorage.setItem('lia-world-sound-volume:other', '.18');
  const view = render(<Harness />);
  expect(events.levels.at(-1)).toBe(0.31);
  fireEvent.change(screen.getByRole('slider', { name: 'World volume' }), {
    target: { value: '.62' },
  });
  expect(events.levels.at(-1)).toBe(0.62);
  expect(localStorage.getItem('lia-world-sound-volume:owner')).toBe('0.62');
  expect(events.loads).toEqual([]);
  view.rerender(<Harness owner="other" />);
  expect(events.levels.at(-1)).toBe(0.18);
  events.current = false;
  fireEvent.change(screen.getByRole('slider', { name: 'World volume' }), {
    target: { value: '.9' },
  });
  expect(localStorage.getItem('lia-world-sound-volume:other')).toBe('.18');
});
