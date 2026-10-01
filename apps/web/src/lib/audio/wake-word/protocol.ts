/**
 * The messages between the wake-word worker and the page (ADR-329).
 *
 * The page sends audio as int16 PCM at 16 kHz in transferable buffers; the
 * worker answers once it is ready (with the phrase its manifest names and the
 * spoken commands it ships), on every detection of the phrase or of a command,
 * and with a coded reason when it cannot run.
 */
import type { Language } from '@/i18n/settings';

import type { WakeCommand } from './commands';

/** Why the detector cannot run: the manifest, a model's bytes, or the runtime itself. */
export type WakeWordFailure = 'manifest' | 'integrity' | 'runtime';

export type ToWorker =
  | { type: 'load'; language: Language }
  | { type: 'audio'; samples: ArrayBuffer }
  | { type: 'reset' };

export type FromWorker =
  | { type: 'ready'; phrase: string; commands: WakeCommand[] }
  | { type: 'detected'; score: number }
  | { type: 'command'; command: WakeCommand }
  | { type: 'failed'; reason: WakeWordFailure };
