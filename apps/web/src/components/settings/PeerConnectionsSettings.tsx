'use client';

import { useState } from 'react';

/**
 * PeerConnectionsSettings — the « Connexions » section shell (peers program).
 *
 * Composes the discovery, requests, connections, blocks and transparency
 * blocks around the discovery master toggle. Every action resolves to a
 * `PeerActionResult`; success toasts a localized confirmation, failure maps
 * the backend `peers_*` code through `toastPeersError` (never a raw code on
 * screen). The section itself is only mounted when the instance flag
 * `features.peers_enabled` is on (page-level gating, OpenLoopsSection
 * precedent).
 */

import { Check, Copy, Users } from 'lucide-react';
import { toast } from 'sonner';

import { Label } from '@/components/ui/label';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { PeerAccessLogBlock } from '@/components/settings/peers/PeerAccessLogBlock';
import { PeerBlocksBlock } from '@/components/settings/peers/PeerBlocksBlock';
import { PeerConnectionCard } from '@/components/settings/peers/PeerConnectionCard';
import { PeerDiscoveryBlock } from '@/components/settings/peers/PeerDiscoveryBlock';
import { PeerRequestsBlock } from '@/components/settings/peers/PeerRequestsBlock';
import { toastPeersError } from '@/components/settings/peers/peers-error-messages';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import type { DiscoveryMatch, PeerActionResult } from '@/hooks/usePeerConnections';
import { usePeerConnections } from '@/hooks/usePeerConnections';
import { useTranslation } from '@/i18n/client';
import type { BaseSettingsProps } from '@/types/settings';

