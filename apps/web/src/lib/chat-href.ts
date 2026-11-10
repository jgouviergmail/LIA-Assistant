/** Chat URL builders shared by every surface, independent of dashboard translations. */
import type { CapabilityDirectiveWire } from '@/types/directive';
import { newIntentId } from '@/lib/intent-replay-guard';
import { formatAttachSource, type AttachSource } from '@/lib/attach-source-link';

/**
 * Build a localized chat link with an optional unsent draft (QW-9).
 *
 * With a draft, the chat input is prefilled (never auto-sent) — the exact
 * onboarding `?draft=` pattern, generalized to the briefing cards.
 *
 * @param lng - Current URL locale segment.
 * @param draft - Optional prefill intent for the chat input.
 * @returns Localized chat route, with the encoded `draft` when provided.
 */
export function chatDraftHref(lng: string, draft?: string): string {
  const base = `/${lng}/dashboard/chat`;
  return draft ? `${base}?draft=${encodeURIComponent(draft)}` : base;
}

/**
 * Build the chat deep-link that attaches a COPY of something the person holds
 * (a kept answer, a generated file) to the composer — never a send.
 *
 * @param lng - UI language for the route prefix.
 * @param source - What to attach.
 * @returns Localized chat route carrying `?attach=<kind>:<id>`.
 */
export function chatAttachHref(lng: string, source: AttachSource): string {
  return `/${lng}/dashboard/chat?attach=${encodeURIComponent(formatAttachSource(source))}`;
}

/**
 * Build the chat deep-link an IMMEDIATE action opens (QW-24, ADR-173).
 *
 * Unlike `?draft=` (prefill, the user presses Enter), `?intent=` is
 * AUTO-SENT by the chat page once it is safe to do so — the click on a
 * named action button IS the deliberate act. External writes stay behind
 * the pipeline's tool-level HITL cards.
 *
 * An optional `directive` rides alongside the prose (ADR-191): the sentence
 * stays what the user reads, the directive is what the backend guarantees to
 * run. Actions whose meaning is fully carried by their text pass nothing and
 * behave exactly as before.
 *
 * Every call also mints a one-shot `iid` (ADR-210): the URL is a replayable
 * carrier (browser history, omnibox, session restore), and the chat page
 * refuses to auto-send an iid it has already consumed. Fresh per CALL, so two
 * clicks on the same action remain two executions. Backend-emitted intent
 * links carry no iid and keep their click-is-consent semantics.
 *
 * @param lng - Current URL locale segment.
 * @param intent - The full localized request to send.
 * @param directive - Capability the click invoked, when the action has one.
 * @returns Localized chat route with the encoded `intent`.
 */
export function chatIntentHref(
  lng: string,
  intent: string,
  directive?: CapabilityDirectiveWire
): string {
  // `encodeURIComponent`, not `URLSearchParams`: the latter encodes a space as
  // `+`, which would rewrite every existing briefing deep link. Both decode
  // identically, but a change nobody asked for is a change nobody tested.
  const parts = [`intent=${encodeURIComponent(intent)}`];
  parts.push(`iid=${newIntentId()}`);
  if (directive) {
    parts.push(`capability=${encodeURIComponent(directive.capability)}`);
    parts.push(`subject=${encodeURIComponent(directive.subject)}`);
  }
  return `/${lng}/dashboard/chat?${parts.join('&')}`;
}
