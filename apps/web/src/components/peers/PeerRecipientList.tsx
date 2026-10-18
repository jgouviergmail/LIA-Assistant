'use client';

import { useTranslation } from 'react-i18next';
import { Loader2, Users } from 'lucide-react';
import { connectionsSettingsPath } from '@/lib/peers/recipients';

interface RecipientListProps {
  loading: boolean;
  failed: boolean;
  recipients: { id: string; peer_display_name: string }[];
  groupName: string;
  selected: string | null;
  onSelect: (connectionId: string) => void;
}

/** The accepted connections as a native radio group — arrows move, Space picks. */
export function PeerRecipientList({
  loading,
  failed,
  recipients,
  groupName,
  selected,
  onSelect,
}: RecipientListProps) {
  const { t } = useTranslation();
  if (loading && recipients.length === 0) {
    return (
      <div className="flex items-center gap-2 py-3 text-sm text-foreground/80" role="status">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        {t('settings.peers.recipients.loading')}
      </div>
    );
  }
  if (failed && recipients.length === 0) {
    return (
      <p className="py-3 text-sm text-destructive" role="alert">
        {t('settings.peers.recipients.load_error')}
      </p>
    );
  }
  if (recipients.length === 0) {
    return (
      <p className="flex items-start gap-2 py-3 text-sm text-foreground/80">
        <Users className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        {t('settings.peers.recipients.no_connection', {
          path: connectionsSettingsPath(t),
        })}
      </p>
    );
  }
  return (
    <ul className="max-h-56 divide-y overflow-y-auto rounded-md border">
      {recipients.map(peer => {
        const inputId = `${groupName}-${peer.id}`;
        return (
          <li key={peer.id}>
            <label
              htmlFor={inputId}
              className="flex min-h-11 cursor-pointer items-center gap-3 px-3 py-2 text-sm transition-colors hover:bg-accent/50"
            >
              <input
                id={inputId}
                type="radio"
                name={groupName}
                aria-labelledby={`${inputId}-name`}
                value={peer.id}
                checked={selected === peer.id}
                onChange={() => onSelect(peer.id)}
                className="h-4 w-4 accent-primary"
              />
              <span id={`${inputId}-name`} className="min-w-0 flex-1 truncate">
                {peer.peer_display_name}
              </span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}
