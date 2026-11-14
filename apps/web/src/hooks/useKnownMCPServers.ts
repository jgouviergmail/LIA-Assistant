'use client';

import { useContext, useMemo } from 'react';

import { useApiQuery } from '@/hooks/useApiQuery';
import { AppConfigSeedContext } from '@/hooks/useAppConfig';
import { capabilityAvailable } from '@/lib/capability-availability';
import { knownMCPServerListSchema, type KnownMCPServer } from '@/lib/mcp-known-servers';

const ENDPOINT = '/mcp/servers/known';
const NONE: KnownMCPServer[] = [];

export interface KnownMCPServers {
  servers: KnownMCPServer[];
  loading: boolean;
  /** The instance's OAuth callback, declared in an application the person brings. */
  oauthRedirectUri: string | null;
}

/**
 * The known MCP servers, for the gallery and the create form.
 *
 * The catalogue is served by the personal servers' router, which refuses every
 * route under the operator's switch (ADR-280): it is asked only where the
 * layout's read of `/config` says the servers are offered. A read that fails,
 * or a body this bundle cannot read, is an empty catalogue — the settings then
 * offer no gallery, and the form is the one it always was, an address to type.
 */
export function useKnownMCPServers(): KnownMCPServers {
  const offered = capabilityAvailable(useContext(AppConfigSeedContext), 'mcp');
  const { data, loading } = useApiQuery<unknown>(ENDPOINT, {
    componentName: 'KnownMCPServers',
    enabled: offered,
  });
  const parsed = useMemo(() => knownMCPServerListSchema.safeParse(data), [data]);
  // A read that is not asked is never « loading »: `useApiQuery` answers so itself.
  return {
    servers: parsed.success ? parsed.data.servers : NONE,
    loading,
    oauthRedirectUri: (parsed.success && parsed.data.oauth_redirect_uri) || null,
  };
}
