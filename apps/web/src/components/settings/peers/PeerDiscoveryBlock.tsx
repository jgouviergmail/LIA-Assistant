'use client';

/**
 * PeerDiscoveryBlock — exact search + connection request (spec §5.1, Bloc B).
 *
 * ONE box takes a full name OR an email address, and the input stays
 * `type="text"`: `type="email"` would let the browser reject a perfectly
 * valid name before the form ever submits. Which identity was typed is
 * decided server-side (`looks_like_email`) — this component holds no second
 * opinion about the same string.
 *
 * The search is EXACT either way (accent/case folded server-side for a name,
 * case folded for an address) — the hint says so, because a prefix search is
 * what users will try first. Results carry the pinned masked email (A6,
 * homonym discriminator). One optional context note applies to the next
 * request sent.
 */

import { useState } from 'react';
import { Search, UserPlus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { DiscoveryMatch } from '@/hooks/usePeerConnections';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

/** Mirror of the backend PEERS_CONTEXT_MESSAGE_MAX_CHARS constant. */
const CONTEXT_MESSAGE_MAX_CHARS = 500;

export interface PeerDiscoveryBlockProps {
  lng: Language;
  mutating: boolean;
  /** Runs the exact search; the argument is a full name OR an email address. */
  search: (query: string) => Promise<DiscoveryMatch[] | undefined>;
  onSendRequest: (peerId: string, contextMessage?: string) => Promise<boolean>;
}

export function PeerDiscoveryBlock({
  lng,
  mutating,
  search,
  onSendRequest,
}: PeerDiscoveryBlockProps) {
  const { t } = useTranslation(lng);
  const [query, setQuery] = useState('');
  const [contextMessage, setContextMessage] = useState('');
  const [results, setResults] = useState<DiscoveryMatch[] | null>(null);
  const [searching, setSearching] = useState(false);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    setSearching(true);
    try {
      const matches = await search(trimmed);
      setResults(matches ?? null);
    } finally {
      setSearching(false);
    }
  };

  const handleRequest = async (peerId: string) => {
    const note = contextMessage.trim();
    const ok = await onSendRequest(peerId, note ? note : undefined);
    if (ok) {
      // The request now lives in the outgoing list — clear the local state.
      setResults(null);
      setQuery('');
      setContextMessage('');
    }
  };

  return (
    <div className="space-y-3">
      <h4 className="flex items-center gap-2 text-sm font-medium">
        <Search className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        {t('settings.peers.discovery.title')}
      </h4>
      <form onSubmit={handleSubmit} className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="flex-1 space-y-1">
          <Label htmlFor="peers-discovery-search">
            {t('settings.peers.discovery.search_label')}
          </Label>
          <Input
            id="peers-discovery-search"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder={t('settings.peers.discovery.search_placeholder')}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <Button type="submit" disabled={searching || !query.trim()}>
          {t('settings.peers.discovery.search_button')}
        </Button>
      </form>
      <p className="text-xs text-muted-foreground">{t('settings.peers.discovery.exact_hint')}</p>

      {results !== null && results.length === 0 && (
        <p className="text-sm text-muted-foreground">{t('settings.peers.discovery.no_results')}</p>
      )}

      {results !== null && results.length > 0 && (
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="peers-discovery-context">
              {t('settings.peers.discovery.context_label')}
            </Label>
            <Textarea
              id="peers-discovery-context"
              value={contextMessage}
              onChange={event => setContextMessage(event.target.value)}
              placeholder={t('settings.peers.discovery.context_placeholder')}
              maxLength={CONTEXT_MESSAGE_MAX_CHARS}
              rows={2}
            />
          </div>
          <ul className="space-y-2">
            {results.map(match => (
              <li
                key={match.peer_id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{match.display_name}</p>
                  <p className="text-xs text-muted-foreground">{match.email_hint}</p>
                </div>
                {match.relationship !== 'none' ? (
                  <span className="rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-xs font-medium text-foreground/80">
                    {match.relationship === 'connected'
                      ? t('settings.peers.discovery.status_connected')
                      : t('settings.peers.discovery.status_pending')}
                  </span>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    disabled={mutating}
                    onClick={() => void handleRequest(match.peer_id)}
                  >
                    <UserPlus className="mr-1 h-4 w-4" aria-hidden="true" />
                    {t('settings.peers.discovery.request_button')}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
