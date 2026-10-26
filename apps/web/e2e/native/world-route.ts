/** The optimized snapshot exercises the real application entry, without dev HMR. */
export function worldProofUrl(baseURL: string, lng: string): URL {
  const optimized =
    process.env.E2E_WORLD_NATIVE_OPTIMIZED === '1' ||
    [
      '127.0.0.7',
      'lia-world-final-production',
      'lia-world-qualification-production',
      'lia-world-qualification-scroll',
    ].includes(new URL(baseURL).hostname);
  const url = new URL(`/${lng}/${optimized ? 'dashboard/world' : 'world-preview'}`, baseURL);
  if (!optimized) {
    url.searchParams.set('shared', '1');
    url.searchParams.set('resume', '1');
  }
  return url;
}
