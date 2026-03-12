'use client';

import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import {
  MessageSquare, Router, Brain, ShieldCheck,
  UserCheck, Cog, Bot, Send,
} from 'lucide-react';

const PIPELINE_NODES = [
  { key: 'query', icon: MessageSquare, color: 'from-blue-500/20 to-blue-600/20', iconColor: 'text-blue-500' },
  { key: 'router', icon: Router, color: 'from-indigo-500/20 to-indigo-600/20', iconColor: 'text-indigo-500' },
  { key: 'planner', icon: Brain, color: 'from-purple-500/20 to-purple-600/20', iconColor: 'text-purple-500' },
  { key: 'validator', icon: ShieldCheck, color: 'from-violet-500/20 to-violet-600/20', iconColor: 'text-violet-500' },
  { key: 'hitl', icon: UserCheck, color: 'from-amber-500/20 to-amber-600/20', iconColor: 'text-amber-500' },
  { key: 'orchestrator', icon: Cog, color: 'from-orange-500/20 to-orange-600/20', iconColor: 'text-orange-500' },
  { key: 'agents', icon: Bot, color: 'from-emerald-500/20 to-emerald-600/20', iconColor: 'text-emerald-500' },
  { key: 'response', icon: Send, color: 'from-green-500/20 to-green-600/20', iconColor: 'text-green-500' },
] as const;

export function ArchitectureDiagram() {
  const { t } = useTranslation();

  return (
    <section id="architecture" className="landing-section pt-12 pb-24" aria-labelledby="architecture-title">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-16">
          <h2 id="architecture-title" className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4">
            {t('landing.architecture.title')}
          </h2>
          <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
            {t('landing.architecture.subtitle')}
          </p>
        </div>

        {/* Pipeline diagram */}
        <div role="img" aria-label={t('landing.architecture.title')}>

          {/* Mobile: vertical pipeline */}
          <div className="flex mobile:hidden flex-col items-center gap-1" aria-hidden="true">
            {PIPELINE_NODES.map(({ key, icon: Icon, color, iconColor }, i) => (
              <div key={key} className="flex flex-col items-center">
                <div className="flex items-center gap-3 w-56">
                  <div
                    className={cn(
                      'w-12 h-12 rounded-xl glass shrink-0',
                      'flex items-center justify-center',
                      'bg-gradient-to-br',
                      color,
                    )}
                  >
                    <Icon className={cn('w-6 h-6', iconColor)} />
                  </div>
                  <span className="text-sm font-medium text-muted-foreground">
                    {t(`landing.architecture.nodes.${key}`)}
                  </span>
                </div>
                {i < PIPELINE_NODES.length - 1 && (
                  <div className="flex flex-col items-center my-1">
                    <div className="w-px h-3 bg-gradient-to-b from-border to-primary/40" />
                    <div className="w-0 h-0 border-l-[4px] border-l-transparent border-r-[4px] border-r-transparent border-t-[5px] border-t-primary/40" />
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Desktop: horizontal pipeline */}
          <div className="hidden mobile:flex items-center gap-2 px-4 justify-center" aria-hidden="true">
            {PIPELINE_NODES.map(({ key, icon: Icon, color, iconColor }, i) => (
              <div key={key} className="flex items-center">
                {/* Node */}
                <div className="flex flex-col items-center gap-2">
                  <div
                    className={cn(
                      'w-20 h-20 rounded-2xl glass',
                      'flex items-center justify-center',
                      'bg-gradient-to-br',
                      color,
                      'hover:scale-110 transition-transform cursor-default'
                    )}
                  >
                    <Icon className={cn('w-8 h-8', iconColor)} />
                  </div>
                  <span className="text-xs font-medium text-muted-foreground whitespace-nowrap">
                    {t(`landing.architecture.nodes.${key}`)}
                  </span>
                </div>

                {/* Arrow */}
                {i < PIPELINE_NODES.length - 1 && (
                  <div className="flex items-center mx-1 -mt-6">
                    <div className="w-6 h-px bg-gradient-to-r from-border to-primary/40" />
                    <div className="w-0 h-0 border-t-[4px] border-t-transparent border-b-[4px] border-b-transparent border-l-[6px] border-l-primary/40" />
                  </div>
                )}
              </div>
            ))}
          </div>

        </div>
      </div>
    </section>
  );
}
