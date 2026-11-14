'use client';

import type { TFunction } from 'i18next';

import { useKnownMCPServers } from '@/hooks/useKnownMCPServers';
import { knownServerOf, knownServerScheme } from '@/lib/mcp-known-servers';
import type { MCPServerFormState } from '@/lib/mcp-server-form';

import { MCPKnownServerIcon } from './MCPKnownServerIcon';

interface Props {
  form: MCPServerFormState;
  t: TFunction;
}

/**
 * What a create form opened from a known server is about: the vendor, what it
 * is for, and what the person does next — type their key or token, or save and
 * sign in at the vendor, with their own OAuth application where the vendor
 * registers none (its callback is this instance's, published with the
 * catalogue).
 *
 * It holds no state: the known server is READ off the form (the address it
 * holds), so an address edited by hand is no known server any more, and the
 * chat's private form, opened already filled, shows the same notice. With no
 * catalogue, or an address the catalogue does not hold, it is not drawn.
 */
export function MCPKnownServerNotice({ form, t }: Props) {
  const { servers, oauthRedirectUri } = useKnownMCPServers();
  const server = knownServerOf(form, servers);
  if (!server) return null;
  const scheme = knownServerScheme(server);
  return (
    <div className="flex gap-3 rounded-lg border bg-background p-3">
      <MCPKnownServerIcon server={server} />
      <div className="min-w-0 space-y-1 text-xs text-muted-foreground">
        <p className="text-sm font-medium text-foreground">{server.name}</p>
        <p>{t(`settings.mcp.known.servers.${server.key}`, { defaultValue: '' })}</p>
        <p>{t(`settings.mcp.known.next.${scheme}`, { name: server.name })}</p>
        {scheme === 'oauth2_own' && oauthRedirectUri && (
          <p>
            {t('settings.mcp.known.callback', { name: server.name })}{' '}
            <code className="break-all rounded bg-muted px-1 py-0.5 text-foreground">
              {oauthRedirectUri}
            </code>
          </p>
        )}
      </div>
    </div>
  );
}
