/**
 * Sharing a capability with a connection is offered where connections are.
 *
 * It read the deployment flag: once the operator had switched the connections
 * off, the share was still offered and its routes refused it.
 */
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  mounted: true,
  capabilities: undefined as Record<string, { enabled: boolean; family: string }> | undefined,
}));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({
    config: { features: { peers_enabled: h.mounted }, capabilities: h.capabilities },
  }),
}));
vi.mock('@/hooks/useApplicationAccountState', () => ({
  useApplicationAccountState: () => [null, vi.fn()],
}));

import { useCapabilitySharing } from '@/hooks/useCapabilitySharing';

beforeEach(() => {
  h.mounted = true;
  h.capabilities = undefined;
});

describe('useCapabilitySharing', () => {
  it('is offered where the deployment mounts the connections', () => {
    expect(renderHook(() => useCapabilitySharing('u1')).result.current.enabled).toBe(true);
    h.mounted = false;
    expect(renderHook(() => useCapabilitySharing('u1')).result.current.enabled).toBe(false);
  });

  it('is withdrawn once the operator switched the connections off', () => {
    h.capabilities = { peers: { enabled: false, family: 'people' } };

    expect(renderHook(() => useCapabilitySharing('u1')).result.current.enabled).toBe(false);
  });
});
