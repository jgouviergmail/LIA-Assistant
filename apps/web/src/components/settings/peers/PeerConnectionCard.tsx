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

import { useRef, useState } from 'react';
import {
  ArrowDownLeft,
  ArrowUpRight,
  Calendar,
  ListTodo,
  ShieldOff,
  UserMinus,
} from 'lucide-react';

import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
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
  onResolved?: () => void;
}

const CALENDAR_LEVELS = ['none', 'availability', 'details'] as const;

export function PeerConnectionCard({
  lng,
  connection,
  mutating,
  onSetShare,
  onRemove,
  onBlock,
  onResolved,
}: PeerConnectionCardProps) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();
  const [calendarOpen, setCalendarOpen] = useState(false);
  const actionLock = useRef(false);
  const [actionPending, setActionPending] = useState(false);
  const busy = mutating || actionPending;

  const calendarLevel =
    connection.my_shares.find(share => share.domain === 'calendar')?.level ?? 'none';
  const taskShared = connection.my_shares.some(share => share.domain === 'task');
  const theirCalendarLevel =
    connection.their_shares.find(share => share.domain === 'calendar')?.level ?? 'none';
  const theirTaskShared = connection.their_shares.some(share => share.domain === 'task');

  const handleCalendarChange = (value: string) => {
    if (mutating) return;
    void onSetShare(connection.id, 'calendar', value === 'none' ? null : value);
  };

  const handleTaskToggle = (checked: boolean) => {
    if (mutating) return;
    void onSetShare(connection.id, 'task', checked ? 'titles' : null);
  };

  const endConnection = async (kind: 'remove' | 'block') => {
    if (mutating || actionLock.current) return;
    actionLock.current = true;
    setActionPending(true);
    try {
      const accepted = await confirm({
        title: t(`settings.peers.connections.${kind}_confirm_title`),
        description: t(`settings.peers.connections.${kind}_confirm_description`),
      });
      if (!accepted) return;
      const ok = await (kind === 'remove' ? onRemove(connection.id) : onBlock(connection.peer_id));
      if (ok) onResolved?.();
    } finally {
      actionLock.current = false;
      setActionPending(false);
    }
  };

  const calendarSelectId = `peers-share-calendar-${connection.id}`;

  return (
    <Accordion type="single" collapsible className="rounded-2xl border border-border/60 bg-card">
      {confirmDialog}
      <AccordionItem value={connection.id} className="border-0">
        <AccordionTrigger className="gap-3 rounded-2xl p-4 text-left hover:no-underline sm:p-5">
          {/* Identity never folds: the address remains the anti-impersonation anchor. */}
          <Avatar
            name={connection.peer_display_name}
            size="sm"
            variant="circular"
            disableHover
            className="shrink-0"
          />
          <span className="min-w-0 flex-1 space-y-1">
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="min-w-0 break-words text-sm font-semibold">
                {connection.peer_display_name}
              </span>
              <Badge
                variant="success"
                className="h-auto min-h-5 whitespace-normal text-left text-xs"
              >
                {t('settings.peers.connections.accepted')}
              </Badge>
            </span>
            <span className="block break-all text-xs font-normal text-muted-foreground">
              {connection.peer_email ?? connection.peer_email_hint}
            </span>
          </span>
        </AccordionTrigger>
        <AccordionContent className="space-y-4 px-4 pb-4 sm:px-5 sm:pb-5">
          {/* Two independent consents share one grid; only this user's side is editable. */}
          <div className="grid min-w-0 gap-4 md:grid-cols-2">
            <section
              aria-label={t('settings.peers.shares.their_named_title', {
                name: connection.peer_display_name,
              })}
              className="min-w-0 space-y-4 rounded-xl border border-border/50 bg-primary/5 p-4"
            >
              <p className="flex items-start gap-2 text-sm font-semibold">
                <ArrowDownLeft
                  className="mt-0.5 h-4 w-4 shrink-0 text-primary"
                  aria-hidden="true"
                />
                <span className="min-w-0 break-words">
                  {t('settings.peers.shares.their_named_title', {
                    name: connection.peer_display_name,
                  })}
                </span>
              </p>
              <div className="space-y-3">
                <p className="flex items-center gap-1.5 text-sm font-medium">
                  <Calendar className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                  {t('settings.peers.shares.calendar_label')}
                </p>
                {/* `h-10 items-center`: the read-only value mirrors the Select's
                height on my side, so the task rows of BOTH columns sit on the
                same line (owner capture 2026-08-05). */}
                <p className="flex min-h-10 items-center text-sm text-muted-foreground">
                  {t(`settings.peers.shares.calendar_level.${theirCalendarLevel}`)}
                </p>
              </div>
              <div className="space-y-2">
                <p className="flex items-center gap-1.5 text-sm font-medium">
                  <ListTodo className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                  {t('settings.peers.shares.task_label')}
                </p>
                <p className="text-sm text-muted-foreground">
                  {theirTaskShared
                    ? t('settings.peers.shares.task_level.titles')
                    : t('settings.peers.shares.task_level.none')}
                </p>
              </div>
            </section>
            <section
              aria-label={t('settings.peers.shares.my_title')}
              className="min-w-0 space-y-4 rounded-xl border border-border/50 p-4"
            >
              <p className="flex items-start gap-2 text-sm font-semibold">
                <ArrowUpRight className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                {t('settings.peers.shares.my_title')}
              </p>
              <div className="space-y-3">
                <Label htmlFor={calendarSelectId} className="flex min-w-0 items-center gap-2">
                  <Calendar className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                  {t('settings.peers.shares.calendar_label')}
                </Label>
                {/* The design-system Select, like every other dropdown in the app:
                this was the last hand-classed native <select> on a user
                surface, and its bespoke class string drifted from the theme. */}
                <Select
                  value={calendarLevel}
                  onValueChange={handleCalendarChange}
                  open={calendarOpen}
                  onOpenChange={open => {
                    if (!mutating || !open) setCalendarOpen(open);
                  }}
                >
                  <SelectTrigger aria-disabled={busy} id={calendarSelectId} className="w-full">
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
              <div className="flex items-start justify-between gap-3">
                <Label
                  htmlFor={`peers-share-task-${connection.id}`}
                  className="flex min-w-0 items-center gap-2"
                >
                  <ListTodo className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                  {t('settings.peers.shares.task_label')}
                </Label>
                <Switch
                  id={`peers-share-task-${connection.id}`}
                  checked={taskShared}
                  aria-disabled={busy}
                  onCheckedChange={handleTaskToggle}
                />
              </div>
            </section>
          </div>

          {/* Connection-level actions follow the consent information, with confirmation. */}
          <div className="flex flex-col items-stretch gap-2 border-t border-border/50 pt-4 sm:items-start">
            <Button
              type="button"
              size="sm"
              variant="destructive"
              aria-disabled={busy}
              onClick={() => void endConnection('remove')}
            >
              <UserMinus aria-hidden="true" />
              {t('settings.peers.connections.remove')}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="default"
              aria-disabled={busy}
              onClick={() => void endConnection('block')}
            >
              <ShieldOff aria-hidden="true" />
              {t('settings.peers.connections.block')}
            </Button>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
