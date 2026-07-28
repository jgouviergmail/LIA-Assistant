/**
 * NotificationPrompt — the enrolment dialog's three outcomes.
 *
 * The real `useFCMToken` runs here (only the Firebase SDK, the API client and
 * the toaster are stubbed) because the defect these tests pin is a React one:
 * the click handler used to read `error` / `permissionStatus` from the render
 * that created it, i.e. AFTER an `await` it still saw the pre-click values.
 * A mocked hook returns a frozen object and cannot reproduce that — it would
 * have shown the tests green while production reported `Enable failed: null`.
 *
 * Contract pinned:
 *  - a refusal and a technical failure are told apart (they call for different
 *    things from the user: re-allow in browser settings vs. report a bug);
 *  - a technical failure reports its REAL cause on the diagnostic channel;
 *  - what the user sees stays translated — an untranslated SDK string
 *    ("Failed to fetch") is not a user-facing message.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: api }));

const { logger } = vi.hoisted(() => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));
vi.mock('@/lib/logger', () => ({ logger }));

const firebase = vi.hoisted(() => ({
  requestNotificationPermission: vi.fn(),
  getNotificationPermission: vi.fn(),
  areNotificationsSupported: vi.fn(),
  isFirebaseConfigured: vi.fn(),
  getDeviceType: vi.fn(),
  isIOSPWA: vi.fn(),
}));
vi.mock('@/lib/firebase', () => firebase);

const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { NotificationPrompt } from '../NotificationPrompt';

/** The exact failure production hit on 2026-07-24 (CSP blocked getToken). */
const CSP_FAILURE =
  "Failed to fetch. Refused to connect because it violates the document's Content Security Policy.";

function renderPrompt(onSuccess?: (token: string) => void) {
  return renderWithProviders(
    <NotificationPrompt lng="en" open onOpenChange={vi.fn()} onSuccess={onSuccess} />
  );
}

/** Clicks the dialog's enable button. */
async function clickEnable(user: ReturnType<typeof renderPrompt>['user']) {
  await user.click(screen.getByRole('button', { name: 'notifications.enable_button' }));
}

beforeEach(() => {
  vi.clearAllMocks();
  firebase.areNotificationsSupported.mockReturnValue(true);
  firebase.isFirebaseConfigured.mockReturnValue(true);
  firebase.isIOSPWA.mockReturnValue(false);
  firebase.getDeviceType.mockReturnValue('web');
  firebase.getNotificationPermission.mockReturnValue('default');
  api.get.mockResolvedValue({ tokens: [] });
  api.post.mockResolvedValue(undefined);
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('NotificationPrompt — enrolment outcomes', () => {
  it('enrols, tells the user, and hands the token back', async () => {
    firebase.requestNotificationPermission.mockResolvedValue('fcm-token-abc');
    firebase.getNotificationPermission.mockReturnValue('granted');
    const onSuccess = vi.fn();
    const { user } = renderPrompt(onSuccess);

    await clickEnable(user);

    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith('fcm-token-abc'));
    expect(api.post).toHaveBeenCalledWith(
      '/notifications/register-token',
      expect.objectContaining({ token: 'fcm-token-abc', device_type: 'web' })
    );
    expect(toast.success).toHaveBeenCalledWith('notifications.enabled_success');
    expect(toast.error).not.toHaveBeenCalled();
  });

  // Regression 2026-07-24: `permissionStatus` was read from the pre-click
  // render, so a refusal fell through to the generic failure branch and the
  // user was told "something went wrong" instead of "you blocked it".
  it('tells a refusal apart from a failure', async () => {
    firebase.requestNotificationPermission.mockResolvedValue(null);
    firebase.getNotificationPermission.mockReturnValueOnce('default').mockReturnValue('denied');
    const { user } = renderPrompt();

    await clickEnable(user);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('notifications.permission_denied')
    );
    expect(api.post).not.toHaveBeenCalled();
  });

  // Regression 2026-07-24: production logged `Enable failed: null` while the
  // hook held "Failed to fetch" — the stale closure swallowed the one piece of
  // information that made the incident diagnosable.
  it('reports the real cause of a technical failure, not null', async () => {
    firebase.requestNotificationPermission.mockRejectedValue(new Error(CSP_FAILURE));
    const { user } = renderPrompt();

    await clickEnable(user);

    await waitFor(() =>
      expect(logger.error).toHaveBeenCalledWith(
        expect.stringContaining('NotificationPrompt'),
        undefined,
        expect.objectContaining({ cause: expect.stringContaining('Content Security Policy') })
      )
    );
  });

  it('keeps the user-facing message translated, never a raw SDK string', async () => {
    firebase.requestNotificationPermission.mockRejectedValue(new Error(CSP_FAILURE));
    const { user } = renderPrompt();

    await clickEnable(user);

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('notifications.enable_failed'));
    expect(toast.error).not.toHaveBeenCalledWith(expect.stringContaining('Failed to fetch'));
  });
});
