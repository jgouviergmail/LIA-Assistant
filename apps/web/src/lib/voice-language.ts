/**
 * Which voices a picker shows for a reader's language (ADR-345 amendment 2026-10-14).
 *
 * A voice that names one language speaks it natively; one that names none speaks
 * every language (a multilingual model, a clone in several), so it always passes.
 * The filter is the reader's convenience over a list the server already decided:
 * it narrows what is SHOWN, never what may be chosen — and the voice a form holds
 * stays in its own list, or its select would show nothing.
 */
import { sameLanguage } from '@/lib/language-match';

/** A voice as a picker holds it: an id, and the one language it is native to, if any. */
export interface LanguageTaggedVoice {
  voice_id: string;
  language?: string | null;
}

/**
 * The voices native to `language` and those that name none, in their order, plus
 * the voices `keep` names.
 */
export function voicesInLanguage<T extends LanguageTaggedVoice>(
  voices: readonly T[],
  language: string,
  keep: readonly (string | null | undefined)[] = []
): T[] {
  const kept = new Set(keep.filter((id): id is string => Boolean(id)));
  return voices.filter(
    voice => kept.has(voice.voice_id) || sameLanguage(voice.language ?? undefined, language)
  );
}

/**
 * Whether narrowing to `language` is worth offering: it must change the list and
 * still leave a voice to choose — a switch that does nothing, or empties the list,
 * is noise.
 */
export function languageNarrows(voices: readonly LanguageTaggedVoice[], language: string): boolean {
  const narrowed = voicesInLanguage(voices, language).length;
  return narrowed > 0 && narrowed < voices.length;
}
