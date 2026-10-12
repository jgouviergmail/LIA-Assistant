'use client';

import { useLayoutEffect, useRef } from 'react';
import type { EyesSize } from '@/stores/eyesWidgetStore';
import type { SpiritVariant } from '@/components/spirit/catalogue';
import { smileySphereResolution } from '../smiley/sphere-geometry';
import { bindBodyVolume } from './volume-binding';
import type { VolumeCharacter } from './volume-geometry';

// This stage includes the body's sides and is wider than the 2.6em face.
// Match its pixels to the 3.4em canvas while retaining the existing GPU cap.
const resolution = (size: EyesSize, dpr: number) =>
  Math.min(192, Math.ceil((smileySphereResolution(size, dpr) * 3.4) / 2.6));

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
