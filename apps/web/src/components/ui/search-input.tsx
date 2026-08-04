'use client';

import {
  type ChangeEvent,
  type InputHTMLAttributes,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { Search, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useDebounce } from '@/hooks/useDebounce';
import { Input } from '@/components/ui/input';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { cn } from '@/lib/utils';

export interface SearchInputProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'onChange' | 'type'
> {
  /**
   * Callback fired when the debounced search value changes
   */
  onSearchChange: (value: string) => void;

  /**
   * Debounce delay in milliseconds
   * @default 300
   */
  debounceMs?: number;

  /**
   * Show clear button when input has value
   * @default true
   */
  clearable?: boolean;

  /**
   * Show loading indicator
   * @default false
   */
  loading?: boolean;

  /**
   * Initial value for controlled component
   */
  value?: string;
}

/**
 * SearchInput component with built-in debouncing
 *
 * Features:
 * - Automatic debouncing (customizable delay)
 * - Clear button (optional)
 * - Loading state indicator
 * - Full accessibility (ARIA searchbox role)
 * - Keyboard support (Escape to clear)
 *
 * @example
 * <SearchInput
 *   placeholder="Search users..."
 *   onSearchChange={(value) => fetchUsers(value)}
 *   debounceMs={500}
 *   clearable
 * />
 */
export function SearchInput({
  onSearchChange,
  debounceMs = 300,
  clearable = true,
  loading = false,
  placeholder,
  className,
  value: controlledValue,
  ...props
}: SearchInputProps) {
  const { t } = useTranslation();
  // Every call site passes a translated placeholder; the fallback exists so the
  // primitive never has to invent an English default of its own.
  const resolvedPlaceholder = placeholder ?? t('settings.search.placeholder');
  const [inputValue, setInputValue] = useState(controlledValue || '');
  const debouncedValue = useDebounce(inputValue, debounceMs);

  // ✅ FIX: Latest Ref pattern - stable reference that always points to the latest callback
  // This prevents infinite loops when parent recreates the callback on every render
  const onSearchChangeRef = useRef(onSearchChange);

  // ✅ Synchronize ref with latest callback (useLayoutEffect runs before browser paint)
  useLayoutEffect(() => {
    onSearchChangeRef.current = onSearchChange;
  });

  // Sync controlled value
  useEffect(() => {
    if (controlledValue !== undefined) {
      setInputValue(controlledValue);
    }
  }, [controlledValue]);

  // ✅ FIX: Call ref instead of prop - no dependency on onSearchChange!
  // This breaks the infinite loop: parent re-render → new callback → no effect re-trigger
  useEffect(() => {
    onSearchChangeRef.current(debouncedValue);
  }, [debouncedValue]);

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
  };

  // ✅ FIX: Use ref in handleClear - no dependency on onSearchChange
  const handleClear = useCallback(() => {
    setInputValue('');
    onSearchChangeRef.current('');
  }, []);

  // Keyboard shortcut: Escape to clear
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && inputValue) {
        handleClear();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [inputValue, handleClear]);

  return (
    <div className="relative">
      <div className="relative">
        {/* Search icon */}
        <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
          <Search className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
        </div>

        <Input
          type="search"
          role="searchbox"
          aria-label={
            typeof resolvedPlaceholder === 'string' ? resolvedPlaceholder : t('common.search')
          }
          value={inputValue}
          onChange={handleChange}
          placeholder={resolvedPlaceholder}
          className={cn('pl-10', clearable && inputValue && 'pr-20', className)}
          {...props}
        />

        {/* Right side: Loading + Clear button */}
        <div className="absolute inset-y-0 right-0 flex items-center gap-1 pr-3">
          {/* Reuses the shared spinner: it is already themed and already names
              itself from the active locale. */}
          {loading && <LoadingSpinner size="default" spinnerColor="muted" />}

          {/* Clear button */}
          {clearable && inputValue && !loading && (
            <button
              type="button"
              onClick={handleClear}
              className="rounded-md p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={t('settings.search.clear')}
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
