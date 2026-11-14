'use client';

import { useId, type ComponentType, type SVGProps } from 'react';
import type { TFunction } from 'i18next';

import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Globe, Key, LayoutGrid, LogIn, Ticket } from '@/lib/icons';
import {
  knownServerScheme,
  type KnownMCPServer,
  type KnownServerScheme,
} from '@/lib/mcp-known-servers';
import { cn } from '@/lib/utils';

import { MCPKnownServerIcon } from './MCPKnownServerIcon';

/** How a scheme is drawn beside its words on a tile. */
const SCHEME_ICONS: Record<KnownServerScheme, ComponentType<SVGProps<SVGSVGElement>>> = {
  none: Globe,
  oauth2: LogIn,
  oauth2_own: LogIn,
  api_key: Key,
  bearer: Ticket,
};

interface Props {
  servers: readonly KnownMCPServer[];
  loading: boolean;
  /** Keys of the known servers the person already has (matched by address). */
  installed: ReadonlySet<string>;
  /** Opens the create form, prefilled with the server picked. */
  onPick: (server: KnownMCPServer) => void;
  onClose: () => void;
  t: TFunction;
}

/**
 * One known server: its icon, its name, how one signs in, what it is for.
 *
 * A native button named by the server's name and described by the rest. A
 * server the person already has is greyed and badged « Installed »; it stays in
 * the tab order, `aria-disabled` and guarded in its handler, so the reason it
 * cannot be picked is read where the focus lands.
 */
function KnownServerTile({
  server,
  installed,
  onPick,
  t,
}: {
  server: KnownMCPServer;
  installed: boolean;
  onPick: (server: KnownMCPServer) => void;
  t: TFunction;
}) {
  const id = useId();
  const scheme = knownServerScheme(server);
  const SchemeIcon = SCHEME_ICONS[scheme];
  const greyed = installed && 'opacity-60 grayscale';
  return (
    <li className="h-full">
      <button
        type="button"
        aria-labelledby={`${id}-name`}
        aria-describedby={`${installed ? `${id}-installed ` : ''}${id}-scheme ${id}-about`}
        aria-disabled={installed || undefined}
        onClick={() => {
          if (!installed) onPick(server);
        }}
        className={cn(
          'flex h-full w-full flex-col gap-2 rounded-lg border p-3 text-left transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
          installed
            ? 'cursor-default bg-muted'
            : 'bg-card hover:border-primary/50 hover:bg-primary/5 active:scale-[0.98]'
        )}
      >
        <span className="flex w-full items-center gap-3">
          <MCPKnownServerIcon server={server} className={cn(greyed)} />
          <span className={cn('min-w-0 flex-1', greyed)}>
            <span id={`${id}-name`} className="block break-words text-sm font-medium">
              {server.name}
            </span>
            <span
              id={`${id}-scheme`}
              className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground"
            >
              <SchemeIcon className="size-3 shrink-0" aria-hidden="true" />
              {t(`settings.mcp.known.scheme.${scheme}`)}
            </span>
          </span>
          {installed && (
            <>
              <Badge variant="success" className="shrink-0 text-xs" aria-hidden="true">
                {t('settings.mcp.known.installed')}
              </Badge>
              <span id={`${id}-installed`} className="sr-only">
                {t('settings.mcp.known.installed_hint')}
              </span>
            </>
          )}
        </span>
        <span
          id={`${id}-about`}
          className={cn('line-clamp-3 text-xs text-muted-foreground', greyed)}
        >
          {t(`settings.mcp.known.servers.${server.key}`, { defaultValue: '' })}
        </span>
      </button>
    </li>
  );
}

/**
 * The known servers, one tile each, every tile the same size: a person picks a
 * server and the create form opens already filled with its name, its address
 * and how it signs in. Mount it only while open: its parent decides.
 */
export function MCPKnownServersDialog({ servers, loading, installed, onPick, onClose, t }: Props) {
  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-3xl lg:max-w-5xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <LayoutGrid className="h-5 w-5 text-primary" aria-hidden="true" />
            {t('settings.mcp.known.title')}
          </DialogTitle>
          <DialogDescription>{t('settings.mcp.known.description')}</DialogDescription>
        </DialogHeader>
        {servers.length > 0 ? (
          <ul className="grid auto-rows-fr grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {servers.map(server => (
              <KnownServerTile
                key={server.key}
                server={server}
                installed={installed.has(server.key)}
                onPick={onPick}
                t={t}
              />
            ))}
          </ul>
        ) : loading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner className="h-6 w-6" />
          </div>
        ) : (
          <p role="status" className="py-4 text-sm text-muted-foreground">
            {t('settings.mcp.known.unavailable')}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
