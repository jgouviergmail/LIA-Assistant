/**
 * Knowledge Enrichment Section Component
 *
 * Displays knowledge enrichment metrics via Brave Search.
 *
 * Shows:
 * - Encyclopedic keywords detected by QueryAnalyzer
 * - Endpoint used (Web vs News)
 * - Results injected into the LLM prompt
 * - Cache/API status
 */

import React from 'react';
import { BookOpen } from 'lucide-react';
import {
  DebugChip,
  DebugSection,
  EmptySection,
  MetricRow,
  SubSectionHeader,
} from '../shared';
import { TONE_TEXT } from '../../utils/tones';
import { cn } from '@/lib/utils';
import type { KnowledgeEnrichmentMetrics } from '@/types/chat';

export interface KnowledgeEnrichmentSectionProps {
  /** Enrichment metrics (can be undefined) */
  data: KnowledgeEnrichmentMetrics | undefined;
}

/** Keyword chip list, shared by the skip and executed variants. */
function KeywordList({ keywords }: { keywords: string[] }) {
  return (
    <div className="space-y-1.5">
      <SubSectionHeader label={`Detected keywords (${keywords.length})`} />
      <div className="flex flex-wrap gap-1.5">
        {keywords.map((keyword, index) => (
          <span
            key={index}
            className="rounded border border-primary/30 bg-primary/10 px-2 py-1 text-xs text-primary"
          >
            {keyword}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * Section Knowledge Enrichment
 *
 * Displays Brave Search enrichment details:
 * - Detected keywords
 * - Search type (web/news)
 * - Injected results
 * - Cache status
 */
export const KnowledgeEnrichmentSection = React.memo(function KnowledgeEnrichmentSection({
  data,
}: KnowledgeEnrichmentSectionProps) {
  if (!data) {
    return <EmptySection value="knowledge-enrichment" title="Knowledge Enrichment" icon={BookOpen} />;
  }

  // Feature globally disabled
  if (!data.enabled) {
    return (
      <EmptySection
        value="knowledge-enrichment"
        title="Knowledge Enrichment"
        icon={BookOpen}
        message="Brave Search enrichment is globally disabled."
      />
    );
  }

  // No keywords detected
  if (data.encyclopedia_keywords.length === 0) {
    return (
      <EmptySection
        value="knowledge-enrichment"
        title="Knowledge Enrichment"
        icon={BookOpen}
        message="No encyclopedic terms detected in the query."
      />
    );
  }

  // Enrichment not executed (skip reason)
  if (!data.executed && data.skip_reason) {
    return (
      <DebugSection
        value="knowledge-enrichment"
        title="Knowledge Enrichment"
        icon={BookOpen}
        badge={
          <>
            <DebugChip tone="warning">{data.encyclopedia_keywords.length} keywords</DebugChip>
            <DebugChip tone="neutral">SKIP</DebugChip>
          </>
        }
      >
        <KeywordList keywords={data.encyclopedia_keywords} />
        <div className="rounded bg-muted/20 p-2 text-xs text-muted-foreground">
          <strong>Not executed:</strong> {data.skip_reason}
        </div>
      </DebugSection>
    );
  }

  // Executed successfully
  return (
    <DebugSection
      value="knowledge-enrichment"
      title="Knowledge Enrichment"
      icon={BookOpen}
      badge={<ExecutedBadges data={data} />}
    >
      <KeywordList keywords={data.encyclopedia_keywords} />
      <QueryTypeBlock isNews={Boolean(data.is_news_query)} />
      {data.executed && <EnrichmentDetailsGrid data={data} />}
      <BraveResultsList results={data.results} />
      <PromptContextBlock context={data.prompt_context} />
      {data.error && (
        <div className={cn('border-t border-border/50 pt-2 text-xs', TONE_TEXT.destructive)}>
          <strong>Error:</strong> {data.error}
        </div>
      )}
    </DebugSection>
  );
});

/** Badge cluster of the executed variant (endpoint, cache, result count). */
function ExecutedBadges({ data }: { data: KnowledgeEnrichmentMetrics }) {
  const hasResults = data.results_count !== undefined && data.results_count > 0;
  return (
    <>
      {data.endpoint && (
        <DebugChip tone={data.endpoint === 'news' ? 'warning' : 'info'}>{data.endpoint}</DebugChip>
      )}
      {data.from_cache !== undefined && (
        <DebugChip tone={data.from_cache ? 'success' : 'warning'}>
          {data.from_cache ? 'CACHE' : 'API'}
        </DebugChip>
      )}
      <DebugChip tone={hasResults ? 'success' : 'neutral'}>
        {hasResults ? `${data.results_count} results` : 'No results'}
      </DebugChip>
    </>
  );
}

/** Query-type detection (is_news_query) block. */
function QueryTypeBlock({ isNews }: { isNews: boolean }) {
  return (
    <div className="space-y-1">
      <SubSectionHeader label="Query type (is_news_query)" />
      <DebugChip tone={isNews ? 'warning' : 'info'}>
        {isNews ? 'TRUE → News (News API)' : 'FALSE → Encyclopedic (Web API + year)'}
      </DebugChip>
    </div>
  );
}

/** Enrichment details grid (query sent, endpoint, results, source). */
function EnrichmentDetailsGrid({ data }: { data: KnowledgeEnrichmentMetrics }) {
  const hasResults = data.results_count !== undefined && data.results_count > 0;
  return (
    <div className="space-y-1">
      <SubSectionHeader label="Enrichment details" borderTop />
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        {data.keyword_used && <MetricRow label="Query sent" value={data.keyword_used} />}
        {data.endpoint && <MetricRow label="Endpoint" value={data.endpoint.toUpperCase()} />}
        {data.results_count !== undefined && (
          <MetricRow label="Results" value={data.results_count} highlight={hasResults} />
        )}
        {data.from_cache !== undefined && (
          <MetricRow label="Source" value={data.from_cache ? 'Redis cache' : 'Brave API'} />
        )}
      </div>
    </div>
  );
}

/** Brave Search result cards (nothing when the API returned none). */
function BraveResultsList({ results }: { results: KnowledgeEnrichmentMetrics['results'] }) {
  if (!results || results.length === 0) return null;
  return (
    <div className="space-y-2">
      <SubSectionHeader label={`Brave Search results (${results.length})`} borderTop />
      <div className="max-h-48 space-y-2 overflow-y-auto">
        {results.map((result, index) => (
          <div key={index} className="rounded border border-border/50 bg-muted/30 p-2 text-xs">
            <div className="truncate font-medium text-primary">
              {index + 1}. {result.title}
            </div>
            <div className="mt-1 line-clamp-2 text-muted-foreground">{result.description}</div>
            <a
              href={result.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 block truncate text-primary hover:underline"
            >
              {result.url}
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Context injected into the LLM prompt (nothing when absent). */
function PromptContextBlock({ context }: { context: string | undefined }) {
  if (!context) return null;
  return (
    <div className="space-y-1">
      <SubSectionHeader label="Context injected into prompt" borderTop />
      <pre className="max-h-32 overflow-y-auto overflow-x-auto whitespace-pre-wrap rounded border border-border/50 bg-muted/30 p-2 text-xs">
        {context}
      </pre>
    </div>
  );
}
