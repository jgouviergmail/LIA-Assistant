'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import {
  User,
  Bot,
  Check,
  ShieldCheck,
  Mail,
  Pencil,
  Send,
  Sun,
  CloudSun,
  CloudRain,
  Sparkles,
  LayoutGrid,
  FileText,
} from 'lucide-react';

/**
 * Animated hero conversation — rotates through three real LIA scenarios,
 * each showcasing one of the actual display modes:
 *  1. Humorous email with HITL draft approval (rich HTML + action buttons)
 *  2. Weather HTML card + proactive cross-domain initiative
 *  3. Multi-agent place search answered in Markdown
 *
 * Step reveal is timeout-driven and loops forever; under
 * `prefers-reduced-motion` scenario 1 renders statically. Purely decorative:
 * exposed as a single `role="img"`, inner "buttons" are non-interactive spans.
 */

type StepKind =
  | 'user'
  | 'planning'
  | 'hitl'
  | 'approve'
  | 'done'
  | 'status'
  | 'weather'
  | 'initiative'
  | 'markdown';

interface Step {
  kind: StepKind;
  at: number;
}

interface Scenario {
  /** i18n key suffix of the title-bar mode chip + its icon */
  chip: 'hitl' | 'cards' | 'markdown';
  steps: Step[];
  holdMs: number;
}

const SCENARIOS: Scenario[] = [
  {
    chip: 'hitl',
    steps: [
      { kind: 'user', at: 400 },
      { kind: 'planning', at: 1400 },
      { kind: 'hitl', at: 2600 },
      { kind: 'approve', at: 4800 },
      { kind: 'done', at: 5800 },
    ],
    holdMs: 9800,
  },
  {
    chip: 'cards',
    steps: [
      { kind: 'user', at: 400 },
      { kind: 'weather', at: 1600 },
      { kind: 'initiative', at: 3600 },
    ],
    holdMs: 9200,
  },
  {
    chip: 'markdown',
    steps: [
      { kind: 'user', at: 400 },
      { kind: 'status', at: 1400 },
      { kind: 'markdown', at: 3200 },
    ],
    holdMs: 8800,
  },
];

const CYCLE_FADE_MS = 600;
/** Typing dots show from user message until the first LIA step lands. */
const TYPING_FROM_STEP = 1;

interface BubbleProps {
  isUser?: boolean;
  children: React.ReactNode;
  icon?: React.ReactNode;
  variant?: 'default' | 'hitl' | 'success' | 'initiative';
  wide?: boolean;
}

function Bubble({ isUser = false, children, icon, variant = 'default', wide = false }: BubbleProps) {
  const variantStyles = {
    default: isUser
      ? 'bg-primary text-primary-foreground'
      : 'bg-card text-card-foreground border border-border',
    hitl: 'bg-amber-500/10 text-amber-800 dark:text-amber-200 border border-amber-500/30',
    success: 'bg-green-500/10 text-green-700 dark:text-green-300 border border-green-500/30',
    initiative: 'bg-violet-500/10 text-violet-800 dark:text-violet-200 border border-violet-500/30',
  };

  return (
    <div
      className={cn(
        'flex gap-2 items-start animate-chat-bubble',
        isUser ? 'flex-row-reverse' : 'flex-row'
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
          'rounded-2xl px-3.5 py-2 text-sm leading-relaxed',
          wide ? 'w-[85%]' : 'max-w-[80%]',
          variantStyles[variant]
        )}
      >
        {children}
      </div>
    </div>
  );
}

/** Three softly bouncing dots shown while LIA "thinks". */
function TypingDots() {
  return (
    <div className="flex gap-2 items-start animate-chat-bubble">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center">
        <Bot className="w-3.5 h-3.5" />
      </div>
      <div className="rounded-2xl px-3.5 py-2.5 bg-card border border-border flex items-center gap-1">
        {[0, 150, 300].map(delay => (
          <span
            key={delay}
            className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 motion-safe:animate-bounce"
            style={{ animationDelay: `${delay}ms`, animationDuration: '1s' }}
          />
        ))}
      </div>
    </div>
  );
}

