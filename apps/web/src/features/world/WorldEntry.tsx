'use client';

import dynamic from 'next/dynamic';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/hooks/useAuth';
import type { Language } from '@/i18n/settings';
import { useAppConfig } from '@/hooks/useAppConfig';
import { worldAvailable } from './availability';

const WorldPrototype = dynamic(
  () => import('./WorldPrototype').then(module => module.WorldPrototype),
  {
    ssr: false,
    loading: () => <Skeleton className="h-[70dvh] w-full rounded-2xl" />,
  }
);
const WorldShared = dynamic(() => import('./WorldShared').then(module => module.WorldShared), {
  ssr: false,
});

export function WorldEntry({ lng }: { lng: Language }) {
  const { user } = useAuth();
  const { config } = useAppConfig();
  const enabled = worldAvailable(config);
  return user && enabled ? <WorldShared key={user.id + lng} lng={lng} ownerId={user.id} /> : null;
}

/** The server exposes this account-free surface in development only. */
export function WorldPreviewEntry({ lng }: { lng: Language }) {
  return (
    <div className="world-preview">
      <WorldPrototype key={lng} lng={lng} ownerId="local-world-preview" />
    </div>
  );
}
