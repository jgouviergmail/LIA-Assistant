'use client';

import { useEffect, useRef } from 'react';
import type { EyesSize } from '@/stores/eyesWidgetStore';
import { bindSmileySphere } from './sphere-binding';
import { smileySphereResolution } from './sphere-geometry';
import type { SpiritVariant } from '@/components/spirit/catalogue';

/** A size-keyed canvas resets only its bounded GPU buffer, never the face rig. */
export function SmileySphere({
  size,
  variant = 'male',
  enabled = true,
}: {
  size: EyesSize;
  variant?: SpiritVariant;
  enabled?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const root = canvas?.closest<HTMLElement>('.lia-smiley');
    if (!enabled || !canvas || !root) return;
    canvas.width = canvas.height = smileySphereResolution(size, window.devicePixelRatio);
    return bindSmileySphere(canvas, root, undefined, variant);
  }, [size, variant, enabled]);
  const resolution = smileySphereResolution(size, 1);
  return (
    <span className="lia-avatar-body" data-sphere-ready="false">
      {enabled ? (
        <canvas
          key={`${size}-${variant}`}
          ref={canvasRef}
          className="lia-smiley-sphere"
          width={resolution}
          height={resolution}
          aria-hidden="true"
        />
      ) : null}
      {variant === 'female' ? <span className="lia-smiley-fallback-cheeks" /> : null}
    </span>
  );
}
