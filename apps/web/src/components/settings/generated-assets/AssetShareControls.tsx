'use client';

/**
 * What the gallery says about sharing an image (ADR-316).
 *
 * Two self-gated pieces, kept out of the grid so its render stays flat (the
 * complexity ratchet): the « share with a connection » action on one of the
 * person's generated images, and the line naming who shared a copy they
 * received. Each renders nothing where it does not apply.
 */

import { useState } from 'react';
import { Send } from 'lucide-react';

import { ShareImageDialog } from '@/components/peers/ShareImageDialog';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { usePeersAvailable } from '@/lib/peers/availability-context';
import type { GeneratedAsset } from '@/types/generated-assets';

/** The origin the API files a generated image under — the only kind that can be shared. */
const SHAREABLE_ORIGIN = 'generated_image';

export interface AssetShareProps {
  lng: Language;
  asset: GeneratedAsset;
  /** What the file is called for a person (the card's own label). */
  label: string;
}

/** « Share with a connection », for a generated image where connections are offered. */
export function ShareAssetButton({ lng, asset, label }: AssetShareProps) {
  const { t } = useTranslation(lng);
  const enabled = usePeersAvailable();
  const [open, setOpen] = useState(false);
  if (!enabled || asset.origin !== SHAREABLE_ORIGIN) return null;
  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen(true)}
        aria-label={t('settings.generated_assets.share', { name: label })}
      >
        <Send className="h-3.5 w-3.5" aria-hidden="true" />
      </Button>
      {open && (
        <ShareImageDialog
          open={open}
          onOpenChange={setOpen}
          attachmentId={asset.id}
          imageTitle={label}
        />
      )}
    </>
  );
}

/** « Shared by … » under a copy a connection sent. */
export function SharedByLine({ lng, asset }: Omit<AssetShareProps, 'label'>) {
  const { t } = useTranslation(lng);
  if (!asset.shared_by_name) return null;
  return (
    <p className="text-xs text-muted-foreground" data-testid="generated-asset-shared-by">
      {t('settings.generated_assets.shared_by', { name: asset.shared_by_name })}
    </p>
  );
}
