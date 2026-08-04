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

import { Eye, Handshake, Radar, ShieldOff, Users, UserSearch } from 'lucide-react';
import { toast } from 'sonner';

import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { EmptyState } from '@/components/ui/empty-state';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { SettingsDisclosure } from '@/components/settings/SettingsDisclosure';
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

export function PeerConnectionsSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
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
      {/* Every zone folds (owner arbitration 2026-08-05): the section reads
          as an INDEX of five titled, icon-carrying entries, and each badge
          says whether anything waits inside without opening. */}
      <SettingsDisclosure icon={Radar} title={t('settings.peers.visibility_title')}>
        <PeerVisibilityCard
          lng={lng}
          fullName={user?.full_name ?? null}
          discoveryEnabled={discoveryEnabled ?? false}
          emailVisible={emailVisible ?? false}
          mutating={mutating}
          onSetDiscovery={value =>
            void settle(setDiscovery(value), 'settings.peers.discovery.toggle_saved')
          }
          onSetEmailVisible={value =>
            void settle(setEmailVisible(value), 'settings.peers.email_visibility.toggle_saved')
          }
        />
      </SettingsDisclosure>

      {/* "Find someone" groups the search with the requests it produces — a
          pending incoming request is exactly what the badge must surface. */}
      <SettingsDisclosure
        icon={UserSearch}
        title={t('settings.peers.discovery.title')}
        badge={requests.length > 0 ? requests.length : undefined}
      >
        <div className="space-y-4">
          <PeerDiscoveryBlock
            lng={lng}
            mutating={mutating}
            search={handleSearch}
            onSendRequest={(peerId, contextMessage) =>
              settle(sendRequest(peerId, contextMessage), 'settings.peers.discovery.request_sent')
            }
          />
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
        </div>
      </SettingsDisclosure>

      <SettingsDisclosure
        icon={Handshake}
        title={t('settings.peers.connections.title')}
        badge={connections.length > 0 ? connections.length : undefined}
      >
        {connections.length === 0 ? (
          <EmptyState description={t('settings.peers.connections.empty')} />
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
      </SettingsDisclosure>

      {/* Blocks and the access log, folded like their new neighbours. */}
      <SettingsDisclosure
        icon={ShieldOff}
        title={t('settings.peers.blocks.title')}
        description={t('settings.peers.blocks.hint')}
        badge={blocks.length > 0 ? blocks.length : undefined}
      >
        <PeerBlocksBlock
          lng={lng}
          blocks={blocks}
          mutating={mutating}
          onUnblock={peerId => settle(unblock(peerId), 'settings.peers.blocks.unblocked')}
        />
      </SettingsDisclosure>

      <SettingsDisclosure
        icon={Eye}
        title={t('settings.peers.access_log.title')}
        description={t('settings.peers.access_log.hint')}
        badge={accessLog.length > 0 ? accessLog.length : undefined}
      >
        <PeerAccessLogBlock lng={lng} entries={accessLog} />
      </SettingsDisclosure>
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
