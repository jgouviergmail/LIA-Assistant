import { expect, it, vi } from 'vitest';
import { VoiceOutputCoordinator } from '../coordinator';
import type { AvatarPhrase } from '../../avatars/engine';

function phrase(overrides: Partial<AvatarPhrase> = {}): AvatarPhrase {
  return { feed: vi.fn(async () => {}), finish: vi.fn(async () => {}), ...overrides };
}
const clip = { sampleRate: 48000 } as AudioBuffer;

it('latches local audio for the whole utterance even when the avatar becomes ready', () => {
  const target = { ready: false, openPhrase: vi.fn(() => phrase()), interrupt: vi.fn() };
  const coordinator = new VoiceOutputCoordinator(target);
  const first = coordinator.begin({ source: 'comments', id: 'one' });
  target.ready = true;
  expect(coordinator.begin({ source: 'comments', id: 'one' })).toBe(first);
  expect(first.output).toBeNull();
  expect(coordinator.begin({ source: 'comments', id: 'two' }).route).toBe('avatar');
  expect(target.openPhrase).not.toHaveBeenCalled();
});
it('rejects stale phrases, selects only one audible output, and interrupts without closing the connection', async () => {
  const opened = phrase();
  const target = { ready: true, openPhrase: vi.fn(() => opened), interrupt: vi.fn() };
  const coordinator = new VoiceOutputCoordinator(target);
  const old = coordinator.begin({ source: 'comments', id: 'old' });
  const current = coordinator.begin({ source: 'live', id: 'current' });
  const signal = new AbortController().signal;
  await expect(old.output!.play(clip, signal, vi.fn())).rejects.toHaveProperty(
    'name',
    'AbortError'
  );
  await current.output!.play(clip, signal, vi.fn());
  expect(target.openPhrase).toHaveBeenCalledTimes(1);
  expect(opened.feed).toHaveBeenCalledTimes(1);
  expect(target.interrupt).toHaveBeenCalledTimes(1);
  expect(current.epoch).toBeGreaterThan(old.epoch);
});

it('feeds every clip of one utterance into ONE phrase and drains it once at the end', async () => {
  const opened = phrase();
  const target = { ready: true, openPhrase: vi.fn(() => opened), interrupt: vi.fn() };
  const coordinator = new VoiceOutputCoordinator(target);
  const selection = coordinator.begin({ source: 'comments', id: 'answer' });
  const signal = new AbortController().signal;
  await selection.output!.play(clip, signal, vi.fn());
  await selection.output!.play(clip, signal, vi.fn());
  expect(target.openPhrase).toHaveBeenCalledOnce();
  expect(opened.feed).toHaveBeenCalledTimes(2);
  expect(opened.finish).not.toHaveBeenCalled();
  await selection.output!.end();
  await selection.output!.end();
  expect(opened.finish).toHaveBeenCalledOnce();
  // A clip after the end (a late chunk) opens a phrase of its own.
  await selection.output!.play(clip, signal, vi.fn());
  expect(target.openPhrase).toHaveBeenCalledTimes(2);
  expect(target.interrupt).not.toHaveBeenCalled();
});

it('ignores late audible/drain callbacks after another source takes ownership', async () => {
  let notify!: () => void;
  let finish!: () => void;
  const target = {
    ready: true,
    interrupt: vi.fn(),
    openPhrase: vi.fn((_rate: number, audible: () => void) => {
      notify = audible;
      return phrase({
        feed: () =>
          new Promise<void>(resolve => {
            finish = resolve;
          }),
      });
    }),
  };
  const coordinator = new VoiceOutputCoordinator(target);
  const old = coordinator.begin({ source: 'comments', id: 'old' });
  const audible = vi.fn();
  const playing = old.output!.play(clip, new AbortController().signal, audible);
  const verdict = expect(playing).rejects.toHaveProperty('name', 'AbortError');
  coordinator.begin({ source: 'live', id: 'new' });
  notify();
  finish();
  await verdict;
  expect(audible).not.toHaveBeenCalled();
  // The superseded utterance drains nothing: its phrase was interrupted.
  await old.output!.end();
  expect(target.interrupt).toHaveBeenCalledOnce();
});

it('resolves a dynamic owner at a boundary and respects an already aborted signal', async () => {
  const target = {
    ready: true,
    interrupt: vi.fn(),
    openPhrase: vi.fn((_rate: number, audible: () => void) =>
      phrase({ feed: vi.fn(async () => audible()) })
    ),
  };
  let current: typeof target | null = null;
  const coordinator = new VoiceOutputCoordinator(() => current);
  expect(coordinator.begin({ source: 'comments', id: 'cold' }).route).toBe('local');
  current = target;
  const selection = coordinator.begin({ source: 'comments', id: 'warm' });
  const audible = vi.fn();
  await selection.output!.play(clip, new AbortController().signal, audible);
  expect(audible).toHaveBeenCalledOnce();
  const abort = new AbortController();
  abort.abort();
  await expect(selection.output!.play(clip, abort.signal, audible)).rejects.toHaveProperty(
    'name',
    'AbortError'
  );
  expect(target.openPhrase).toHaveBeenCalledOnce();
  current = null;
  coordinator.interrupt();
  expect(target.interrupt).toHaveBeenCalledOnce();
});
