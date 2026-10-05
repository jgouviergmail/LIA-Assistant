'use client';

/**
 * useLiveSession — the React shell around `LiveSessionController` (ADR-299).
 *
 * One controller per mount, built with the real transport, player, microphone
 * and API client; the page hands the chat's doors through `bindings` and the
 * hook points the controller at the LATEST ones without rebuilding it (a
 * delegated turn must reach the chat the page currently renders, not the one
 * it rendered when the session started). Two effects belong here and nowhere
 * else: the page visibility (a hidden page past the grace puts the session to
 * sleep, ADR-329) and the unmount (a session never outlives its page).
 *
 * A sleeping session's wake word listens in the interface's language, read
 * at each sleep — the controller is built once, the language may change.
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { playReadyChime } from '@/lib/audio/ready-chime';
import { WakeListener } from '@/lib/audio/wake-word/listener';
import { wakeLanguageOf } from '@/lib/audio/wake-word/manifest';
import { isWakeWordSupported } from '@/lib/audio/wake-word/support';
import apiClient from '@/lib/api-client';
import { startMicCapture } from '@/lib/live/mic-capture';
import { PcmStreamPlayer } from '@/lib/live/pcm-player';
import { RoutedLivePlayer } from '@/lib/voice-output/live-player';
import { avatarEngine, awaitAvatarReady } from '@/lib/avatars/runtime';
import {
  LiveSessionController,
  type LiveChatBindings,
  type LiveSpokenMeta,
} from '@/lib/live/session-controller';
import { isSessionOpen } from '@/lib/live/session-machine';
import { isAppleMobile, isLiveSupported } from '@/lib/live/support';
import { createLiveTransport } from '@/lib/live/transports';
import type { LiveOutcome, LiveSessionMode } from '@/lib/live/types';
import { useLiveStore } from '@/stores/liveStore';

export type { LiveChatBindings, LiveSpokenMeta };

export interface UseLiveSessionReturn {
  /** Open a session, delegated unless said (ADR-300 wave 4: `direct`). */
  start: (mode?: LiveSessionMode) => Promise<void>;
  end: (outcome?: LiveOutcome) => Promise<void>;
  toggleMute: () => void;
  /** Prolong the session on the person's explicit word; false when the API refused. */
  extend: () => Promise<boolean>;
  /** The person let the extension dialog go. */
  declineExtension: () => void;
  /** Put the session to sleep: nothing billed until it wakes (ADR-329). */
  standby: () => Promise<void>;
  /** Wake a sleeping session (its phrase wakes it by itself). */
  wake: () => Promise<void>;
}

export function useLiveSession(bindings: LiveChatBindings): UseLiveSessionReturn {
  const { i18n } = useTranslation();
  // One controller per mount (a lazy initial state, never re-created); the
  // chat's doors are pointed at the page's CURRENT bindings by an effect.
  const [controller] = useState(
    () =>
      new LiveSessionController({
        api: apiClient,
        createTransport: createLiveTransport,
        // Give iOS PCM playback headroom for uneven WebSocket arrivals; WebRTC
        // transports own their audio and never use this player.
        createPlayer: () => new RoutedLivePlayer(new PcmStreamPlayer(isAppleMobile() ? 120 : 0), avatarEngine),
        startMic: startMicCapture,
        isSupported: isLiveSupported,
        chat: bindings,
        createWakeListener: options => (isWakeWordSupported() ? new WakeListener(options) : null),
        // The i18n instance is the app's singleton: its language is the current one.
        wakeLanguage: () => wakeLanguageOf(i18n.language),
        chime: playReadyChime,
        awaitAvatar: awaitAvatarReady,
      })
  );
  useEffect(() => {
    controller.setChat(bindings);
  }, [controller, bindings]);

  useEffect(() => {
    const onVisibility = () => controller.pageHidden(document.visibilityState === 'hidden');
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [controller]);

  useEffect(
    () => () => {
      if (isSessionOpen(useLiveStore.getState().status)) void controller.end('ended');
    },
    [controller]
  );

  // A start asked from the header (this page or another one): consumed once,
  // here, by the only session that holds the chat's doors — in the mode asked.
  useEffect(() => {
    const consume = () => {
      const mode = useLiveStore.getState().consumeStart();
      if (mode !== null) void controller.start(mode);
    };
    consume();
    return useLiveStore.subscribe(state => {
      if (state.pendingStart !== null) consume();
    });
  }, [controller]);

  const start = useCallback((mode?: LiveSessionMode) => controller.start(mode), [controller]);
  const end = useCallback((outcome?: LiveOutcome) => controller.end(outcome), [controller]);
  const toggleMute = useCallback(() => controller.toggleMute(), [controller]);
  const extend = useCallback(() => controller.extend(), [controller]);
  const declineExtension = useCallback(() => controller.declineExtension(), [controller]);
  const standby = useCallback(() => controller.standby('manual'), [controller]);
  const wake = useCallback(() => controller.wake(), [controller]);

  return { start, end, toggleMute, extend, declineExtension, standby, wake };
}
