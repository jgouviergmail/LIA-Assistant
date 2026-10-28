'use client';

import { UsersRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { sessionDialogState } from './session-dialog-state';
import type { SessionPresentation } from './useWorldSession';

export function WorldSessionDialog({
  lng,
  presentation,
  open,
  onLeave,
  onAccept,
  onTakeover,
}: {
  lng: Language;
  presentation: SessionPresentation;
  open: boolean;
  onLeave(): void;
  onAccept(): void;
  onTakeover(): void;
}) {
  const { t } = useTranslation(lng);
  const state = sessionDialogState(presentation);
  const actions = { accept: onAccept, rejoin: onAccept, takeover: onTakeover };
  return (
    <Dialog
      open={open}
      onOpenChange={value => {
        if (!value) onLeave();
      }}
    >
      <DialogContent
        onInteractOutside={event => event.preventDefault()}
        onEscapeKeyDown={event => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UsersRound className="size-5 text-primary" aria-hidden="true" />
            {t('world.session.' + state.title)}
          </DialogTitle>
          <DialogDescription>
            {t('world.session.' + state.hint, { position: presentation.position })}
          </DialogDescription>
        </DialogHeader>
        {state.offered && <p className="text-sm">{t('world.session.offer')}</p>}
        {presentation.connection === 'outdated' && (
          <Button onClick={() => window.location.reload()}>{t('world.session.reload')}</Button>
        )}
        {state.action && (
          <Button onClick={actions[state.action]}>{t('world.session.' + state.action)}</Button>
        )}
        <Button variant="outline" onClick={onLeave}>
          {t('world.session.leave')}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
