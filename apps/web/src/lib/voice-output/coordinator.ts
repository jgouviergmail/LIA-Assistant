import type { AvatarPhrase } from '../avatars/engine';
import type { DecodedAudioOutput, VoiceUtterance } from './types';
import { logger } from '@/lib/logger';

export interface AvatarAudioTarget {
  readonly ready: boolean;
  interrupt(): void;
  /** One phrase per utterance: every clip of it joins the same remote stream. */
  openPhrase(sampleRate: number, onAudible: () => void): AvatarPhrase;
}
export interface VoiceOutputSelection {
  readonly epoch: number;
  readonly route: 'local' | 'avatar';
  readonly output: DecodedAudioOutput | null;
}

/** One immutable destination per utterance. Late readiness never switches a prefix. */
export class VoiceOutputCoordinator {
  private epoch = 0;
  private active: {
    identity: VoiceUtterance;
    selection: VoiceOutputSelection;
    avatar: AvatarAudioTarget | null;
  } | null = null;
  constructor(private readonly target: AvatarAudioTarget | (() => AvatarAudioTarget | null)) {}

  begin(identity: VoiceUtterance): VoiceOutputSelection {
    if (
      this.active?.identity.source === identity.source &&
      this.active.identity.id === identity.id
    ) {
      return this.active.selection;
    }
    this.interrupt();
    const epoch = this.epoch;
    const avatar = typeof this.target === 'function' ? this.target() : this.target;
    const output = avatar?.ready ? this.avatarOutput(avatar, epoch) : null;
    const selection: VoiceOutputSelection = { epoch, route: output ? 'avatar' : 'local', output };
    logger.info('voice_output_selected', {
      component: 'VoiceOutputCoordinator',
      source: identity.source,
      route: selection.route,
      avatarReady: avatar?.ready ?? false,
    });
    this.active = { identity, selection, avatar };
    return selection;
  }

  /**
   * The utterance's clips join ONE phrase, opened on the first clip and
   * drained once by `end()`. Per clip, the face used to drain and restart:
   * measured 2026-10-04, about 0.6 s of idle face between two sentences.
   */
  private avatarOutput(avatar: AvatarAudioTarget, epoch: number): DecodedAudioOutput {
    const stale = () => epoch !== this.epoch;
    let phrase: AvatarPhrase | null = null;
    return {
      play: async (buffer, signal, onAudible) => {
        if (signal.aborted || stale()) throw new DOMException('Aborted', 'AbortError');
        phrase ??= avatar.openPhrase(buffer.sampleRate, () => {
          if (!stale()) onAudible();
        });
        try {
          await phrase.feed(buffer, signal);
        } catch (error) {
          // A failed or cancelled phrase is closed: nothing is left to drain.
          phrase = null;
          throw error;
        }
        if (signal.aborted || stale()) throw new DOMException('Aborted', 'AbortError');
      },
      end: async () => {
        const current = phrase;
        phrase = null;
        if (!current || stale()) return;
        await current.finish();
      },
    };
  }

  interrupt(): void {
    this.epoch++;
    if (this.active?.selection.route === 'avatar') this.active.avatar?.interrupt();
    this.active = null;
  }
}
