'use client';

import dynamic from 'next/dynamic';
import type { GeneratedAssetTab } from '@/types/generated-assets';
import { Skeleton } from '@/components/ui/skeleton';
import { SettingsPaneFrame } from '@/components/settings/SettingsPaneFrame';
import { LayoutGrid } from 'lucide-react';
import { useSettingsAvailability } from '@/hooks/useSettingsAvailability';
import { useAuth } from '@/hooks/useAuth';
import { worldCatalogue } from './functions';
import type { SettingsSectionToken } from '@/lib/settings-sections';
import type { Language } from '@/i18n/settings';
import { useTranslation } from '@/i18n/client';

const ChatWorkspace = dynamic(
  () => import('@/components/chat/ChatWorkspace').then(module => module.ChatWorkspace),
  {
    ssr: false,
    loading: () => <Skeleton className="h-full min-h-48 w-full" />,
  }
);

const GeneratedAssets = dynamic(
  () =>
    import('@/components/settings/GeneratedAssetsSettings').then(
      module => module.GeneratedAssetsSettings
    ),
  { ssr: false }
);

export function WorldNativePanel({
  lng,
  ownerId,
  selection,
  onBack,
  openingDraft,
  galleryTab,
}: {
  lng: Language;
  ownerId: string;
  selection: SettingsSectionToken | 'lia';
  onBack(): void;
  openingDraft?: string;
  galleryTab?: GeneratedAssetTab;
}) {
  const { user } = useAuth();
  const availability = useSettingsAvailability();
  const { t } = useTranslation(lng);
  if (user?.id !== ownerId || !user.is_active) return null;
  if (selection === 'lia')
    return <ChatWorkspace key={ownerId} embedded openingDraft={openingDraft} />;
  if (!worldCatalogue(availability).some(item => item.token === selection))
    return <p role="status">{t('world.functions.unavailable')}</p>;
  if (selection === 'generated-assets' && galleryTab)
    return (
      <div className="h-full overflow-y-auto p-1">
        <GeneratedAssets key={ownerId + galleryTab} lng={lng} initialTab={galleryTab} />
      </div>
    );
  return (
    <div className="h-full overflow-y-auto p-1">
      <SettingsPaneFrame
        key={ownerId + selection}
        lng={lng}
        token={selection}
        availability={availability}
        onBack={onBack}
        focusRequest={1}
        showBack={false}
        icon={LayoutGrid}
      />
    </div>
  );
}
