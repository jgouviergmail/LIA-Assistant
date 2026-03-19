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
 *
 * v3.2: Brave Search integration for knowledge enrichment
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';
import { MetricRow, SectionBadge } from '../shared';
import { INFO_SECTION_CLASSES } from '../../utils/constants';
import type { KnowledgeEnrichmentMetrics } from '@/types/chat';

export interface KnowledgeEnrichmentSectionProps {
  /** Enrichment metrics (can be undefined) */
  data: KnowledgeEnrichmentMetrics | undefined;
}

/**
 * Badge for endpoint (Web vs News)
 */
const EndpointBadge = React.memo(function EndpointBadge({
  endpoint,
}: {
  endpoint: 'web' | 'news';
}) {
  const isNews = endpoint === 'news';

  return (
    <span
      className={cn(
        'text-[10px] px-1.5 py-0.5 rounded font-mono font-semibold uppercase',
        isNews
          ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
          : 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
      )}
    >
      {endpoint}
    </span>
  );
});

/**
 * Badge for cache status
 */
const CacheBadge = React.memo(function CacheBadge({ fromCache }: { fromCache: boolean }) {
  return (
    <span
      className={cn(
        'text-[10px] px-1.5 py-0.5 rounded font-medium',
        fromCache
          ? 'bg-green-500/20 text-green-400 border border-green-500/30'
          : 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30'
      )}
    >
      {fromCache ? 'CACHE' : 'API'}
    </span>
  );
});

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
  // Case: no data
  if (!data) {
    return null;
  }

  // Case: feature globally disabled
  if (!data.enabled) {
    return (
      <AccordionItem value="knowledge-enrichment">
        <AccordionTrigger className="py-2 text-sm">
          <div className="flex items-center gap-2">
            <span>Knowledge Enrichment</span>
            <SectionBadge passed={false} label="OFF" />
          </div>
        </AccordionTrigger>
        <AccordionContent>
          <div className={INFO_SECTION_CLASSES}>
            <strong>Disabled:</strong> Brave Search enrichment is globally disabled.
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  }

  // Case: no keywords detected
  if (data.encyclopedia_keywords.length === 0) {
    return (
      <AccordionItem value="knowledge-enrichment">
        <AccordionTrigger className="py-2 text-sm">
          <div className="flex items-center gap-2">
            <span>Knowledge Enrichment</span>
            <SectionBadge passed={false} label="SKIP" />
          </div>
        </AccordionTrigger>
        <AccordionContent>
          <div className={INFO_SECTION_CLASSES}>
            <strong>No keywords:</strong> No encyclopedic terms detected in the query.
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  }

  // Case: enrichment not executed (skip reason)
  if (!data.executed && data.skip_reason) {
    return (
      <AccordionItem value="knowledge-enrichment">
        <AccordionTrigger className="py-2 text-sm">
          <div className="flex items-center gap-2">
            <span>Knowledge Enrichment</span>
            <span className="text-xs bg-yellow-500/20 text-yellow-400 px-1.5 py-0.5 rounded font-medium border border-yellow-500/30">
              {data.encyclopedia_keywords.length} keywords
            </span>
            <SectionBadge passed={false} label="SKIP" />
          </div>
        </AccordionTrigger>
        <AccordionContent>
          <div className="space-y-3">
            {/* Detected keywords */}
            <div className="space-y-1.5">
              <div className="text-xs text-muted-foreground font-medium">Detected keywords</div>
              <div className="flex flex-wrap gap-1.5">
                {data.encyclopedia_keywords.map((keyword, index) => (
                  <span
                    key={index}
                    className="text-xs px-2 py-1 bg-primary/10 text-primary rounded border border-primary/30"
                  >
                    {keyword}
                  </span>
                ))}
              </div>
            </div>

            {/* Skip reason */}
            <div className={INFO_SECTION_CLASSES}>
              <strong>Not executed:</strong> {data.skip_reason}
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  }

  // Case: enrichment executed successfully
  const hasResults = data.results_count !== undefined && data.results_count > 0;

  return (
    <AccordionItem value="knowledge-enrichment">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Knowledge Enrichment</span>
          {data.endpoint && <EndpointBadge endpoint={data.endpoint} />}
          {data.from_cache !== undefined && <CacheBadge fromCache={data.from_cache} />}
          <span
            className={cn(
              'text-xs px-1.5 py-0.5 rounded font-medium border',
              hasResults
                ? 'bg-green-500/20 text-green-400 border-green-500/30'
                : 'bg-muted/50 text-muted-foreground border-border/50'
            )}
          >
            {hasResults ? `${data.results_count} results` : 'No results'}
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Detected keywords */}
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground font-medium">
              Detected keywords ({data.encyclopedia_keywords.length})
            </div>
            <div className="flex flex-wrap gap-1.5">
              {data.encyclopedia_keywords.map((keyword, index) => (
                <span
                  key={index}
                  className="text-xs px-2 py-1 bg-primary/10 text-primary rounded border border-primary/30"
                >
                  {keyword}
                </span>
              ))}
            </div>
          </div>

          {/* Query type - is_news_query detection */}
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground font-medium">
              Query type (is_news_query)
            </div>
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'text-xs px-2 py-1 rounded font-medium',
                  data.is_news_query
                    ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                    : 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                )}
              >
                {data.is_news_query
                  ? 'TRUE → News (News API)'
                  : 'FALSE → Encyclopedic (Web API + year)'}
              </span>
            </div>
          </div>

          {/* Enrichment details */}
          {data.executed && (
            <div className="border-t pt-2 space-y-1">
              <div className="text-xs text-muted-foreground font-medium">Enrichment details</div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
                {data.keyword_used && <MetricRow label="Query sent" value={data.keyword_used} />}
                {data.endpoint && (
                  <MetricRow label="Endpoint" value={data.endpoint.toUpperCase()} />
                )}
                {data.results_count !== undefined && (
                  <MetricRow label="Results" value={data.results_count} highlight={hasResults} />
                )}
                {data.from_cache !== undefined && (
                  <MetricRow label="Source" value={data.from_cache ? 'Cache Redis' : 'API Brave'} />
                )}
              </div>
            </div>
          )}

          {/* Brave Search results */}
          {data.results && data.results.length > 0 && (
            <div className="border-t pt-2 space-y-2">
              <div className="text-xs text-muted-foreground font-medium">
                Brave Search results ({data.results.length})
              </div>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {data.results.map((result, index) => (
                  <div
                    key={index}
                    className="text-xs p-2 bg-muted/30 rounded border border-border/50"
                  >
                    <div className="font-medium text-primary truncate">
                      {index + 1}. {result.title}
                    </div>
                    <div className="text-muted-foreground mt-1 line-clamp-2">
                      {result.description}
                    </div>
                    <a
                      href={result.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-400 hover:underline mt-1 block truncate"
                    >
                      {result.url}
                    </a>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Context injected into the LLM prompt */}
          {data.prompt_context && (
            <div className="border-t pt-2 space-y-1">
              <div className="text-xs text-muted-foreground font-medium">
                Context injected into prompt
              </div>
              <pre className="text-xs p-2 bg-muted/30 rounded border border-border/50 overflow-x-auto whitespace-pre-wrap max-h-32 overflow-y-auto">
                {data.prompt_context}
              </pre>
            </div>
          )}

          {/* Potential error */}
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
