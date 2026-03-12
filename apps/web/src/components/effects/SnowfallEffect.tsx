'use client';

import { useEffect, useState } from 'react';
import Snowfall from 'react-snowfall';
import { useTheme } from 'next-themes';

/**
 * SnowfallEffect - Decorative snowfall for Christmas season
 *
 * Features:
 * - Limits height to 1/6 of viewport (16.67vh)
 * - Progressive fade-out via CSS mask
 * - Theme-aware colors (light/dark)
 * - Seasonal activation (Dec 1 - Jan 6)
 * - Respects prefers-reduced-motion
 */
export function SnowfallEffect() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  // Seasonal activation: December 1 → January 6
  const now = new Date();
  const month = now.getMonth();
  const day = now.getDate();
  const isChristmasSeason = month === 11 || (month === 0 && day <= 6);

  if (!isChristmasSeason) return null;

  // Respect prefers-reduced-motion
  if (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ) {
    return null;
  }

  // Theme-aware snowflake color
  const snowflakeColor =
    resolvedTheme === 'dark' ? 'rgba(255, 255, 255, 0.85)' : 'rgba(180, 200, 230, 0.8)';

  return (
    <div
      aria-hidden="true"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        height: '16.67vh', // 1/6 of viewport
        pointerEvents: 'none',
        zIndex: 9999,
        overflow: 'hidden',
        // Progressive fade-out
        maskImage: 'linear-gradient(to bottom, black 0%, black 30%, transparent 100%)',
        WebkitMaskImage: 'linear-gradient(to bottom, black 0%, black 30%, transparent 100%)',
      }}
    >
      <Snowfall
        color={snowflakeColor}
        snowflakeCount={50}
        radius={[0.5, 3.5]}
        speed={[0.3, 1.0]}
        wind={[-0.5, 1.0]}
      />
    </div>
  );
}
