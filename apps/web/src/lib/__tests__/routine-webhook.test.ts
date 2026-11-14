/**
 * The signed-call example a sender adapts (ADR-386): it must sign the body the
 * way the server checks it — HMAC-SHA256 of the exact body, hex, `sha256=` —
 * and send that signature in the header the server reads first.
 */

import { describe, expect, it } from 'vitest';

import {
  ROUTINE_WEBHOOK_SIGNATURE_HEADER,
  drawnSecretOf,
  signedCallExample,
} from '../routine-webhook';

const DRAWN = {
  webhook_url: 'https://lia.example/api/v1/hooks/routines/AbCdEfGhIjKlMnOpQrStUvWxYz012345',
  webhook_secret: 's3cr3t-value_with-url-safe-chars',
};

describe('signedCallExample', () => {
  it('names the address and the secret it was drawn with', () => {
    const lines = signedCallExample(DRAWN).split('\n');

    expect(lines[0]).toBe(`URL='${DRAWN.webhook_url}'`);
    expect(lines[1]).toBe(`SECRET='${DRAWN.webhook_secret}'`);
  });

  it('signs the exact body with HMAC-SHA256 and sends it in the header the server reads', () => {
    const example = signedCallExample(DRAWN);
    const body = /BODY='([^']*)'/.exec(example)?.[1] ?? '';

    // The EXACT bytes: `printf '%s'`, never `echo`, which would sign a newline
    // the call does not send.
    expect(example).toContain(`printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET"`);
    expect(example).toContain('SIGNATURE="sha256=$(');
    expect(example).toContain(`-H "${ROUTINE_WEBHOOK_SIGNATURE_HEADER}: $SIGNATURE"`);
    expect(example).toContain('-d "$BODY"');
    // And the body it signs is one a run can read.
    expect(() => JSON.parse(body)).not.toThrow();
  });
});

describe('drawnSecretOf', () => {
  const url = 'https://lia.example/api/v1/hooks/routines/k';

  it('reads the pair an answer carries when the request drew a secret', () => {
    expect(drawnSecretOf({ webhook_url: url, new_webhook_secret: 's' })).toEqual({
      webhook_url: url,
      webhook_secret: 's',
    });
  });

  it('reads nothing from an answer that drew none, or from no answer', () => {
    expect(drawnSecretOf({ webhook_url: url, new_webhook_secret: null })).toBeNull();
    expect(drawnSecretOf({ webhook_url: null, new_webhook_secret: 's' })).toBeNull();
    expect(drawnSecretOf(undefined)).toBeNull();
  });
});
