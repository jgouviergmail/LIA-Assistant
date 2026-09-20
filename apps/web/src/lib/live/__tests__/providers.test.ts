/**
 * The live provider rows: the brand a provider id shows, and the ONE
 * predicate that says whether a stored connector type belongs to the live
 * category — read by the connectors section to declare a live disconnect
 * to the header's voice menu, and by the group that draws the category.
 */
import { describe, expect, it } from 'vitest';

import { LIVE_PROVIDERS, isLiveConnectorType, liveProviderLabel } from '../providers';

describe('live providers', () => {
  it('names the brand of a known provider and echoes an unknown id', () => {
    expect(liveProviderLabel('gemini')).toBe('Gemini');
    expect(liveProviderLabel('nope')).toBe('nope');
  });

  it('recognises every live connector type, whatever its case, and nothing else', () => {
    for (const provider of LIVE_PROVIDERS) {
      expect(isLiveConnectorType(provider.connectorType)).toBe(true);
      expect(isLiveConnectorType(provider.connectorType.toUpperCase())).toBe(true);
    }
    expect(isLiveConnectorType('gmail')).toBe(false);
    expect(isLiveConnectorType('elevenlabs_telephony')).toBe(false);
  });
});
