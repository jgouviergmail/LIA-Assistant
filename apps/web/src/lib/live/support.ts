/**
 * Whether this browser can hold a live session at all (ADR-299): a WebSocket
 * to the provider, an audio worklet for the microphone, a media device to
 * open. `navigator.mediaDevices` is undefined outside a secure context — a
 * self-hosted install reached over plain HTTP on a LAN — and an old WebView
 * has no worklet. Asked BEFORE the credential is minted, so an unsupported
 * browser costs no session, no claim and no mint; asked after, the failure
 * surfaced as « microphone denied » on a session already counted.
 */
export function isLiveSupported(): boolean {
  if (typeof window === 'undefined') return false;
  return (
    typeof WebSocket === 'function' &&
    typeof AudioContext === 'function' &&
    typeof AudioWorkletNode === 'function' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function'
  );
}
