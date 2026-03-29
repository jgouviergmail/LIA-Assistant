/**
 * Memory Detection Section Component
 *
 * Displays memories extracted and stored in long-term memory from the
 * current message. Similar to Interest Detection but for psychological
 * profiling memories.
 *
 * Shows:
 * - Memories extracted by background LLM analysis (content, category, emotional weight)
 * - Existing similar memories found during deduplication
 * - Storage status (success/failure per memory)
 * - LLM metadata (tokens, model)
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import { SectionBadge } from '../shared';
import { INFO_SECTION_CLASSES, DEBUG_TEXT_SIZES } from '../../utils/constants';
import { getEmotionalLabel } from '../../utils/formatters';
import type {
  MemoryDetectionMetrics,
  ExtractedMemory,
  ExistingSimilarMemory,
} from '@/types/chat';

export interface MemoryDetectionSectionProps {
  /** Memory detection metrics (can be undefined) */
  data: MemoryDetectionMetrics | undefined;
}

/**
 * Importance color for the bar
 */
function getImportanceColor(importance: number): string {
  if (importance >= 0.8) return 'bg-green-500';
  if (importance >= 0.5) return 'bg-yellow-500';
  return 'bg-orange-500';
}

/**
 * Displays an extracted memory with its details
 */
const ExtractedMemoryRow = React.memo(function ExtractedMemoryRow({
  memory,
}: {
  memory: ExtractedMemory;
}) {
  const emotional = getEmotionalLabel(memory.emotional_weight);
  const importanceBarWidth = memory.importance * 100;

  return (
    <div className="flex flex-col gap-1 text-xs py-2 px-2 bg-muted/10 rounded">
      <div className="flex items-center gap-2">
        {/* Storage status indicator */}
        <span
          className={cn(
            'w-2 h-2 rounded-full flex-shrink-0',
            memory.stored ? 'bg-green-500' : 'bg-red-500'
          )}
          title={memory.stored ? 'Stored successfully' : 'Storage failed'}
        />

        {/* Category badge */}
        <span
          className={cn(
            'text-[10px] px-1.5 py-0.5 rounded border flex-shrink-0',
            'bg-primary/10 text-primary/80 border-primary/20'
          )}
        >
          {memory.category}
        </span>

        {/* Emotional weight badge */}
        <span
          className={cn('text-[9px] px-1 py-0.5 rounded border flex-shrink-0', emotional.className)}
          title={`Emotional weight: ${memory.emotional_weight}`}
        >
          {emotional.label} ({memory.emotional_weight > 0 ? '+' : ''}{memory.emotional_weight})
        </span>

        {/* Importance bar + value */}
        <div className="flex-1 flex items-center gap-2 min-w-0">
          <div className="relative h-1.5 bg-muted/30 rounded-full flex-1 max-w-[60px]">
            <div
              className={cn(
                'absolute left-0 top-0 h-full rounded-full transition-all',
                getImportanceColor(memory.importance)
              )}
              style={{ width: `${importanceBarWidth}%` }}
            />
          </div>
          <span
            className={`font-mono ${DEBUG_TEXT_SIZES.mono} w-10 text-right text-muted-foreground`}
          >
            {memory.importance.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="pl-4 text-[11px] text-muted-foreground/80 truncate" title={memory.content}>
        {memory.content}
      </div>

      {/* Trigger topic */}
      {memory.trigger_topic && (
        <div className="pl-4 flex items-center gap-1 text-[10px] text-muted-foreground/60">
          <span>Trigger:</span>
          <span className="font-mono">{memory.trigger_topic}</span>
        </div>
      )}
    </div>
  );
});

/**
 * Displays an existing similar memory found during dedup
 */
const SimilarMemoryRow = React.memo(function SimilarMemoryRow({
  memory,
  index,
}: {
  memory: ExistingSimilarMemory;
  index: number;
}) {
  const barWidth = memory.score * 100;

  return (
    <div className="flex items-center gap-2 text-xs py-1 px-2">
      <span className={`${DEBUG_TEXT_SIZES.tiny} text-muted-foreground w-4 text-right flex-shrink-0`}>
        #{index + 1}
      </span>

      {/* Score bar */}
      <div className="flex items-center gap-1.5 flex-shrink-0 w-[80px]">
        <div className="relative h-1.5 bg-muted/30 rounded-full flex-1 max-w-[45px]">
          <div
            className="absolute left-0 top-0 h-full rounded-full bg-blue-500 transition-all"
            style={{ width: `${barWidth}%` }}
          />
        </div>
        <span className={`font-mono ${DEBUG_TEXT_SIZES.mono} w-10 text-right text-muted-foreground`}>
          {memory.score.toFixed(3)}
        </span>
      </div>

      {/* Category */}
      <span
        className={cn(
          'text-[10px] px-1.5 py-0.5 rounded border flex-shrink-0',
          'bg-blue-500/10 text-blue-400/80 border-blue-500/20'
        )}
      >
        {memory.category}
      </span>

      {/* Content (truncated) */}
      <span className="text-[11px] text-muted-foreground/70 truncate" title={memory.content}>
        {memory.content}
      </span>
    </div>
  );
});

/**
 * Section Memory Detection
 *
 * Displays memories extracted from the current user message and stored
 * in long-term memory by the background extraction pipeline.
 */
export const MemoryDetectionSection = React.memo(function MemoryDetectionSection({
  data,
}: MemoryDetectionSectionProps) {
  // Case: no data or feature disabled
  if (!data || !data.enabled) {
    return (
      <AccordionItem value="memory-detection">
        <AccordionTrigger className="py-2 text-sm">
          <div className="flex items-center gap-2">
            <span>Memory Detection</span>
            <SectionBadge passed={false} label={data?.enabled === false ? 'OFF' : 'N/A'} />
          </div>
        </AccordionTrigger>
        <AccordionContent>
          <div className={INFO_SECTION_CLASSES}>
            {data?.enabled === false ? (
              <>
                <strong>Disabled:</strong> Memory extraction is globally disabled.
              </>
            ) : (
              <>
                <strong>Not available:</strong> No detection data.
              </>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  }

  // Case: skipped
  if (data.skipped_reason) {
    return (
      <AccordionItem value="memory-detection">
        <AccordionTrigger className="py-2 text-sm">
          <div className="flex items-center gap-2">
            <span>Memory Detection</span>
            <SectionBadge passed={false} label="SKIP" />
          </div>
        </AccordionTrigger>
        <AccordionContent>
          <div className={INFO_SECTION_CLASSES}>
            <strong>Skipped:</strong> {data.skipped_reason}
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  }

  const extractedCount = data.extracted_memories?.length ?? 0;
  const hasExtracted = extractedCount > 0;
  const storedCount = data.extracted_memories?.filter(m => m.stored).length ?? 0;
  const similarCount = data.existing_similar?.length ?? 0;

  return (
    <AccordionItem value="memory-detection">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Memory Detection</span>
          <span
            className={cn(
              'text-xs px-1.5 py-0.5 rounded font-medium border',
              hasExtracted
                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                : 'bg-muted/50 text-muted-foreground border-border/50'
            )}
          >
            {storedCount}/{extractedCount}
          </span>
          {similarCount > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-blue-500/20 text-blue-400 border-blue-500/30">
              {similarCount} dedup
            </span>
          )}
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Extracted memories list */}
          {hasExtracted ? (
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground font-medium mb-1">
                Extracted memories ({storedCount} stored / {extractedCount} extracted)
              </div>
              <div className="space-y-1.5 max-h-[250px] overflow-y-auto">
                {data.extracted_memories.map((memory, index) => (
                  <ExtractedMemoryRow key={`${memory.category}-${index}`} memory={memory} />
                ))}
              </div>
            </div>
          ) : (
            <div className="text-xs text-muted-foreground italic p-2 bg-muted/20 rounded">
              No new memories detected in this message.
            </div>
          )}

          {/* Existing similar memories (dedup) */}
          {similarCount > 0 && (
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground font-medium mb-1">
                Similar existing memories ({similarCount})
              </div>
              <div className="space-y-0.5 max-h-[150px] overflow-y-auto bg-muted/10 rounded p-1">
                {data.existing_similar.map((memory, index) => (
                  <SimilarMemoryRow key={`similar-${index}`} memory={memory} index={index} />
                ))}
              </div>
            </div>
          )}

          {/* LLM Metadata */}
          {data.llm_metadata && (
            <div className="border-t pt-2 flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground">
              <span title="LLM Model">
                <strong>Model:</strong> {data.llm_metadata.model}
              </span>
              <span title="Input tokens">
                <strong>IN:</strong> {data.llm_metadata.input_tokens}
              </span>
              <span title="Output tokens">
                <strong>OUT:</strong> {data.llm_metadata.output_tokens}
              </span>
              {data.llm_metadata.cached_tokens > 0 && (
                <span title="Cached tokens">
                  <strong>CACHE:</strong> {data.llm_metadata.cached_tokens}
                </span>
              )}
            </div>
          )}

          {/* Legend */}
          {hasExtracted && (
            <div className="border-t pt-2 flex items-center gap-4 text-[10px] text-muted-foreground">
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                <span>Stored</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-red-500" />
                <span>Failed</span>
              </div>
              <span className="text-muted-foreground/50">|</span>
              <span>Importance: </span>
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                <span>&ge;0.8</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-yellow-500" />
                <span>0.5-0.8</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-orange-500" />
                <span>&lt;0.5</span>
              </div>
            </div>
          )}

          {/* Error if any */}
          {data.error && (
            <div className="border-t pt-2 text-xs text-red-400">
              <strong>Error:</strong> {data.error}
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
