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
import { Puzzle } from 'lucide-react';
import { DebugChip, DebugSection, EmptySection, MetricRow } from '../shared';
import type { DebugTone } from '../../utils/tones';
import type { SkillsMetrics } from '@/types/chat';

export interface SkillsSectionProps {
  data: SkillsMetrics | undefined;
}

/** Activation mode tones: bypass = best path, planner = planned, tool = LLM-decided. */
const ACTIVATION_TONE: Record<string, DebugTone> = {
  bypass: 'success',
  planner: 'info',
  tool: 'warning',
};

export const SkillsSection = React.memo(function SkillsSection({ data }: SkillsSectionProps) {
  if (!data) {
    return (
      <EmptySection
        value="skills"
        title="Skills"
        icon={Puzzle}
        message="No skill was activated on this turn."
      />
    );
  }

  return (
    <DebugSection
      value="skills"
      title="Skills"
      icon={Puzzle}
      badge={
        <>
          <DebugChip tone="info">{data.skill_name}</DebugChip>
          <DebugChip tone={ACTIVATION_TONE[data.activation_mode] ?? 'neutral'}>
            {data.activation_mode}
          </DebugChip>
        </>
      }
    >
      <MetricRow label="Skill" value={data.skill_name} />
      <MetricRow label="Mode" value={data.activation_mode} />
      <MetricRow label="Deterministic" value={data.is_deterministic} />
      {data.scope && <MetricRow label="Scope" value={data.scope} />}
      {data.category && <MetricRow label="Category" value={data.category} />}
      {data.priority !== undefined && <MetricRow label="Priority" value={data.priority} />}

      {/* Capability flags */}
      <div className="flex flex-wrap items-center gap-2 rounded bg-muted/20 p-2 text-[10px] text-muted-foreground">
        {data.has_scripts && <DebugChip tone="warning">scripts/</DebugChip>}
        {data.has_references && <DebugChip tone="neutral">references/</DebugChip>}
        {!data.has_scripts && !data.has_references && (
          <span className="italic">Pure instructions (no bundled resources)</span>
        )}
      </div>
    </DebugSection>
  );
});
