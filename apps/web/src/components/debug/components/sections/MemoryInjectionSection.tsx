/**
 * Memory Injection Section Component
 *
 * Displays memories injected into the psychological profile with their
 * semantic similarity scores. Allows tuning of min_score and max_results.
 */

import React from 'react';
import { Brain } from 'lucide-react';
import {
  DebugChip,
  DebugSection,
  EmptySection,
  ScoreBar,
  ScoreLegend,
  SubSectionHeader,
} from '../shared';
import { DEBUG_TEXT_SIZES } from '../../utils/constants';
import { getEmotionalLabel } from '../../utils/formatters';
import type { DebugTone } from '../../utils/tones';
import type { MemoryInjectionMetrics, MemoryInjectionDebugItem } from '@/types/chat';

export interface MemoryInjectionSectionProps {
  data: MemoryInjectionMetrics | undefined;
}

/** Aggregated emotional state tone */
function emotionalStateTone(state: string): DebugTone {
  if (state === 'comfort') return 'success';
  if (state === 'danger') return 'destructive';
  return 'neutral';
}

/**
 * Displays an injected memory with its score
 */
const MemoryRow = React.memo(function MemoryRow({
  memory,
  index,
}: {
  memory: MemoryInjectionDebugItem;
  index: number;
}) {
  const emotional = getEmotionalLabel(memory.emotional_weight);

  return (
    <div className="flex flex-col gap-1 rounded bg-muted/10 px-2 py-1.5 text-xs">
      <div className="flex items-center gap-2">
        {/* Rank */}
        <span
          className={`${DEBUG_TEXT_SIZES.tiny} w-4 flex-shrink-0 text-right text-muted-foreground`}
        >
          #{index + 1}
        </span>

        {/* Score bar + value (shared primitive, similarity space) */}
        <ScoreBar score={memory.score} space="similarity" className="flex-shrink-0" />

        {/* Category badge */}
        <DebugChip tone="info">{memory.category}</DebugChip>

        {/* Emotional weight badge */}
        <DebugChip tone={emotional.tone} title={`Emotional weight: ${memory.emotional_weight}`}>
          {emotional.label}
        </DebugChip>
      </div>

      {/* Content (truncated) */}
      <div className="truncate pl-6 text-[11px] text-muted-foreground" title={memory.content}>
        {memory.content}
      </div>
    </div>
  );
});

/**
 * Section Memory Injection
 *
 * Displays memories injected into the psychological profile
 * with their similarity scores for parameter tuning.
 */
export const MemoryInjectionSection = React.memo(function MemoryInjectionSection({
  data,
}: MemoryInjectionSectionProps) {
  if (!data) {
    return (
      <EmptySection
        value="memory-injection"
        title="Memory Injection"
        icon={Brain}
        message="No memory-injection data for this request."
      />
    );
  }

  const hasMemories = data.memory_count > 0;

  return (
    <DebugSection
      value="memory-injection"
      title="Memory Injection"
      icon={Brain}
      badge={
        <>
          <DebugChip tone={hasMemories ? 'info' : 'neutral'}>{data.memory_count}</DebugChip>
          <DebugChip tone={emotionalStateTone(data.emotional_state)}>
            {data.emotional_state}
          </DebugChip>
        </>
      }
    >
      {/* Settings summary */}
      <div className="flex flex-wrap items-center gap-3 rounded bg-muted/20 p-2 text-[10px] text-muted-foreground">
        <span>
          <strong>min_score:</strong> <span className="font-mono">{data.settings.min_score}</span>
        </span>
        <span>
          <strong>max_results:</strong>{' '}
          <span className="font-mono">{data.settings.max_results}</span>
        </span>
      </div>

      {/* Memories list */}
      {hasMemories ? (
        <div className="space-y-1">
          <SubSectionHeader label={`Injected memories (${data.memory_count})`} />
          <div className="max-h-[300px] space-y-1 overflow-y-auto">
            {data.memories.map((memory, index) => (
              <MemoryRow key={`${memory.category}-${index}`} memory={memory} index={index} />
            ))}
          </div>
        </div>
      ) : (
        <div className="rounded bg-muted/20 p-2 text-xs italic text-muted-foreground">
          No memory was injected for this request.
        </div>
      )}

      {/* Score distribution legend */}
      {hasMemories && <ScoreLegend space="similarity" className="border-t border-border/50" />}
    </DebugSection>
  );
});
