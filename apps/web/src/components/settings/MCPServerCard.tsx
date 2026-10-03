'use client';

/**
 * One configured MCP server, as a card of the two-column settings grid.
 *
 * The list used to stack full-width rows whose actions were revealed by hover
 * (invisible to a keyboard user), whose card was a tap-anywhere handler gated
 * on `window.innerWidth`, and whose phone path was a dialog of its own — the
 * three patterns ADR-208 retired in favour of `RowActions`. The server's
 * DESCRIPTION — the text the router reads to decide when the server is worth
 * calling — was only visible inside the edit form; it now leads the card,
 * clamped to three lines with the whole text one tap away.
 *
 * The card must hold at HALF width (two columns from `md`, like the knowledge
 * spaces): the name truncates against the switch alone, the badges wrap on a
 * line of their own, the URL truncates (full text in `title`), and the row
 * actions sit in the footer where they never compete with the name.
 */

import { useEffect, useRef, useState } from 'react';
import type { TFunction } from 'i18next';
import { AlertTriangle, Pencil, Plug, Server, Trash2, Unplug, Zap } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { RowActions, type RowAction } from '@/components/ui/row-actions';
import { Switch } from '@/components/ui/switch';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { UserMCPAuthType, UserMCPServer } from '@/hooks/useUserMCPServers';
import { formatInstant } from '@/lib/format-instant';
import { lifecycleTone, type BadgeTone } from '@/lib/status-tone';

/**
 * Tone of a server's status pill.
 *
 * Being switched OFF outranks whatever the last probe reported: a disabled
 * server is inert, not healthy and not broken. Everything else comes from the
 * shared lifecycle table, so `active` and `error` look the same here as on
 * scheduled actions, Drive sources, documents and calls — they did not before
 * (`active` was blue here, green there, and `auth_required` was an outline
 * rather than the warning it is).
 */
function getStatusBadgeVariant(server: UserMCPServer): BadgeTone {
  if (!server.is_enabled) return 'secondary';
  return lifecycleTone(server.status);
}

function getStatusLabel(server: UserMCPServer, t: TFunction): string {
  if (!server.is_enabled) return t('settings.mcp.status_disabled');
  switch (server.status) {
    case 'active':
      return t('settings.mcp.status_active');
    case 'error':
      return t('settings.mcp.status_error');
    case 'auth_required':
      return t('settings.mcp.status_auth_required');
    case 'inactive':
      return t('settings.mcp.status_inactive');
    default:
      return server.status;
  }
}

function getAuthTypeLabel(authType: UserMCPAuthType, t: TFunction): string {
  switch (authType) {
    case 'none':
      return t('settings.mcp.auth_none');
    case 'api_key':
      return t('settings.mcp.auth_api_key');
    case 'bearer':
      return t('settings.mcp.auth_bearer');
    case 'oauth2':
      return t('settings.mcp.auth_oauth2');
    default:
      return authType;
  }
}

/**
 * The server's description, clamped to three lines.
 *
 * The toggle appears only when the clamp actually HIDES something — measured
 * on the rendered box (`scrollHeight > clientHeight`), re-measured when the
 * card changes width, because the same sentence fits a full-width phone card
 * and overflows a half-width desktop one. A character-count threshold would be
 * wrong at one of the two widths. `title` carries the whole text for a pointer.
 */
function ServerDescription({ text, t }: { text: string; t: TFunction }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);

  useEffect(() => {
    const element = ref.current;
    // Expanded, nothing is clipped: keep the last verdict so "show less" stays.
    if (!element || expanded || typeof ResizeObserver === 'undefined') return;
    // A ResizeObserver reports every observed element once on `observe()`, so
    // the first measurement needs no synchronous call here.
    const observer = new ResizeObserver(() => {
      setOverflows(element.scrollHeight > element.clientHeight + 1);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [text, expanded]);

  return (
    <div>
      <p
        ref={ref}
        title={text}
        className={`whitespace-pre-line break-words text-sm text-muted-foreground ${
          expanded ? '' : 'line-clamp-3'
        }`}
      >
        {text}
      </p>
      {overflows && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded(value => !value)}
          className="mt-1 text-xs font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
        >
          {expanded ? t('common.show_less') : t('common.show_more')}
        </button>
      )}
    </div>
  );
}

export interface MCPServerCardProps {
  server: UserMCPServer;
  lng: Language;
  /** True while THIS server's connection test runs. */
  testing: boolean;
  disconnecting: boolean;
  onToggle: (server: UserMCPServer) => void;
  onTest: (server: UserMCPServer) => void;
  onEdit: (server: UserMCPServer) => void;
  onDelete: (server: UserMCPServer) => void;
  onConnectOAuth: (server: UserMCPServer) => void;
  onDisconnectOAuth: (server: UserMCPServer) => void;
}

