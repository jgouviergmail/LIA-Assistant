/**
 * Error Boundary for Debug Panel
 *
 * Isolates debug panel errors to prevent them from crashing the application.
 * If the panel crashes, the user sees a fallback UI but can continue
 * using the application normally.
 *
 * Reference: https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary
 */

import { Component, ErrorInfo, ReactNode } from 'react';
import { logger } from '@/lib/logger';
import { FallbackUI } from './FallbackUI';

export interface DebugPanelErrorBoundaryProps {
  /** Child components to protect */
  children: ReactNode;
  /** Optional callback when an error is caught */
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  /** Custom fallback UI (optional) */
  fallback?: ReactNode;
}

interface DebugPanelErrorBoundaryState {
  /** true if an error has been caught */
  hasError: boolean;
  /** Caught error (if hasError=true) */
  error: Error | null;
  /** Stack trace React (componentStack) */
  errorInfo: ErrorInfo | null;
}

/**
 * Debug Panel specific Error Boundary
 *
 * Features:
 * - Catches all React errors in the debug panel
 * - Automatic logging to the logging system
 * - Displays FallbackUI instead of crashing
 * - Allows retry via unmount/remount
 * - Does not affect the main application
 *
 * Usage:
 * ```tsx
 * <DebugPanelErrorBoundary>
 *   <DebugPanel metrics={metrics} />
 * </DebugPanelErrorBoundary>
 * ```
 *
 * Avec callback custom:
 * ```tsx
 * <DebugPanelErrorBoundary
 *   onError={(error, errorInfo) => {
 *     sendToAnalytics('debug_panel_error', { error, errorInfo });
 *   }}
 * >
 *   <DebugPanel metrics={metrics} />
 * </DebugPanelErrorBoundary>
 * ```
 */
export class DebugPanelErrorBoundary extends Component<
  DebugPanelErrorBoundaryProps,
  DebugPanelErrorBoundaryState
> {
  constructor(props: DebugPanelErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  /**
   * getDerivedStateFromError
   *
   * Called during render if an error is thrown in a child component.
   * Allows updating state to display fallback UI on the next render.
   *
   * @param error - Caught error
   * @returns New state
   */
  static getDerivedStateFromError(error: Error): Partial<DebugPanelErrorBoundaryState> {
    return {
      hasError: true,
      error,
    };
  }

  /**
   * componentDidCatch
   *
   * Called after getDerivedStateFromError, allows logging the error.
   * This is where logging and side-effects are performed.
   *
   * @param error - Caught error
   * @param errorInfo - Additional info (componentStack)
   */
  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log to the logging system
    logger.error('debug_panel_error_boundary_caught', error, {
      componentStack: errorInfo.componentStack,
      errorName: error.name,
      errorMessage: error.message,
      context: 'DebugPanel rendering',
    });

    // Update state with errorInfo for display in fallback
    this.setState({
      errorInfo,
    });

    // Optional callback
    if (this.props.onError) {
      try {
        this.props.onError(error, errorInfo);
      } catch (callbackError) {
        logger.error('debug_panel_error_boundary_callback_failed', callbackError as Error);
      }
    }
  }

  /**
   * handleRetry
   *
   * Resets the error boundary for retry.
   * Sets hasError back to false, which triggers a re-render of children.
   */
  handleRetry = () => {
    logger.info('debug_panel_error_boundary_retry');

    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  render() {
    if (this.state.hasError) {
      // Display custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Display default FallbackUI
      return (
        <FallbackUI
          error={this.state.error}
          onRetry={this.handleRetry}
        />
      );
    }

    // No error, normal render
    return this.props.children;
  }
}

/**
 * Helper hook to use the error boundary declaratively
 *
 * Note: This is a functional wrapper, the error boundary itself
 * must remain a class component.
 *
 * @example
 * ```tsx
 * function MyComponent() {
 *   return (
 *     <WithDebugPanelErrorBoundary>
 *       <DebugPanel metrics={metrics} />
 *     </WithDebugPanelErrorBoundary>
 *   );
 * }
 * ```
 */
export function WithDebugPanelErrorBoundary({
  children,
  onError,
}: {
  children: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}) {
  return (
    <DebugPanelErrorBoundary onError={onError}>
      {children}
    </DebugPanelErrorBoundary>
  );
}
