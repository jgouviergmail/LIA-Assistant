import { Mail, Paperclip, Send, Mic, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Translate } from './FeatureCatalog';

/**
 * Chapter chat scenes — the same visual grammar as the hero mockup, with
 * content deliberately complementary to its four acts: the morning briefing
 * (chapter 02) and a HITL *edit* round-trip (chapter 04 — the hero only
 * shows a plain approval). Decorative, rendered inside aria-hidden wrappers.
 */

function SceneFrame({
  t,
  chip,
  children,
}: {
  t: Translate;
  chip: string;
  children: React.ReactNode;
}) {
  return (
    <div className="relative mx-auto w-full max-w-md">
      <div
        className="absolute -inset-5 rounded-[1.75rem] bg-gradient-to-br from-primary/20 via-violet-500/10 to-transparent blur-2xl"
        aria-hidden="true"
      />
      <div className="relative overflow-hidden rounded-2xl border border-border/60 bg-background/85 shadow-xl backdrop-blur-md">
        <div className="flex items-center gap-2 border-b border-border/40 bg-card/60 px-3 py-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-md bg-primary text-[8px] font-extrabold text-primary-foreground">
            LIA
          </span>
          <span className="inline-flex items-center gap-1 rounded-full border border-green-500/30 bg-green-500/10 px-2 py-px text-[9px] text-green-700 dark:text-green-300">
            <span className="h-1.5 w-1.5 rounded-full bg-current" />
            {t('landing.chat_mockup.online')}
          </span>
          <span className="ml-auto rounded-full border border-border/60 bg-muted px-2 py-px text-[9px] font-semibold text-primary">
            {chip}
          </span>
        </div>
        <div className="space-y-2.5 p-3.5">{children}</div>
        <div className="flex items-center gap-2 border-t border-border/40 bg-card/60 px-3 py-2">
          <Paperclip className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="flex-1 truncate rounded-lg border border-border bg-background px-2.5 py-1.5 text-[11px] leading-none text-muted-foreground">
            {t('landing.chat_mockup.input_placeholder')}
          </span>
          <Mic className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="inline-flex items-center gap-1 rounded-lg bg-primary px-2.5 py-1 text-[10px] font-semibold text-primary-foreground">
            <Send className="h-2.5 w-2.5" />
            {t('landing.chat_mockup.btn_send')}
          </span>
        </div>
      </div>
    </div>
  );
}

function UserLine({ text }: { text: string }) {
  return (
    <span className="block">
      <span className="inline-block max-w-[85%] rounded-2xl rounded-tl-[4px] bg-primary px-3 py-1.5 text-xs leading-relaxed text-primary-foreground">
        {text}
      </span>
    </span>
  );
}

function AssistantLine({
  mood,
  variant = 'default',
  children,
}: {
  mood: string;
  variant?: 'default' | 'hitl';
  children: React.ReactNode;
}) {
  return (
    <span className="flex flex-row-reverse items-start gap-2">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border bg-card text-sm leading-none">
        {mood}
      </span>
      <span
        className={cn(
          'flex-1 rounded-2xl rounded-tr-[4px] border px-3 py-2 text-xs leading-relaxed',
          variant === 'hitl'
            ? 'border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-200'
            : 'border-border bg-card text-card-foreground'
        )}
      >
        {children}
      </span>
    </span>
  );
}

/** Chapter 02 — the morning briefing arrives before any question is asked. */
export function SceneBriefing({ t }: { t: Translate }) {
  const k = (s: string) => t(`landing.chapters.c2.${s}`);
  return (
    <SceneFrame t={t} chip={k('s_chip')}>
      <AssistantLine mood="🙂">{k('s_greet')}</AssistantLine>
      <AssistantLine mood="🙂">
        <span className="block rounded-lg border border-border border-l-[3px] border-l-sky-600 bg-background px-2.5 py-1.5">
          <span className="block text-[11px] font-semibold">🌦️ {k('s_weather')}</span>
          <span className="mt-1 flex flex-wrap gap-1">
            <span className="rounded border border-border bg-muted px-1.5 py-px text-[9px] text-muted-foreground">
              {k('s_weather_b1')}
            </span>
            <span className="rounded border border-border bg-muted px-1.5 py-px text-[9px] text-muted-foreground">
              {k('s_weather_b2')}
            </span>
          </span>
        </span>
        <span className="mt-2 block rounded-lg border border-border border-l-[3px] border-l-green-600 bg-background px-2.5 py-1.5">
          <span className="block text-[11px] font-semibold">📅 {k('s_day')}</span>
          <span className="mt-1 flex flex-wrap gap-1">
            {(['s_day_b1', 's_day_b2', 's_day_b3'] as const).map(b => (
              <span
                key={b}
                className="rounded border border-border bg-muted px-1.5 py-px text-[9px] tabular-nums text-muted-foreground"
              >
                {k(b)}
              </span>
            ))}
          </span>
        </span>
      </AssistantLine>
    </SceneFrame>
  );
}

/** Chapter 04 — approval with an edit round-trip: control beyond yes/no. */
export function SceneEdit({ t }: { t: Translate }) {
  const k = (s: string) => t(`landing.chapters.c4.${s}`);
  return (
    <SceneFrame t={t} chip={k('s_chip')}>
      <AssistantLine mood="🙂" variant="hitl">
        <ShieldCheck className="mr-1 inline h-3 w-3 align-[-1.5px] text-amber-600 dark:text-amber-400" />
        {k('s_hitl')}
        <span className="mt-2 block rounded-lg border border-amber-500/25 bg-background/70 px-2.5 py-1.5 text-foreground">
          <span className="block text-[10px] text-muted-foreground">
            <Mail className="mr-1 inline h-3 w-3 align-[-1.5px] text-amber-600 dark:text-amber-400" />
            {k('s_subject')}
          </span>
          <span className="mt-0.5 block text-[11px] italic text-muted-foreground">
            {k('s_quote')}
          </span>
        </span>
      </AssistantLine>
      <UserLine text={k('s_user')} />
      <AssistantLine mood="🙂">{k('s_reply')}</AssistantLine>
    </SceneFrame>
  );
}
