/**
 * WebAuthn (passkeys) browser helpers — security program D1.
 *
 * Pure conversion utilities between the WebAuthn JSON wire format
 * (base64url fields, as produced/consumed by the backend's py_webauthn)
 * and the browser's ArrayBuffer-based credential API. No key material is
 * ever stored client-side (BFF invariant): everything transits in memory
 * for the duration of one ceremony.
 */

/** Decode a base64url string into an ArrayBuffer. */
export function base64urlToBuffer(base64url: string): ArrayBuffer {
  const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

/** Encode an ArrayBuffer as a base64url string (no padding). */
export function bufferToBase64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** Whether this browser exposes the WebAuthn credential API. */
export function isWebAuthnSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'PublicKeyCredential' in window &&
    typeof navigator.credentials?.create === 'function'
  );
}

/**
 * Whether conditional UI (passkey autofill in the login form) is available.
 * Resolves false on any detection failure — the explicit button remains.
 */
export async function isConditionalUIAvailable(): Promise<boolean> {
  if (!isWebAuthnSupported()) return false;
  const pkc = window.PublicKeyCredential as typeof PublicKeyCredential & {
    isConditionalMediationAvailable?: () => Promise<boolean>;
  };
  if (typeof pkc.isConditionalMediationAvailable !== 'function') return false;
  try {
    return await pkc.isConditionalMediationAvailable();
  } catch {
    return false;
  }
}

interface WireCredentialDescriptor {
  id: string;
  type: PublicKeyCredentialType;
  transports?: AuthenticatorTransport[];
}

interface WireCreationOptions {
  rp: PublicKeyCredentialRpEntity;
  user: { id: string; name: string; displayName: string };
  challenge: string;
  pubKeyCredParams: PublicKeyCredentialParameters[];
  timeout?: number;
  excludeCredentials?: WireCredentialDescriptor[];
  authenticatorSelection?: AuthenticatorSelectionCriteria;
  attestation?: AttestationConveyancePreference;
}

interface WireRequestOptions {
  challenge: string;
  timeout?: number;
  rpId?: string;
  allowCredentials?: WireCredentialDescriptor[];
  userVerification?: UserVerificationRequirement;
}

/** Convert backend registration options JSON into navigator.credentials.create input. */
export function parseCreationOptions(optionsJson: string): CredentialCreationOptions {
  const wire = JSON.parse(optionsJson) as WireCreationOptions;
  return {
    publicKey: {
      ...wire,
      challenge: base64urlToBuffer(wire.challenge),
      user: { ...wire.user, id: base64urlToBuffer(wire.user.id) },
      excludeCredentials: wire.excludeCredentials?.map(descriptor => ({
        ...descriptor,
        id: base64urlToBuffer(descriptor.id),
      })),
    },
  };
}

/** Convert backend authentication options JSON into navigator.credentials.get input. */
export function parseRequestOptions(optionsJson: string): CredentialRequestOptions {
  const wire = JSON.parse(optionsJson) as WireRequestOptions;
  return {
    publicKey: {
      ...wire,
      challenge: base64urlToBuffer(wire.challenge),
      allowCredentials: wire.allowCredentials?.map(descriptor => ({
        ...descriptor,
        id: base64urlToBuffer(descriptor.id),
      })),
    },
  };
}

/** Serialize a registration ceremony result for the backend (base64url JSON). */
export function serializeRegistrationCredential(
  credential: PublicKeyCredential
): Record<string, unknown> {
  const response = credential.response as AuthenticatorAttestationResponse;
  const transports =
    typeof response.getTransports === 'function' ? response.getTransports() : undefined;
  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment ?? undefined,
    clientExtensionResults: credential.getClientExtensionResults(),
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      attestationObject: bufferToBase64url(response.attestationObject),
      ...(transports ? { transports } : {}),
    },
  };
}

/** Serialize an authentication ceremony result for the backend (base64url JSON). */
export function serializeAuthenticationCredential(
  credential: PublicKeyCredential
): Record<string, unknown> {
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment ?? undefined,
    clientExtensionResults: credential.getClientExtensionResults(),
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      authenticatorData: bufferToBase64url(response.authenticatorData),
      signature: bufferToBase64url(response.signature),
      userHandle: response.userHandle ? bufferToBase64url(response.userHandle) : null,
    },
  };
}
