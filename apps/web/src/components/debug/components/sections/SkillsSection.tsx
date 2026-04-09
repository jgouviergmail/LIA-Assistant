/**
 * Skills Section Component
 *
 * Displays activated skill information for this turn:
 * - Skill name and scope (admin/user)
 * - Activation mode (bypass/planner/tool)
 * - Category and priority
 * - Flags (deterministic, scripts, references)
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import { MetricRow, EmptySection } from '../shared';
import type { SkillsMetrics } from '@/types/chat';

export interface SkillsSectionProps {
  data: SkillsMetrics | undefined;
}

function getActivationBadge(mode: string): { label: string; className: string } {
  switch (mode) {
    case 'bypass':
      return {
        label: 'BYPASS',
        className: 'bg-green-500/20 text-green-400 border-green-500/30',
      };
    case 'planner':
      return {
        label: 'PLANNER',
        className: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
      };
    case 'tool':
      return {
        label: 'TOOL',
        className: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
      };
    default:
      return {
        label: mode.toUpperCase(),
        className: 'bg-muted/50 text-muted-foreground border-border/50',
      };
  }
}

export const SkillsSection = React.memo(function SkillsSection({ data }: SkillsSectionProps) {
  if (!data) {
    return <EmptySection value="skills" title="Skills" />;
  }

  const activation = getActivationBadge(data.activation_mode);

  return (
    <AccordionItem value="skills">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Skills</span>
          <span
            className={cn(
              'text-xs px-1.5 py-0.5 rounded font-medium border',
              'bg-cyan-500/20 text-cyan-400 border-cyan-500/30'
            )}
          >
            {data.skill_name}
          </span>
          <span className={cn('text-[10px] px-1 py-0.5 rounded border', activation.className)}>
            {activation.label}
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          <MetricRow label="Skill" value={data.skill_name} />
          <MetricRow label="Mode" value={data.activation_mode} />
          <MetricRow label="Deterministic" value={data.is_deterministic} />
          {data.scope && <MetricRow label="Scope" value={data.scope} />}
          {data.category && <MetricRow label="Category" value={data.category} />}
          {data.priority !== undefined && <MetricRow label="Priority" value={data.priority} />}

          {/* Capability flags */}
          <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground p-2 bg-muted/20 rounded">
            {data.has_scripts && (
              <span className="px-1.5 py-0.5 rounded border bg-amber-500/20 text-amber-400 border-amber-500/30">
                scripts/
              </span>
            )}
            {data.has_references && (
              <span className="px-1.5 py-0.5 rounded border bg-teal-500/20 text-teal-400 border-teal-500/30">
                references/
              </span>
            )}
            {!data.has_scripts && !data.has_references && (
              <span className="italic">Pure instructions (no bundled resources)</span>
            )}
          </div>
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
