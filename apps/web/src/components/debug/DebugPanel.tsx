/**
 * Debug Panel — execution-ordered orchestrator (v2)
 *
 * Reads like the run itself: seven numbered phases in true execution order
 * (request → analysis → planning → execution → response context →
 * background extraction → totals). Idle sections fold behind a per-phase
 * disclosure, anomalies surface on the entry header, and each history
 * entry carries a scannable summary strip.
 *
 * Payload validation (Zod) runs per section as a DETECTOR inside the
 * anomaly channel (`collectAnomalies`) — mismatches surface as warnings,
 * sections never disappear because a payload drifted.
 *
 * CRITICAL: Displayed scores are always CAL (calibrated), never RAW.
 */

'use client';

import React, { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { Accordion } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import type { DebugMetrics } from '@/types/chat';
import type { DebugMetricsEntry } from '@/types/chat-state';

// Error boundary
import { DebugPanelErrorBoundary } from './errors/DebugPanelErrorBoundary';

// Orchestrator building blocks
import { PipelineStrip } from './components/PipelineStrip';
import { RequestEntryHeader } from './components/RequestEntryHeader';
import { EmptySection } from './components/shared';
import { collectAnomalies } from './utils/anomalies';
import { sectionPresence } from './utils/presence';

// Section components
import {
  IntentSection,
  DomainSection,
  RoutingSection,
  ToolSection,
  TokenBudgetSection,
  PlannerSection,
  ExecutionSection,
  ContextSection,
  QuerySection,
  LLMCallsSection,
  GoogleApiCallsSection,
  IntelligentMechanismsSection,
  ForEachAnalysisSection,
  ExecutionWavesSection,
  RequestLifecycleSection,
  InterestProfileSection,
  KnowledgeEnrichmentSection,
  MemoryInjectionSection,
  MemoryDetectionSection,
  RAGInjectionSection,
  JournalInjectionSection,
  JournalExtractionSection,
  OpenLoopExtractionSection,
  SkillsSection,
  LLMPipelineSection,
  SemanticValidatorSection,
  ReactExecutionSection,
  ImageGenerationSection,
  HitlSection,
  VoiceSection,
  CompactionSection,
} from './components/sections';
import { Repeat2, UserCheck, Volume2, Archive, Image as ImageIcon } from 'lucide-react';

import { DEFAULT_OPEN_SECTIONS } from './utils/constants';

export interface DebugPanelProps {
  /** Debug metrics (validated by useDebugMetrics) */
  metrics: DebugMetrics | null;
  /** Cumulative metrics history (most recent first) */
  history?: DebugMetricsEntry[];
  /** Additional CSS classes */
  className?: string;
}

/**
 * Debug Panel Component (Wrapped with Error Boundary)
 *
 * Main entry point for the debug panel. Automatically wrapped
 * in an error boundary for isolation.
 */
export function DebugPanel(props: DebugPanelProps) {
  return (
    <DebugPanelErrorBoundary>
      <DebugPanelContent {...props} />
    </DebugPanelErrorBoundary>
  );
}

/** One section slot inside a phase. */
interface SectionSlot {
  /** Accordion value — key into the presence map. */
  value: string;
  /** Rendered when the section has data. */
  node: React.ReactNode;
  /** Rendered inside the idle fold (defaults to `node`, whose component
   * shows its own contextual empty state). Null-returning components
   * provide an explicit EmptySection here. */
  idleNode?: React.ReactNode;
}

/**
 * One numbered phase: its data-bearing sections render directly; idle
 * sections fold behind a disclosure so a conversational turn is not
 * two-thirds N/A rows.
 */
function PhaseGroup({
  label,
  present,
  idle,
}: {
  label: string;
  present: React.ReactNode[];
  idle: React.ReactNode[];
}) {
  const [showIdle, setShowIdle] = useState(false);

  return (
    <div>
      <div className="px-1 pb-1 pt-3 first:pt-1">
        <div
          data-testid="phase-header"
          className="border-b border-border/30 pb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground"
        >
          {label}
        </div>
      </div>
      {present}
      {idle.length > 0 && (
        <>
          <button
            type="button"
            aria-expanded={showIdle}
            onClick={() => setShowIdle(v => !v)}
            className="flex w-full items-center gap-1 px-1 py-1 text-[10px] text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronRight
              aria-hidden="true"
              className={cn('h-3 w-3 transition-transform', showIdle && 'rotate-90')}
            />
            {idle.length} idle section{idle.length > 1 ? 's' : ''}
          </button>
          {showIdle && idle}
        </>
      )}
    </div>
  );
}

/**
 * Render all metric sections for a single request, in execution order.
 */
function MetricsSections({ metrics }: { metrics: DebugMetrics }) {
  const presence = sectionPresence(metrics);

  const phases: { label: string; sections: SectionSlot[] }[] = [
    {
      label: '1 · Request',
      sections: [
        {
          value: 'query',
          node: <QuerySection data={metrics.query_info} executionMode={metrics.execution_mode} />,
        },
      ],
    },
    {
      label: '2 · Analysis (router)',
      sections: [
        {
          value: 'intent',
          node: (
            <IntentSection
              data={metrics.intent_detection}
              mechanisms={metrics.intelligent_mechanisms}
            />
          ),
        },
        {
          value: 'domain',
          node: (
            <DomainSection
              data={metrics.domain_selection}
              mechanisms={metrics.intelligent_mechanisms}
            />
          ),
        },
        { value: 'context', node: <ContextSection data={metrics.context_resolution} /> },
        {
          value: 'for_each_analysis',
          node: <ForEachAnalysisSection data={metrics.for_each_analysis} />,
        },
        {
          value: 'mechanisms',
          node: <IntelligentMechanismsSection data={metrics.intelligent_mechanisms} />,
        },
        { value: 'routing', node: <RoutingSection data={metrics.routing_decision} /> },
      ],
    },
    {
      label: '3 · Planning',
      sections: [
        { value: 'token_budget', node: <TokenBudgetSection data={metrics.token_budget} /> },
        { value: 'tools', node: <ToolSection data={metrics.tool_selection} /> },
        { value: 'skills', node: <SkillsSection data={metrics.skills} /> },
        { value: 'planner', node: <PlannerSection data={metrics.planner_intelligence} /> },
        {
          value: 'semantic_validation',
          node: <SemanticValidatorSection data={metrics.semantic_validation} />,
        },
      ],
    },
    {
      label: '4 · Execution',
      sections: [
        { value: 'execution_waves', node: <ExecutionWavesSection data={metrics.execution_waves} /> },
        { value: 'execution', node: <ExecutionSection data={metrics.execution_timeline} /> },
        {
          value: 'react_execution',
          node: <ReactExecutionSection data={metrics.react_execution} />,
          idleNode: (
            <EmptySection
              value="react_execution"
              title="ReAct Loop"
              icon={Repeat2}
              message="This turn did not run in ReAct mode."
            />
          ),
        },
        {
          value: 'hitl',
          node: <HitlSection data={metrics.hitl} />,
          idleNode: (
            <EmptySection
              value="hitl"
              title="Human in the Loop"
              icon={UserCheck}
              message="No human gate on this turn."
            />
          ),
        },
        {
          value: 'google-api',
          node: (
            <GoogleApiCallsSection
              calls={metrics.google_api_calls}
              summary={metrics.google_api_summary}
            />
          ),
        },
        {
          value: 'image_generation',
          node: (
            <ImageGenerationSection
              calls={metrics.image_generation_calls}
              summary={metrics.image_generation_summary}
            />
          ),
          idleNode: (
            <EmptySection
              value="image_generation"
              title="Image Generation"
              icon={ImageIcon}
              message="No image was generated on this turn."
            />
          ),
        },
      ],
    },
    {
      label: '5 · Response context',
      sections: [
        { value: 'memory-injection', node: <MemoryInjectionSection data={metrics.memory_injection} /> },
        { value: 'rag-injection', node: <RAGInjectionSection data={metrics.rag_injection} /> },
        {
          value: 'knowledge-enrichment',
          node: <KnowledgeEnrichmentSection data={metrics.knowledge_enrichment} />,
        },
        {
          value: 'journal-injection',
          node: (
            <JournalInjectionSection
              data={metrics.journal_injection}
              plannerData={metrics.journal_planner_injection}
            />
          ),
        },
      ],
    },
    {
      label: '6 · Background extraction',
      sections: [
        { value: 'memory-detection', node: <MemoryDetectionSection data={metrics.memory_detection} /> },
        {
          value: 'journal-extraction',
          node: <JournalExtractionSection data={metrics.journal_extraction} />,
        },
        {
          value: 'open-loop-extraction',
          node: <OpenLoopExtractionSection data={metrics.open_loop_extraction} />,
        },
        { value: 'interest-profile', node: <InterestProfileSection data={metrics.interest_profile} /> },
      ],
    },
    {
      label: '7 · Totals & pipeline',
      sections: [
        {
          value: 'request_lifecycle',
          node: <RequestLifecycleSection data={metrics.request_lifecycle} />,
        },
        { value: 'llm_pipeline', node: <LLMPipelineSection data={metrics.llm_pipeline} /> },
        {
          value: 'llm',
          node: <LLMCallsSection calls={metrics.llm_calls} summary={metrics.llm_summary} />,
        },
        {
          value: 'voice',
          node: <VoiceSection data={metrics.voice} />,
          idleNode: (
            <EmptySection
              value="voice"
              title="Voice Synthesis"
              icon={Volume2}
              message="No paid speech synthesis on this turn."
            />
          ),
        },
        {
          value: 'compaction',
          node: <CompactionSection data={metrics.compaction} />,
          idleNode: (
            <EmptySection
              value="compaction"
              title="Context Compaction"
              icon={Archive}
              message="The conversation has not been compacted."
            />
          ),
        },
      ],
    },
  ];

  return (
    <Accordion type="multiple" defaultValue={DEFAULT_OPEN_SECTIONS} className="px-3">
      {phases.map(phase => {
        const present: React.ReactNode[] = [];
        const idle: React.ReactNode[] = [];
        for (const slot of phase.sections) {
          if (presence[slot.value]) {
            present.push(<React.Fragment key={slot.value}>{slot.node}</React.Fragment>);
          } else {
            idle.push(
              <React.Fragment key={slot.value}>{slot.idleNode ?? slot.node}</React.Fragment>
            );
          }
        }
        return <PhaseGroup key={phase.label} label={phase.label} present={present} idle={idle} />;
      })}
    </Accordion>
  );
}

/**
 * Debug Panel Content (Internal Component)
 *
 * Orchestrates section display; isolated by the error boundary so a
 * rendering failure never crashes the app.
 *
 * Supports cumulative history display with collapsible request sections.
 */
function DebugPanelContent({ metrics, history = [], className }: DebugPanelProps) {
  // Track which history entries are expanded (most recent expanded by default)
  const [expandedEntries, setExpandedEntries] = useState<string[]>(
    history.length > 0 ? [history[0].id] : []
  );

  const toggleEntry = (entryId: string) => {
    setExpandedEntries(prev =>
      prev.includes(entryId) ? prev.filter(id => id !== entryId) : [...prev, entryId]
    );
  };

  // Case: no metrics available and no history
  if (!metrics && history.length === 0) {
    return (
      <div className={cn('p-4 text-center text-sm text-muted-foreground', className)}>
        <p className="mb-1">No debug metrics available</p>
        <p className="text-xs">Metrics will appear here after the next conversation turn.</p>
      </div>
    );
  }

  // Case: history available - cumulative display
  if (history.length > 0) {
    return (
      <div className={cn('flex h-full flex-col', className)}>
        {/* Header with count */}
        <div className="border-b bg-muted/30 p-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">Debug Metrics</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Execution-ordered trace • Calibrated scores only
              </p>
            </div>
            <div className="rounded-full bg-muted px-2 py-1 text-xs text-muted-foreground">
              {history.length} request{history.length > 1 ? 's' : ''}
            </div>
          </div>
        </div>

        {/* Scrollable content with collapsible history entries */}
        <div className="flex-1 overflow-y-auto">
          {history.map((entry, index) => {
            const isExpanded = expandedEntries.includes(entry.id);
            const isLatest = index === 0;
            const anomalies = collectAnomalies(entry.metrics);

            return (
              <div
                key={entry.id}
                className={cn('border-b border-border/50', isLatest && 'bg-primary/5')}
              >
                <RequestEntryHeader
                  entry={entry}
                  isLatest={isLatest}
                  isExpanded={isExpanded}
                  onToggle={() => toggleEntry(entry.id)}
                  anomalyCount={anomalies.length}
                />

                {/* Collapsible content - pipeline strip + metrics sections */}
                {isExpanded && (
                  <div className="border-t border-border/30">
                    <PipelineStrip lifecycle={entry.metrics.request_lifecycle} />
                    <MetricsSections metrics={entry.metrics} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Fallback: single metrics display (backward compatible, no history)
  return (
    <div className={cn('flex h-full flex-col', className)}>
      <div className="border-b bg-muted/30 p-3">
        <h2 className="text-sm font-semibold">Debug Metrics</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Execution-ordered trace • Calibrated scores only
        </p>
      </div>

      <div className="flex-1 overflow-y-auto">
        {metrics && (
          <>
            <PipelineStrip lifecycle={metrics.request_lifecycle} />
            <MetricsSections metrics={metrics} />
          </>
        )}
      </div>
    </div>
  );
}

/**
 * Default export for compatibility
 */
export default DebugPanel;
