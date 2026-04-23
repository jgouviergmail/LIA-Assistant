'use client';

import { LLMUsageBadge } from './LLMUsageBadge';
import type { TextSection } from '@/types/briefing';

interface BriefingGreetingProps {
  greeting: TextSection;
}

/**
 * Top-of-page greeting — single sentence, time-aware via the LLM.
 *
 * Sober presentation:
 *  - text-xl mobile → text-2xl desktop (compact)
 *  - Centered, balanced text-wrap
 *  - Subtle gradient underline accent
 *  - Smooth fade-in entrance
 */
export function BriefingGreeting({ greeting }: BriefingGreetingProps) {
  return (
    <div className="relative py-6 sm:py-8 text-center">
      <div className="relative inline-flex flex-col items-center gap-3 max-w-3xl mx-auto px-4">
        <h1
          className="text-xl sm:text-2xl font-semibold tracking-tight text-foreground leading-tight motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-500"
          style={{ textWrap: 'balance' } as React.CSSProperties}
        >
          {greeting.text}
        </h1>
        <div
          className="h-px w-20 bg-gradient-to-r from-transparent via-primary/40 to-transparent motion-safe:animate-in motion-safe:fade-in motion-safe:duration-700 motion-safe:[animation-delay:200ms]"
          aria-hidden="true"
        />
        {greeting.usage && (
          <LLMUsageBadge
            usage={greeting.usage}
            className="motion-safe:animate-in motion-safe:fade-in motion-safe:duration-700 motion-safe:[animation-delay:300ms]"
          />
        )}
      </div>
    </div>
  );
}
