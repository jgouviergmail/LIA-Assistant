/**
 * Fallback UI for Debug Panel Error Boundary
 *
 * Displays a graceful degradation UI when an error occurs in the debug panel.
 * Does not block the main application - the panel is isolated.
 */

import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

export interface FallbackUIProps {
  /** Error caught by the error boundary */
  error: Error | null;
  /** Callback for retry (optional) */
  onRetry?: () => void;
}

/**
 * Fallback UI displayed when the debug panel encounters an error
 *
 * Design:
 * - Non-alarming colors (orange/yellow) since this is a debug panel, not the app
 * - Reassuring message for the user
 * - Technical details in accordion for debugging
 * - Optional retry button
 *
 * @example
 * ```tsx
 * <FallbackUI
 *   error={new Error("Invalid metrics structure")}
 *   onRetry={() => window.location.reload()}
 * />
 * ```
 */
export function FallbackUI({ error, onRetry }: FallbackUIProps) {
  const [showDetails, setShowDetails] = React.useState(false);

  return (
    <div className="p-4 bg-yellow-900/20 border border-yellow-700/50 rounded-lg">
      {/* Header with icon */}
      <div className="flex items-start gap-3 mb-3">
        <div className="flex-shrink-0 mt-0.5">
          <AlertCircle className="h-5 w-5 text-yellow-500" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-yellow-300 mb-1">Debug Panel Error</h3>
          <p className="text-xs text-yellow-200/90 leading-relaxed">
            The debug panel encountered an error while rendering metrics. This does not affect the
            main application functionality. Debug metrics may be unavailable or incomplete for this
            conversation turn.
          </p>
        </div>
      </div>

      {/* Error message (if available and short) */}
      {error?.message && error.message.length < 150 && (
        <div className="mb-3 p-2 bg-yellow-900/30 rounded text-xs text-yellow-200 font-mono">
          {error.message}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2">
        {/* Retry button if callback provided */}
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry} className="text-xs h-7">
            <RefreshCw className="h-3 w-3 mr-1.5" />
            Retry
          </Button>
        )}

        {/* Toggle technical details */}
        {error && (
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="text-xs text-yellow-300 hover:text-yellow-100 underline"
          >
            {showDetails ? 'Hide' : 'Show'} technical details
          </button>
        )}
      </div>

      {/* Technical details (accordion) */}
      {showDetails && error && (
        <details open className="mt-3">
          <summary className="text-xs font-medium text-yellow-300 cursor-pointer mb-2">
            Error Details
          </summary>
          <div className="p-3 bg-muted/30 rounded border border-yellow-700/50">
            {/* Error name */}
            <div className="mb-2">
              <span className="text-[10px] font-semibold text-yellow-400 uppercase">
                Error Type
              </span>
              <div className="text-xs font-mono text-foreground">{error.name || 'Error'}</div>
            </div>

            {/* Error message */}
            <div className="mb-2">
              <span className="text-[10px] font-semibold text-yellow-400 uppercase">Message</span>
              <div className="text-xs text-foreground break-words">
                {error.message || 'No message'}
              </div>
            </div>

            {/* Stack trace */}
            {error.stack && (
              <div>
                <span className="text-[10px] font-semibold text-yellow-400 uppercase">
                  Stack Trace
                </span>
                <pre className="mt-1 p-2 bg-muted/30 rounded text-[10px] text-muted-foreground overflow-auto max-h-40 leading-tight">
                  {error.stack}
                </pre>
              </div>
            )}
          </div>
        </details>
      )}

      {/* Instructions for the user */}
      <div className="mt-3 pt-3 border-t border-yellow-700/50">
        <p className="text-[10px] text-yellow-200/80 leading-relaxed">
          <strong>What to do:</strong> You can continue using the application normally. Debug
          metrics will resume on the next conversation turn. If this error persists, please report
          it to the development team with the technical details above.
        </p>
      </div>
    </div>
  );
}

/**
 * Compact variant for display in constrained spaces
 */
export function FallbackUICompact({ error }: { error: Error | null }) {
  return (
    <div className="p-3 bg-yellow-900/20 border border-yellow-700/50 rounded text-center">
      <AlertCircle className="h-4 w-4 text-yellow-500 mx-auto mb-2" />
      <p className="text-xs text-yellow-300 font-medium mb-1">Debug Panel Unavailable</p>
      <p className="text-[10px] text-yellow-200/80">
        {error?.message || 'An error occurred while loading debug metrics'}
      </p>
    </div>
  );
}
