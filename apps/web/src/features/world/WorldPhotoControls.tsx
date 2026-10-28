'use client';
import { useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { Camera } from 'lucide-react';
import { WorldWidgetButton } from './WorldWidgetButton';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorldRuntime } from './runtime';
import type { PhotoScene } from './photo-projection';
import { WorldActivityPanel } from './WorldActivityPanel';

const PhotoPanel = dynamic(
  () => import('./WorldPhotoPanel').then(module => module.WorldPhotoPanel),
  { ssr: false }
);
export function WorldPhotoControls({
  lng,
  ownerId,
  disabled,
  command,
  onOpen,
}: {
  lng: Language;
  ownerId: string;
  disabled: boolean;
  command(action: (runtime: WorldRuntime) => void): void;
  onOpen(open: boolean): void;
}) {
  const { t } = useTranslation(lng);
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const [scene, setScene] = useState<PhotoScene | null>(null);
  const [failed, setFailed] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  const open = scene !== null;
  useEffect(() => {
    onOpen(open);
    return () => onOpen(false);
  }, [open, onOpen]);
  function capture() {
    if (disabled || !isCurrent()) return;
    try {
      command(runtime => {
        const still = runtime.photoScene();
        if (still) {
          setFailed(false);
          setScene(still);
        }
      });
    } catch {
      setFailed(true);
    }
  }
  return (
    <>
      <WorldWidgetButton
        ref={opener}
        icon={Camera}
        label={t('world.photo.title')}
        aria-disabled={disabled}
        onClick={capture}
      />
      {failed && (
        <p role="alert" className="text-sm">
          {t('world.photo.error')}
        </p>
      )}
      <WorldActivityPanel
        lng={lng}
        ownerId={ownerId}
        open={open}
        title={t('world.photo.title')}
        description={t('world.photo.privacy')}
        icon={Camera}
        opener={opener}
        fallbackToScene
        onClose={() => setScene(null)}
      >
        {scene && <PhotoPanel lng={lng} ownerId={ownerId} scene={scene} />}
      </WorldActivityPanel>
    </>
  );
}
