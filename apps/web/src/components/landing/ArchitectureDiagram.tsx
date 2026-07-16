'use client';

import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import {
  MessageSquare,
  Router,
  Brain,
  ShieldCheck,
  UserCheck,
  Cog,
  Bot,
  Send,
  RefreshCw,
  Wrench,
  Eye,
  Zap,
  Coins,
  ArrowRight,
  ArrowDown,
} from 'lucide-react';

/**
 * Two-mode execution diagram — entry (request → router) forks into two
 * side-by-side panels: the economical Pipeline (5 numbered steps, human
 * approval highlighted) and the autonomous ReAct loop (reason → act →
 * observe). Both converge on the streaming response. Mirrors the real
 * LangGraph topology (ADR-070).
 */

interface EntryNodeProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  color: string;
  iconColor: string;
}

function EntryNode({ icon: Icon, label, color, iconColor }: EntryNodeProps) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div
        className={cn(
          'w-14 h-14 rounded-2xl glass flex items-center justify-center bg-gradient-to-br',
          color
        )}
      >
        <Icon className={cn('w-6 h-6', iconColor)} />
      </div>
      <span className="text-xs font-medium text-muted-foreground whitespace-nowrap">{label}</span>
    </div>
  );
}

interface PipelineStepProps {
  index: number;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  iconColor: string;
  iconBg: string;
  highlight?: boolean;
  last?: boolean;
}

function PipelineStep({
  index,
  icon: Icon,
  label,
  iconColor,
  iconBg,
  highlight,
  last,
}: PipelineStepProps) {
  return (
    <li className="relative flex items-center gap-3">
      {/* Vertical connector to the next step */}
      {!last && (
        <span
          className="absolute left-[15px] top-8 h-4 w-px bg-gradient-to-b from-border to-primary/40"
          aria-hidden="true"
        />
      )}
      <span
        className={cn(
          'relative z-10 w-8 h-8 rounded-lg flex items-center justify-center bg-gradient-to-br shrink-0',
          iconBg,
          highlight && 'ring-2 ring-amber-500/50'
        )}
      >
        <Icon className={cn('w-4 h-4', iconColor)} />
      </span>
      <span className="text-sm font-medium">
        <span className="text-muted-foreground tabular-nums mr-1.5">{index}.</span>
        {label}
      </span>
    </li>
  );
}

