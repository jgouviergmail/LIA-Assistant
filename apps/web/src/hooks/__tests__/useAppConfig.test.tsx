/**
 * The instance configuration a component starts from: the dashboard layout's
 * last read when there is one (a page mounted by a navigation renders at once —
 * the home page's radio card no longer lands a round trip late and pushes « My
 * dashboard » down), and its own read either way, so nothing turns staler than
 * before.
 */
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { AppConfig } from '../useAppConfig';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn() } }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { AppConfigSeedContext, useAppConfig } from '../useAppConfig';

function config(radio: boolean): AppConfig {
  return {
    sse: { heartbeat_interval_seconds: 30 },
    rate_limits: { enabled: false, per_minute: 60, burst: 10 },
    i18n: { supported_languages: ['fr'], default_language: 'fr' },
    features: {
      tool_approval_enabled: true,
      attachments_enabled: false,
      rag_spaces_enabled: false,
      rag_spaces_embedding_model: 'models/x',
      journals_enabled: false,
      radio_enabled: radio,
    },
    api_version: 'v1',
  };
}

beforeEach(() => {
  api.get.mockReset();
});

describe('useAppConfig', () => {
  it('starts from nothing where no layout read the configuration', async () => {
    api.get.mockResolvedValue(config(true));
    const { result } = renderHook(() => useAppConfig());
    expect(result.current.config).toBeNull();
    await waitFor(() => expect(result.current.config?.features.radio_enabled).toBe(true));
  });

  it('starts from the layout’s last read, and still reads its own', async () => {
    const seed = config(false);
    const fresh = config(true);
    api.get.mockResolvedValue(fresh);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <AppConfigSeedContext.Provider value={seed}>{children}</AppConfigSeedContext.Provider>
    );
    const { result } = renderHook(() => useAppConfig(), { wrapper });
    expect(result.current.config).toBe(seed); // the first render already has it
    await waitFor(() => expect(result.current.config).toBe(fresh));
    expect(api.get).toHaveBeenCalledWith('/config', expect.anything());
  });
});
