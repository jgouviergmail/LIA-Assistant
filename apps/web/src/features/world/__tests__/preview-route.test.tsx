import { expect, it, vi } from 'vitest';
import WorldPreviewPage from '../../../app/[lng]/world-preview/page';

vi.mock('@/features/world/WorldEntry', () => ({ WorldPreviewEntry: () => null }));
vi.mock('next/navigation', async importOriginal => {
  const original = await importOriginal<typeof import('next/navigation')>();
  return { notFound: original.notFound };
});

it('refuses the account-free preview outside development before reading route parameters', async () => {
  await expect(WorldPreviewPage({ params: Promise.resolve({ lng: 'en' }) })).rejects.toThrow(
    'NEXT_HTTP_ERROR_FALLBACK;404'
  );
});