export function ArchitectureDiagram() {
  const { t } = useTranslation();
  const n = (key: string) => t(`landing.architecture.nodes.${key}`);

  const pipelineSteps = [
    {
      icon: Brain,
      label: n('planner'),
      iconColor: 'text-purple-500',
      iconBg: 'from-purple-500/20 to-purple-600/20',
    },
    {
      icon: ShieldCheck,
      label: n('validator'),
      iconColor: 'text-violet-500',
      iconBg: 'from-violet-500/20 to-violet-600/20',
    },
    {
      icon: UserCheck,
      label: n('hitl'),
      iconColor: 'text-amber-500',
      iconBg: 'from-amber-500/20 to-amber-600/20',
      highlight: true,
    },
    {
      icon: Cog,
      label: n('orchestrator'),
      iconColor: 'text-orange-500',
      iconBg: 'from-orange-500/20 to-orange-600/20',
    },
    {
      icon: Bot,
      label: n('agents'),
      iconColor: 'text-emerald-500',
      iconBg: 'from-emerald-500/20 to-emerald-600/20',
    },
  ];

  const reactSteps = [
    { icon: Brain, label: n('reason'), iconColor: 'text-purple-500' },
    { icon: Wrench, label: n('tools'), iconColor: 'text-emerald-500' },
    { icon: Eye, label: n('observe'), iconColor: 'text-sky-500' },
  ];

  return (
    <section
      id="architecture"
      className="landing-section pt-12 pb-20"
      aria-labelledby="architecture-title"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2
            id="architecture-title"
            className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4"
          >
            {t('landing.architecture.title')}
          </h2>
          <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
            {t('landing.architecture.subtitle')}
          </p>
        </div>

        <div role="img" aria-label={t('landing.architecture.title')} className="max-w-3xl mx-auto">
          <div aria-hidden="true">
            {/* Entry: request → router */}
            <div className="flex items-center justify-center gap-3">
              <EntryNode
                icon={MessageSquare}
                label={n('query')}
                color="from-blue-500/20 to-blue-600/20"
                iconColor="text-blue-500"
              />
              <ArrowRight className="w-4 h-4 text-primary/40 -mt-5" />
              <EntryNode
                icon={Router}
                label={n('router')}
                color="from-indigo-500/20 to-indigo-600/20"
                iconColor="text-indigo-500"
              />
            </div>

            {/* Fork connector */}
            <div className="flex justify-center my-3">
              <ArrowDown className="w-4 h-4 text-primary/40" />
            </div>

            {/* The two execution modes, side by side */}
            <div className="grid sm:grid-cols-[1fr_auto_1fr] gap-4 items-stretch">
              {/* Pipeline panel — header stacked (title, badge, desc) so both
                  panels stay homogeneous whatever the locale's text length */}
              <div className="rounded-2xl border border-border/60 bg-card/50 p-5 flex flex-col">
                <span className="text-sm font-semibold">
                  {t('landing.architecture.pipeline_label')}
                </span>
                <span className="self-start inline-flex items-center gap-1 rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30 px-2.5 py-0.5 text-[11px] font-medium mt-1.5">
                  <Coins className="w-3 h-3" />
                  {t('landing.architecture.pipeline_badge')}
                </span>
                <p className="text-xs text-muted-foreground mt-2 mb-4">
                  {t('landing.architecture.pipeline_desc')}
                </p>
                <ol className="space-y-4">
                  {pipelineSteps.map((step, i) => (
                    <PipelineStep
                      key={step.label}
                      index={i + 1}
                      {...step}
                      last={i === pipelineSteps.length - 1}
                    />
                  ))}
                </ol>
              </div>

              {/* "or" divider */}
              <div className="hidden sm:flex flex-col items-center justify-center gap-2">
                <span className="w-px flex-1 bg-border" />
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t('landing.architecture.or_label')}
                </span>
                <span className="w-px flex-1 bg-border" />
              </div>

              {/* ReAct panel — same stacked header as Pipeline */}
              <div className="rounded-2xl border border-border/60 bg-card/50 p-5 flex flex-col">
                <span className="text-sm font-semibold">
                  {t('landing.architecture.react_label')}
                </span>
                <span className="self-start inline-flex items-center gap-1 rounded-full bg-violet-500/10 text-violet-700 dark:text-violet-300 border border-violet-500/30 px-2.5 py-0.5 text-[11px] font-medium mt-1.5">
                  <Zap className="w-3 h-3" />
                  {t('landing.architecture.react_badge')}
                </span>
                <p className="text-xs text-muted-foreground mt-2 mb-4">
                  {t('landing.architecture.react_desc')}
                </p>
                {/* The loop: three steps with a cycling arrow rail */}
                <div className="flex-1 flex items-center justify-center">
                  <div className="flex items-center gap-4">
                    <RefreshCw
                      className="w-6 h-6 text-primary/50 motion-safe:animate-spin shrink-0"
                      style={{ animationDuration: '6s' }}
                    />
                    <ul className="space-y-4">
                      {reactSteps.map(({ icon: Icon, label, iconColor }, i) => (
                        <li key={label} className="relative flex items-center gap-3">
                          {i < reactSteps.length - 1 && (
                            <span
                              className="absolute left-[15px] top-8 h-4 w-px bg-gradient-to-b from-border to-primary/40"
                              aria-hidden="true"
                            />
                          )}
                          <span className="relative z-10 w-8 h-8 rounded-lg bg-muted flex items-center justify-center shrink-0">
                            <Icon className={cn('w-4 h-4', iconColor)} />
                          </span>
                          <span className="text-sm font-medium">{label}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>

            {/* Convergence: streaming response */}
            <div className="flex justify-center my-3">
              <ArrowDown className="w-4 h-4 text-primary/40" />
            </div>
            <div className="flex flex-col items-center gap-1.5">
              <div className="w-14 h-14 rounded-2xl glass flex items-center justify-center bg-gradient-to-br from-green-500/20 to-green-600/20">
                <Send className="w-6 h-6 text-green-500" />
              </div>
              <span className="text-xs font-medium text-muted-foreground">{n('response')}</span>
              <span className="text-[11px] text-muted-foreground">
                {t('landing.architecture.response_hint')}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
