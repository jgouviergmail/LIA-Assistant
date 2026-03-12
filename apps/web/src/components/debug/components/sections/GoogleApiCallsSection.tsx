/**
 * Google API Calls Section Component
 *
 * Displays Google API calls (Places, Routes, Geocoding) and cost summary.
 * Dark mode compatible with detailed breakdown per API.
 */

import React from 'react';
import {
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '@/components/ui/accordion';
import { MetricRow } from '../shared';
import { formatCost } from '../../utils/formatters';
import { cn } from '@/lib/utils';
import type { DebugMetrics } from '@/types/chat';

export interface GoogleApiCallsSectionProps {
  /** List of Google API calls (can be undefined) */
  calls: DebugMetrics['google_api_calls'];
  /** Google API calls summary (can be undefined) */
  summary: DebugMetrics['google_api_summary'];
}

/**
 * Colors for different Google API types
 */
const API_COLORS: Record<string, string> = {
  places: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  routes: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  geocoding: 'bg-green-500/20 text-green-400 border-green-500/30',
  static_maps: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  default: 'bg-muted text-muted-foreground border-border',
};

/**
 * Get color class for API type
 */
function getApiColor(apiName: string): string {
  const normalizedName = apiName.toLowerCase();
  return API_COLORS[normalizedName] || API_COLORS.default;
}

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
 *
 * Not displayed if calls/summary is undefined (no Google API calls).
 */
export const GoogleApiCallsSection = React.memo(function GoogleApiCallsSection({
  calls,
  summary,
}: GoogleApiCallsSectionProps) {
  if (!calls || !summary || calls.length === 0) {
    return null;
  }

  return (
    <AccordionItem value="google-api">
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>Google API</span>
          <span className="text-xs bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded border border-purple-500/30">
            {summary.billable_calls} calls
          </span>
          {summary.cached_calls > 0 && (
            <span className="text-xs bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded border border-green-500/30">
              +{summary.cached_calls} cached
            </span>
          )}
          <span className="text-xs text-primary font-mono">
            {formatCost(summary.total_cost_eur)}
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="space-y-3">
          {/* Global summary */}
          <div className="p-2 bg-muted/30 rounded border border-border/50">
            <div className="text-xs text-muted-foreground font-medium mb-1.5">
              Résumé
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              <MetricRow label="Total" value={summary.total_calls} />
              <MetricRow
                label="Facturables"
                value={summary.billable_calls}
                highlight
              />
              <MetricRow
                label="En cache"
                value={summary.cached_calls}
                valueClassName="text-green-400"
              />
              <MetricRow
                label="Coût USD"
                value={`$${summary.total_cost_usd.toFixed(4)}`}
                valueClassName="font-mono"
              />
            </div>
            <div className="mt-2 pt-2 border-t border-border/30">
              <MetricRow
                label="Coût total"
                value={formatCost(summary.total_cost_eur)}
                highlight
                mono
                valueClassName="text-primary font-semibold"
              />
            </div>
          </div>

          {/* Detailed calls list */}
          <div className="border-t border-border/50 pt-2">
            <div className="text-xs text-muted-foreground font-medium mb-2">
              Détail par appel
            </div>
            <div className="space-y-2">
              {calls.map((call, index) => (
                <div
                  key={`${call.api_name}-${call.endpoint}-${index}`}
                  className={cn(
                    'border-l-2 pl-3 pb-1',
                    call.cached ? 'border-green-500/50' : 'border-border'
                  )}
                >
                  {/* Header: API type + endpoint */}
                  <div className="flex items-center justify-between text-xs mb-1 gap-2">
                    <span
                      className={cn(
                        'text-[10px] px-1.5 py-0.5 rounded uppercase font-medium border flex-shrink-0',
                        getApiColor(call.api_name)
                      )}
                    >
                      {call.api_name}
                    </span>
                    <span
                      className="font-mono text-[10px] text-muted-foreground truncate"
                      title={call.endpoint}
                    >
                      {formatEndpoint(call.endpoint)}
                    </span>
                  </div>

                  {/* Call metrics */}
                  <div className="text-[10px] text-muted-foreground space-y-0.5">
                    {call.cached ? (
                      <div className="flex justify-between text-green-400">
                        <span>Status:</span>
                        <span className="font-medium">CACHED (gratuit)</span>
                      </div>
                    ) : (
                      <>
                        <div className="flex justify-between">
                          <span>USD:</span>
                          <span className="font-mono">${call.cost_usd.toFixed(5)}</span>
                        </div>
                        <div className="flex justify-between font-medium text-foreground pt-0.5 border-t border-border/30">
                          <span>EUR:</span>
                          <span className="font-mono text-primary">
                            {formatCost(call.cost_eur)}
                          </span>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