/** The OAuth call to action the server's state asks for, or nothing. */
function OAuthAction({
  server,
  t,
  disconnecting,
  onConnectOAuth,
  onDisconnectOAuth,
}: Pick<MCPServerCardProps, 'server' | 'disconnecting' | 'onConnectOAuth' | 'onDisconnectOAuth'> & {
  t: TFunction;
}) {
  if (server.auth_type !== 'oauth2') return null;
  if (server.status === 'auth_required') {
    return (
      <Button size="sm" variant="outline" onClick={() => onConnectOAuth(server)}>
        <Plug className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
        {t('settings.mcp.connect_oauth')}
      </Button>
    );
  }
  if (server.status === 'active') {
    return (
      // `aria-disabled` + guard, not `disabled`: the control holds the focus
      // the click just gave it, and `disabled` would blur it to `<body>`.
      <Button
        size="sm"
        variant="outline"
        aria-disabled={disconnecting || undefined}
        onClick={() => {
          if (!disconnecting) onDisconnectOAuth(server);
        }}
      >
        <Unplug className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
        {t('settings.mcp.disconnect_oauth')}
      </Button>
    );
  }
  return null;
}

/** Secondary facts: authentication, tool count, last connection, last error. */
function ServerFacts({ server, lng, t }: { server: UserMCPServer; lng: Language; t: TFunction }) {
  return (
    <div className="space-y-1 text-xs text-muted-foreground">
      {/* The URL has no break opportunity: truncated, whole in `title`. */}
      <p className="truncate" title={server.url}>
        {server.url}
      </p>
      <p className="flex flex-wrap gap-x-2 gap-y-0.5">
        {/* Named, never bare: « Aucune » alone said nothing about what it was. */}
        <span>
          {t('settings.mcp.field_auth_type')}
          {t('common.label_separator')}
          {getAuthTypeLabel(server.auth_type, t)}
        </span>
        {server.tool_count > 0 && (
          <span>· {t('settings.mcp.tools_count', { count: server.tool_count })}</span>
        )}
      </p>
      {server.last_connected_at && (
        <p>
          {t('settings.mcp.last_connected', {
            date: formatInstant(server.last_connected_at, lng, 'short'),
          })}
        </p>
      )}
      {server.last_error && (
        <div className="flex items-start gap-1.5 text-destructive">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
          <span className="line-clamp-2 break-words" title={server.last_error}>
            {server.last_error}
          </span>
        </div>
      )}
    </div>
  );
}

export function MCPServerCard(props: MCPServerCardProps) {
  const { server, lng, testing, onToggle, onTest, onEdit, onDelete } = props;
  const { t } = useTranslation(lng);

  const actions: RowAction[] = [
    {
      key: 'test',
      label: t('settings.mcp.test_connection'),
      icon: Zap,
      onSelect: () => onTest(server),
      loading: testing,
    },
    { key: 'edit', label: t('common.edit'), icon: Pencil, onSelect: () => onEdit(server) },
    {
      key: 'delete',
      label: t('common.delete'),
      icon: Trash2,
      tone: 'destructive',
      onSelect: () => onDelete(server),
    },
  ];

  return (
    <li className="flex h-full min-w-0 flex-col gap-3 rounded-lg border bg-card p-4">
      <div className="flex items-start gap-3">
        <div className="shrink-0 rounded-lg bg-primary/10 p-2">
          <Server className="h-4 w-4 text-primary" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1 space-y-1.5">
          <h4 className="truncate font-medium leading-8" title={server.name}>
            {server.name}
          </h4>
          <div className="flex flex-wrap gap-1.5">
            <Badge variant={getStatusBadgeVariant(server)}>{getStatusLabel(server, t)}</Badge>
            {server.plugin_id && (
              <Badge variant="outline">{t('settings.plugins.via_plugin')}</Badge>
            )}
          </div>
        </div>
        <Switch
          className="mt-1.5 shrink-0"
          checked={server.is_enabled}
          onCheckedChange={() => onToggle(server)}
          aria-label={t('settings.mcp.toggle_server', { name: server.name })}
        />
      </div>

      {server.domain_description && <ServerDescription text={server.domain_description} t={t} />}

      <ServerFacts server={server} lng={lng} t={t} />

      {/* `mt-auto`: in a grid row the footers line up whatever each card holds. */}
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t pt-3">
        <OAuthAction
          server={server}
          t={t}
          disconnecting={props.disconnecting}
          onConnectOAuth={props.onConnectOAuth}
          onDisconnectOAuth={props.onDisconnectOAuth}
        />
        <RowActions
          className="ml-auto"
          actions={actions}
          menuLabel={t('common.actions_for', { name: server.name })}
        />
      </div>
    </li>
  );
}
