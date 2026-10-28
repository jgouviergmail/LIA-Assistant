'use client';
import { LayoutDashboard } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { WorldDashboardOffer } from './WorldDashboardOffer';
import {
  dashboardOfferOpen,
  type DashboardOffer,
  type SeatDashboardIntent,
} from './seat-dashboard-intent';

/** Accessible current-seat action and its explicit private-dashboard consent. */
export function WorldSeatedDashboard({
  lng,
  active,
  seatKey,
  pose,
  offer,
  intent,
  onAccept,
}: {
  lng: Language;
  active: boolean;
  seatKey: string | null;
  pose: string | null;
  offer: DashboardOffer | null;
  intent: SeatDashboardIntent;
  onAccept(): void;
}) {
  const { t } = useTranslation(lng);
  return (
    <>
      {active && seatKey && (
        <Button
          size="sm"
          variant="ghost"
          className="min-h-11 min-w-11"
          aria-label={t('world.dashboard.title')}
          onClick={() => {
            if (pose) intent.request(pose);
          }}
        >
          <LayoutDashboard className="size-4 text-primary" aria-hidden="true" />
          <span className="hidden lg:inline">{t('world.dashboard.title')}</span>
        </Button>
      )}
      <WorldDashboardOffer
        lng={lng}
        open={dashboardOfferOpen(offer, pose, seatKey, active)}
        onChoice={show => {
          if (show) onAccept();
          intent.cancel();
        }}
      />
    </>
  );
}
