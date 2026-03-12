'use client';

import { Megaphone } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import { useBroadcast } from '@/hooks/useBroadcast';
import type { Language } from '@/i18n/settings';

interface BroadcastModalProps {
  lng: Language;
}

/**
 * Modal for displaying admin broadcast messages.
 *
 * Features:
 * - Cannot be dismissed by clicking outside or pressing Escape
 * - Shows queue count (1/n) when multiple broadcasts pending
 * - Marks broadcast as read on dismiss
 */
export function BroadcastModal({ lng }: BroadcastModalProps) {
  const { t } = useTranslation(lng);
  const { currentBroadcast, showModal, queueLength, handleDismiss } = useBroadcast();

  if (!currentBroadcast) return null;

  return (
    <Dialog open={showModal} onOpenChange={() => {}}>
      <DialogContent
        className="sm:max-w-md [&>button]:hidden"
        onEscapeKeyDown={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Megaphone className="h-5 w-5 text-primary" />
            {t('broadcast.modal.title')}
            {queueLength > 1 && (
              <span className="text-sm font-normal text-muted-foreground">
                (1/{queueLength})
              </span>
            )}
          </DialogTitle>
          <DialogDescription>{t('broadcast.modal.from_admin')}</DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <p className="text-foreground whitespace-pre-wrap">{currentBroadcast.message}</p>
        </div>

        <DialogFooter>
          <Button onClick={handleDismiss} className="w-full">
            {queueLength > 1 ? t('broadcast.modal.next') : t('broadcast.modal.understood')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
