'use client';

import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { User, Bot, Check, ShieldCheck } from 'lucide-react';

interface BubbleProps {
  isUser: boolean;
  children: React.ReactNode;
  delay: string;
  icon?: React.ReactNode;
  variant?: 'default' | 'hitl' | 'success';
}

function Bubble({ isUser, children, delay, icon, variant = 'default' }: BubbleProps) {
  const variantStyles = {
    default: isUser
      ? 'bg-primary text-primary-foreground'
      : 'bg-card text-card-foreground border border-border',
    hitl: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-500/30',
    success: 'bg-green-500/10 text-green-700 dark:text-green-300 border border-green-500/30',
  };

  return (
    <div
      className={cn(
        'flex gap-2 items-start opacity-0 animate-chat-bubble',
        isUser ? 'flex-row-reverse' : 'flex-row',
        delay
      )}
    >
      <div
        className={cn(
          'flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center',
          isUser ? 'bg-primary/20' : 'bg-primary/10'
        )}
      >
        {icon || (isUser ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />)}
      </div>
      <div
        className={cn(
          'rounded-2xl px-3.5 py-2 text-sm max-w-[75%] leading-relaxed',
          variantStyles[variant]
        )}
      >
        {children}
      </div>
    </div>
  );
}

export function ChatMockup() {
  const { t } = useTranslation();

  return (
    <div className="relative w-full max-w-md mx-auto">
      {/* Window frame */}
      <div className="rounded-2xl border border-border/60 bg-background/80 backdrop-blur-sm shadow-xl overflow-hidden">
        {/* Title bar */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/40 bg-card/50">
          <div className="flex gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-red-400/70" />
            <div className="w-2.5 h-2.5 rounded-full bg-amber-400/70" />
            <div className="w-2.5 h-2.5 rounded-full bg-green-400/70" />
          </div>
          <span className="text-xs text-muted-foreground ml-2 font-medium">LIA</span>
        </div>

        {/* Chat area */}
        <div className="p-4 space-y-3 min-h-[260px]">
          {/* User message */}
          <Bubble isUser delay="delay-300">
            {t('landing.chat_mockup.user_message')}
          </Bubble>

          {/* LIA planning */}
          <Bubble isUser={false} delay="delay-1000">
            {t('landing.chat_mockup.lia_planning')}
          </Bubble>

          {/* LIA HITL */}
          <Bubble
            isUser={false}
            delay="delay-1500"
            variant="hitl"
            icon={<ShieldCheck className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />}
          >
            {t('landing.chat_mockup.lia_hitl')}
          </Bubble>

          {/* User approve */}
          <Bubble isUser delay="delay-2000">
            {t('landing.chat_mockup.user_approve')}
          </Bubble>

          {/* LIA done */}
          <Bubble
            isUser={false}
            delay="delay-2500"
            variant="success"
            icon={<Check className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />}
          >
            {t('landing.chat_mockup.lia_done')}
          </Bubble>
        </div>
      </div>
    </div>
  );
}
