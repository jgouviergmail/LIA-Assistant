'use client';
import { useRef, useState } from 'react';
import Image from 'next/image';
import { Download, Loader2, RotateCcw, Share2 } from 'lucide-react';
import { Button, buttonVariants } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { PhotoScene } from './photo-projection';
import { canShareWorldPhoto, shareWorldPhoto, type PhotoFormat } from './photo-export';
import { usePhotoPreview } from './usePhotoPreview';
import { useNativePhotoSharing } from './useNativePhotoSharing';

export function WorldPhotoPanel(props: { lng: Language; ownerId: string; scene: PhotoScene }) {
  return <OwnedPhotoPanel key={props.ownerId} {...props} />;
}
function OwnedPhotoPanel({
  lng,
  ownerId,
  scene,
}: {
  lng: Language;
  ownerId: string;
  scene: PhotoScene;
}) {
  const { t } = useTranslation(lng);
  const [format, setFormat] = useState<PhotoFormat>('landscape');
  const [sharing, setSharing] = useState(false);
  const shareLock = useRef(false);
  const [notice, setNotice] = useState<string | null>(null);
  const photo = usePhotoPreview(ownerId, scene, format);
  const nativeSharing = useNativePhotoSharing();
  const busy = photo.loading || sharing;
  async function share() {
    if (!photo.preview || busy || shareLock.current || !photo.isCurrent()) return;
    shareLock.current = true;
    setSharing(true);
    setNotice(null);
    try {
      const result = await shareWorldPhoto(photo.preview.file, photo.isCurrent, nativeSharing);
      if (photo.isCurrent()) setNotice('world.photo.' + result);
    } catch {
      if (photo.isCurrent()) setNotice('world.photo.share_error');
    } finally {
      shareLock.current = false;
      if (photo.isCurrent()) setSharing(false);
    }
  }
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto" aria-busy={busy}>
      <PhotoOptions
        lng={lng}
        format={format}
        busy={busy}
        onFormat={value => {
          if (!busy && photo.isCurrent()) {
            setNotice(null);
            setFormat(value);
          }
        }}
      />
      {photo.loading && (
        <p role="status" className="flex items-center gap-2 text-sm">
          <Loader2 className="size-4 motion-safe:animate-spin" aria-hidden="true" />
          {t('world.photo.preparing')}
        </p>
      )}
      {photo.error && (
        <div role="alert" className="space-y-2 text-sm">
          <p>{t('world.photo.error')}</p>
          {photo.preview && <p>{t('world.photo.previous')}</p>}
          <Button
            className="min-h-11"
            variant="outline"
            onClick={() => {
              if (!busy && photo.isCurrent()) photo.retry();
            }}
          >
            <RotateCcw aria-hidden="true" className="size-4" />
            {t('world.photo.retry')}
          </Button>
        </div>
      )}
      {photo.preview && (
        <>
          <div className="shrink-0 overflow-hidden rounded-xl border bg-muted/20">
            <Image
              src={photo.preview.url}
              width={photo.preview.width}
              height={photo.preview.height}
              unoptimized
              loading="eager"
              alt={t('world.photo.preview')}
              className="mx-auto h-auto max-h-[55dvh] w-full object-contain"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {(nativeSharing || canShareWorldPhoto(photo.preview.file)) && (
              <Button
                className="min-h-11"
                aria-disabled={busy}
                onClick={() => {
                  void share();
                }}
              >
                <Share2 className="size-4" aria-hidden="true" />
                {t('world.photo.share')}
              </Button>
            )}
            <a
              className={buttonVariants({ variant: 'outline', className: 'min-h-11' })}
              href={photo.preview.url}
              download={photo.preview.file.name}
              aria-disabled={busy}
              onClick={event => {
                if (busy || !photo.isCurrent()) event.preventDefault();
              }}
            >
              <Download className="size-4" aria-hidden="true" />
              {t('world.photo.download')}
            </a>
          </div>
        </>
      )}
      {notice && (
        <p role="status" className="text-sm">
          {t(notice)}
        </p>
      )}
    </div>
  );
}
function PhotoOptions({
  lng,
  format,
  busy,
  onFormat,
}: {
  lng: Language;
  format: PhotoFormat;
  busy: boolean;
  onFormat(value: PhotoFormat): void;
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div role="group" aria-label={t('world.photo.format')} className="flex flex-wrap gap-2">
        {(['landscape', 'portrait'] as const).map(value => (
          <Button
            key={value}
            className="min-h-11"
            variant={value === format ? 'default' : 'outline'}
            aria-pressed={value === format}
            aria-disabled={busy}
            onClick={() => onFormat(value)}
          >
            {t('world.photo.' + value)}
          </Button>
        ))}
      </div>
    </div>
  );
}
