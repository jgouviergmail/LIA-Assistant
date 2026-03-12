'use client';

import { Component, ErrorInfo, ReactNode } from 'react';
import { withTranslation, WithTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { logger } from '@/lib/logger';

interface Props extends WithTranslation {
  /** Feature name for logging and display */
  feature: string;
  /** Custom fallback UI (optional) */
  fallback?: ReactNode;
  /** Callback when error is caught */
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  /** Children to render */
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Reusable error boundary for feature components.
 *
 * Use this to wrap critical components that might fail (complex rendering,
 * external data, etc.) to prevent crashes from propagating.
 *
 * Uses withTranslation() HOC for i18n support (class components cannot use hooks).
 *
 * @example
 * ```tsx
 * <FeatureErrorBoundary feature="memory-settings">
 *   <MemorySettings />
 * </FeatureErrorBoundary>
 * ```
 */
class FeatureErrorBoundaryBase extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    const { feature, onError } = this.props;

    // Log error
    logger.error(`Feature error: ${feature}`, error, {
      component: 'FeatureErrorBoundary',
      feature,
      componentStack: errorInfo.componentStack,
    });

    // Call optional callback
    onError?.(error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    const { hasError, error } = this.state;
    const { feature, fallback, children, t } = this.props;

    if (hasError) {
      // Use custom fallback if provided
      if (fallback) {
        return fallback;
      }

      // Default fallback UI
      return (
        <Card className="p-6">
          <div className="text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-yellow-100 mb-3">
              <svg
                className="h-6 w-6 text-yellow-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </div>

            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">
              {t('errors.featureErrorBoundary.title', { feature })}
            </h3>

            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              {t('errors.featureErrorBoundary.description')}
            </p>

            {process.env.NODE_ENV === 'development' && error && (
              <div className="mb-4 rounded-lg bg-gray-100 dark:bg-gray-800 p-3 text-left">
                <p className="text-xs font-mono text-gray-800 dark:text-gray-200 break-all">
                  {error.message}
                </p>
              </div>
            )}

            <Button
              onClick={this.handleReset}
              variant="outline"
              size="sm"
              aria-label={t('errors.featureErrorBoundary.retryAriaLabel', { feature })}
            >
              {t('errors.featureErrorBoundary.retryButton')}
            </Button>
          </div>
        </Card>
      );
    }

    return children;
  }
}

// Wrap with i18n HOC for translation support
export const FeatureErrorBoundary = withTranslation()(FeatureErrorBoundaryBase);

/**
 * HOC to wrap a component with error boundary
 *
 * @example
 * ```tsx
 * const SafeMemorySettings = withErrorBoundary(MemorySettings, 'memory-settings');
 * ```
 */
export function withErrorBoundary<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  feature: string
) {
  return function WithErrorBoundary(props: P) {
    return (
      <FeatureErrorBoundary feature={feature}>
        <WrappedComponent {...props} />
      </FeatureErrorBoundary>
    );
  };
}

export default FeatureErrorBoundary;