/** Scenario 2 — weather HTML card, faithful to LIA's rich card mode. */
function WeatherCard({ t }: { t: (key: string) => string }) {
  const slots = [
    { icon: Sun, label: t('landing.chat_mockup.s2_slot_morning'), temp: '12°' },
    { icon: CloudSun, label: t('landing.chat_mockup.s2_slot_afternoon'), temp: '16°' },
    { icon: CloudRain, label: t('landing.chat_mockup.s2_slot_evening'), temp: '14°' },
  ];
  return (
    <div className="flex gap-2 items-start animate-chat-bubble">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center">
        <Bot className="w-3.5 h-3.5" />
      </div>
      <div className="w-[85%] rounded-xl border border-border bg-card overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-sky-500/15 to-blue-500/10 border-b border-border/60">
          <CloudSun className="w-4 h-4 text-sky-600 dark:text-sky-400" />
          <span className="text-xs font-semibold">{t('landing.chat_mockup.s2_card_title')}</span>
        </div>
        <div className="px-3 py-2.5 flex items-center gap-3">
          <span className="text-2xl font-bold tabular-nums">16°</span>
          <span className="text-xs text-muted-foreground leading-snug">
            {t('landing.chat_mockup.s2_card_desc')}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-px bg-border/60 border-t border-border/60">
          {slots.map(({ icon: Icon, label, temp }) => (
            <div key={label} className="bg-card px-2 py-1.5 text-center">
              <Icon className="w-3.5 h-3.5 mx-auto text-muted-foreground" />
              <div className="text-[10px] text-muted-foreground mt-0.5">{label}</div>
              <div className="text-xs font-semibold tabular-nums">{temp}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Scenario 3 — Markdown-mode reply (numbered list, bold names). */
function MarkdownReply({ t }: { t: (key: string) => string }) {
  const places = [
    { name: 'Café Bretelle', rating: '4,7', walk: 4 },
    { name: "L'Atelier", rating: '4,6', walk: 7 },
    { name: 'Oor Café', rating: '4,5', walk: 9 },
  ];
  return (
    <Bubble wide>
      <span className="block text-sm mb-1.5">{t('landing.chat_mockup.s3_md_intro')}</span>
      <ol className="space-y-1 text-sm">
        {places.map(({ name, rating, walk }, i) => (
          <li key={name} className="flex items-baseline gap-1.5">
            <span className="text-muted-foreground tabular-nums">{i + 1}.</span>
            <span>
              <strong>{name}</strong>
              <span className="text-muted-foreground">
                {' '}
                — ★ {rating} · {walk} {t('landing.chat_mockup.s3_md_walk')}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </Bubble>
  );
}

const CHIP_ICONS = { hitl: ShieldCheck, cards: LayoutGrid, markdown: FileText } as const;

export function ChatMockup() {
  const { t } = useTranslation();
  const [scenarioIndex, setScenarioIndex] = useState(0);
  const [stepCount, setStepCount] = useState(0);
  const [fading, setFading] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setReducedMotion(true);
      setStepCount(SCENARIOS[0].steps.length);
      return;
    }

    let cancelled = false;
    let index = 0;

    const runCycle = () => {
      if (cancelled) return;
      const scenario = SCENARIOS[index];
      setScenarioIndex(index);
      setFading(false);
      setStepCount(0);
      timersRef.current = scenario.steps.map((step, i) =>
        setTimeout(() => setStepCount(i + 1), step.at)
      );
      timersRef.current.push(
        setTimeout(() => setFading(true), scenario.holdMs),
        setTimeout(() => {
          index = (index + 1) % SCENARIOS.length;
          runCycle();
        }, scenario.holdMs + CYCLE_FADE_MS)
      );
    };

    runCycle();
    return () => {
      cancelled = true;
      timersRef.current.forEach(clearTimeout);
    };
  }, []);

  const scenario = SCENARIOS[scenarioIndex];
  const visibleSteps = scenario.steps.slice(0, stepCount);
  const showTyping =
    !reducedMotion && stepCount === TYPING_FROM_STEP && stepCount < scenario.steps.length;
  const approvePressed = visibleSteps.some(s => s.kind === 'approve');
  const ChipIcon = CHIP_ICONS[scenario.chip];
  const sk = scenarioIndex === 0 ? '' : `s${scenarioIndex + 1}_`;

  const renderStep = (step: Step, i: number) => {
    switch (step.kind) {
      case 'user':
        return (
          <Bubble key={i} isUser>
            {t(`landing.chat_mockup.${sk}user_message`)}
          </Bubble>
        );
      case 'planning':
        return <Bubble key={i}>{t('landing.chat_mockup.lia_planning')}</Bubble>;
      case 'status':
        return (
          <Bubble key={i}>
            <span className="italic text-muted-foreground">
              {t('landing.chat_mockup.s3_status')}
            </span>
          </Bubble>
        );
      case 'hitl':
        return (
          <Bubble
            key={i}
            variant="hitl"
            icon={<ShieldCheck className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />}
          >
            <span>{t('landing.chat_mockup.lia_hitl')}</span>
            <span className="mt-2 flex items-center gap-2 rounded-lg border border-amber-500/25 bg-background/60 px-2.5 py-1.5 text-xs text-foreground/80">
              <Mail className="w-3.5 h-3.5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
              <span className="italic truncate">{t('landing.chat_mockup.draft_subject')}</span>
            </span>
            <span className="mt-2 flex gap-2">
              <span
                className={cn(
                  'inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-transform duration-200',
                  'bg-primary text-primary-foreground',
                  approvePressed && 'scale-95 ring-2 ring-primary/40'
                )}
              >
                <Send className="w-3 h-3" />
                {t('landing.chat_mockup.btn_send')}
              </span>
              <span className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground">
                <Pencil className="w-3 h-3" />
                {t('landing.chat_mockup.btn_edit')}
              </span>
            </span>
          </Bubble>
        );
      case 'approve':
        return (
          <Bubble key={i} isUser>
            {t('landing.chat_mockup.user_approve')}
          </Bubble>
        );
      case 'done':
        return (
          <Bubble
            key={i}
            variant="success"
            icon={<Check className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />}
          >
            {t('landing.chat_mockup.lia_done')}
          </Bubble>
        );
      case 'weather':
        return <WeatherCard key={i} t={t} />;
      case 'initiative':
        return (
          <Bubble
            key={i}
            variant="initiative"
            icon={<Sparkles className="w-3.5 h-3.5 text-violet-600 dark:text-violet-400" />}
            wide
          >
            {t('landing.chat_mockup.s2_initiative')}
          </Bubble>
        );
      case 'markdown':
        return <MarkdownReply key={i} t={t} />;
    }
  };

  return (
    <div
      className="relative w-full max-w-md mx-auto"
      role="img"
      aria-label={t('landing.chat_mockup.aria')}
    >
      {/* Ambient glow behind the card */}
      <div
        className="absolute -inset-6 rounded-[2rem] bg-gradient-to-br from-primary/25 via-violet-500/15 to-transparent blur-2xl"
        aria-hidden="true"
      />

      {/* Window frame */}
      <div
        aria-hidden="true"
        className={cn(
          'relative rounded-2xl border border-border/60 bg-background/85 backdrop-blur-md shadow-2xl overflow-hidden transition-opacity',
          fading ? 'opacity-0 duration-500' : 'opacity-100 duration-300'
        )}
      >
        {/* Title bar — the mode chip mirrors the scenario's display mode */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/40 bg-card/50">
          <div className="flex gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-red-400/70" />
            <div className="w-2.5 h-2.5 rounded-full bg-amber-400/70" />
            <div className="w-2.5 h-2.5 rounded-full bg-green-400/70" />
          </div>
          <span className="text-xs text-muted-foreground ml-2 font-medium">LIA</span>
          <span className="ml-auto inline-flex items-center gap-1 text-[10px] font-medium text-muted-foreground/80 border border-border/50 rounded-full px-2 py-0.5">
            <ChipIcon className="w-3 h-3 text-primary" />
            {t(`landing.chat_mockup.chip_${scenario.chip}`)}
          </span>
        </div>

        {/* Chat area */}
        <div className="p-4 space-y-3 min-h-[330px]">
          {visibleSteps.map((step, i) => renderStep(step, i))}
          {showTyping && <TypingDots />}
        </div>
      </div>
    </div>
  );
}
