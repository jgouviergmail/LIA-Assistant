/**
 * Native push enrolment: what the web layer does, and what it refuses to know.
 *
 * The property under test is a boundary, not a behaviour. This module fetches
 * the server's answer and hands it to the shell WHOLE — it must never read a
 * platform-specific field, and must never branch on which platform it is
 * running on. The moment it does, adding a third platform means editing the web
 * app, and the two existing ones start drifting.
 *
 * The rest is failure handling: not a shell, an older shell without the method,
 * a server that cannot answer.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get } }));

const { isNativeShell } = vi.hoisted(() => ({ isNativeShell: vi.fn() }));
vi.mock('@/lib/native/shell', () => ({ isNativeShell }));

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { enrolNativePush } from '../push';

const CONFIG = {
  android: { app_id: 'a', api_key: 'k', project_id: 'p', sender_id: 's' },
  ios: { relay_url: 'https://relay.example.com' },
};

function installShell(registerPush: unknown): void {
  (window as unknown as { Capacitor?: unknown }).Capacitor = {
    Plugins: { LiaShell: registerPush ? { registerPush } : {} },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  isNativeShell.mockReturnValue(true);
  get.mockResolvedValue(CONFIG);
});

afterEach(() => {
  delete (window as unknown as { Capacitor?: unknown }).Capacitor;
});

describe('enrolNativePush', () => {
  it('hands the whole configuration to the shell, untouched', async () => {
    const registerPush = vi.fn().mockResolvedValue({ token: 't', deviceType: 'android' });
    installShell(registerPush);

    await enrolNativePush('de');

    // Whole, and with the language alongside. Picking out `config.android`
    // here would put platform knowledge in the web app, where a third
    // platform would then have to be added by hand.
    expect(registerPush).toHaveBeenCalledWith({ ...CONFIG, language: 'de' });
  });

  it('returns the shell answer verbatim, including which platform replied', async () => {
    installShell(vi.fn().mockResolvedValue({ token: 'relay:h', deviceType: 'ios' }));

    const result = await enrolNativePush('fr');

    // The caller registers the token with `deviceType` and never sniffs the
    // user agent, which is wrong in a WebView more often than it is right.
    expect(result).toEqual({ token: 'relay:h', deviceType: 'ios' });
  });

  it('passes a refusal through rather than flattening it to null', async () => {
    installShell(
      vi.fn().mockResolvedValue({ token: null, deviceType: 'android', reason: 'permission_denied' })
    );

    const result = await enrolNativePush('fr');

    // "You said no" and "this server has no push" lead to different things
    // being shown, so the reason has to survive the trip.
    expect(result).toEqual({ token: null, deviceType: 'android', reason: 'permission_denied' });
  });
});

describe('when there is nothing to enrol with', () => {
  it('says so in a browser, without calling the server', async () => {
    isNativeShell.mockReturnValue(false);

    expect(await enrolNativePush('fr')).toBeNull();
    expect(get).not.toHaveBeenCalled();
  });

  it('says so when an older shell has no push method', async () => {
    installShell(null);

    expect(await enrolNativePush('fr')).toBeNull();
    // The browser path is what the caller falls back to — which in a WebView
    // reports "unsupported", the honest answer for a shell that cannot.
    expect(get).not.toHaveBeenCalled();
  });

  it('lets a failing configuration call surface', async () => {
    installShell(vi.fn());
    get.mockRejectedValue(new Error('503'));

    // Swallowed here, this would read as "your phone does not support
    // notifications" — a diagnosis nobody could act on.
    await expect(enrolNativePush('fr')).rejects.toThrow('503');
  });
});
