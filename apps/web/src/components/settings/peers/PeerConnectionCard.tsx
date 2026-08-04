'use client';

/**
 * PeerConnectionCard — one accepted connection (peers program, spec §10).
 *
 * Identity keeps the masked email PERMANENTLY pinned (spec §12.8 — the
 * anti-impersonation anchor). The two share directions render as MIRRORED
 * bordered panels (owner arbitration 2026-08-05): mine editable — calendar
 * through the design-system Select (none/availability/details), task as a
 * switch (titles) — theirs the same icon-carrying rows in read-only, on the
 * muted wash every read-only surface wears. Remove and block go through the
 * house confirm dialog.
 */

import { ArrowDownLeft, ArrowUpRight, Calendar, ListTodo } from 'lucide-react';

import { Avatar } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
  const theirCalendarLevel =
    connection.their_shares.find(share => share.domain === 'calendar')?.level ?? 'none';
  const theirTaskShared = connection.their_shares.some(share => share.domain === 'task');

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
      <div className="flex items-center gap-3">
        {/* The app's own avatar, as everywhere a person is named: initials on
            a colour hashed from the name, so two connections are told apart at
            a glance rather than by reading. NO `src` on purpose — a peer's
            profile picture is not published by this domain, and exposing one
            would add a personal datum to a surface whose whole design keeps
            the other side unobservable. */}
        <Avatar
          name={connection.peer_display_name}
          size="sm"
          variant="circular"
          disableHover
          className="shrink-0"
        />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{connection.peer_display_name}</p>
          {/* The real address when its owner opened it to their connections
              (ADR-189), the masked hint otherwise — never both, which would
              read as two different pieces of information about one person.
              `break-all`: an address has no spaces to wrap on. */}
          <p className="break-all text-xs text-muted-foreground">
            {connection.peer_email ?? connection.peer_email_hint}
          </p>
        </div>
      </div>

      {/* Both directions read the SAME way (owner arbitration 2026-08-05):
          the same two icon-carrying rows on each side — mine editable, theirs
          the read-only values. The old badge soup made the two columns look
          like two different features. Each direction is its own bordered
          panel (owner request 2026-08-05): side by side they sat one `gap-3`
          apart and read as one list — the frame is what says where "what I
          share" ends and "what they share" begins; the peer side wears the
          muted wash the identity box uses for every read-only surface. */}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-3 rounded-md border border-border/40 p-3">
          <p className="flex items-center gap-1.5 text-xs font-medium uppercase text-muted-foreground">
            <ArrowUpRight className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
            {t('settings.peers.shares.my_title')}
          </p>
          <div className="space-y-3">
            <Label htmlFor={calendarSelectId} className="flex items-center gap-1.5">
              <Calendar className="h-4 w-4 text-primary" aria-hidden="true" />
              {t('settings.peers.shares.calendar_label')}
            </Label>
            {/* The design-system Select, like every other dropdown in the app:
                this was the last hand-classed native <select> on a user
                surface, and its bespoke class string drifted from the theme. */}
            <Select value={calendarLevel} onValueChange={handleCalendarChange} disabled={mutating}>
              <SelectTrigger id={calendarSelectId} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CALENDAR_LEVELS.map(level => (
                  <SelectItem key={level} value={level}>
                    {t(`settings.peers.shares.calendar_level.${level}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-between gap-2">
            <Label
              htmlFor={`peers-share-task-${connection.id}`}
              className="flex items-center gap-1.5"
            >
              <ListTodo className="h-4 w-4 text-primary" aria-hidden="true" />
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

        <div className="space-y-3 rounded-md border border-border/40 bg-muted/30 p-3">
          <p className="flex items-center gap-1.5 text-xs font-medium uppercase text-muted-foreground">
            <ArrowDownLeft className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
            {t('settings.peers.shares.their_title')}
          </p>
          <div className="space-y-3">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <Calendar className="h-4 w-4 text-primary" aria-hidden="true" />
              {t('settings.peers.shares.calendar_label')}
            </p>
            {/* `h-10 items-center`: the read-only value mirrors the Select's
                height on my side, so the task rows of BOTH columns sit on the
                same line (owner capture 2026-08-05). */}
            <p className="flex h-10 items-center text-sm text-muted-foreground">
              {t(`settings.peers.shares.calendar_level.${theirCalendarLevel}`)}
            </p>
          </div>
          <div className="flex items-center justify-between gap-2">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <ListTodo className="h-4 w-4 text-primary" aria-hidden="true" />
              {t('settings.peers.shares.task_label')}
            </p>
            <p className="text-sm text-muted-foreground">
              {theirTaskShared
                ? t('settings.peers.shares.task_level.titles')
                : t('settings.peers.shares.task_level.none')}
            </p>
          </div>
        </div>
      </div>

      {/* Both actions end something, and both said nothing about it: two grey
          buttons. They carry their red at rest now (ADR-207 — a colour the
          pointer must reveal is not a code), remove outweighing block. */}
      <div className="flex flex-wrap gap-2 border-t pt-3">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="text-destructive hover:text-destructive"
          disabled={mutating}
          onClick={() => void handleRemove()}
        >
          {t('settings.peers.connections.remove')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="text-destructive hover:text-destructive"
          disabled={mutating}
          onClick={() => void handleBlock()}
        >
          {t('settings.peers.connections.block')}
        </Button>
      </div>
    </div>
  );
}
