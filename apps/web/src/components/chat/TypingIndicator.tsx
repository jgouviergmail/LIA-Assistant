import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';

export interface TypingIndicatorProps {
  className?: string;
}

/** Animation variants — one is picked at random per response (per mount). */
export type TypingVariant = 'wave' | 'orbit' | 'equalizer' | 'sparkle' | 'breathe' | 'typewriter';

export const TYPING_VARIANTS: readonly TypingVariant[] = [
  'wave',
  'orbit',
  'equalizer',
  'sparkle',
  'breathe',
  'typewriter',
] as const;

function VariantShapes({ variant }: { variant: TypingVariant }) {
  switch (variant) {
    case 'orbit':
      return (
        <div className="relative w-5 h-5 animate-typing-orbit">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-current" />
          <div className="absolute bottom-0 left-0.5 w-1.5 h-1.5 rounded-full bg-current opacity-70" />
          <div className="absolute bottom-0 right-0.5 w-1.5 h-1.5 rounded-full bg-current opacity-40" />
        </div>
      );
    case 'equalizer':
      return (
        <div className="flex items-end gap-0.5 h-4">
          {[0, 1, 2, 3].map(i => (
            <div
              key={i}
              className="w-1 h-full rounded-full bg-current origin-bottom animate-typing-eq"
              style={{ animationDelay: `${i * -0.18}s` }}
            />
          ))}
        </div>
      );
    case 'sparkle':
      return (
        <div className="flex items-center justify-center w-5 h-5">
          <span aria-hidden="true" className="text-base leading-none animate-typing-sparkle">
            ✦
          </span>
        </div>
      );
    case 'breathe':
      return (
        <div className="flex items-center justify-center w-5 h-5">
          <div className="w-3.5 h-3.5 rounded-full border-2 border-current animate-typing-breathe" />
        </div>
      );
    case 'typewriter':
      return (
        <div className="flex items-center space-x-1">
          {[0, 1, 2].map(i => (
            <div
              key={i}
              className="w-2 h-2 rounded-full bg-current animate-typing-type"
              style={{ animationDelay: `${i * 0.22}s` }}
            />
          ))}
        </div>
      );
    case 'wave':
    default:
      return (
        <div className="flex items-center space-x-1">
          <div className="w-2 h-2 rounded-full bg-current animate-typing-wave [animation-delay:-0.32s]" />
          <div className="w-2 h-2 rounded-full bg-current animate-typing-wave [animation-delay:-0.16s]" />
          <div className="w-2 h-2 rounded-full bg-current animate-typing-wave" />
        </div>
      );
  }
}

export const TypingIndicator: React.FC<TypingIndicatorProps> = ({ className }) => {
  const { t } = useTranslation();

  // Stable per mount: ChatMessageList renders this component only while
  // isTyping is true, so each response gets one randomly picked variant.
  const [variant] = useState<TypingVariant>(
    () => TYPING_VARIANTS[Math.floor(Math.random() * TYPING_VARIANTS.length)]
  );

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={t('chat.assistant_typing')}
      data-variant={variant}
      className={cn('flex items-center gap-2 text-gray-400', className)}
    >
      <div className="motion-reduce:hidden">
        <VariantShapes variant={variant} />
      </div>
      {/* Reduced motion: swap to the classic static dots — never a frozen variant (spec D-6). */}
      <div className="hidden motion-reduce:flex items-center space-x-1">
        <div className="w-2 h-2 rounded-full bg-current" />
        <div className="w-2 h-2 rounded-full bg-current" />
        <div className="w-2 h-2 rounded-full bg-current" />
      </div>
      {/* The Lot 1-A5 mood-tinted wait phrase used to sit here — removed on
          owner decision 2026-08-20 ("c'était mieux avant"): the indicator
          speaks through motion alone. */}
    </div>
  );
};
