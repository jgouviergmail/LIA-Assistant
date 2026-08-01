/**
 * A capability the user invoked directly, sent alongside the visible message.
 *
 * A button is not a sentence. When someone presses "run the 360°" on a named
 * relationship card, the browser already knows which capability must run and on
 * whom — and serialising that into French prose for three LLM stages to recover
 * is how it gets lost. Measured in production on 2026-08-01: the 360° tool
 * scored 0.853, the best of the whole catalogue, and the plan called
 * `get_emails_tool` instead (ADR-191).
 *
 * Same doctrine as `HitlDecisionWire`: the click travels as data, the prose
 * stays what the user reads. `capability` names a CAPABILITY, never a tool —
 * the backend closes the list (Pydantic `Literal`) and chooses which read-only
 * tool implements it, so this channel cannot reach an arbitrary tool.
 */
export interface CapabilityDirectiveWire {
  /** Closed allowlist, mirrored from the backend `DirectiveCapability`. */
  capability: 'person_overview';
  /** What the capability applies to — here, the person's display name. */
  subject: string;
}
