/**
 * Whether this browser can run the wake-word detector (ADR-329): a module
 * worker, WebAssembly, an audio worklet and a microphone in a secure context.
 *
 * Deliberately NOT asked: `SharedArrayBuffer` or cross-origin isolation. The
 * runtime is single-threaded, so the detector runs where the previous engine's
 * predicate refused to — iOS, which implements no `credentialless` COEP, and
 * the native shells, whose WebViews are never isolated (measured, ADR-136,
 * ADR-246). That predicate is what lost the wake word there, not the engine.
 */
export function isWakeWordSupported(): boolean {
  if (typeof window === 'undefined') return false;
  return (
    typeof Worker === 'function' &&
    typeof WebAssembly === 'object' &&
    typeof AudioContext === 'function' &&
    typeof AudioWorkletNode === 'function' &&
    typeof crypto?.subtle?.digest === 'function' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function'
  );
}
