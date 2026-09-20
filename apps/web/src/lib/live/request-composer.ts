/**
 * The request of a NATIVE delegation, composed from the input transcript
 * (ADR-299, wave 2 spec A9).
 *
 * GPT-Live's `session.delegation.created` carries an id and an `offset_ms`,
 * never the request text (documented 2026-09-19: « the delegation object
 * contains metadata, not task text »). The request is therefore what the
 * person said since the previous delegation, as the provider transcribed it
 * — fragments with `start_ms` / `end_ms` — up to the delegation's offset.
 * Short replies (« yes », « no, Tuesday ») are sent as they are: the chat
 * thread already holds the earlier turns, and the newest-request rule of the
 * bridge (A7) applies unchanged.
 */

interface Fragment {
  text: string;
  startMs: number;
  endMs: number;
}

export class RequestComposer {
  private fragments: Fragment[] = [];
  /** Fragments at or before this instant belong to an earlier request. */
  private cutoffMs = 0;

  /** One input-transcript delta as the provider timed it. */
  record(text: string, startMs: number, endMs: number): void {
    if (!text) return;
    this.fragments.push({ text, startMs, endMs });
  }

  /**
   * The words since the previous delegation, up to `offsetMs` — or null when
   * nothing was transcribed. Composing moves the cut: the next request starts
   * after this one.
   */
  compose(offsetMs: number): string | null {
    const cut = Math.max(this.cutoffMs, 0);
    const mine = this.fragments.filter(f => f.startMs >= cut && f.startMs <= offsetMs);
    const rest = this.fragments.filter(f => f.startMs > offsetMs);
    this.fragments = rest;
    this.cutoffMs = Math.max(this.cutoffMs, offsetMs);
    const text = mine
      .map(f => f.text)
      .join('')
      .replace(/\s+/g, ' ')
      .trim();
    return text || null;
  }
}
