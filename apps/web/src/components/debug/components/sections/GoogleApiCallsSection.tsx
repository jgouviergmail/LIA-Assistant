/**
 * Google API Calls Section Component
 *
 * Displays Google API calls (Places, Routes, Geocoding) and cost summary.
 */

import React from 'react';
import { Globe } from 'lucide-react';
import {
  DebugChip,
  DebugSection,
  EmptySection,
  MetricRow,
  SubSectionHeader,
} from '../shared';
import { formatCost } from '../../utils/formatters';
import { TONE_TEXT } from '../../utils/tones';
import { cn } from '@/lib/utils';
import type { DebugTone } from '../../utils/tones';
import type { DebugMetrics } from '@/types/chat';

export interface GoogleApiCallsSectionProps {
  /** List of Google API calls (can be undefined) */
  calls: DebugMetrics['google_api_calls'];
  /** Google API calls summary (can be undefined) */
  summary: DebugMetrics['google_api_summary'];
}

/** Identity tones for Google API types (semantic families are for statuses). */
const API_TONES: Record<string, DebugTone> = {
  places: 'info',
  routes: 'info',
  geocoding: 'info',
  static_maps: 'info',
};

/**
 * Format endpoint for display (truncate long paths)
 */
function formatEndpoint(endpoint: string): string {
  if (endpoint.length > 30) {
    return '...' + endpoint.slice(-27);
  }
  return endpoint;
}

/**
 * Section Google API Calls
 *
 * Displays:
 * - Global summary (total calls, billable, cached, cost)
 * - Detailed list of calls per API (places, routes, geocoding)
 * - USD and EUR costs per call
 * - Cache indicator
 */
export const GoogleApiCallsSection = React.memo(function GoogleApiCallsSection({
  calls,
  summary,
}: GoogleApiCallsSectionProps) {
  if (!calls || !summary || calls.length === 0) {
    return (
      <EmptySection
        value="google-api"
        title="Google API"
        icon={Globe}
        message="No Google API call on this request."
      />
    );
  }

  return (
    <DebugSection
      value="google-api"
      title="Google API"
      icon={Globe}
      badge={
        <>
          <DebugChip tone="info">{summary.billable_calls} calls</DebugChip>
          {summary.cached_calls > 0 && (
            <DebugChip tone="success">+{summary.cached_calls} cached</DebugChip>
          )}
          <span className="font-mono text-xs text-primary">
            {formatCost(summary.total_cost_eur)}
          </span>
        </>
      }
    >
      {/* Global summary */}
      <div className="rounded border border-border/50 bg-muted/30 p-2">
        <SubSectionHeader label="Summary" />
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <MetricRow label="Total" value={summary.total_calls} />
          <MetricRow label="Billable" value={summary.billable_calls} highlight />
          <MetricRow
            label="Cached"
            value={summary.cached_calls}
            valueClassName={TONE_TEXT.success}
          />
          <MetricRow
            label="Cost USD"
            value={`$${summary.total_cost_usd.toFixed(4)}`}
            valueClassName="font-mono"
          />
        </div>
        <div className="mt-2 border-t border-border/30 pt-2">
          <MetricRow
            label="Total cost"
            value={formatCost(summary.total_cost_eur)}
            highlight
            mono
            valueClassName="text-primary font-semibold"
          />
        </div>
      </div>

      {/* Detailed calls list */}
      <div>
        <SubSectionHeader label="Detail per call" borderTop />
        <div className="space-y-2">
          {calls.map((call, index) => (
            <div
              key={`${call.api_name}-${call.endpoint}-${index}`}
              className={cn(
                'border-l-2 pl-3 pb-1',
                call.cached ? 'border-success/50' : 'border-border'
              )}
            >
              {/* Header: API type + endpoint */}
              <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                <DebugChip tone={API_TONES[call.api_name.toLowerCase()] ?? 'neutral'}>
                  {call.api_name}
                </DebugChip>
                <span
                  className="truncate font-mono text-[10px] text-muted-foreground"
                  title={call.endpoint}
                >
                  {formatEndpoint(call.endpoint)}
                </span>
              </div>

              {/* Call metrics */}
              <div className="space-y-0.5 text-[10px] text-muted-foreground">
                {call.cached ? (
                  <div className={cn('flex justify-between', TONE_TEXT.success)}>
                    <span>Status:</span>
                    <span className="font-medium">CACHED (free)</span>
                  </div>
                ) : (
                  <>
                    <div className="flex justify-between">
                      <span>USD:</span>
                      <span className="font-mono">${call.cost_usd.toFixed(5)}</span>
                    </div>
                    <div className="flex justify-between border-t border-border/30 pt-0.5 font-medium text-foreground">
                      <span>EUR:</span>
                      <span className="font-mono text-primary">{formatCost(call.cost_eur)}</span>
                    </div>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </DebugSection>
  );
});
