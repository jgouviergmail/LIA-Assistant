'use client';

/**
 * The page's one radio player (ADR-324): built on first use, in the browser
 * only, and kept for the life of the document — navigating inside the app never
 * interrupts the antenna.
 */
import { useRadioStore } from '@/stores/radioStore';

import { radioApi } from './api';
import { radioAudio } from './audio-element';
import { RadioController } from './controller';
import { browserMusicBed } from './web-audio';

/** How often the player reports where it is (every report is answered with the session). */
export const RADIO_REPORT_INTERVAL_MS = 5000;
/** Failed reports in a row, with nothing left to play, before the player gives up. */
export const RADIO_REPORT_FAILURES_MAX = 6;

let player: RadioController | null = null;

/** The player, created at the first call (which must come from the click). */
export function radioPlayer(): RadioController {
  player ??= new RadioController({
    api: radioApi,
    // Built inside the click: the audio engine starts running there.
    audio: radioAudio(new Audio(), browserMusicBed()),
    timers: {
      setInterval: (callback, ms) => window.setInterval(callback, ms),
      clearInterval: handle => window.clearInterval(handle),
      setTimeout: (callback, ms) => window.setTimeout(callback, ms),
      clearTimeout: handle => window.clearTimeout(handle),
    },
    urls: {
      create: blob => URL.createObjectURL(blob),
      revoke: url => URL.revokeObjectURL(url),
    },
    reportIntervalMs: RADIO_REPORT_INTERVAL_MS,
    reportFailuresMax: RADIO_REPORT_FAILURES_MAX,
    onChange: view => useRadioStore.getState().setView(view),
  });
  return player;
}
