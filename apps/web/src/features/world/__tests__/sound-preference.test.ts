import { expect, it, vi } from 'vitest';
import { soundPreference, volumePreference } from '../audio/sound-preference';
it('isolates accounts and keeps mute working when storage is unavailable', () => {
  localStorage.clear();
  const a = soundPreference('a'),
    b = soundPreference('b');
  const changed = vi.fn(),
    unsubscribe = a.subscribe(changed);
  expect(a.snapshot()).toBe(false);
  a.update(true);
  expect(a.snapshot()).toBe(true);
  expect(b.snapshot()).toBe(false);
  const fail = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('quota');
  });
  a.update(false);
  expect(a.snapshot()).toBe(false);
  a.update(true);
  expect(a.snapshot()).toBe(true);
  expect(changed).toHaveBeenCalledTimes(3);
  fail.mockRestore();
  unsubscribe();
});
it('applies a same-account tab change without accepting another account storage event', () => {
  localStorage.clear();
  const a = soundPreference('a');
  const unsubscribe = a.subscribe(() => {});
  localStorage.setItem('lia-world-sound:a', 'on');
  window.dispatchEvent(new StorageEvent('storage', { key: 'lia-world-sound:b' }));
  expect(a.snapshot()).toBe(false);
  window.dispatchEvent(new StorageEvent('storage', { key: 'lia-world-sound:a' }));
  expect(a.snapshot()).toBe(true);
  unsubscribe();
});

it('has a silent server snapshot, tolerates failed reads and keeps the remaining subscriber active', () => {
  localStorage.clear();
  const fail = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('storage blocked');
  });
  const blocked = soundPreference('blocked');
  expect(blocked.snapshot()).toBe(false);
  expect(blocked.serverSnapshot()).toBe(false);
  fail.mockRestore();
  const store = soundPreference('shared'),
    first = vi.fn(),
    second = vi.fn();
  const a = store.subscribe(first),
    b = store.subscribe(second);
  a();
  localStorage.setItem('lia-world-sound:shared', 'on');
  window.dispatchEvent(new StorageEvent('storage', { key: null }));
  expect(second).toHaveBeenCalledOnce();
  expect(first).not.toHaveBeenCalled();
  b();
});

it('remembers owner-local volume independently of mute and clamps restored or changed input', () => {
  localStorage.clear();
  const volume = volumePreference('a'),
    other = volumePreference('b');
  const changed = vi.fn(),
    off = volume.subscribe(changed);
  expect(volume.snapshot()).toBe(1);
  expect(volume.serverSnapshot()).toBe(1);
  volume.update(0.37);
  expect(volume.snapshot()).toBe(0.37);
  expect(volumePreference('a').snapshot()).toBe(0.37);
  expect(other.snapshot()).toBe(1);
  const mute = soundPreference('a');
  mute.update(true);
  mute.update(false);
  expect(volume.snapshot()).toBe(0.37);
  volume.update(-2);
  expect(volume.snapshot()).toBe(0);
  volume.update(20);
  expect(volume.snapshot()).toBe(1);
  volume.update(0.37);
  volume.update(Number.NaN);
  expect(volume.snapshot()).toBe(0.37);
  localStorage.setItem('lia-world-sound-volume:a', '.65');
  window.dispatchEvent(new StorageEvent('storage', { key: 'lia-world-sound-volume:b' }));
  expect(volume.snapshot()).toBe(0.37);
  window.dispatchEvent(new StorageEvent('storage', { key: 'lia-world-sound-volume:a' }));
  expect(volume.snapshot()).toBe(0.65);
  off();
  localStorage.setItem('lia-world-sound-volume:a', 'not a number');
  expect(volumePreference('a').snapshot()).toBe(1);
});
it('keeps the volume slider effective when persistent storage is blocked', () => {
  localStorage.clear();
  const volume = volumePreference('blocked');
  const fail = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw Error('blocked');
  });
  volume.update(0.2);
  expect(volume.snapshot()).toBe(0.2);
  fail.mockRestore();
});
