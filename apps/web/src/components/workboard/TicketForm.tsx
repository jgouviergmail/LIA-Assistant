'use client';
/**
 * Creating a ticket (ADR-276).
 *
 * A `Dialog`, so the form traps focus and `Esc` closes it. One field carries
 * its own hint because it is not obvious: the DESCRIPTION becomes the
 * instruction LIA follows when the ticket is handed to it. The mode and the
 * follow switch carry their name and nothing under it (owner, 2026-09-09).
 *
 * The submit button is guarded by a HANDLER, never by `disabled` on the control
 * that holds focus: disabling a focused button blurs it and drops the keyboard
 * user back on `<body>`.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { ExecutionModeField } from '@/components/workboard/ExecutionModeField';
import { HolderSelect } from '@/components/workboard/HolderSelect';
import { PrioritySelect } from '@/components/workboard/PrioritySelect';
import { Textarea } from '@/components/ui/textarea';
import type { Language } from '@/i18n/settings';
import { dueAtFromInput } from '@/lib/workboard/dates';
import type { PeerName } from '@/lib/workboard/display';
import type { ExecutionMode, TicketCreateBody } from '@/types/workboard';

export interface TicketFormProps {
  open: boolean;
  lng: Language;
  peers: readonly PeerName[];
  onClose: () => void;
  onCreate: (body: TicketCreateBody) => Promise<{ ok: boolean }>;
}

export function TicketForm({ open, peers, onClose, onCreate }: TicketFormProps) {
  const { t } = useTranslation();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('medium');
  const [assignee, setAssignee] = useState('me');
  const [dueAt, setDueAt] = useState('');
  const [executionMode, setExecutionMode] = useState<ExecutionMode>('react');
  const [follow, setFollow] = useState(false);
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setTitle('');
    setDescription('');
    setPriority('medium');
    setAssignee('me');
    setDueAt('');
    setExecutionMode('react');
    setFollow(false);
  };

  const submit = async () => {
    if (!title.trim() || busy) return;
    setBusy(true);
    const peer = peers.find(connection => connection.peer_id === assignee);
    const result = await onCreate({
      title: title.trim(),
      description: description.trim() || null,
      priority,
      // `me` and `lia` are keywords; anything else is a connected peer's id.
      ...(peer ? { assignee_user_id: peer.peer_id } : { assignee: assignee as 'me' | 'lia' }),
      due_at: dueAtFromInput(dueAt),
      execution_mode: executionMode,
      follow,
    });
    setBusy(false);
    if (result.ok) reset();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={next => {
        if (!next) {
          reset();
          onClose();
        }
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('workboard.form.new_title')}</DialogTitle>
          <DialogDescription>{t('workboard.form.title_hint')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4" aria-busy={busy}>
          <div className="space-y-2">
            <Label htmlFor="wb-new-title">{t('workboard.form.title')}</Label>
            <Input
              id="wb-new-title"
              value={title}
              onChange={event => setTitle(event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="wb-new-description">{t('workboard.form.description')}</Label>
            <Textarea
              id="wb-new-description"
              rows={4}
              value={description}
              onChange={event => setDescription(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">{t('workboard.form.description_hint')}</p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {/* The panel's own lists, not copies of them (D81): three surfaces,
                one vocabulary, one set of marks. */}
            <div className="space-y-2">
              <PrioritySelect
                id="wb-new-priority"
                hideLabel={false}
                label={t('workboard.form.priority')}
                value={priority}
                className="h-10 px-3 text-sm"
                onChange={setPriority}
              />
            </div>

            <div className="space-y-2">
              <HolderSelect
                id="wb-new-assignee"
                hideLabel={false}
                label={t('workboard.form.assignee')}
                value={assignee}
                peers={peers}
                className="h-10 px-3 text-sm"
                onChange={setAssignee}
              />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="wb-new-due">{t('workboard.form.due_at')}</Label>
              <Input
                id="wb-new-due"
                type="date"
                value={dueAt}
                onChange={event => setDueAt(event.target.value)}
              />
            </div>
            <ExecutionModeField
              id="wb-new-mode"
              value={executionMode}
              onChange={setExecutionMode}
            />
          </div>

          <div className="flex items-center gap-3">
            <Switch
              id="wb-new-follow"
              checked={follow}
              onCheckedChange={setFollow}
              aria-label={t('workboard.form.follow')}
            />
            <Label htmlFor="wb-new-follow">{t('workboard.form.follow')}</Label>
          </div>

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => {
                reset();
                onClose();
              }}
            >
              {t('workboard.actions.cancel')}
            </Button>
            {/* `aria-disabled` plus a guard in the handler: `disabled` on a
                focused control blurs it and drops it from the tab order. */}
            <Button aria-disabled={!title.trim() || busy} isLoading={busy} onClick={submit}>
              {t('workboard.actions.create')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
