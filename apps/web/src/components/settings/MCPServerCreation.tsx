'use client';

import { useMemo, useRef } from 'react';
import type { TFunction } from 'i18next';

import { Button } from '@/components/ui/button';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useKnownMCPServers } from '@/hooks/useKnownMCPServers';
import type { UserMCPServer } from '@/hooks/useUserMCPServers';
import { Plus } from '@/lib/icons';
import type { UserMCPDefaults } from '@/lib/mcp-behavior';
import { installedKnownKeys, type KnownMCPServer } from '@/lib/mcp-known-servers';

import { MCPKnownServersDialog } from './MCPKnownServersDialog';
import { MCPServerFormDialog, type MCPServerFormActions } from './MCPServerFormDialog';

interface Props {
  ownerId: string | undefined;
  /** The person's servers: a known server among them is shown installed. */
  servers: readonly UserMCPServer[];
  defaults: UserMCPDefaults | undefined;
  actions: MCPServerFormActions;
  t: TFunction;
}

/**
 * How a person adds a server: « Known MCPs », a gallery whose tile opens the
 * create form already filled, or « Add server », the form with an address to
 * type. Both end in the same create dialog.
 *
 * The gallery closes when its tile opens the form, so the form's opener is
 * gone: once the form closes, the focus returns to « Known MCPs ». Without a
 * catalogue (closed by the operator, unreadable), only « Add server » is drawn.
 */
export function MCPServerCreation({ ownerId, servers, defaults, actions, t }: Props) {
  const known = useKnownMCPServers();
  const installed = useMemo(
    () => installedKnownKeys(known.servers, servers),
    [known.servers, servers]
  );
  const knownButton = useRef<HTMLButtonElement>(null);
  const [galleryOpen, setGalleryOpen] = useApplicationAccountState(ownerId, false);
  // `undefined` while no form is open; `null` for a typed address; else the server picked.
  const [creating, setCreating] = useApplicationAccountState<KnownMCPServer | null | undefined>(
    ownerId,
    undefined
  );
  const offered = known.loading || known.servers.length > 0;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {offered && (
        <Button ref={knownButton} size="sm" onClick={() => setGalleryOpen(true)}>
          <Plus className="h-4 w-4 mr-1" />
          {t('settings.mcp.known.button')}
        </Button>
      )}
      <Button size="sm" onClick={() => setCreating(null)}>
        <Plus className="h-4 w-4 mr-1" />
        {t('settings.mcp.add_server')}
      </Button>
      {galleryOpen && (
        <MCPKnownServersDialog
          servers={known.servers}
          loading={known.loading}
          installed={installed}
          onPick={server => {
            setGalleryOpen(false);
            setCreating(server);
          }}
          onClose={() => setGalleryOpen(false)}
          t={t}
        />
      )}
      {creating !== undefined && (
        <CreateDialog
          known={creating}
          defaults={defaults}
          ownerId={ownerId}
          actions={actions}
          onClose={() => setCreating(undefined)}
          returnFocus={() => knownButton.current?.focus()}
          t={t}
        />
      )}
    </div>
  );
}

/** The create dialog, mounted per pick so that it starts from the server picked. */
function CreateDialog({
  known,
  returnFocus,
  ...props
}: {
  known: KnownMCPServer | null;
  defaults: UserMCPDefaults | undefined;
  ownerId: string | undefined;
  actions: MCPServerFormActions;
  onClose: () => void;
  returnFocus: () => void;
  t: TFunction;
}) {
  return (
    <MCPServerFormDialog
      key={known ? known.key : 'typed'}
      server={null}
      known={known}
      // A typed address keeps the dialog's own return, to « Add server » that opened it.
      returnFocus={known ? returnFocus : undefined}
      {...props}
    />
  );
}
