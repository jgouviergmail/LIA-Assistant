/**
 * A `cues` session's words as the person heard them (ADR-373).
 *
 * On a session whose voice performs cues (an ElevenLabs agent whose engine plays
 * audio tags), the vendor's transcript keeps every tag its model wrote, unspoken —
 * and the model may write tags beyond the palette LIA offered. So every bounded
 * bracketed span of the voice's text goes, a tag the text was cut inside at its
 * end included (a caption still streaming, a turn bounded at its maximum). Only
 * such a session's assistant text is read here: anywhere else a bracket is words.
 *
 * The twin of the server's `expressive_cues.strip_transcript_cues`; ONE corpus
 * (`apps/api/tests/unit/domains/voice/cue_strip_corpus.json`) pins the two.
 */

/** The server's `MARKDOWN_SPAN_MAX_CHARS` (ADR-326): a bounded span keeps the pattern linear. */
const SPAN_MAX_CHARS = 400;
/** A tag, with the one blank before it. */
const TAG = new RegExp(` ?\\[([^\\[\\]\\n]{1,${SPAN_MAX_CHARS}})\\]`, 'g');
/** A tag the text was cut inside: an opening bracket nothing closes before the end. */
const CUT_TAG = new RegExp(` ?\\[[^\\[\\]\\n]{0,${SPAN_MAX_CHARS}}$`);
const BLANKS = /[ \t]{2,}/g;
const BLANK_AT_BREAK = / ?\n ?/g;

/** The text without its tags, blanks tidied, and each tag's words as written. */
export function stripTranscriptCues(text: string): { text: string; tags: string[] } {
  const tags: string[] = [];
  const kept = text
    .replace(TAG, (_tag: string, words: string) => {
      tags.push(words.trim());
      return '';
    })
    .replace(CUT_TAG, '');
  return { text: kept.replace(BLANKS, ' ').replace(BLANK_AT_BREAK, '\n').trim(), tags };
}

/** What a caption or a row shows of the voice's words on a `cues` session. */
export function heardText(text: string): string {
  return stripTranscriptCues(text).text;
}
