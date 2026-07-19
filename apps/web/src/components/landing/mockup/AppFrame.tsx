'use client';

import { useTranslation } from 'react-i18next';
import { Mic, Paperclip, Send, Square } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatEuro, formatNumber } from '@/lib/format';
import type { Language } from '@/i18n/settings';
import type { TokenbarState } from './scenarios';
import { MOOD_EMOJI } from './bubbles';

/**
 * Window chrome faithful to the real LIA web app (see public/screenshots):
 * app bar (logo, Online pill, psyche mood, benefit chip), the conversation
 * token/cost bar, the chat area (with the optional backstage glass pane) and
 * the input bar — where the user's request visibly types itself in, and the
 * send button morphs into Stop while a response streams (ADR-117).
 */

export interface AppFrameProps {
  /** Translated benefit chip shown in the app bar. */
  chip: string;
  tokenbar: TokenbarState;
  /** True once the token bar has flipped to its end state (tick animation). */
  ticked: boolean;
  /** Translated text currently being typed into the input, if any. */
  typingText: string | null;
  /** The typed request is dictated by voice: the mic pulses while it types. */
  voice?: boolean;
  /** A response is streaming: the send button shows Stop. */
  streaming: boolean;
  /** Glass pane content; when present the chat behind it dims. */
  backstage?: React.ReactNode;
  children: React.ReactNode;
}

/** Word-by-word (or char-by-char for unspaced scripts) input typing reveal. */
function TypedText({ text }: { text: string }) {
  const parts = text.includes(' ') ? text.split(' ').map(w => `${w} `) : text.split('');
  const stagger = text.includes(' ') ? 65 : 40;
  return (
    <>
      {parts.map((part, i) => (
        <span key={i} className="animate-word-in" style={{ animationDelay: `${i * stagger}ms` }}>
          {part}
        </span>
      ))}
      <span className="mockup-caret" aria-hidden="true" />
    </>
  );
}

export function AppFrame({
  chip,
  tokenbar,
  ticked,
  typingText,
  voice = false,
  streaming,
  backstage,
  children,
}: AppFrameProps) {
  const { t, i18n } = useTranslation();
  const lng = i18n.language as Language;

  return (
    <div className="relative rounded-2xl border border-border/60 bg-background/85 backdrop-blur-md shadow-2xl overflow-hidden">
      {/* App bar — logo, presence, psyche mood, benefit chip (no macOS lights) */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/40 bg-card/60">
        <span className="flex h-5 w-5 items-center justify-center rounded-md bg-primary text-[8px] font-extrabold text-primary-foreground">
          LIA
        </span>
        <span className="inline-flex items-center gap-1 rounded-full border border-green-500/30 bg-green-500/10 px-2 py-px text-[9px] text-green-700 dark:text-green-300">
          <span className="h-1.5 w-1.5 rounded-full bg-current" />
          {t('landing.chat_mockup.online')}
        </span>
        <span className="ml-auto inline-flex items-center gap-1 text-[9px] text-muted-foreground">
          {MOOD_EMOJI} {t('landing.chat_mockup.mood')}
        </span>
        <span className="rounded-full border border-border/60 bg-muted px-2 py-px text-[9px] font-semibold text-primary">
          {chip}
        </span>
      </div>

      {/* Conversation token/cost bar — flips and ticks when the answer lands */}
      <div className="flex items-center justify-center gap-2.5 border-b border-border/40 bg-muted/60 px-3 py-1 text-[9px] text-muted-foreground tabular-nums">
        <span>
          <span className="font-semibold text-foreground">
            {formatNumber(tokenbar.totalTokens, lng)}
          </span>{' '}
          {t('landing.chat_mockup.tokens_unit')}
        </span>
        <span aria-hidden="true">·</span>
        <span>
          {formatNumber(tokenbar.messages, lng)}{' '}
          {t('landing.chat_mockup.messages', { count: tokenbar.messages })}
        </span>
        <span aria-hidden="true">·</span>
        <span
          key={String(ticked)}
          className={cn('font-semibold text-foreground', ticked && 'animate-token-tick')}
        >
          {formatEuro(tokenbar.costEur, 3, lng)}
        </span>
      </div>

      {/* Chat area — dims under the backstage glass pane */}
      <div className="relative">
        <div
          className={cn(
            'p-3.5 space-y-2.5 min-h-[340px] transition-[opacity,filter] duration-300',
            backstage && 'opacity-30 saturate-50'
          )}
        >
          {children}
        </div>
        {backstage}
      </div>

      {/* Input bar — typing reveal, voice mic, Send morphing into Stop */}
      <div className="flex items-center gap-2 border-t border-border/40 bg-card/60 px-3 py-2">
        <Paperclip className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate rounded-lg border border-border bg-background px-2.5 py-1.5 text-[11px] leading-none">
          {typingText ? (
            <span className="text-foreground">
              <TypedText text={typingText} />
            </span>
          ) : (
            <span className="text-muted-foreground">
              {t('landing.chat_mockup.input_placeholder')}
            </span>
          )}
        </span>
        <Mic
          className={cn(
            'w-3.5 h-3.5 shrink-0',
            voice && typingText ? 'text-red-500 animate-step-breathe' : 'text-muted-foreground'
          )}
        />
        {streaming ? (
          <span className="inline-flex items-center gap-1 rounded-lg border-[1.5px] border-border px-2.5 py-1 text-[10px] font-semibold text-foreground">
            <Square className="w-2.5 h-2.5 fill-current" />
            {t('landing.chat_mockup.btn_stop')}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-lg bg-primary px-2.5 py-1 text-[10px] font-semibold text-primary-foreground">
            <Send className="w-2.5 h-2.5" />
            {t('landing.chat_mockup.btn_send')}
          </span>
        )}
      </div>
    </div>
  );
}
