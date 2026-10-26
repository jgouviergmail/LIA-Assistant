'use client';
import { useEffect, useRef, useState } from 'react';
import { RotateCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { AvatarAppearance } from './avatar-catalogue';
import { paintPerson } from './art/person';
export function WorldAvatarPreview({
  lng,
  appearance,
}: {
  lng: Language;
  appearance: AvatarAppearance;
}) {
  const { t } = useTranslation(lng);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [heading, setHeading] = useState(2);
  useEffect(() => {
    const surface = canvas.current,
      c = surface?.getContext('2d');
    if (!surface || !c) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    surface.width = 144 * ratio;
    surface.height = 156 * ratio;
    c.setTransform(ratio, 0, 0, ratio, 0, 0);
    c.fillStyle = '#2b665d22';
    c.beginPath();
    c.ellipse(72, 138, 44, 13, 0, 0, Math.PI * 2);
    c.fill();
    const sprite = paintPerson(1, 0, 2, 'sage', heading, null, appearance);
    c.drawImage(
      sprite.canvas,
      72 - sprite.anchorX,
      138 - sprite.anchorY,
      sprite.width,
      sprite.height
    );
    sprite.canvas.width = sprite.canvas.height = 0;
  }, [appearance, heading]);
  return (
    <div className="world-avatar-preview">
      <div className="relative">
        <canvas
          ref={canvas}
          className="relative h-[156px] w-36"
          role="img"
          aria-label={t('world.avatar.preview')}
        >
          {t('world.avatar.preview')}
        </canvas>
      </div>
      <Button
        type="button"
        variant="ghost"
        className="min-h-11"
        onClick={() => setHeading(value => (value + 1) % 8)}
      >
        <RotateCw className="size-4" aria-hidden="true" />
        {t('world.avatar.rotate')}
      </Button>
    </div>
  );
}
