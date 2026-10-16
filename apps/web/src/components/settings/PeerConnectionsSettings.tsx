'use client';

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

import { useRef, useState } from 'react';
import { Eye, Handshake, Inbox, Radar, ShieldOff, UserSearch } from 'lucide-react';
import { toast } from 'sonner';

import { Card } from '@/components/ui/card';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Disclosure } from '@/components/ui/disclosure';
import { PeerAccessLogBlock } from '@/components/settings/peers/PeerAccessLogBlock';
import { PeerBlocksBlock } from '@/components/settings/peers/PeerBlocksBlock';
import { PeerConnectionCard } from '@/components/settings/peers/PeerConnectionCard';
import { PeerDiscoveryBlock } from '@/components/settings/peers/PeerDiscoveryBlock';
import { PeerVisibilityCard } from '@/components/settings/peers/PeerVisibilityCard';
import { PeerRequestsBlock } from '@/components/settings/peers/PeerRequestsBlock';
import { toastPeersError } from '@/components/settings/peers/peers-error-messages';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import type { DiscoveryMatch, PeerActionResult } from '@/hooks/usePeerConnections';
import { usePeerConnections } from '@/hooks/usePeerConnections';
import { useTranslation } from '@/i18n/client';
import type { BaseSettingsProps } from '@/types/settings';

export function PeerConnectionsSettings(props: BaseSettingsProps) {
  const { user } = useAuth();
  return <OwnedPeerConnectionsSettings key={user?.id ?? 'anonymous'} {...props} />;
}

function OwnedPeerConnectionsSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const [retrying, setRetrying] = useState(false);
  const retryLock = useRef(false);
  const requestsSummary = useRef<HTMLElement>(null);
  const blocksSummary = useRef<HTMLElement>(null);
  const connectionsHeading = useRef<HTMLHeadingElement>(null);
  // Instance-flag self-gating (OpenLoopsSection precedent): flag off → no
  // section AND no queries (the /peers router is not even mounted then).
  const { config } = useAppConfig();
  const flagOn = Boolean(config?.features.peers_enabled);
  const {
    discoveryEnabled,
    emailVisible,
    requests,
    connections,
    blocks,
    accessLog,
    loading,
    error,
    hasCompleteData,
    refetchAll,
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
    if (!isCurrent()) return false;
    if (result.ok) {
      toast.success(t(successKey));
    } else {
      toastPeersError(t, result.errorCode);
    }
    return result.ok;
  };

  const handleSearch = async (query: string): Promise<DiscoveryMatch[] | undefined> => {
    const result = await search(query);
    if (!isCurrent()) return undefined;
    if (result.matches === null) {
      toastPeersError(t, result.errorCode);
      return undefined;
    }
    return result.matches;
  };

  const retry = async () => {
    if (!isCurrent() || retryLock.current) return;
    retryLock.current = true;
    setRetrying(true);
    try {
      await refetchAll();
      if (isCurrent()) document.getElementById('settings-section-peer-connections')?.focus();
    } catch {
      // Query errors stay visible in the section; a retry rejection is already represented there.
    } finally {
      retryLock.current = false;
      if (isCurrent()) setRetrying(false);
    }
  };

  if (!flagOn) return null;

  // `initialLoading`, never `loading`: every mutation refetches, and swapping
  // this subtree for a spinner then would unmount the discovery block under a
  // user mid-search — losing their typed query, their results and their
  // keyboard focus. Refreshes are announced with aria-busy instead.
  const commandClass =
    'rounded-[var(--lia-radius-lg)] border border-border/60 px-4 [&>summary]:min-h-11';
  const content =
    (error || retrying) && !hasCompleteData ? null : initialLoading ? (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-36 w-full" />
        <Skeleton className="h-52 w-full" />
        <Skeleton className="h-28 w-full" />
      </div>
    ) : (
      <div className="space-y-5" aria-busy={loading}>
        <div className="space-y-3">
          <Disclosure
            surface="nested"
            icon={Radar}
            title={t('settings.peers.visibility_title')}
            className={commandClass}
          >
            <PeerVisibilityCard
              lng={lng}
              fullName={user?.full_name ?? null}
              discoveryEnabled={Boolean(discoveryEnabled)}
              emailVisible={Boolean(emailVisible)}
              mutating={mutating}
              onSetDiscovery={value =>
                void settle(setDiscovery(value), 'settings.peers.discovery.toggle_saved')
              }
              onSetEmailVisible={value =>
                void settle(setEmailVisible(value), 'settings.peers.email_visibility.toggle_saved')
              }
            />
          </Disclosure>
          <Disclosure
            surface="nested"
            icon={ShieldOff}
            title={t('settings.peers.blocks.title')}
            summaryRef={blocksSummary}
            badge={blocks.length}
            badgeClassName="bg-primary/10 text-primary"
            className={commandClass}
          >
            <p className="mb-4 text-sm text-muted-foreground">{t('settings.peers.blocks.hint')}</p>
            <PeerBlocksBlock
              lng={lng}
              blocks={blocks}
              mutating={mutating}
              onUnblock={peerId => settle(unblock(peerId), 'settings.peers.blocks.unblocked')}
              onResolved={() => blocksSummary.current?.focus()}
            />
          </Disclosure>
          <Disclosure
            surface="nested"
            icon={Eye}
            title={t('settings.peers.access_log.title')}
            badge={accessLog.length}
            badgeClassName="bg-primary/10 text-primary"
            className={commandClass}
          >
            <p className="mb-4 text-sm text-muted-foreground">
              {t('settings.peers.access_log.hint')}
            </p>
            <PeerAccessLogBlock lng={lng} entries={accessLog} />
          </Disclosure>
        </div>

        <Card
          surface="nested"
          variant="flat"
          role="region"
          className="space-y-4 border-border/60 p-4 sm:p-5"
          aria-labelledby="peers-search-title"
        >
          <h4 id="peers-search-title" className="flex items-center gap-2 font-semibold">
            <UserSearch className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
            {t('settings.peers.discovery.title')}
          </h4>
          <PeerDiscoveryBlock
            lng={lng}
            mutating={mutating}
            search={handleSearch}
            onSendRequest={(peerId, contextMessage) =>
              settle(sendRequest(peerId, contextMessage), 'settings.peers.discovery.request_sent')
            }
          />
        </Card>

        <Disclosure
          surface="nested"
          icon={Inbox}
          title={t('settings.peers.requests.title')}
          summaryRef={requestsSummary}
          titleClassName="whitespace-normal break-words"
          badge={requests.length}
          badgeClassName="bg-primary/10 text-primary"
          className="rounded-2xl border-border/60 px-4 [&>summary]:min-h-12 sm:px-5"
        >
          <PeerRequestsBlock
            lng={lng}
            requests={requests}
            mutating={mutating}
            onResolved={() => requestsSummary.current?.focus()}
            onRespond={(connectionId, accept) =>
              settle(
                respond(connectionId, accept),
                accept ? 'settings.peers.requests.accepted' : 'settings.peers.requests.declined'
              )
            }
            onBlock={peerId => settle(block(peerId), 'settings.peers.blocks.blocked')}
          />
        </Disclosure>

        <Card
          surface="nested"
          variant="flat"
          role="region"
          className="space-y-3 border-border/60 p-4 sm:p-5"
          aria-labelledby="peers-connections-title"
        >
          <h4
            ref={connectionsHeading}
            tabIndex={-1}
            id="peers-connections-title"
            className="flex items-center gap-2 font-semibold"
          >
            <Handshake className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
            <span className="min-w-0 flex-1">{t('settings.peers.connections.title')}</span>
            <Badge variant={connections.length ? 'default' : 'secondary'} className="tabular-nums">
              {connections.length}
            </Badge>
          </h4>
          {connections.length === 0 ? (
            <EmptyState description={t('settings.peers.connections.empty')} />
          ) : (
            <ul className="space-y-3">
              {connections.map(connection => (
                <li key={connection.id}>
                  <PeerConnectionCard
                    lng={lng}
                    connection={connection}
                    mutating={mutating}
                    onResolved={() => connectionsHeading.current?.focus()}
                    onSetShare={(connectionId, domain, level) =>
                      settle(setShare(connectionId, domain, level), 'settings.peers.shares.saved')
                    }
                    onRemove={connectionId =>
                      settle(removeConnection(connectionId), 'settings.peers.connections.removed')
                    }
                    onBlock={peerId => settle(block(peerId), 'settings.peers.blocks.blocked')}
                  />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    );

  return (
    <SettingsSection
      value="peer-connections"
      title={t('settings.peers.title')}
      description={t('settings.peers.description')}
      icon={Handshake}
    >
      {(error || retrying) && (
        <Alert variant="error" className="mb-5">
          <div className="space-y-3" aria-busy={retrying}>
            <p>{t('settings.peers.load_error')}</p>
            <Button
              type="button"
              variant="outline"
              aria-disabled={retrying}
              onClick={() => void retry()}
            >
              {t('common.retry')}
            </Button>
          </div>
        </Alert>
      )}
      {content}
    </SettingsSection>
  );
}
