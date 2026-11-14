/**
 * Whether the knowledge spaces are offered now: the operator's switch when the
 * configuration carries it, the deployment ceiling otherwise.
 */
import { describe, expect, it } from 'vitest';

import { ragSpacesAvailable } from '@/lib/rag-spaces/availability';

describe('ragSpacesAvailable', () => {
  it('follows the operator when the capability map carries the spaces', () => {
    expect(
      ragSpacesAvailable({
        features: { rag_spaces_enabled: true },
        capabilities: { rag_spaces: { enabled: false, family: 'knowledge' } },
      })
    ).toBe(false);
    expect(
      ragSpacesAvailable({
        features: {},
        capabilities: { rag_spaces: { enabled: true, family: 'knowledge' } },
      })
    ).toBe(true);
  });

  it('falls back to the deployment ceiling for an API that publishes no map', () => {
    expect(ragSpacesAvailable({ features: { rag_spaces_enabled: true } })).toBe(true);
    expect(ragSpacesAvailable({ features: { rag_spaces_enabled: true }, capabilities: {} })).toBe(
      true
    );
    expect(ragSpacesAvailable({ features: {} })).toBe(false);
  });

  it('offers nothing before the configuration answers', () => {
    expect(ragSpacesAvailable(null)).toBe(false);
    expect(ragSpacesAvailable(undefined)).toBe(false);
  });
});
