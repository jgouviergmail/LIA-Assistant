/**
 * Memory Extraction Section Component
 *
 * Displays memories created, updated, or deleted by the background
 * extraction pipeline. Shows action type, category, emotional weight,
 * and storage status for each memory action.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import { ActionBadge, SectionBadge } from '../shared';
import { INFO_SECTION_CLASSES, DEBUG_TEXT_SIZES } from '../../utils/constants';
import { getEmotionalLabel } from '../../utils/formatters';
import type {
  MemoryDetectionMetrics,
  ExtractedMemory,
  ExistingSimilarMemory,
} from '@/types/chat';

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
    <div className="flex flex-col gap-1 text-xs py-2 px-2 bg-muted/10 rounded">
      <div className="flex items-center gap-2">
        {/* Storage status */}
        <span
          className={cn(
            'w-2 h-2 rounded-full flex-shrink-0',
            memory.stored ? 'bg-green-500' : 'bg-red-500'
          )}
          title={memory.stored ? 'Applied successfully' : 'Failed'}
        />

        {/* Action badge */}
        <ActionBadge action={action} />

        {/* Category badge */}
        <span
          className={cn(
            'text-[10px] px-1.5 py-0.5 rounded border flex-shrink-0',
            'bg-primary/10 text-primary/80 border-primary/20'
          )}
        >
          {memory.category}
        </span>

        {/* Emotional weight */}
        <span
          className={cn('text-[9px] px-1 py-0.5 rounded border flex-shrink-0', emotional.className)}
          title={`Emotional weight: ${memory.emotional_weight}`}
        >
          {emotional.label} ({(memory.emotional_weight ?? 0) > 0 ? '+' : ''}{memory.emotional_weight ?? 0})
        </span>

        {/* Importance */}
        {action !== 'delete' && (
          <span className={`font-mono ${DEBUG_TEXT_SIZES.mono} text-muted-foreground`}>
            imp={importance.toFixed(2)}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="pl-4 text-[11px] text-muted-foreground/80 truncate" title={memory.content}>
        {action === 'delete' ? (
          <span className="line-through text-red-400/60">{memory.content}</span>
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
  const barWidth = memory.score * 100;

  return (
    <div className="flex items-center gap-2 text-xs py-1 px-2">
      <span className={`${DEBUG_TEXT_SIZES.tiny} text-muted-foreground w-4 text-right flex-shrink-0`}>
        #{index + 1}
      </span>
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
      <span className={cn(
        'text-[10px] px-1.5 py-0.5 rounded border flex-shrink-0',
        'bg-blue-500/10 text-blue-400/80 border-blue-500/20'
      )}>
        {memory.category}
      </span>
      <span className="text-[11px] text-muted-foreground/70 truncate" title={memory.content}>
        {memory.content}
      </span>
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
      <AccordionItem value="memory-detection">
        <AccordionTrigger className="py-2 text-sm">
          <div className="flex items-center gap-2">
            <span>Memory Extraction</span>
            <SectionBadge passed={false} label={data?.enabled === false ? 'OFF' : 'N/A'} />
          </div>
        </AccordionTrigger>
        <AccordionContent>
          <div className={INFO_SECTION_CLASSES}>
            {data?.enabled === false ? (
              <><strong>Disabled:</strong> Memory extraction is globally disabled.</>
            ) : (
              <><strong>Not available:</strong> No extraction data.</>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  }

  if (data.skipped_reason) {
    return (
      <AccordionItem value="memory-detection">
        <AccordionTrigger className="py-2 text-sm">
          <div className="flex items-center gap-2">
            <span>Memory Extraction</span>
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

  const memories = data.extracted_memories ?? [];
  const hasActions = memories.length > 0;
  const appliedCount = memories.filter(m => m.stored).length;
  const similarCount = data.existing_similar?.length ?? 0;

  // Count by action type
  const creates = memories.filter(m => (m.action ?? 'create') === 'create').length;
  const updates = memories.filter(m => m.action === 'update').length;
  const deletes = memories.filter(m => m.action === 'delete').length;

  return (
    <AccordionItem value="memory-detection">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Memory Extraction</span>
          <span
            className={cn(
              'text-xs px-1.5 py-0.5 rounded font-medium border',
              hasActions
                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                : 'bg-muted/50 text-muted-foreground border-border/50'
            )}
          >
            {appliedCount}/{memories.length}
          </span>
          {/* Action type summary */}
          {creates > 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-emerald-500/15 text-emerald-400">
              +{creates}
            </span>
          )}
          {updates > 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-amber-500/15 text-amber-400">
              ~{updates}
            </span>
          )}
          {deletes > 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-red-500/15 text-red-400">
              -{deletes}
            </span>
          )}
          {similarCount > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-blue-500/20 text-blue-400 border-blue-500/30">
              {similarCount} ctx
            </span>
          )}
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {hasActions ? (
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground font-medium mb-1">
                Actions ({appliedCount} applied / {memories.length} parsed)
              </div>
              <div className="space-y-1.5 space-y-1.5">
                {memories.map((memory, index) => (
                  <MemoryActionRow key={`mem-${index}`} memory={memory} />
                ))}
              </div>
            </div>
          ) : (
            <div className="text-xs text-muted-foreground italic p-2 bg-muted/20 rounded">
              No memory actions for this message.
            </div>
          )}

          {similarCount > 0 && (
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground font-medium mb-1">
                Context shown to LLM ({similarCount} similar)
              </div>
              <div className="space-y-0.5 bg-muted/10 rounded p-1">
                {data.existing_similar.map((memory, index) => (
                  <SimilarMemoryRow key={`similar-${index}`} memory={memory} index={index} />
                ))}
              </div>
            </div>
          )}

          {data.llm_metadata && (
            <div className="border-t pt-2 flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground">
              <span><strong>Model:</strong> {data.llm_metadata.model}</span>
              <span><strong>IN:</strong> {data.llm_metadata.input_tokens}</span>
              <span><strong>OUT:</strong> {data.llm_metadata.output_tokens}</span>
              {data.llm_metadata.cached_tokens > 0 && (
                <span><strong>CACHE:</strong> {data.llm_metadata.cached_tokens}</span>
              )}
            </div>
          )}

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
