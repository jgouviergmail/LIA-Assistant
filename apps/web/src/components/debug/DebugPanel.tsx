/**
 * Debug Panel - Production-Grade Orchestrator
 *
 * Displays debug metrics for application analysis and tuning.
 *
 * Architecture:
 * - Minimal orchestrator component (~200 lines)
 * - Modular imported sections
 * - Zod data validation
 * - Error boundary for isolation
 * - Zero console.logs
 * - Zero `as any` casts
 *
 * CRITICAL: Displayed scores are always CAL (calibrated), never RAW.
 */

'use client';

import { useState } from 'react';
import { Accordion } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import { ChevronDown, Clock, MessageSquare } from 'lucide-react';
import type { DebugMetrics } from '@/types/chat';
import type { DebugMetricsEntry } from '@/types/chat-state';

// Error boundary
import { DebugPanelErrorBoundary } from './errors/DebugPanelErrorBoundary';

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
  // v3.1 enrichments
  ForEachAnalysisSection,
  ExecutionWavesSection,
  RequestLifecycleSection,
  // Interest Learning System
  InterestProfileSection,
  // Knowledge Enrichment (Brave Search)
  KnowledgeEnrichmentSection,
  // Memory Injection (debug tuning)
  MemoryInjectionSection,
  // RAG Injection (Knowledge Spaces)
  RAGInjectionSection,
  // Journal Injection (Personal Journals)
  JournalInjectionSection,
  // Skills activation
  SkillsSection,
  // LLM Pipeline (v3.3 - chronological reconciliation)
  LLMPipelineSection,
} from './components/sections';

// Constants
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
 * Format timestamp for display (HH:MM:SS)
 */
