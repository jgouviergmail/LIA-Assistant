'use client';
import { LayoutDashboard } from 'lucide-react';
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

export function WorldDashboardOffer({
  lng,
  open,
  onChoice,
}: {
  lng: Language;
  open: boolean;
  onChoice(show: boolean): void;
}) {
  const { t } = useTranslation(lng);
  return (
    <Dialog
      open={open}
      onOpenChange={value => {
        if (!value) onChoice(false);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <LayoutDashboard className="size-5 text-primary" aria-hidden="true" />
            {t('world.dashboard.title')}
          </DialogTitle>
          <DialogDescription>{t('world.dashboard.offer')}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={() => onChoice(false)}>
            {t('world.dashboard.stay')}
          </Button>
          <Button onClick={() => onChoice(true)}>{t('world.dashboard.open')}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
