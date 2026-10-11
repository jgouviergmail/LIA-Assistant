/** An address for this document; the HTTP-only session remains the authority. */
export const APPLICATION_DEVICE_HEADER = 'X-Lia-Device-ID';

let documentAddress: string | undefined;

export function applicationDeviceId(): string | undefined {
  if (typeof window === 'undefined' || typeof globalThis.crypto?.randomUUID !== 'function')
    return undefined;
  documentAddress ??= globalThis.crypto.randomUUID();
  return documentAddress;
}

/** Other requests, including auth/features, keep their existing CORS behavior. */
export function applicationDeviceHeaders(endpoint: string): Record<string, string> {
  if (
    endpoint !== '/agents/chat/stream' &&
    !endpoint.startsWith('/application-commands/') &&
    !endpoint.startsWith('/application-device/')
  )
    return {};
  const address = applicationDeviceId();
  return address ? { [APPLICATION_DEVICE_HEADER]: address } : {};
}
