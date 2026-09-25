/**
 * image-share — which attachment a card shows, and whether connections exist.
 */

import { describe, expect, it } from 'vitest';

import type { AppConfig } from '@/hooks/useAppConfig';
import { attachmentIdFromUrl, peersAvailable } from '../image-share';

const ID = '0b0e3c3a-6f1d-4c2e-9a51-3d2f1e0c9b8a';

function config(over: Partial<AppConfig>): AppConfig {
  return { features: {}, ...over } as AppConfig;
}

describe('attachmentIdFromUrl', () => {
  it.each([
    `/api/v1/attachments/${ID}`,
    `https://api.example.org/api/v1/attachments/${ID}`,
    `/api/v1/attachments/${ID}?download=1`,
    `/api/v1/attachments/${ID.toUpperCase()}`,
  ])('reads the id of our attachment: %s', url => {
    expect(attachmentIdFromUrl(url)?.toLowerCase()).toBe(ID);
  });

  it.each([
    'https://upload.wikimedia.org/some.png',
    '/api/v1/attachments/not-a-uuid',
    `/api/v1/connectors/photo/${ID}`,
    `/api/v1/attachments/${ID}extra`,
  ])('refuses anything else: %s', url => {
    expect(attachmentIdFromUrl(url)).toBeNull();
  });
});

describe('peersAvailable', () => {
  it('follows the effective capability when the API publishes it', () => {
    expect(
      peersAvailable(
        config({
          features: { peers_enabled: true } as AppConfig['features'],
          capabilities: { peers: { enabled: false, family: 'social' } },
        })
      )
    ).toBe(false);
  });

  it('falls back to the deployment flag on an older API', () => {
    expect(
      peersAvailable(config({ features: { peers_enabled: true } as AppConfig['features'] }))
    ).toBe(true);
    expect(peersAvailable(null)).toBe(false);
  });
});
