/**
 * Generic form handler hook for consistent error/loading state management.
 *
 * Eliminates code duplication across form components by providing a reusable
 * pattern for handling form submission, error states, and loading indicators.
 *
 * Features:
 * - Automatic error state management
 * - Loading state tracking
 * - Structured error logging
 * - Type-safe with generics
 *
 * @example
 * ```tsx
 * const LoginForm = () => {
 *   const { error, isLoading, handleSubmit } = useFormHandler(
 *     async (data: LoginFormData) => {
 *       const response = await fetch('/api/auth/login', {
 *         method: 'POST',
 *         body: JSON.stringify(data),
 *       });
 *       if (!response.ok) throw new Error('Login failed');
 *       // Handle successful login
 *     },
 *     'LoginForm'
 *   );
 *
 *   return (
 *     <form onSubmit={(e) => {
 *       e.preventDefault();
 *       const formData = { email, password };
 *       handleSubmit(formData);
 *     }}>
 *       {error && <div className="error">{error}</div>}
 *       <button disabled={isLoading}>
 *         {isLoading ? 'Loading...' : 'Login'}
 *       </button>
 *     </form>
 *   );
 * };
 * ```
 */

import { useState, useCallback } from 'react';
import { logger } from '@/lib/logger';

/**
 * Options for form handler configuration
 */
export interface UseFormHandlerOptions {
  /** Callback invoked on successful submission */
  onSuccess?: () => void;

  /** Callback invoked on error (receives error message) */
  onError?: (error: string) => void;

  /** Custom error message formatter */
  formatError?: (error: unknown) => string;
}

/**
 * Return type for useFormHandler hook
 */
export interface UseFormHandlerReturn<T> {
  /** Current error message (empty string if no error) */
  error: string;

  /** True if form is currently submitting */
  isLoading: boolean;

  /** Submit handler function */
  handleSubmit: (data: T) => Promise<void>;

  /** Manually clear error state */
  clearError: () => void;

  /** Manually set error state */
  setError: (error: string) => void;
}

/**
 * Default error formatter that extracts message from various error types
 */
const defaultFormatError = (error: unknown): string => {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === 'string') {
    return error;
  }
  if (error && typeof error === 'object' && 'message' in error) {
    return String(error.message);
  }
  return 'Une erreur inattendue est survenue';
};

/**
 * Generic form submission handler hook
 *
 * @param onSubmit - Async function to call on form submission
 * @param componentName - Name of component for logging/debugging
 * @param options - Optional configuration
 * @returns Form handler utilities
 */
export function useFormHandler<T = unknown>(
  onSubmit: (data: T) => Promise<void>,
  componentName: string,
  options: UseFormHandlerOptions = {}
): UseFormHandlerReturn<T> {
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const { onSuccess, onError, formatError = defaultFormatError } = options;

  const handleSubmit = useCallback(
    async (data: T) => {
      // Clear previous errors
      setError('');
      setIsLoading(true);

      try {
        await onSubmit(data);

        logger.info('Form submission successful', {
          component: componentName,
        });

        // Call success callback if provided
        onSuccess?.();
      } catch (err) {
        const errorMessage = formatError(err);

        logger.error('Form submission failed', err as Error, {
          component: componentName,
        });

        setError(errorMessage);

        // Call error callback if provided
        onError?.(errorMessage);
      } finally {
        setIsLoading(false);
      }
    },
    [onSubmit, componentName, formatError, onSuccess, onError]
  );

  const clearError = useCallback(() => {
    setError('');
  }, []);

  return {
    error,
    isLoading,
    handleSubmit,
    clearError,
    setError,
  };
}
