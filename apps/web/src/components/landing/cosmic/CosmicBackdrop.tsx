'use client';

/**
 * Fixed cosmic layers behind every `.cosmos` page: nebula gradients, a star
 * canvas drawn ONCE (no continuous cost), and a film-grain overlay. All layers
 * are decorative (`aria-hidden`) and sit on negative z-index so the page
 * content scrolls over one continuous cosmos.
 */

import { useEffect, useRef } from 'react';

const MAX_STARS = 180;
const STAR_DENSITY_PX_PER_STAR = 8;
const MAX_DEVICE_PIXEL_RATIO = 2;
const REDRAW_DEBOUNCE_MS = 200;
const STAR_HUES = ['238, 241, 251', '79, 141, 253', '56, 212, 245'] as const;

function drawStars(canvas: HTMLCanvasElement): void {
  const context = canvas.getContext('2d');
  if (!context) return;

  const dpr = Math.min(window.devicePixelRatio || 1, MAX_DEVICE_PIXEL_RATIO);
  canvas.width = window.innerWidth * dpr;
  canvas.height = window.innerHeight * dpr;
  context.scale(dpr, dpr);

  const count = Math.min(MAX_STARS, Math.floor(window.innerWidth / STAR_DENSITY_PX_PER_STAR));
  for (let i = 0; i < count; i++) {
    const x = Math.random() * window.innerWidth;
    const y = Math.random() * window.innerHeight;
    const radius = Math.random() * 1.2 + 0.2;
    const hue = STAR_HUES[Math.floor(Math.random() * STAR_HUES.length)];
    const alpha = (Math.random() * 0.55 + 0.15).toFixed(2);
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    context.fillStyle = `rgba(${hue}, ${alpha})`;
    context.fill();
  }
}

export function CosmicBackdrop() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    drawStars(canvas);

    let timer: number | undefined;
    const onResize = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => drawStars(canvas), REDRAW_DEBOUNCE_MS);
    };
    window.addEventListener('resize', onResize);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('resize', onResize);
    };
  }, []);

  return (
    <div aria-hidden="true" data-testid="cosmic-backdrop">
      <div className="cosmos-nebula" />
      <canvas ref={canvasRef} className="cosmos-stars" aria-hidden="true" />
      <div className="cosmos-grain" />
    </div>
  );
}
