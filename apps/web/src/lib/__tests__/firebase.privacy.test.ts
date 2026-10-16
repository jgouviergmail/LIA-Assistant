import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MessagePayload } from 'firebase/messaging';

const sdk = vi.hoisted(() => ({
  receive: undefined as ((payload: MessagePayload) => void) | undefined,
  token: vi.fn<() => Promise<string>>(),
  unsubscribe: vi.fn(),
}));
vi.mock('firebase/app', () => ({
  initializeApp: vi.fn(() => ({})),
  getApps: vi.fn(() => []),
  getApp: vi.fn(() => ({})),
}));
vi.mock('firebase/messaging', () => ({
  getMessaging: vi.fn(() => ({})),
  getToken: sdk.token,
  onMessage: vi.fn((_messaging: unknown, receive: (payload: MessagePayload) => void) => {
    sdk.receive = receive;
    return sdk.unsubscribe;
  }),
}));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  sdk.receive = undefined;
  for (const name of ['API_KEY', 'PROJECT_ID', 'MESSAGING_SENDER_ID', 'VAPID_KEY']) {
    vi.stubEnv(`NEXT_PUBLIC_FIREBASE_${name}`, 'public-test-configuration');
  }
  vi.stubGlobal('Notification', {
    permission: 'granted',
    requestPermission: vi.fn(async () => 'granted'),
  });
  vi.stubGlobal('navigator', {
    userAgent: 'unit-test',
    serviceWorker: {
      register: vi.fn(async () => ({ scope: 'https://lia.example/' })),
      ready: Promise.resolve({}),
    },
  });
  for (const method of ['log', 'info', 'warn', 'error'] as const) {
    vi.spyOn(console, method).mockImplementation(() => {});
  }
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe('Firebase diagnostics preserve private push data', () => {
  it('delivers the original foreground payload without writing its content to the console', async () => {
    const { onForegroundMessage } = await import('../firebase');
    const received = vi.fn();
    const unsubscribe = onForegroundMessage(received);
    const payload = {
      from: 'unit-sender',
      collapseKey: 'reminders',
      messageId: 'private-message-fixture',
      notification: { body: 'private-push-canary@example.invalid' },
    } satisfies MessagePayload;

    sdk.receive?.(payload);

    expect(received).toHaveBeenCalledWith(payload);
    expect(JSON.stringify(vi.mocked(console.info).mock.calls)).not.toContain(
      payload.notification.body
    );
    unsubscribe?.();
    expect(sdk.unsubscribe).toHaveBeenCalledOnce();
  });

  it('returns a device token without logging even its prefix', async () => {
    const { requestNotificationPermission } = await import('../firebase');
    const token = 'private-device-token-canary-long-fixture';
    sdk.token.mockResolvedValueOnce(token);

    await expect(requestNotificationPermission()).resolves.toBe(token);

    expect(JSON.stringify(vi.mocked(console.info).mock.calls)).not.toContain(token.slice(0, 20));
  });

  it('keeps the original failure for its caller and only its type in console diagnostics', async () => {
    const { requestNotificationPermission } = await import('../firebase');
    const failure = new Error('private-provider-canary@example.invalid');
    sdk.token.mockRejectedValueOnce(failure);

    await expect(requestNotificationPermission()).rejects.toBe(failure);

    expect(console.error).toHaveBeenCalled();
    const diagnostics = vi.mocked(console.error).mock.calls.flat().map(String).join(' ');
    expect(diagnostics).not.toContain(failure.message);
  });
});
