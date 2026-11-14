/**
 * A routine another system starts with a signed call (ADR-386): what the web
 * shows the person who sets the sender up.
 *
 * The address and the secret are the server's; the browser only shows them and
 * writes the one example a sender adapts. The example is a shell command —
 * `openssl` signs the EXACT body, `curl` sends it — because the scheme is the one
 * code forges already use, and a person configuring a home automation box or a
 * form service recognises it.
 */

import type { RoutineWebhookSecret, ScheduledAction } from '@/hooks/useScheduledActions';

/** The header a sender puts the signature in (`X-Hub-Signature-256` is read alike). */
export const ROUTINE_WEBHOOK_SIGNATURE_HEADER = 'X-LIA-Signature-256';

/** The body the example sends: any JSON (or text) the routine should read. */
const EXAMPLE_BODY = '{"event": "door_opened"}';

/**
 * A shell example signing a body with the secret and sending it to the address.
 *
 * @param drawn - The routine's address and the secret just drawn.
 * @returns Five lines a sender pastes: the address, the secret, a body, its
 *   signature (HMAC-SHA256, hex, `sha256=` prefix) and the call.
 */
export function signedCallExample(drawn: RoutineWebhookSecret): string {
  return [
    `URL='${drawn.webhook_url}'`,
    `SECRET='${drawn.webhook_secret}'`,
    `BODY='${EXAMPLE_BODY}'`,
    `SIGNATURE="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')"`,
    `curl -X POST "$URL" -H 'Content-Type: application/json' -H "${ROUTINE_WEBHOOK_SIGNATURE_HEADER}: $SIGNATURE" -d "$BODY"`,
  ].join('\n');
}

/**
 * The address and the secret a routine's answer carries, when the request
 * drew one — the creation of a routine on calls, its switch onto calls.
 *
 * @param action - The routine as the server answered, or nothing.
 * @returns The pair to show once, or `null` when no secret was drawn.
 */
export function drawnSecretOf(
  action: Pick<ScheduledAction, 'webhook_url' | 'new_webhook_secret'> | null | undefined
): RoutineWebhookSecret | null {
  if (!action?.webhook_url || !action.new_webhook_secret) return null;
  return { webhook_url: action.webhook_url, webhook_secret: action.new_webhook_secret };
}
