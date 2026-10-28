/** Finite authored gestures; labels stay in the native locale catalogue. */
export const EMOTES = ['wave', 'thanks', 'applause', 'laugh', 'question', 'celebrate'] as const;
export type EmoteKind = (typeof EMOTES)[number];
export const EMOTE_SYMBOLS: Record<EmoteKind, string> = {
  wave: '👋',
  thanks: '🙏',
  applause: '👏',
  laugh: '😄',
  question: '❓',
  celebrate: '🎉',
};
/** One gesture's visible lifetime, and the interval the server enforces between two. */
export const EMOTE_SECONDS = 2;
/** The server receipt vocabulary of a gesture, also used for refusals decided locally. */
export const EMOTE_OUTCOMES = ['accepted', 'rate_limited', 'unavailable'] as const;
export type EmoteOutcome = (typeof EMOTE_OUTCOMES)[number];
export type EmoteRefusal = Exclude<EmoteOutcome, 'accepted'>;
