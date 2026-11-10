'use client';

import { useLayoutEffect, useRef } from 'react';
import type { EyesSize } from '@/stores/eyesWidgetStore';
import type { SpiritVariant } from '@/components/spirit/catalogue';
import { bindBodyVolume } from './volume-binding';
import {
  VOLUME_BUFFER_MAX,
  VOLUME_EXTENT,
  VOLUME_SOURCE_EM,
  type VolumeCharacter,
} from './volume-geometry';

const FONT_SIZE = { sm: 20, md: 30, lg: 44, xl: 64 } as const;

// This stage includes the body's sides and is wider than the 2.6em face.
// Match its pixels to the 3.4em canvas while retaining the existing GPU cap.
const resolution = (size: EyesSize, dpr: number) => {
  const density = Number.isFinite(dpr) ? Math.max(1, Math.min(2, dpr)) : 1;
  const facePixels = Math.ceil(FONT_SIZE[size] * VOLUME_SOURCE_EM * density);
  return Math.min(
    VOLUME_BUFFER_MAX,
    Math.ceil((facePixels * VOLUME_EXTENT * 2) / VOLUME_SOURCE_EM)
  );
};

/** Native rig frames paint this bounded surface; React only owns its lifetime. */
export function BodyVolume({
  character,
  variant,
  size,
  enabled,
}: {
  character: VolumeCharacter;
  variant: SpiritVariant;
  size: EyesSize;
  enabled: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    const root = canvas?.closest<HTMLElement>('.lia-eyes');
    if (!enabled || !canvas || !root) return;
    canvas.width = canvas.height = resolution(size, window.devicePixelRatio);
    return bindBodyVolume(canvas, root, character, variant);
  }, [character, variant, size, enabled]);
  if (!enabled) return null;
  const pixels = resolution(size, 1);
  return (
    <span className="lia-volume-body" aria-hidden="true">
      <canvas
        key={`${character}-${variant}-${size}`}
        ref={canvasRef}
        className="lia-volume-canvas"
        data-volume-canvas=""
        width={pixels}
        height={pixels}
        aria-hidden="true"
      />
    </span>
  );
}