function formatTime(date: Date): string {
  return date.toLocaleTimeString('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/**
 * Truncate query for display in collapsed header
 */
function truncateQuery(query: string, maxLength: number = 40): string {
  if (query.length <= maxLength) return query;
  return query.slice(0, maxLength) + '...';
}

/**
 * Debug Panel Component (Wrapped with Error Boundary)
 *
 * Main entry point for the debug panel. Automatically wrapped
 * in an error boundary for isolation.
 *
 * @example
 * ```tsx
 * <DebugPanel metrics={latestDebugMetrics} history={debugMetricsHistory} />
 * ```
 */
export function DebugPanel(props: DebugPanelProps) {
  return (
    <DebugPanelErrorBoundary>
      <DebugPanelContent {...props} />
    </DebugPanelErrorBoundary>
  );
}

/**
 * Render all metric sections for a single request
 */
function MetricsSections({ metrics }: { metrics: DebugMetrics }) {
  const {
    intent_detection,
    domain_selection,
    routing_decision,
    tool_selection,
    token_budget,
    planner_intelligence,
    execution_timeline,
    context_resolution,
    query_info,
    llm_calls,
    llm_summary,
    llm_pipeline,
    google_api_calls,
    google_api_summary,
    intelligent_mechanisms,
    for_each_analysis,
    execution_waves,
    request_lifecycle,
    interest_profile,
    knowledge_enrichment,
    memory_injection,
    rag_injection,
    journal_injection,
    journal_planner_injection,
    journal_extraction,
    skills,
  } = metrics;

  return (
    <Accordion type="multiple" defaultValue={DEFAULT_OPEN_SECTIONS} className="px-3">
      <IntentSection data={intent_detection} mechanisms={intelligent_mechanisms} />
      <DomainSection data={domain_selection} mechanisms={intelligent_mechanisms} />
      <RoutingSection data={routing_decision} />
      <ToolSection data={tool_selection} />
      <ContextSection data={context_resolution} />
      <QuerySection data={query_info} />
      <IntelligentMechanismsSection data={intelligent_mechanisms} />
      <MemoryInjectionSection data={memory_injection} />
      <InterestProfileSection data={interest_profile} />
      <KnowledgeEnrichmentSection data={knowledge_enrichment} />
      <RAGInjectionSection data={rag_injection} />
      <JournalInjectionSection
        data={journal_injection}
        plannerData={journal_planner_injection}
        extraction={journal_extraction}
      />
      <TokenBudgetSection data={token_budget} />
      <PlannerSection data={planner_intelligence} />
      <ExecutionSection data={execution_timeline} />
      <ForEachAnalysisSection data={for_each_analysis} />
      <ExecutionWavesSection data={execution_waves} />
      <RequestLifecycleSection data={request_lifecycle} />
      <LLMPipelineSection data={llm_pipeline} />
      <LLMCallsSection calls={llm_calls} summary={llm_summary} />
      <GoogleApiCallsSection calls={google_api_calls} summary={google_api_summary} />
      <SkillsSection data={skills} />
    </Accordion>
  );
}

/**
 * Debug Panel Content (Internal Component)
 *
 * Internal component that orchestrates section display.
 * Isolated by the error boundary to prevent app crashes on error.
 *
 * Supports cumulative history display with collapsible request sections.
 */
function DebugPanelContent({ metrics, history = [], className }: DebugPanelProps) {
  // Track which history entries are expanded (most recent expanded by default)
  const [expandedEntries, setExpandedEntries] = useState<string[]>(
    history.length > 0 ? [history[0].id] : []
  );

  // Toggle expansion of a history entry
  const toggleEntry = (entryId: string) => {
    setExpandedEntries(prev =>
      prev.includes(entryId) ? prev.filter(id => id !== entryId) : [...prev, entryId]
    );
  };

  // Case: no metrics available and no history
  if (!metrics && history.length === 0) {
    return (
      <div className={cn('p-4 text-center text-muted-foreground text-sm', className)}>
        <p className="mb-1">No debug metrics available</p>
        <p className="text-xs">Metrics will appear here after the next conversation turn.</p>
      </div>
    );
  }

  // Case: history available - cumulative display
  if (history.length > 0) {
    return (
      <div className={cn('flex flex-col h-full', className)}>
        {/* Header with count */}
        <div className="p-3 border-b bg-muted/30">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-sm">Debug Metrics</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Scoring thresholds analysis • Calibrated scores only
              </p>
            </div>
            <div className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded-full">
              {history.length} request{history.length > 1 ? 's' : ''}
            </div>
          </div>
        </div>

        {/* Scrollable content with collapsible history entries */}
        <div className="flex-1 overflow-y-auto">
          {history.map((entry, index) => {
            const isExpanded = expandedEntries.includes(entry.id);
            const isLatest = index === 0;

            return (
              <div
                key={entry.id}
                className={cn('border-b border-border/50', isLatest && 'bg-primary/5')}
              >
                {/* Collapsible header for request */}
                <button
                  onClick={() => toggleEntry(entry.id)}
                  className={cn(
                    'w-full px-3 py-2 flex items-center gap-2 text-left hover:bg-muted/50 transition-colors',
                    isExpanded && 'bg-muted/30'
                  )}
                >
                  <ChevronDown
                    className={cn(
                      'h-4 w-4 text-muted-foreground transition-transform',
                      !isExpanded && '-rotate-90'
                    )}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      {isLatest && (
                        <span className="text-[10px] bg-primary text-primary-foreground px-1.5 py-0.5 rounded font-medium">
                          LATEST
                        </span>
                      )}
                      <span className="text-xs text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatTime(
                          entry.timestamp instanceof Date
                            ? entry.timestamp
                            : new Date(entry.timestamp)
                        )}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 mt-0.5">
                      <MessageSquare className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                      <span className="text-sm truncate font-medium">
                        {truncateQuery(entry.query)}
                      </span>
                    </div>
                  </div>
                  {/* Route badge */}
                  <span
                    className={cn(
                      'text-[10px] px-1.5 py-0.5 rounded font-mono',
                      entry.metrics.routing_decision?.route_to === 'planner'
                        ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300'
                        : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'
                    )}
                  >
                    {entry.metrics.routing_decision?.route_to || '?'}
                  </span>
                </button>

                {/* Collapsible content - metrics sections */}
                {isExpanded && (
                  <div className="border-t border-border/30">
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
    <div className={cn('flex flex-col h-full', className)}>
      <div className="p-3 border-b bg-muted/30">
        <h2 className="font-semibold text-sm">Debug Metrics</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Scoring thresholds analysis • Calibrated scores only
        </p>
      </div>

      <div className="flex-1 overflow-y-auto">
        {metrics && <MetricsSections metrics={metrics} />}
      </div>
    </div>
  );
}

/**
 * Default export for compatibility
 */
export default DebugPanel;
