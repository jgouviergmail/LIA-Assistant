/** Release the browser context only when its canvas is permanently detached. */
export interface NativeContextRelease {
  getExtension(name: 'WEBGL_lose_context'): { loseContext(): void } | null;
}
export function releaseNativeContext(context: NativeContextRelease | null) {
  try {
    context?.getExtension('WEBGL_lose_context')?.loseContext();
  } catch {
    return;
  }
}
