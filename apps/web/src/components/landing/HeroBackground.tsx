'use client';

import Image from 'next/image';
import { useLiaGender } from '@/hooks/useLiaGender';

/**
 * Hero background image — adapts to theme (light/dark) and LIA gender.
 * Click anywhere on the background to toggle male/female avatar.
 * Uses the existing `useLiaGender` hook (cookie-persisted preference).
 */
export function HeroBackground() {
  const { liaBackgroundImage, toggleGender, mounted } = useLiaGender();

  return (
    <div
      className="absolute inset-0 cursor-pointer"
      onClick={toggleGender}
      role="presentation"
      aria-hidden="true"
    >
      <Image
        src={liaBackgroundImage}
        alt=""
        fill
        priority
        sizes="100vw"
        className={`object-cover transition-opacity duration-700 ${mounted ? 'opacity-100' : 'opacity-0'}`}
      />
      {/* Semi-transparent overlay — text readable, image visible through */}
      <div className="absolute inset-0 bg-background/40" />
      {/* Top and bottom fades for seamless blending */}
      <div className="absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-background to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-background to-transparent" />
    </div>
  );
}
