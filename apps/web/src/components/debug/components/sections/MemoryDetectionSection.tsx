/**
 * Memory Extraction Section Component
 *
 * Displays memories created, updated, or deleted by the background
 * extraction pipeline. Shows action type, category, emotional weight,
 * and storage status for each memory action.
 */

import React from 'react';
import { BrainCog } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  ActionBadge,
  DebugChip,
  DebugSection,
  EmptySection,
  ScoreBar,
  SubSectionHeader,
} from '../shared';
import { DEBUG_TEXT_SIZES } from '../../utils/constants';
import { getEmotionalLabel } from '../../utils/formatters';
import { TONE_BAR, TONE_TEXT } from '../../utils/tones';
import type { MemoryDetectionMetrics, ExtractedMemory, ExistingSimilarMemory } from '@/types/chat';

export interface MemoryDetectionSectionProps {
  data: MemoryDetectionMetrics | undefined;
}

/**
 * Single memory action row with action badge + details
 */
const MemoryActionRow = React.memo(function MemoryActionRow({
  memory,
}: {
  memory: ExtractedMemory;
}) {
  const action = memory.action ?? 'create';
  const emotional = getEmotionalLabel(memory.emotional_weight ?? 0);
  const importance = memory.importance ?? 0;

  return (
    <div className="flex flex-col gap-1 rounded bg-muted/10 px-2 py-2 text-xs">
      <div className="flex items-center gap-2">
        {/* Storage status */}
        <span
          className={cn(
            'h-2 w-2 flex-shrink-0 rounded-full',
            memory.stored ? TONE_BAR.success : TONE_BAR.destructive
          )}
          title={memory.stored ? 'Applied successfully' : 'Failed'}
        />

        {/* Action badge */}
        <ActionBadge action={action} />

        {/* Category badge */}
        <DebugChip tone="info">{memory.category}</DebugChip>

        {/* Emotional weight */}
        <DebugChip tone={emotional.tone} title={`Emotional weight: ${memory.emotional_weight}`}>
          {emotional.label} ({(memory.emotional_weight ?? 0) > 0 ? '+' : ''}
          {memory.emotional_weight ?? 0})
        </DebugChip>

        {/* Importance */}
        {action !== 'delete' && (
          <span className={`font-mono ${DEBUG_TEXT_SIZES.mono} text-muted-foreground`}>
            imp={importance.toFixed(2)}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="truncate pl-4 text-[11px] text-muted-foreground" title={memory.content}>
        {action === 'delete' ? (
          <span className={cn('line-through', TONE_TEXT.destructive, 'opacity-70')}>
            {memory.content}
          </span>
        ) : (
          memory.content
        )}
      </div>
    </div>
  );
});

/**
 * Similar memory row (dedup context)
 */
const SimilarMemoryRow = React.memo(function SimilarMemoryRow({
  memory,
  index,
}: {
  memory: ExistingSimilarMemory;
  index: number;
}) {
  return (
    <div className="flex items-center gap-2 px-2 py-1 text-xs">
      <span
        className={`${DEBUG_TEXT_SIZES.tiny} w-4 flex-shrink-0 text-right text-muted-foreground`}
      >
        #{index + 1}
      </span>
      <ScoreBar score={memory.score} space="similarity" className="flex-shrink-0" />
      <DebugChip tone="info">{memory.category}</DebugChip>
      <span className="truncate text-[11px] text-muted-foreground" title={memory.content}>
        {memory.content}
      </span>
    </div>
  );
});

/** Shared LLM-spend footer line for extraction families. */
export const ExtractionLLMFooter = React.memo(function ExtractionLLMFooter({
  metadata,
}: {
  metadata: {
    model: string;
    input_tokens: number;
    output_tokens: number;
    cached_tokens: number;
  };
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-border/50 pt-2 text-[10px] text-muted-foreground">
      <span>
        <strong>Model:</strong> {metadata.model}
      </span>
      <span>
        <strong>IN:</strong> {metadata.input_tokens}
      </span>
      <span>
        <strong>OUT:</strong> {metadata.output_tokens}
      </span>
      {metadata.cached_tokens > 0 && (
        <span>
          <strong>CACHE:</strong> {metadata.cached_tokens}
        </span>
      )}
    </div>
  );
});

/**
 * Memory Extraction Section
 */
export const MemoryDetectionSection = React.memo(function MemoryDetectionSection({
  data,
}: MemoryDetectionSectionProps) {
  if (!data || !data.enabled) {
    return (
      <EmptySection
        value="memory-detection"
        title="Memory Extraction"
        icon={BrainCog}
        message={
          data?.enabled === false
            ? 'Memory extraction is globally disabled.'
            : 'No extraction data for this request.'
        }
      />
    );
  }

  if (data.skipped_reason) {
    return (
      <EmptySection
        value="memory-detection"
        title="Memory Extraction"
        icon={BrainCog}
        message={`Skipped: ${data.skipped_reason}`}
      />
    );
  }

  const memories = data.extracted_memories ?? [];
  const hasActions = memories.length > 0;
  const appliedCount = memories.filter(m => m.stored).length;
  const similarCount = data.existing_similar?.length ?? 0;

  // Count by action type
  const creates = memories.filter(m => (m.action ?? 'create') === 'create').length;
  const updates = memories.filter(m => m.action === 'update').length;
  const deletes = memories.filter(m => m.action === 'delete').length;

  return (
    <DebugSection
      value="memory-detection"
      title="Memory Extraction"
      icon={BrainCog}
      badge={
        <>
          <DebugChip tone={hasActions ? 'success' : 'neutral'}>
            {appliedCount}/{memories.length}
          </DebugChip>
          {creates > 0 && <DebugChip tone="success">+{creates}</DebugChip>}
          {updates > 0 && <DebugChip tone="warning">~{updates}</DebugChip>}
          {deletes > 0 && <DebugChip tone="destructive">-{deletes}</DebugChip>}
          {similarCount > 0 && <DebugChip tone="info">{similarCount} ctx</DebugChip>}
        </>
      }
    >
      {hasActions ? (
        <div className="space-y-1">
          <SubSectionHeader label={`Actions (${appliedCount} applied / ${memories.length} parsed)`} />
          <div className="space-y-1.5">
            {memories.map((memory, index) => (
              <MemoryActionRow key={`mem-${index}`} memory={memory} />
            ))}
          </div>
        </div>
      ) : (
        <div className="rounded bg-muted/20 p-2 text-xs italic text-muted-foreground">
          No memory actions for this message.
        </div>
      )}

      {similarCount > 0 && (
        <div className="space-y-1">
          <SubSectionHeader label={`Context shown to LLM (${similarCount} similar)`} />
          <div className="space-y-0.5 rounded bg-muted/10 p-1">
            {data.existing_similar.map((memory, index) => (
              <SimilarMemoryRow key={`similar-${index}`} memory={memory} index={index} />
            ))}
          </div>
        </div>
      )}

      {data.llm_metadata && <ExtractionLLMFooter metadata={data.llm_metadata} />}

      {data.error && (
        <div className={cn('border-t border-border/50 pt-2 text-xs', TONE_TEXT.destructive)}>
          <strong>Error:</strong> {data.error}
        </div>
      )}
    </DebugSection>
  );
});
