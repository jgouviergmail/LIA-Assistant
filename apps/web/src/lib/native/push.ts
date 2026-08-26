/**
 * Enrolling a native shell for notifications.
 *
 * The browser path cannot be reused: `Notification` and `PushManager` are both
 * absent from the Android and iOS WebViews (measured), so a shell has to ask
 * its host for a token instead of asking the browser.
 *
 * What it asks for differs per platform, and the difference is structural
 * rather than incidental:
 *
 * - Android talks to whichever Firebase project the user's own server owns,
 *   using options that server publishes. Nothing passes through anyone else.
 * - iOS cannot, because only the Apple Developer team owning the published app
 *   may notify it. It registers with a wake relay and gets back an opaque
 *   handle instead.
 *
 * None of that lives here. This module fetches the server's answer and hands it
 * to the shell whole; each platform reads its own half. Adding a platform, or
 * changing what one of them needs, must not touch this file — and must never
 * turn into a `if (platform === …)` in the web layer.
 */

import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { isNativeShell } from '@/lib/native/shell';

/** Server's answer about how its native shells receive notifications. */
interface PushConfig {
  android: {
    app_id: string;
    api_key: string;
    project_id: string;
    sender_id: string;
  } | null;
  ios: { relay_url: string } | null;
}

/** What the shell reports back. */
export interface NativeEnrolment {
  /** The token to register, or null when there is none to register. */
  token: string | null;
  /** Which platform answered, so the caller never has to sniff it. */
  deviceType: 'android' | 'ios';
  /** Machine-readable cause when there is no token. */
  reason?: string;
}

interface ShellPush {
  registerPush(config: PushConfig & { language: string }): Promise<NativeEnrolment>;
}

/**
 * Read the shell's push capability, if this is running inside one.
 *
 * Deliberately not imported from `@capacitor/core`: the bridge injects
 * `window.Capacitor` at document start, and adding a native dependency to a
 * bundle that is first and foremost a website would be paying for it on every
 * page load in every browser.
 */
function shellPush(): ShellPush | null {
  const plugins = (window as unknown as { Capacitor?: { Plugins?: Record<string, unknown> } })
    .Capacitor?.Plugins;
  const plugin = plugins?.LiaShell as ShellPush | undefined;
  return plugin && typeof plugin.registerPush === 'function' ? plugin : null;
}

/**
 * Ask the shell to enrol this device for notifications.
 *
 * @param language - Language the notification text should be written in. Only
 *   iOS uses it: the relay writes the one sentence it is allowed to send, and
 *   it has no other way to know who it is writing to.
 * @returns The shell's answer, or `null` when this is not a shell — which the
 *   caller reads as "keep doing what the browser does".
 */
export async function enrolNativePush(language: string): Promise<NativeEnrolment | null> {
  if (!isNativeShell()) return null;

  const plugin = shellPush();
  if (!plugin) {
    // An older shell against a newer server. Reporting it beats behaving as if
    // the platform had no push at all, which is what a silent null would say.
    logger.warn('Native push: shell has no registerPush', { component: 'nativePush' });
    return null;
  }

  const config = await apiClient.get<PushConfig>('/notifications/push-config');
  return plugin.registerPush({ ...config, language });
}
