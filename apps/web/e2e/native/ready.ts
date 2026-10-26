/** Wait for infrastructure readiness, without retrying an admission or write. */
import type { FullConfig } from '@playwright/test';

export default async function ready(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL;
  if (typeof baseURL !== 'string') throw new Error('Missing owned proof URL');
  const url = new URL('/api/v1/world-proof/me', baseURL);
  const deadline = Date.now() + 45000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(2000), redirect: 'error' });
      await response.arrayBuffer();
      if (response.status === 401) return;
    } catch {
      /* The owned server is still starting; no business call is made. */
    }
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error('Owned world proof did not become ready');
}
