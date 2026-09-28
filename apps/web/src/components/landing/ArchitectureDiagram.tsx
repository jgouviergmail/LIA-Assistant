'use client';

import { useTranslation } from 'react-i18next';
import {
  ClipboardCheck,
  Compass,
  Eye,
  GitBranch,
  ListChecks,
  ListOrdered,
  MessageSquareText,
  RefreshCw,
  ShieldCheck,
  Workflow,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const MODES = [
  {
    id: 'pipeline',
    icon: Workflow,
    accent: 'border-emerald-500/60',
    ink: 'text-emerald-700 dark:text-emerald-300',
    tint: 'bg-emerald-500/10',
    steps: [
      { id: 'plan', icon: ListOrdered },
      { id: 'validate', icon: ClipboardCheck },
      { id: 'execute', icon: GitBranch },
    ],
  },
  {
    id: 'react',
    icon: Compass,
    accent: 'border-violet-500/60',
    ink: 'text-violet-700 dark:text-violet-300',
    tint: 'bg-violet-500/10',
    steps: [
      { id: 'explore', icon: Compass },
      { id: 'observe', icon: Eye },
      { id: 'adapt', icon: RefreshCw },
    ],
  },
] as const;

const SHARED = [
  { id: 'control', icon: ShieldCheck },
  { id: 'trace', icon: ListChecks },
  { id: 'result', icon: MessageSquareText },
] as const;

/** A readable comparison of execution choices, with their shared safeguards. */
export function ArchitectureDiagram() {
  const { t } = useTranslation();
  const a = (key: string) => t(`landing.architecture.${key}`);

  return (
    <section
      id="architecture"
      className="mt-10 border-t border-border pt-8 sm:pt-10"
      aria-labelledby="architecture-title"
    >
      <div className="max-w-3xl">
        <h2
          id="architecture-title"
          className="flex items-center gap-3 text-2xl font-semibold tracking-tight sm:text-3xl"
        >
          <Workflow className="size-6 shrink-0 text-primary" aria-hidden="true" />
          {a('title')}
        </h2>
        <p className="mt-3 text-base leading-relaxed text-muted-foreground">{a('subtitle')}</p>
      </div>

      <div className="mt-7 grid gap-6 lg:grid-cols-2 lg:gap-y-0">
        {MODES.map(({ id, icon: Icon, accent, ink, tint, steps }) => (
          <article
            key={id}
            className={cn(
              'min-w-0 border-t-2 bg-background/50 px-4 pb-5 pt-5 sm:px-5 lg:row-span-4 lg:grid lg:grid-rows-subgrid',
              accent
            )}
            aria-labelledby={`architecture-${id}`}
          >
            <div className="flex items-center gap-3">
              <span
                className={cn('flex size-11 shrink-0 items-center justify-center rounded-xl', tint)}
              >
                <Icon className={cn('size-6', ink)} aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <h3 id={`architecture-${id}`} className="text-lg font-semibold">
                  {a(`${id}_label`)}
                </h3>
                <p className={cn('mt-0.5 text-sm font-medium', ink)}>{a(`${id}_badge`)}</p>
              </div>
            </div>
            <p className="mt-4 text-sm leading-6 text-muted-foreground">{a(`${id}_desc`)}</p>

            <ol className="mt-6 space-y-5">
              {steps.map(({ id: step, icon: StepIcon }, index) => (
                <li key={step} className="flex items-start gap-3">
                  <span
                    className={cn(
                      'mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular-nums',
                      ink,
                      tint
                    )}
                    aria-hidden="true"
                  >
                    {index + 1}
                  </span>
                  <div>
                    <h4 className="flex items-center gap-2 text-sm font-semibold">
                      <StepIcon className={cn('size-4 shrink-0', ink)} aria-hidden="true" />
                      {a(`flow.${id}.${step}_title`)}
                    </h4>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">
                      {a(`flow.${id}.${step}_body`)}
                    </p>
                  </div>
                </li>
              ))}
            </ol>

            <div className="mt-6 border-t border-border pt-4">
              <p className={cn('flex items-center gap-2 text-xs font-medium', ink)}>
                <Zap className="size-3.5 shrink-0" aria-hidden="true" />
                {a('example_label')}
              </p>
              <p className="mt-1.5 text-sm leading-6">{a(`${id}_example`)}</p>
            </div>
          </article>
        ))}
      </div>

      <div className="mt-7 border-t border-border pt-6">
        <h3 className="flex items-center gap-2 text-base font-semibold">
          <ShieldCheck className="size-5 shrink-0 text-primary" aria-hidden="true" />
          {a('shared_title')}
        </h3>
        <ul className="mt-4 grid gap-5 md:grid-cols-3">
          {SHARED.map(({ id, icon: Icon }) => (
            <li key={id}>
              <h4 className="flex items-center gap-2 text-sm font-semibold">
                <Icon className="size-4 shrink-0 text-primary" aria-hidden="true" />
                {a(`shared_${id}_title`)}
              </h4>
              <p className="mt-1.5 text-sm leading-6 text-muted-foreground">
                {a(`shared_${id}_body`)}
              </p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
