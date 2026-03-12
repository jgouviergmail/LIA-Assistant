/**
 * Memory Injection Section Component
 *
 * Displays memories injected into the psychological profile with their
 * semantic similarity scores. Allows tuning of min_score and max_results.
 *
 * Shows:
 * - Number of injected memories vs settings
 * - Similarity score per memory (bar + value)
 * - Category and emotional weight
 * - Aggregated emotional state
 * - Settings used (min_score, max_results, hybrid_enabled)
 */

import React from 'react';
import {
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import { SectionBadge } from '../shared';
import { INFO_SECTION_CLASSES, DEBUG_TEXT_SIZES } from '../../utils/constants';
import type {
  MemoryInjectionMetrics,
  MemoryInjectionDebugItem,
} from '@/types/chat';

export interface MemoryInjectionSectionProps {
  data: MemoryInjectionMetrics | undefined;
}

/**
 * Similarity score color (bar and dot)
 */
function getScoreColor(score: number): string {
  if (score >= 0.8) return 'bg-green-500';
  if (score >= 0.6) return 'bg-yellow-500';
  return 'bg-orange-500';
}

/**
 * Emotional label with color
 */
function getEmotionalLabel(weight: number): { label: string; className: string } {
  if (weight <= -7) return { label: 'TRAUMA', className: 'bg-red-500/30 text-red-300 border-red-500/40' };
  if (weight <= -3) return { label: 'NEG', className: 'bg-red-500/20 text-red-400 border-red-500/30' };
  if (weight >= 7) return { label: 'TRES+', className: 'bg-green-500/30 text-green-300 border-green-500/40' };
  if (weight >= 3) return { label: 'POS', className: 'bg-green-500/20 text-green-400 border-green-500/30' };
  return { label: 'NEU', className: 'bg-muted/50 text-muted-foreground border-border/50' };
}

/**
 * Aggregated emotional state color
 */
function getEmotionalStateColor(state: string): string {
  if (state === 'comfort') return 'bg-green-500/20 text-green-400 border-green-500/30';
  if (state === 'danger') return 'bg-red-500/20 text-red-400 border-red-500/30';
  return 'bg-muted/50 text-muted-foreground border-border/50';
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
  const barWidth = memory.score * 100;
  const emotional = getEmotionalLabel(memory.emotional_weight);

  return (
    <div className="flex flex-col gap-1 text-xs py-1.5 px-2 bg-muted/10 rounded">
      <div className="flex items-center gap-2">
        {/* Rank */}
        <span className={`${DEBUG_TEXT_SIZES.tiny} text-muted-foreground w-4 text-right flex-shrink-0`}>
          #{index + 1}
        </span>

        {/* Score dot */}
        <span
          className={cn('w-2 h-2 rounded-full flex-shrink-0', getScoreColor(memory.score))}
          title={`Score: ${memory.score.toFixed(4)}`}
        />

        {/* Score bar + value */}
        <div className="flex items-center gap-1.5 flex-shrink-0 w-[100px]">
          <div className="relative h-1.5 bg-muted/30 rounded-full flex-1 max-w-[60px]">
            <div
              className={cn('absolute left-0 top-0 h-full rounded-full transition-all', getScoreColor(memory.score))}
              style={{ width: `${barWidth}%` }}
            />
          </div>
          <span className={`font-mono ${DEBUG_TEXT_SIZES.mono} w-12 text-right text-muted-foreground`}>
            {memory.score.toFixed(3)}
          </span>
        </div>

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
          className={cn(
            'text-[9px] px-1 py-0.5 rounded border flex-shrink-0',
            emotional.className
          )}
          title={`Poids émotionnel: ${memory.emotional_weight}`}
        >
          {emotional.label}
        </span>
      </div>

      {/* Content (truncated) */}
      <div className="pl-6 text-[11px] text-muted-foreground/80 truncate" title={memory.content}>
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
  // No data
  if (!data) {
    return (
      <AccordionItem value="memory-injection">
        <AccordionTrigger className="py-2 text-sm">
          <div className="flex items-center gap-2">
            <span>Memory Injection</span>
            <SectionBadge passed={false} label="N/A" />
          </div>
        </AccordionTrigger>
        <AccordionContent>
          <div className={INFO_SECTION_CLASSES}>
            <strong>Non disponible :</strong> Aucune donnée de mémoire injectée.
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  }

  const hasMemories = data.memory_count > 0;
  const emotionalStateColor = getEmotionalStateColor(data.emotional_state);

  return (
    <AccordionItem value="memory-injection">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Memory Injection</span>
          <span
            className={cn(
              'text-xs px-1.5 py-0.5 rounded font-medium border',
              hasMemories
                ? 'bg-purple-500/20 text-purple-400 border-purple-500/30'
                : 'bg-muted/50 text-muted-foreground border-border/50'
            )}
          >
            {data.memory_count}
          </span>
          <span className={cn('text-[10px] px-1.5 py-0.5 rounded border', emotionalStateColor)}>
            {data.emotional_state}
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Settings summary */}
          <div className="flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground p-2 bg-muted/20 rounded">
            <span>
              <strong>min_score:</strong>{' '}
              <span className="font-mono">{data.settings.min_score}</span>
            </span>
            <span>
              <strong>max_results:</strong>{' '}
              <span className="font-mono">{data.settings.max_results}</span>
            </span>
            <span>
              <strong>hybrid:</strong>{' '}
              <span className={cn('font-mono', data.settings.hybrid_enabled ? 'text-green-400' : 'text-red-400')}>
                {data.settings.hybrid_enabled ? 'ON' : 'OFF'}
              </span>
            </span>
          </div>

          {/* Memories list */}
          {hasMemories ? (
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground font-medium mb-1">
                Mémoires injectées ({data.memory_count})
              </div>
              <div className="space-y-1 max-h-[300px] overflow-y-auto">
                {data.memories.map((memory, index) => (
                  <MemoryRow
                    key={`${memory.category}-${index}`}
                    memory={memory}
                    index={index}
                  />
                ))}
              </div>
            </div>
          ) : (
            <div className="text-xs text-muted-foreground italic p-2 bg-muted/20 rounded">
              Aucune mémoire injectée pour cette requête.
            </div>
          )}

          {/* Score distribution legend */}
          {hasMemories && (
            <div className="border-t pt-2 flex items-center gap-4 text-[10px] text-muted-foreground">
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                <span>&ge;0.80</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-yellow-500" />
                <span>0.60-0.79</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-orange-500" />
                <span>&lt;0.60</span>
              </div>
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