export function PeerConnectionsSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const [nameCopied, setNameCopied] = useState(false);
  // Instance-flag self-gating (OpenLoopsSection precedent): flag off → no
  // section AND no queries (the /peers router is not even mounted then).
  const { config } = useAppConfig();
  const flagOn = !!config?.features?.peers_enabled;
  const {
    discoveryEnabled,
    emailVisible,
    requests,
    connections,
    blocks,
    accessLog,
    loading,
    initialLoading,
    mutating,
    setDiscovery,
    setEmailVisible,
    search,
    sendRequest,
    respond,
    removeConnection,
    setShare,
    block,
    unblock,
  } = usePeerConnections(flagOn);

  /** Toast the outcome; returns plain ok for the child components. */
  const settle = async (
    action: Promise<PeerActionResult>,
    successKey: string
  ): Promise<boolean> => {
    const result = await action;
    if (result.ok) {
      toast.success(t(successKey));
    } else {
      toastPeersError(t, result.errorCode);
    }
    return result.ok;
  };

  const handleSearch = async (query: string): Promise<DiscoveryMatch[] | undefined> => {
    const result = await search(query);
    if (result.matches === null) {
      toastPeersError(t, result.errorCode);
      return undefined;
    }
    return result.matches;
  };

  if (!flagOn) return null;

  // `initialLoading`, never `loading`: every mutation refetches, and swapping
  // this subtree for a spinner then would unmount the discovery block under a
  // user mid-search — losing their typed query, their results and their
  // keyboard focus. Refreshes are announced with aria-busy instead.
  const content = initialLoading ? (
    <div className="flex justify-center py-6">
      <LoadingSpinner />
    </div>
  ) : (
    <div className="space-y-6" aria-busy={loading}>
      <div className="flex items-center justify-between gap-2">
        <div className="space-y-0.5">
          <Label htmlFor="peers-discovery-enabled" className="text-sm font-medium">
            {t('settings.peers.discovery.toggle_label')}
          </Label>
          <p className="text-xs text-muted-foreground">
            {t('settings.peers.discovery.toggle_hint')}
          </p>
        </div>
        {/* `aria-disabled`, not `disabled`: a control disabled while it is
            focused is blurred by the browser and leaves the tab order, so a
            keyboard user who toggles this switch is thrown back to the top of
            the document. The state is still announced, and the guard below —
            not the attribute — is what actually prevents a double submit. */}
        <Switch
          id="peers-discovery-enabled"
          checked={discoveryEnabled ?? false}
          aria-disabled={mutating}
          className={mutating ? 'cursor-not-allowed opacity-50' : undefined}
          onCheckedChange={value => {
            if (mutating) return;
            void settle(setDiscovery(value), 'settings.peers.discovery.toggle_saved');
          }}
        />
      </div>

      {/* Lot 7: users could not SEE their own name — the identity peers
          search for. Shown at the point of need, with one-click copy; empty
          name = undiscoverable, said plainly. */}
      <div className="rounded-md border border-border/40 bg-muted/40 px-3 py-2 text-sm">
        {user?.full_name ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">{t('settings.peers.my_name.label')}</span>
            <span className="font-medium">{user.full_name}</span>
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard.writeText(user.full_name ?? '');
                setNameCopied(true);
                setTimeout(() => setNameCopied(false), 2000);
              }}
              aria-label={t('settings.peers.my_name.copy')}
              className="p-1 rounded-md border border-border/30 bg-background/80 hover:bg-background transition-colors"
            >
              {nameCopied ? (
                <Check className="h-3.5 w-3.5 text-green-600" />
              ) : (
                <Copy className="h-3.5 w-3.5 text-muted-foreground" />
              )}
            </button>
            <span className="w-full text-xs text-muted-foreground">
              {t('settings.peers.my_name.hint')}
            </span>
          </div>
        ) : (
          <p className="text-muted-foreground">{t('settings.peers.my_name.missing')}</p>
        )}
      </div>

      {/* ADR-189: a SECOND, independent consent. Being findable and handing
          your address over are different decisions — and this one only ever
          reaches people you already accepted. Same aria-disabled treatment as
          the switch above: disabling a focused control loses the keyboard. */}
      <div className="flex items-center justify-between gap-2">
        <div className="space-y-0.5">
          <Label htmlFor="peers-email-visible" className="text-sm font-medium">
            {t('settings.peers.email_visibility.toggle_label')}
          </Label>
          <p className="text-xs text-muted-foreground">
            {t('settings.peers.email_visibility.toggle_hint')}
          </p>
        </div>
        <Switch
          id="peers-email-visible"
          checked={emailVisible ?? false}
          aria-disabled={mutating}
          className={mutating ? 'cursor-not-allowed opacity-50' : undefined}
          onCheckedChange={value => {
            if (mutating) return;
            void settle(setEmailVisible(value), 'settings.peers.email_visibility.toggle_saved');
          }}
        />
      </div>

      <Separator />

      <PeerDiscoveryBlock
        lng={lng}
        mutating={mutating}
        search={handleSearch}
        onSendRequest={(peerId, contextMessage) =>
          settle(sendRequest(peerId, contextMessage), 'settings.peers.discovery.request_sent')
        }
      />

      <Separator />

      <PeerRequestsBlock
        lng={lng}
        requests={requests}
        mutating={mutating}
        onRespond={(connectionId, accept) =>
          settle(
            respond(connectionId, accept),
            accept ? 'settings.peers.requests.accepted' : 'settings.peers.requests.declined'
          )
        }
        onBlock={peerId => settle(block(peerId), 'settings.peers.blocks.blocked')}
      />

      <Separator />

      <div className="space-y-2">
        <h4 className="text-sm font-medium">{t('settings.peers.connections.title')}</h4>
        {connections.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t('settings.peers.connections.empty')}
          </p>
        ) : (
          <div className="space-y-3">
            {connections.map(connection => (
              <PeerConnectionCard
                key={connection.id}
                lng={lng}
                connection={connection}
                mutating={mutating}
                onSetShare={(connectionId, domain, level) =>
                  settle(setShare(connectionId, domain, level), 'settings.peers.shares.saved')
                }
                onRemove={connectionId =>
                  settle(removeConnection(connectionId), 'settings.peers.connections.removed')
                }
                onBlock={peerId => settle(block(peerId), 'settings.peers.blocks.blocked')}
              />
            ))}
          </div>
        )}
      </div>

      <Separator />

      <PeerBlocksBlock
        lng={lng}
        blocks={blocks}
        mutating={mutating}
        onUnblock={peerId => settle(unblock(peerId), 'settings.peers.blocks.unblocked')}
      />

      <Separator />

      <PeerAccessLogBlock lng={lng} entries={accessLog} />
    </div>
  );

  return (
    <SettingsSection
      value="peer-connections"
      title={t('settings.peers.title')}
      description={t('settings.peers.description')}
      icon={Users}
      collapsible={collapsible}
    >
      {content}
    </SettingsSection>
  );
}
