import {
  type ChangeEvent,
  type InputHTMLAttributes,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { useDebounce } from '@/hooks/useDebounce';
import { Input } from '@/components/ui/input';
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
  placeholder = 'Search...',
  className,
  value: controlledValue,
  ...props
}: SearchInputProps) {
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
          <svg
            className="h-5 w-5 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>

        <Input
          type="search"
          role="searchbox"
          aria-label={typeof placeholder === 'string' ? placeholder : 'Search'}
          value={inputValue}
          onChange={handleChange}
          placeholder={placeholder}
          className={cn('pl-10', clearable && inputValue && 'pr-20', className)}
          {...props}
        />

        {/* Right side: Loading + Clear button */}
        <div className="absolute inset-y-0 right-0 flex items-center gap-1 pr-3">
          {/* Loading spinner */}
          {loading && (
            <div
              className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600"
              role="status"
              aria-label="Loading"
            >
              <span className="sr-only">Loading...</span>
            </div>
          )}

          {/* Clear button */}
          {clearable && inputValue && !loading && (
            <button
              type="button"
              onClick={handleClear}
              className="rounded-md p-1 text-gray-400 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label="Clear search"
            >
              <svg
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
