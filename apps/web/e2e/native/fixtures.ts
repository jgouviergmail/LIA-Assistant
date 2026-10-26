/** Every native journey gets a fresh authoritative epoch on the exact inert host. */
import { test as base, expect } from '@playwright/test';
export * from '@playwright/test';

export const test = base.extend<{ _worldEpoch: void }>({
  _worldEpoch: [
    async ({ request, baseURL }, use) => {
      if (!baseURL) throw new Error('Explicit disposable World proof URL required');
      const response = await request.post('/api/v1/world-proof/reset', {
        headers: { Origin: new URL(baseURL).origin },
      });
      expect(response.status()).toBe(204);
      await use();
    },
    { auto: true },
  ],
});
