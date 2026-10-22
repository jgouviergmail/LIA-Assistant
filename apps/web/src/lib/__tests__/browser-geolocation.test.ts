import { afterEach, describe, expect, it, vi } from 'vitest';
import { readGrantedPosition } from '../browser-geolocation';

afterEach(() => {
  Reflect.deleteProperty(navigator, 'permissions');
  Reflect.deleteProperty(navigator, 'geolocation');
});

describe('already granted browser position', () => {
  it.each(['prompt', 'denied'])('never requests a position when permission is %s', async state => {
    const getCurrentPosition = vi.fn();
    Object.defineProperty(navigator, 'permissions', {
      configurable: true,
      value: { query: async () => ({ state }) },
    });
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition },
    });
    expect(await readGrantedPosition()).toBeNull();
    expect(getCurrentPosition).not.toHaveBeenCalled();
  });

  it('stops waiting when its owning selection is aborted', async () => {
    Object.defineProperty(navigator, 'permissions', {
      configurable: true,
      value: { query: async () => ({ state: 'granted' }) },
    });
    const getCurrentPosition = vi.fn();
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition },
    });
    const controller = new AbortController();
    const pending = readGrantedPosition(controller.signal);
    await Promise.resolve();
    controller.abort();
    expect(await pending).toBeNull();
  });
});
