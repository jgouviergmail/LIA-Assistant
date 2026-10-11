'use client';

import { useLayoutEffect, useRef } from 'react';
import type { EyesSize } from '@/stores/eyesWidgetStore';
import type { SpiritVariant } from '@/components/spirit/catalogue';
import { smileySphereResolution } from '../smiley/sphere-geometry';
import { bindBodyVolume } from './volume-binding';
import type { VolumeCharacter } from './volume-geometry';

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
    canvas.width = canvas.height = Math.min(
      192,
      smileySphereResolution(size, window.devicePixelRatio)
    );
    return bindBodyVolume(canvas, root, character, variant);
  }, [character, variant, size, enabled]);
  if (!enabled) return null;
  const resolution = Math.min(192, smileySphereResolution(size, 1));
  return (
    <span className="lia-volume-body" aria-hidden="true">
      <canvas
        key={`${character}-${variant}-${size}`}
        ref={canvasRef}
        className="lia-volume-canvas"
        data-volume-canvas=""
        width={resolution}
        height={resolution}
        aria-hidden="true"
      />
    </span>
  );
}
