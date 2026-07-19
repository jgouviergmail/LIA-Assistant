'use client';

import { useTranslation } from 'react-i18next';
import { Mic, ShieldCheck, Check, Sparkles, User } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatEuro, formatNumber } from '@/lib/format';
import type { Language } from '@/i18n/settings';
import type { MessageFooter } from './scenarios';

/**
 * Chat rows for the landing mockup, faithful to the real app layout:
 * the user sits on the LEFT (primary bubble), LIA answers in a wide card on
 * the RIGHT with the psyche emoji avatar. Everything is decorative — plain
 * spans, no interactive elements (the whole mockup is one role="img").
 */

/** Psyche mood shown on every assistant row (Cynical, like the screenshots). */
export const MOOD_EMOJI = '😏';

export function UserBubble({ text, voice = false }: { text: string; voice?: boolean }) {
  return (
    <div className="flex gap-2 items-start animate-chat-bubble">
      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-muted flex items-center justify-center">
        <User className="w-3 h-3 text-muted-foreground" />
      </span>
      <span className="rounded-2xl rounded-tl-[4px] px-3 py-1.5 max-w-[82%] text-xs leading-relaxed bg-primary text-primary-foreground">
        {voice && <Mic className="inline w-3 h-3 mr-1 opacity-75 align-[-1px]" />}
        {text}
      </span>
    </div>
  );
}

export type AssistantVariant = 'default' | 'hitl' | 'success' | 'initiative';

const VARIANT_STYLES: Record<AssistantVariant, string> = {
  default: 'bg-card text-card-foreground border-border',
  hitl: 'bg-amber-500/10 text-amber-800 dark:text-amber-200 border-amber-500/30',
  success: 'bg-green-500/10 text-green-700 dark:text-green-300 border-green-500/30',
  initiative: 'bg-violet-500/10 text-violet-800 dark:text-violet-200 border-violet-500/30',
};

const VARIANT_ICONS: Record<AssistantVariant, React.ReactNode> = {
  default: null,
  hitl: (
    <ShieldCheck className="inline w-3 h-3 mr-1 align-[-1.5px] text-amber-600 dark:text-amber-400" />
  ),
  success: (
    <Check className="inline w-3 h-3 mr-1 align-[-1.5px] text-green-600 dark:text-green-400" />
  ),
  initiative: (
    <Sparkles className="inline w-3 h-3 mr-1 align-[-1.5px] text-violet-600 dark:text-violet-400" />
  ),
};

export interface AssistantRowProps {
  variant?: AssistantVariant;
  /** Skip the bubble chrome (the child renders its own card, e.g. weather). */
  bare?: boolean;
  footer?: MessageFooter;
  children: React.ReactNode;
}

/** Wide right-side assistant row with the psyche avatar, like the real app. */
export function AssistantRow({
  variant = 'default',
  bare = false,
  footer,
  children,
}: AssistantRowProps) {
  return (
    <div className="flex flex-row-reverse gap-2 items-start animate-chat-bubble">
      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-card border border-border flex items-center justify-center text-sm leading-none">
        {MOOD_EMOJI}
      </span>
      <div className="flex-1 min-w-0">
        {bare ? (
          children
        ) : (
          <div
            className={cn(
              'rounded-2xl rounded-tr-[4px] border px-3 py-2 text-xs leading-relaxed',
              VARIANT_STYLES[variant]
            )}
          >
            {VARIANT_ICONS[variant]}
            {children}
          </div>
        )}
        {footer && <BubbleFooter footer={footer} />}
      </div>
    </div>
  );
}

/**
 * Per-message token/cost line, mirroring the real ChatMessage footer.
 * "IN"/"OUT" are untranslated product vocabulary, exactly like the app.
 */
function BubbleFooter({ footer }: { footer: MessageFooter }) {
  const { i18n } = useTranslation();
  const lng = i18n.language as Language;
  return (
    <span className="block text-right text-[9px] text-muted-foreground mt-1 tabular-nums">
      {footer.time}
      {' · '}
      <span className="text-orange-500">🟠 {formatNumber(footer.tokensIn, lng)} IN</span>{' '}
      <span className="text-green-600">🟢 {formatNumber(footer.tokensOut, lng)} OUT</span>
      {' · '}
      {formatEuro(footer.costEur, 3, lng)}
    </span>
  );
}

/** Humorous waiting line (one of the 50 real ones), italic and breathing. */
export function WaitBubble({ text }: { text: string }) {
  return (
    <AssistantRow>
      <span className="inline-block italic text-muted-foreground animate-step-breathe">{text}</span>
    </AssistantRow>
  );
}
