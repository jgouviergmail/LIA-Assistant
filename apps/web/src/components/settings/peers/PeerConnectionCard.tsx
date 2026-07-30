'use client';

/**
 * PeerConnectionCard — one accepted connection (peers program, spec §10).
 *
 * Identity keeps the masked email PERMANENTLY pinned (spec §12.8 — the
 * anti-impersonation anchor). MY shares are editable: calendar as a native
 * labeled select (none/availability/details — native form controls are the
 * house preference and stay testable), task as a switch (titles). THEIR
 * shares render as read-only badges — the both-directions requirement.
 * Remove and block go through the house confirm dialog.
 */

import { UserRound } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useConfirm } from '@/components/ui/use-confirm';
import type { ConnectionView } from '@/hooks/usePeerConnections';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

export interface PeerConnectionCardProps {
  lng: Language;
  connection: ConnectionView;
  mutating: boolean;
  onSetShare: (connectionId: string, domain: string, level: string | null) => Promise<boolean>;
  onRemove: (connectionId: string) => Promise<boolean>;
  onBlock: (peerId: string) => Promise<boolean>;
}

const CALENDAR_LEVELS = ['none', 'availability', 'details'] as const;

export function PeerConnectionCard({
  lng,
  connection,
  mutating,
  onSetShare,
  onRemove,
  onBlock,
}: PeerConnectionCardProps) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();

  const calendarLevel =
    connection.my_shares.find(share => share.domain === 'calendar')?.level ?? 'none';
  const taskShared = connection.my_shares.some(share => share.domain === 'task');

  const handleCalendarChange = (value: string) => {
    void onSetShare(connection.id, 'calendar', value === 'none' ? null : value);
  };

  const handleTaskToggle = (checked: boolean) => {
    void onSetShare(connection.id, 'task', checked ? 'titles' : null);
  };

  const handleRemove = async () => {
    const accepted = await confirm({
      title: t('settings.peers.connections.remove_confirm_title'),
      description: t('settings.peers.connections.remove_confirm_description'),
    });
    if (accepted) await onRemove(connection.id);
  };

  const handleBlock = async () => {
    const accepted = await confirm({
      title: t('settings.peers.connections.block_confirm_title'),
      description: t('settings.peers.connections.block_confirm_description'),
    });
    if (accepted) await onBlock(connection.peer_id);
  };

  const calendarSelectId = `peers-share-calendar-${connection.id}`;

  return (
    <div className="space-y-3 rounded-md border p-3">
      {confirmDialog}
      <div className="flex items-center gap-2">
        <UserRound className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{connection.peer_display_name}</p>
          <p className="text-xs text-muted-foreground">{connection.peer_email_hint}</p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase text-muted-foreground">
            {t('settings.peers.shares.my_title')}
          </p>
          <div className="space-y-1">
            <Label htmlFor={calendarSelectId}>{t('settings.peers.shares.calendar_label')}</Label>
            <select
              id={calendarSelectId}
              value={calendarLevel}
              disabled={mutating}
              onChange={event => handleCalendarChange(event.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background text-foreground px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              {CALENDAR_LEVELS.map(level => (
                <option key={level} value={level}>
                  {t(`settings.peers.shares.calendar_level.${level}`)}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor={`peers-share-task-${connection.id}`}>
              {t('settings.peers.shares.task_label')}
            </Label>
            <Switch
              id={`peers-share-task-${connection.id}`}
              checked={taskShared}
              disabled={mutating}
              onCheckedChange={handleTaskToggle}
            />
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase text-muted-foreground">
            {t('settings.peers.shares.their_title')}
          </p>
          {connection.their_shares.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t('settings.peers.shares.their_empty')}
            </p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {connection.their_shares.map(share => (
                <Badge key={`${share.domain}-${share.level}`} variant="secondary">
                  {t(`settings.peers.shares.badge.${share.domain}_${share.level}`)}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 border-t pt-3">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={mutating}
          onClick={() => void handleRemove()}
        >
          {t('settings.peers.connections.remove')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={mutating}
          onClick={() => void handleBlock()}
        >
          {t('settings.peers.connections.block')}
        </Button>
      </div>
    </div>
  );
}
