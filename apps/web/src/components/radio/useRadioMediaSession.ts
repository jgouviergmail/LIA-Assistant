'use client';

/**
 * The radio under the system's media controls (ADR-324): the keyboard's
 * play/pause key, the headset's button and the browser's media hub pause,
 * resume and stop the station, and show what is on air.
 *
 * Mounted by the radio bar, so it follows the station across pages. A browser
 * without the Media Session API (and every test runner) is left untouched;
 * an action a browser does not know is skipped rather than thrown.
 */

import { useEffect } from 'react';

import { isOnAir } from '@/lib/radio/machine';
import { radioPlayer } from '@/lib/radio/player';
import { useRadioStore } from '@/stores/radioStore';

type Handled = 'play' | 'pause' | 'stop';

function handle(session: MediaSession, action: Handled, handler: (() => void) | null): void {
  try {
    session.setActionHandler(action, handler);
  } catch {
    // An action this browser does not support: the others still work.
  }
}

export function useRadioMediaSession(title: string | null, station: string): void {
  const status = useRadioStore(state => state.view.status);
  const onAir = isOnAir(status);

  useEffect(() => {
    if (!onAir || typeof navigator === 'undefined' || !('mediaSession' in navigator)) return;
    const session = navigator.mediaSession;
    handle(session, 'play', () => void radioPlayer().resume());
    handle(session, 'pause', () => radioPlayer().pause());
    handle(session, 'stop', () => void radioPlayer().stop());
    return () => {
      handle(session, 'play', null);
      handle(session, 'pause', null);
      handle(session, 'stop', null);
      session.metadata = null;
    };
  }, [onAir]);

  useEffect(() => {
    if (!onAir || typeof navigator === 'undefined' || !('mediaSession' in navigator)) return;
    if (typeof MediaMetadata === 'undefined') return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: title ?? station,
      artist: station,
    });
  }, [onAir, title, station]);
}
