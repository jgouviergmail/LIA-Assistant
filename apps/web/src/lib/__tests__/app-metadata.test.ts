import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildAppMetadata } from '@/lib/app-metadata';
import { mapsMetadata } from '@/lib/maps/metadata';

describe('social metadata in host-neutral builds', () => {
  afterEach(() => vi.unstubAllEnvs());

  it('does not publish localhost social images when the origin is unknown', () => {
    vi.stubEnv('APP_URL_SERVER', '');
    vi.stubEnv('NEXT_PUBLIC_APP_URL', '');

    const metadata = buildAppMetadata('fr');

    expect(metadata.metadataBase).toBeUndefined();
    expect(metadata.openGraph?.images).toBeUndefined();
    expect(metadata.twitter?.images).toBeUndefined();
    const map = mapsMetadata('fr', '/maps', 'Maps', 'Maps');
    expect(map.openGraph?.images).toBeUndefined();
    expect(map.twitter?.images).toBeUndefined();
  });

  it('publishes absolute social images when an origin is configured', () => {
    vi.stubEnv('APP_URL_SERVER', 'https://lia.example');

    const metadata = buildAppMetadata('fr');

    expect(metadata.metadataBase).toEqual(new URL('https://lia.example'));
    expect(metadata.openGraph?.images).toEqual([
      expect.objectContaining({ url: 'https://lia.example/Title.png' }),
    ]);
    expect(metadata.twitter?.images).toEqual(['https://lia.example/Title.png']);
    const map = mapsMetadata('fr', '/maps', 'Maps', 'Maps');
    expect(map.twitter?.images).toEqual(['https://lia.example/Title.png']);
  });
});
