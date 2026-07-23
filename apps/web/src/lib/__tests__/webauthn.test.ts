/**
 * WebAuthn helpers — base64url round-trips, wire-format parsing for both
 * ceremonies, credential serialization, and feature detection. These are the
 * pure conversions every passkey ceremony depends on: a drift here corrupts
 * challenges or credential ids silently.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';

import {
  base64urlToBuffer,
  bufferToBase64url,
  isConditionalUIAvailable,
  isWebAuthnSupported,
  parseCreationOptions,
  parseRequestOptions,
  serializeAuthenticationCredential,
  serializeRegistrationCredential,
} from '../webauthn';

describe('base64url conversions', () => {
  it('round-trips arbitrary bytes', () => {
    const bytes = new Uint8Array([0, 1, 2, 250, 251, 252, 253, 254, 255]);
    const encoded = bufferToBase64url(bytes.buffer);
    expect(encoded).not.toMatch(/[+/=]/); // url-safe, unpadded
    expect(new Uint8Array(base64urlToBuffer(encoded))).toEqual(bytes);
  });

  it('decodes unpadded input from the backend (py_webauthn strips padding)', () => {
    // "challenge" → base64url without padding
    const decoded = new TextDecoder().decode(base64urlToBuffer('Y2hhbGxlbmdl'));
    expect(decoded).toBe('challenge');
  });
});

describe('parseCreationOptions', () => {
  it('converts challenge, user.id and excludeCredentials ids to buffers', () => {
    const wire = JSON.stringify({
      rp: { id: 'localhost', name: 'LIA' },
      user: { id: 'dXNlci1pZA', name: 'a@b.c', displayName: 'A' },
      challenge: 'Y2hhbGxlbmdl',
      pubKeyCredParams: [{ type: 'public-key', alg: -7 }],
      timeout: 300000,
      excludeCredentials: [{ id: 'Y3JlZC1pZA', type: 'public-key' }],
      authenticatorSelection: { residentKey: 'required', userVerification: 'required' },
    });

    const parsed = parseCreationOptions(wire);
    const pk = parsed.publicKey!;

    expect(new TextDecoder().decode(pk.challenge as ArrayBuffer)).toBe('challenge');
    expect(new TextDecoder().decode(pk.user.id as ArrayBuffer)).toBe('user-id');
    expect(pk.excludeCredentials).toHaveLength(1);
    expect(new TextDecoder().decode(pk.excludeCredentials![0].id as ArrayBuffer)).toBe('cred-id');
    expect(pk.rp.id).toBe('localhost');
    expect(pk.authenticatorSelection?.residentKey).toBe('required');
  });
});

describe('parseRequestOptions', () => {
  it('converts the challenge and tolerates absent allowCredentials (discoverable)', () => {
    const parsed = parseRequestOptions(
      JSON.stringify({ challenge: 'Y2hhbGxlbmdl', rpId: 'localhost', userVerification: 'required' })
    );
    const pk = parsed.publicKey!;
    expect(new TextDecoder().decode(pk.challenge as ArrayBuffer)).toBe('challenge');
    expect(pk.allowCredentials).toBeUndefined();
    expect(pk.rpId).toBe('localhost');
  });
});

function fakeCredential(response: object): PublicKeyCredential {
  return {
    id: 'Y3JlZC1pZA',
    rawId: new TextEncoder().encode('cred-id').buffer,
    type: 'public-key',
    authenticatorAttachment: 'platform',
    getClientExtensionResults: () => ({}),
    response,
  } as unknown as PublicKeyCredential;
}

describe('serializeRegistrationCredential', () => {
  it('emits base64url fields + transports for the backend', () => {
    const credential = fakeCredential({
      clientDataJSON: new TextEncoder().encode('cdj').buffer,
      attestationObject: new TextEncoder().encode('att').buffer,
      getTransports: () => ['internal', 'hybrid'],
    });

    const wire = serializeRegistrationCredential(credential) as {
      rawId: string;
      response: { clientDataJSON: string; attestationObject: string; transports?: string[] };
    };

    expect(new TextDecoder().decode(base64urlToBuffer(wire.rawId))).toBe('cred-id');
    expect(new TextDecoder().decode(base64urlToBuffer(wire.response.clientDataJSON))).toBe('cdj');
    expect(new TextDecoder().decode(base64urlToBuffer(wire.response.attestationObject))).toBe(
      'att'
    );
    expect(wire.response.transports).toEqual(['internal', 'hybrid']);
  });

  it('omits transports when the authenticator does not report them', () => {
    const credential = fakeCredential({
      clientDataJSON: new ArrayBuffer(1),
      attestationObject: new ArrayBuffer(1),
    });
    const wire = serializeRegistrationCredential(credential) as {
      response: Record<string, unknown>;
    };
    expect('transports' in wire.response).toBe(false);
  });
});

describe('serializeAuthenticationCredential', () => {
  it('emits base64url assertion fields, null userHandle preserved', () => {
    const credential = fakeCredential({
      clientDataJSON: new TextEncoder().encode('cdj').buffer,
      authenticatorData: new TextEncoder().encode('ad').buffer,
      signature: new TextEncoder().encode('sig').buffer,
      userHandle: null,
    });

    const wire = serializeAuthenticationCredential(credential) as {
      response: { signature: string; userHandle: string | null };
    };
    expect(new TextDecoder().decode(base64urlToBuffer(wire.response.signature))).toBe('sig');
    expect(wire.response.userHandle).toBeNull();
  });
});

describe('feature detection', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('reports unsupported without PublicKeyCredential', () => {
    vi.stubGlobal('PublicKeyCredential', undefined);
    // jsdom has no PublicKeyCredential by default either way
    expect(isWebAuthnSupported()).toBe(false);
  });

  it('conditional UI resolves false when detection is absent or throws', async () => {
    await expect(isConditionalUIAvailable()).resolves.toBe(false);
  });
});
